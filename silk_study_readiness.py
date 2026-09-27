"""فحص الجاهزية قبل أي حجز أو نداء مدفوع — data preflight (P1-1 / F-03).

قبل `try_reserve_usd` وقبل أول نداء نموذج، تُجلب ثلاث نقاط بمصادر مجانية/مكاشة
بمهلة قصيرة: سلسلة واردات ≥ 3 سنوات، حصص موردين، تعرفة. النقص يُعاد إلى العميل
بقائمته (409 `insufficient_data_preflight`) ليختار المتابعة بتقرير محدود
(`accept_limited=true`) أو الإلغاء — لا يُستهلك رصيد قبل هذا الفحص. لا نداء نموذج
هنا إطلاقاً؛ الفشل الشبكي = فجوة معلنة لا خطأ.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout

MIN_YEARS = 3


def _timeout_s() -> float:
    try:
        return float(os.environ.get("SILK_PREFLIGHT_TIMEOUT_S", "8"))
    except ValueError:
        return 8.0


def _imports_years(hs: str, market) -> int:
    from silk_data_layer import comtrade_trade
    import datetime as _dt
    y0 = _dt.date.today().year - 1
    n = 0
    for y in range(y0, y0 - 4, -1):
        try:
            dp = comtrade_trade(hs, market.m49, y)
        except Exception:  # noqa: BLE001 — فجوة لا انهيار
            dp = None
        v = getattr(dp, "value", None) if dp is not None else None
        if isinstance(v, (int, float)) and v > 0:
            n += 1
    return n


def _shares_present(hs: str, market) -> bool:
    from silk_data_layer_v2 import market_competitors
    import datetime as _dt
    try:
        rows = market_competitors(hs, market.m49, _dt.date.today().year - 1) or []
    except Exception:  # noqa: BLE001
        return False
    return any(isinstance(getattr(r, "value", None), dict) for r in rows)


def _tariff_present(hs: str, market) -> bool:
    from silk_tariffs_agent import tariff_with_fallback
    try:
        dp = tariff_with_fallback(hs, market.iso3)
    except Exception:  # noqa: BLE001
        return False
    return getattr(dp, "value", None) is not None


def preflight(hs: str, market) -> dict:
    """{ok, missing:[…], checked:{…}} — تُقيَّم الثلاثة بالتوازي تحت المهلة."""
    checks = {
        "سلسلة واردات لثلاث سنوات على الأقل": lambda: _imports_years(hs, market) >= MIN_YEARS,
        "حصص الموردين": lambda: _shares_present(hs, market),
        "الرسم الجمركي المنطبق": lambda: _tariff_present(hs, market),
    }
    missing, checked = [], {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {k: ex.submit(fn) for k, fn in checks.items()}
        for k, fut in futs.items():
            try:
                ok = bool(fut.result(timeout=_timeout_s()))
            except (_Timeout, Exception):  # noqa: BLE001 — المهلة/الفشل = ناقص
                ok = False
            checked[k] = ok
            if not ok:
                missing.append(k)
    return {"ok": not missing, "missing": missing, "checked": checked}
