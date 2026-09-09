"""ITC Market Access Map tariff evidence.

Trade Map is a trade-statistics source; customs duties are supplied by ITC's
Market Access Map.  The portal is free but its detailed query/download can
require a registered session, so this module never invents a rate.  It emits
an actionable source link when no machine-readable row is available.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from silk_data_layer import DataPoint, _today

ITC_MAM_URL = "https://www.macmap.org/en/query/results"


def hs6(hs_code: str) -> str:
    digits = re.sub(r"\D", "", str(hs_code or ""))
    return digits.zfill(6) if 1 <= len(digits) <= 6 else ""


def query_url(hs_code: str, exporter_iso3: str = "SAU",
              importer_iso3: str = "") -> str:
    """Stable human-verification URL; query parameters remain optional."""
    code = hs6(hs_code)
    params = []
    if code:
        params.append(f"product={quote(code)}")
    if exporter_iso3:
        params.append(f"exporter={quote(str(exporter_iso3).upper())}")
    if importer_iso3:
        params.append(f"importer={quote(str(importer_iso3).upper())}")
    return ITC_MAM_URL + ("?" + "&".join(params) if params else "")


def market_access_evidence(hs_code: str, importer_iso3: str,
                           exporter_iso3: str = "SAU", year: int | None = None) -> DataPoint:
    """Return ITC evidence or an explicit gap, never a guessed percentage."""
    code = hs6(hs_code)
    if not code:
        return DataPoint(None, "ITC Market Access Map", 0.0,
                         "لا يمكن البحث في ITC قبل إدخال رمز HS من 6 خانات.", _today())
    url = query_url(code, exporter_iso3, importer_iso3)
    period = f" لسنة {year}" if year else ""
    note = (f"لم تُستخرج نسبة رقمية آلياً من ITC Market Access Map{period}. "
            f"تحقق من الرسوم العادية والتفضيلية على HS{code} من {exporter_iso3} "
            f"إلى {importer_iso3} عبر الرابط: {url}. "
            "الضريبة على القيمة المضافة والرسوم الأخرى تُراجع منفصلة عن التعرفة.")
    return DataPoint(None, "ITC Market Access Map", 0.0, note, _today())


