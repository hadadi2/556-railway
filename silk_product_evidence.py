"""Keep adjacent sesame products out of each other's retail price comparisons."""
from dataclasses import replace
import re
from urllib.parse import unquote, urlsplit

_HALVA = re.compile(r"حلاو[ةه]|\bhal(?:va[h]?|wa|awa)\b", re.I)
_TAHINI = re.compile(r"(?:طحين[يةه]+|تحين[ةه])|\btahin[ai]\b", re.I)


def _family(product):
    text = str(product or "")
    if _HALVA.search(text):
        return "halva"
    return "tahini" if _TAHINI.search(text) else ""


def _other_product(text, expected):
    # "حلاوة طحينية" names halva; tahini alone names a different product.
    text = re.sub(r"حلاو[ةه]\s+طحيني[ةه]", "حلاوة", str(text), flags=re.I)
    if expected == "halva":
        return bool(_TAHINI.search(text))
    return bool(_HALVA.search(text)) if expected == "tahini" else False


def price_reports(reports, product):
    result = dict(reports or {})
    expected = _family(product)
    if not expected:
        return result
    for name, report in result.items():
        if not ("pric" in name and hasattr(report, "findings")):
            continue
        out, changed = [], False
        for dp in report.findings:
            if dp.value is None:
                out.append(dp)
                continue
            title = (dp.value if isinstance(dp.value, str) else
                     str(dp.value.get("title") or dp.value.get("name") or "")
                     if isinstance(dp.value, dict) else "")
            path = unquote(urlsplit(str(dp.url or "")).path)
            parts = path.split("/")
            slug = parts[parts.index("product") + 1] if "product" in parts and parts.index("product") + 1 < len(parts) else parts[-1]
            # Ignore category paths: they can correctly contain both products.
            specific_slug = slug if "product" in parts else ""
            if _other_product(title, expected) or _other_product(specific_slug.replace("-", " "), expected):
                changed = True
                out.append(replace(dp, value=None, confidence=0.0, raw_evidence=(),
                    note="استُبعد عرض لمنتج مختلف عن المنتج المدروس؛ لا يُستخدم للمقارنة السعرية."))
            else:
                out.append(dp)
        if changed:
            # This is an input projection. Original saved evidence is untouched.
            result[name] = replace(report, findings=out)
    return result
