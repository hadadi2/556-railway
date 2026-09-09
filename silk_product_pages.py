"""Read public product pages through the configured Tavily extraction service.

The model receives source text, not a generated price or answer. No request is
made directly to a model-supplied host, and missing content remains a gap.
"""
import ipaddress
import os
from urllib.parse import urlsplit

from silk_data_layer import DataPoint, _today, throttled_request


def _public(url):
    try:
        p = urlsplit(str(url))
        host = (p.hostname or '').lower()
        if p.scheme not in ('https', 'http') or not host or p.username or p.password:
            return False
        if '.' not in host or host.endswith(('.localhost', '.local', '.internal')):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return True
    except ValueError:
        return False


def read_product_pages(urls, product=''):
    requested = list(dict.fromkeys(str(u) for u in (urls or []) if _public(u)))[:3]
    source = 'Product page (Tavily Extract)'
    def missing(note, status='no_record'):
        return [DataPoint(None, source, 0.0, note, _today(), status=status)]
    if not requested:
        return missing('No valid public product URLs')
    key = os.environ.get('TAVILY_API_KEY', '').strip()
    if not key:
        return missing('Product-page extraction requires the configured Tavily key')
    try:
        body = {'urls': requested, 'extract_depth': 'basic', 'format': 'markdown',
                'include_images': False, 'timeout': 20}
        if str(product or '').strip():
            body.update(query=str(product) + ' price currency package size سعر حجم العبوة',
                        chunks_per_source=5)
        response = throttled_request('POST', 'https://api.tavily.com/extract',
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
            json_body=body, timeout=30)
        response.raise_for_status()
        findings = []
        for row in (response.json() or {}).get('results') or []:
            url = str(row.get('url') or '')
            content = str(row.get('raw_content') or '').strip()
            if url not in requested or not content:
                continue
            findings.append(DataPoint(
                {'link': url, 'content': content[:18000]}, source, .65,
                'Original page excerpt. Match the exact product and pack; distinguish '
                'current price, old price, delivery charges and related products. '
                'Do not infer a price from a product name alone.', _today(),
                url=url, retrieval_method='llm_web'))
        return findings or missing('No readable product content; try another public store')
    except Exception:
        return missing('Product-page extraction unavailable; retain the price gap', 'fetch_failed')
