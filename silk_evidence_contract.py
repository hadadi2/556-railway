"""الأرقام تُراجع مقابل لقطة المصدر، لا مقابل صياغة النموذج لنفسه."""
import copy
import json
import math
import re
from dataclasses import asdict


def raw_snapshots(points):
    rows = []
    seen = set()
    for point in points:
        inherited = getattr(point, "raw_evidence", ())
        for row in (copy.deepcopy(inherited) if inherited else [asdict(point)]):
            key = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return tuple(rows)


_SCALE = {"thousand": 1e3, "thousands": 1e3, "ألف": 1e3, "الف": 1e3,
          "آلاف": 1e3, "million": 1e6, "millions": 1e6, "مليون": 1e6,
          "ملايين": 1e6, "billion": 1e9, "billions": 1e9, "مليار": 1e9,
          "مليارات": 1e9, "trillion": 1e12, "trillions": 1e12, "تريليون": 1e12}
_SCALE_RE = re.compile(r"(-?\d[\d,]*\.?\d*)\s+(" + "|".join(
    sorted(_SCALE, key=len, reverse=True)) + r")\b", re.IGNORECASE)


def _expanded_numbers(text):
    """وسم التحجيم الصريح جزء من العدد؛ 10 million لا يساوي 10."""
    normalized = str(text).replace("٬", "").replace("٫", ".")
    return _SCALE_RE.sub(lambda m: format(float(m[1].replace(",", "")) *
                                         _SCALE[m[2].lower()], ".15f"), normalized)


def source_numbers(rows):
    """حقول القيمة والوحدة والفترة وحدها؛ تاريخ الاسترجاع ليس حقيقة اقتصادية."""
    from silk_evals import _extract_numbers
    values = set()
    for row in rows:
        text = str(row.get("value")) + " " + str(row.get("unit") or "")
        text += " " + json.dumps({k: row.get(k) for k in ("data_year", "reference_period", "note")}, ensure_ascii=False, default=str)
        values.update(_extract_numbers(_expanded_numbers(text)))
    return values


def unsupported_numbers(claim, points):
    from silk_evals import _extract_numbers, formula_grounded_numbers
    normalized = _expanded_numbers(claim)
    known = source_numbers(raw_snapshots(points))
    known.update(formula_grounded_numbers(normalized, known))
    # تطابق عددي دقيق؛ صيغ التحجيم لا تُخمّن من النثر.
    return [n for n in _extract_numbers(normalized)
            if not any(math.isclose(n, k, rel_tol=1e-6, abs_tol=1e-8) for k in known)]


def unsupported_currencies(claim, points):
    pattern = r"\b(?:USD|EUR|SAR|AED|JPY|CNY|GBP|QAR|KWD|BHD|OMR)\b"
    used = set(re.findall(pattern, claim.upper()))
    source = json.dumps(raw_snapshots(points), ensure_ascii=False, default=str).upper()
    known = set(re.findall(pattern, source))
    return sorted(used - known)
