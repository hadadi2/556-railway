"""Read public product pages through Agent Reach/Exa with configured Tavily fallback.

The model receives source text, not a generated price or answer. No request is
made directly to a model-supplied host, and missing content remains a gap.
"""
import ipaddress
import os
import re
from urllib.parse import urlsplit, unquote

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


def _canonical(url):
    p = urlsplit(url)
    return (p.scheme.lower(), p.netloc.lower(), unquote(p.path), p.query)


def _exa_pages(requested):
    from silk_agent_reach_search import ENDPOINT, _message
    response = throttled_request('POST', ENDPOINT,
        headers={'Accept': 'application/json, text/event-stream'},
        json_body={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
            'name': 'web_fetch_exa', 'arguments': {'urls': requested, 'maxCharacters': 14000}}},
        timeout=30)
    response.raise_for_status()
    payload = _message(response)
    if payload.get('error') or (payload.get('result') or {}).get('isError'):
        return []
    findings = []
    allowed = {_canonical(u) for u in requested}
    for block in (payload.get('result') or {}).get('content') or []:
        if block.get('type') != 'text':
            continue
        for record in re.split(r'(?m)(?=^# )', block.get('text') or ''):
            match = re.match(r'# ([^\n]+)\nURL: (https?://[^\s]+)\n([\s\S]*)', record)
            if not match:
                continue
            title, url, content = match.groups()
            if _canonical(url) not in allowed or not content.strip():
                continue
            findings.append(DataPoint({'title': title, 'link': url, 'content': content[:18000]},
                'Product page (Exa via Agent Reach)', .65,
                'Original page content; match product, pack and current price. A listing is not proof of sales.',
                _today(), url=url, retrieval_method='llm_web'))
    return findings


def _tavily_pages(requested, product=''):
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
            if not _public(url) or _canonical(url) not in {_canonical(u) for u in requested} or not content:
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


def read_product_pages(urls, product=''):
    requested = list(dict.fromkeys(str(u) for u in (urls or []) if _public(u)))[:3]
    if not requested:
        return [DataPoint(None, 'Product pages', 0.0, 'No valid public product URLs', _today())]
    findings = []
    if os.environ.get('SEARCH_PROVIDER', '').strip().lower() == 'agent_reach':
        try:
            findings = _exa_pages(requested)
        except Exception:
            findings = []
    found = {_canonical(f.url) for f in findings}
    remaining = [u for u in requested if _canonical(u) not in found]
    if remaining and os.environ.get('TAVILY_API_KEY', '').strip():
        findings += [f for f in _tavily_pages(remaining, product) if f.value is not None]
    return findings or [DataPoint(None, 'Product pages', 0.0,
        'No source content could be read; try another public store and retain the price gap.',
        _today(), status='fetch_failed')]
