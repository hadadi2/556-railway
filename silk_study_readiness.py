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
# فحوص تُعلَن فجوةً ولا تمنع الإطلاق — advisory checks: declared gap, never a blocker.
ADVISORY = frozenset({"الرسم الجمركي المنطبق"})


def _timeout_s() -> float:
    try:
        return float(os.environ.get("SILK_PREFLIGHT_TIMEOUT_S", "8"))
    except ValueError:
        return 8.0


class Unverified(RuntimeError):
    """تعذّر الجلب (شبكة/حد معدل) — ليس «لا بيانات»؛ يُعلَن مؤقتاً لا نقصاً."""


def _mirror_records(comtrade_trade, hs: str, market, year: int) -> list | None:
    """سجلات المرآة: تصريحات تصدير الشركاء إلى السوق — الاحتياطُ نفسه في خط الدراسة
    (`silk_llm_runtime` للواردات والموردين) حين لا تُبلِغ السوق كومتريد عن نفسها.
    None = تعذّر الجلب؛ [] = لا سجل فعلاً. الجالب يُمرَّر مربوطاً مرةً واحدة لكل فحص."""
    try:
        return comtrade_trade(hs, "all", year, flow="X", partner=market.m49)
    except Exception:  # noqa: BLE001 — فجوة لا انهيار
        return None


def _positive_total(recs) -> bool:
    from silk_data_layer import primary_value
    return sum(v for v in (primary_value(r) for r in recs or [] if isinstance(r, dict))
               if v is not None) > 0


def _imports_years(hs: str, market) -> int:
    from silk_data_layer import comtrade_trade
    import datetime as _dt
    y0 = _dt.date.today().year - 1
    n, failed = 0, 0
    for y in range(y0, y0 - 4, -1):
        try:
            recs = comtrade_trade(hs, market.m49, y)
        except Exception:  # noqa: BLE001 — فجوة لا انهيار
            recs = None
        if recs is None:              # None = تعذّر الجلب؛ [] = لا سجل فعلاً
            failed += 1
            continue
        # comtrade_trade تعيد list[dict] (سجلات كومتريد) لا DataPoint — كان
        # getattr(.., "value") يعطي None دائماً فيُرفض كل طلب بـ409 (بلاغ حي).
        if _positive_total(recs):
            n += 1
            continue
        # الدرس 288: لا سجل مباشر ⇒ المرآة كما في خط الدراسة (لا عند تعذّر الجلب).
        mirror = _mirror_records(comtrade_trade, hs, market, y)
        if mirror is None:
            failed += 1
        elif _positive_total(mirror):
            n += 1
    if n < MIN_YEARS and failed and n + failed >= MIN_YEARS:
        raise Unverified("comtrade")  # قد تكفي لو نجح الجلب — لا نحكم بالنقص
    return n


def _shares_present(hs: str, market) -> bool:
    from silk_data_layer import comtrade_trade, primary_value
    from silk_data_layer_v2 import market_competitors_status
    import datetime as _dt
    year = _dt.date.today().year - 1
    try:
        rows, fetch_failed = market_competitors_status(hs, market.m49, year)
    except Exception as e:  # noqa: BLE001
        raise Unverified("competitors") from e
    if fetch_failed and not rows:
        raise Unverified("competitors")
    if any(isinstance(getattr(r, "value", None), dict) for r in rows):
        return True
    # الدرس 288: المرآة للسنة نفسها كما في `competition_summary_findings`.
    mirror = _mirror_records(comtrade_trade, hs, market, year)
    if mirror is None:
        raise Unverified("competitors")
    return any(r.get("reporterCode") and (primary_value(r) or 0) > 0
               for r in mirror if isinstance(r, dict))


def _tariff_present(hs: str, market) -> bool:
    from silk_tariffs_agent import tariff_with_fallback
    try:
        dp = tariff_with_fallback(hs, market.iso3)
    except Exception as e:  # noqa: BLE001
        raise Unverified("tariff") from e
    if getattr(dp, "value", None) is None and getattr(dp, "status", "") == "fetch_failed":
        raise Unverified("tariff")
    return getattr(dp, "value", None) is not None


def preflight(hs: str, market) -> dict:
    """{ok, missing:[…], unverified:[…], checked:{…}} — الثلاثة بالتوازي تحت مهلة واحدة.
    `unverified` ⊂ `missing`: تعذّر الجلب أو انقضت المهلة — لا يُعرض نقصَ بيانات."""
    checks = {
        "سلسلة واردات لثلاث سنوات على الأقل": lambda: _imports_years(hs, market) >= MIN_YEARS,
        "حصص الموردين": lambda: _shares_present(hs, market),
        "الرسم الجمركي المنطبق": lambda: _tariff_present(hs, market),
    }
    import time as _time
    missing, unverified, checked = [], [], {}
    ex = ThreadPoolExecutor(max_workers=3)
    try:
        futs = {k: ex.submit(fn) for k, fn in checks.items()}
        deadline = _time.monotonic() + _timeout_s()      # مهلة واحدة للفحص كله
        for k, fut in futs.items():
            try:
                ok = bool(fut.result(timeout=max(0.0, deadline - _time.monotonic())))
            except (_Timeout, Unverified):
                ok = False
                unverified.append(k)
            except Exception:  # noqa: BLE001 — عطل غير متوقع = غير مُتحقق لا نقص
                ok = False
                unverified.append(k)
            checked[k] = ok
            if not ok:
                missing.append(k)
    finally:
        ex.shutdown(wait=False)       # لا انتظار لعامل متعثّر بعد المهلة
    # التعرفة فجوة معلنة في التقرير (silk_study_case) لا شرط إطلاق: كثير من
    # الأسواق بلا صفّ WITS/WTO ثنائي، فكان غيابها وحده يرفض الدراسة كلها (بلاغ حي).
    advisory = [k for k in missing if k in ADVISORY]
    missing = [k for k in missing if k not in ADVISORY]
    unverified = [k for k in unverified if k not in ADVISORY]
    return {"ok": not missing, "missing": missing, "unverified": unverified,
            "checked": checked, "advisory_gaps": advisory}
