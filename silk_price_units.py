"""Observed package units and shared report consistency checks; no density guesses."""
import math
import re

_PACK = re.compile(r'(\d+(?:[.٫]\d+)?)\s*(كيلوغرام|كيلوجرام|كجم|كغم|كغ|kg|غرام|جرام|غم|جم|غ|g|ملليلتر|مليلتر|مل|ml|لتر|litres?|liters?|l|قطع|قطعة|pieces?|pcs)(?!\w)', re.I)
_UNITS = {'kg': ('kg', 1), 'كيلوغرام': ('kg', 1), 'كيلوجرام': ('kg', 1),
          'كجم': ('kg', 1), 'كغم': ('kg', 1), 'كغ': ('kg', 1),
          'g': ('kg', .001), 'غرام': ('kg', .001), 'جرام': ('kg', .001),
          'غم': ('kg', .001), 'جم': ('kg', .001), 'غ': ('kg', .001),
          'ml': ('litre', .001), 'مل': ('litre', .001), 'ملليلتر': ('litre', .001),
          'مليلتر': ('litre', .001)}


def package_basis(text):
    matches = list(_PACK.finditer(str(text or '')))
    if len(matches) != 1:
        return None  # conflicting/multiple packs need an explicit selection
    m = matches[0]
    # Multipacks require their multiplier; do not silently price one bottle.
    if re.search(r'(?:\d\s*[x×]|[x×]\s*\d)', str(text), re.I):
        return None
    raw = m.group(2).lower()
    unit, factor = _UNITS.get(raw, ('piece', 1) if raw in
        ('قطع', 'قطعة', 'piece', 'pieces', 'pcs') else ('litre', 1))
    quantity = float(m.group(1).replace('٫', '.')) * factor
    return (quantity, unit) if quantity > 0 else None


def normalize_listing(listing):
    result = dict(listing)
    basis = package_basis(result.get('pack_size') or result.get('title'))
    price = result.get('price')
    if not basis or isinstance(price, bool) or not result.get('currency'):
        return result
    try:
        price = float(price)
    except (TypeError, ValueError):
        return result
    if not math.isfinite(price) or price <= 0:
        return result
    quantity, unit = basis
    result.update(comparison_unit=unit, comparison_price=round(price / quantity, 4),
                  package_quantity=quantity)
    return result


def report_price_issues(text):
    """Flag only explicit table contradictions, using the same checks in review/export."""
    findings, price_cells = [], []
    header = None
    for line in str(text or '').splitlines():
        if not line.strip().startswith('|'):
            header = None
            continue
        cells = [c.strip().replace('**', '') for c in line.strip().strip('|').split('|')]
        if any('سعر التجزئة' in c or 'retail price' in c.lower() for c in cells):
            header = cells
            continue
        if not header or len(cells) != len(header) or all(re.fullmatch(r'[:\- ]+', c) for c in cells):
            continue
        price_i = next(i for i, c in enumerate(header) if 'سعر التجزئة' in c or 'retail price' in c.lower())
        price_cells.append(cells[price_i])
        pack_i = next((i for i, c in enumerate(header) if 'العبوة' in c or 'pack' in c.lower()), None)
        if pack_i is None:
            continue
        basis = package_basis(cells[pack_i])
        if basis and basis[1] in ('litre', 'piece') and any(
                re.search(r'(?:/\s*(?:كجم|كغ|kg)|per\s+kg)', c, re.I) for c in header):
            findings.append({'check': 'retail_unit_mismatch', 'repairable': False,
                'note': 'وحدة عمود السعر بالكيلوغرام تخالف حجم العبوة أو عددها؛ استخدم اللتر أو القطعة أو افصل المقارنة.'})
    if price_cells and all(not re.search(r'\d', c) for c in price_cells) and (
            'أسعار السوق مرصودة' in str(text) or 'market prices are observed' in str(text).lower()):
        findings.append({'check': 'retail_price_presence_conflict', 'repairable': False,
            'note': 'الجدول لا يحمل أي سعر تجزئة رقمي بينما يعلن النص أن أسعار السوق مرصودة؛ صحح الادعاء أو وثق السعر.'})
    return findings
