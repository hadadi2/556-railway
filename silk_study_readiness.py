"""فحص الجاهزية قبل أي حجز أو نداء مدفوع — data preflight (P1-1 / F-03).

قبل `try_reserve_usd` وقبل أول نداء نموذج، تُجلب ثلاث نقاط بمصادر مجانية/مكاشة
بمهلة قصيرة: سلسلة واردات ≥ 3 سنوات، حصص موردين، تعرفة. النقص يُعاد إلى العميل
بقائمته (409 `insufficient_data_preflight`) ليختار المتابعة بتقرير محدود
(`accept_limited=true`) أو الإلغاء — لا يُستهلك رصيد قبل هذا الفحص. لا نداء نموذج
هنا إطلاقاً؛ الفشل الشبكي = فجوة معلنة لا خطأ.
"""
from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _Timeout

MIN_YEARS = 3
# فحوص تُعلَن فجوةً ولا تمنع الإطلاق — advisory checks: declared gap, never a blocker.
ADVISORY = frozenset({"الرسم الجمركي المنطبق"})


# مراجعة §58 (الدرس 288): سوقٌ لا تُبلِغ كومتريد تحتاج حتى ٧ نداءات كومتريد متسلسلة (٦ للواردات
# مباشرةً ومرآةً ثم خروج مبكر، ونداء مباشر للحصص؛ مرآة السنة الأحدث مشتركة، وسنةٌ سابقة
# للحصص فقط حين تغيب الأحدث) تحت مباعدة
# SILK_COMTRADE_MIN_GAP_MS (١٫١ث) + زمن الشبكة — ٨ث كانت تُسقِط أول إطلاق إلى 503. الإطلاق من
# المنصّة غير متزامن فلا يعلّق الواجهة؛ مسار /research المباشر ينتظر الـ202 فقط.
_DEFAULT_TIMEOUT_S = 25.0


def _timeout_s() -> float:
    try:
        return float(os.environ.get("SILK_PREFLIGHT_TIMEOUT_S", _DEFAULT_TIMEOUT_S))
    except ValueError:
        return _DEFAULT_TIMEOUT_S


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


class _Mirror:
    """مرآة (رمز، سوق، سنة) تُجلب مرةً واحدة لكل فحص مسبق — single-flight بين فحصي الواردات
    والحصص (كانا يجلبان مرآة السنة الأحدث معاً فيستهلكان خانتين من مباعدة كومتريد)."""

    def __init__(self, fetch):
        self._fetch = fetch
        self._lock = threading.Lock()
        self._slots: dict = {}

    def get(self, hs: str, market, year: int) -> list | None:
        key = (hs, market.m49, year)
        with self._lock:
            slot = self._slots.get(key)
            owner = slot is None
            if owner:
                slot = self._slots[key] = {"ready": threading.Event()}
        if owner:
            try:
                slot["value"] = _mirror_records(self._fetch, hs, market, year)
            finally:
                slot["ready"].set()
        else:
            slot["ready"].wait()
        return slot.get("value")


def _positive_total(recs) -> bool:
    from silk_data_layer import primary_value
    return sum(v for v in (primary_value(r) for r in recs or [] if isinstance(r, dict))
               if v is not None) > 0


def _imports_years(hs: str, market, fetch=None, mirror: "_Mirror | None" = None) -> int:
    if fetch is None:
        from silk_data_layer import comtrade_trade as fetch
    mirror = mirror or _Mirror(fetch)
    import datetime as _dt
    y0 = _dt.date.today().year - 1
    years = list(range(y0, y0 - 4, -1))
    n, failed = 0, 0
    for i, y in enumerate(years):
        # الحكم محسوم (كفاية، أو نقص لا تغيّره بقية السنوات) ⇒ لا نداء كومتريد زائد تحت المباعدة.
        if n >= MIN_YEARS or n + failed + (len(years) - i) < MIN_YEARS:
            break
        try:
            recs = fetch(hs, market.m49, y)
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
        found = mirror.get(hs, market, y)
        if found is None:
            failed += 1
        elif _positive_total(found):
            n += 1
    if n < MIN_YEARS and failed and n + failed >= MIN_YEARS:
        raise Unverified("comtrade")  # قد تكفي لو نجح الجلب — لا نحكم بالنقص
    return n


def _shares_present(hs: str, market, fetch=None, mirror: "_Mirror | None" = None) -> bool:
    from silk_data_layer import primary_value
    from silk_data_layer_v2 import market_competitors_status
    if fetch is None:
        from silk_data_layer import comtrade_trade as fetch
    mirror = mirror or _Mirror(fetch)
    import datetime as _dt
    y0 = _dt.date.today().year - 1
    unknown = False
    # الأحدث ثم السابقة — كما في `competition_summary_findings` بلا سنة صريحة (الدرس 288).
    for year in (y0, y0 - 1):
        try:
            rows, fetch_failed = market_competitors_status(hs, market.m49, year)
        except Exception:  # noqa: BLE001
            rows, fetch_failed = [], True
        if any(isinstance(getattr(r, "value", None), dict) for r in rows):
            return True
        # الدرس 288: المرآة للسنة نفسها كما في `competition_summary_findings` — وهي تُجرَّب هناك
        # بعد فشل الجلب المباشر أيضاً.
        found = mirror.get(hs, market, year)
        if found is None:
            unknown = True
            continue
        if any(r.get("reporterCode") and (primary_value(r) or 0) > 0
               for r in found if isinstance(r, dict)):
            return True
        unknown = unknown or fetch_failed
    if unknown:
        raise Unverified("competitors")   # مصدرٌ تعذّر جلبه — لا نحكم بالنقص
    return False


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
    from silk_data_layer import comtrade_trade
    mirror = _Mirror(comtrade_trade)   # جالبٌ مربوط مرةً ومرآةٌ مشتركة بين الفحصين
    checks = {
        "سلسلة واردات لثلاث سنوات على الأقل":
            lambda: _imports_years(hs, market, comtrade_trade, mirror) >= MIN_YEARS,
        "حصص الموردين": lambda: _shares_present(hs, market, comtrade_trade, mirror),
        "الرسم الجمركي المنطبق": lambda: _tariff_present(hs, market),
    }
    import time as _time
    missing, unverified, checked = [], [], {}
    ex = ThreadPoolExecutor(max_workers=3)
    try:
        futs = {k: ex.submit(fn) for k, fn in checks.items()}
        deadline = _time.monotonic() + _timeout_s()      # مهلة واحدة للفحص كله
        for k, fut in futs.items():
            if k in ADVISORY and not fut.done():
                continue              # الاستشاري لا يطيل انتظار الإطلاق — يُعلَن إن اكتمل فقط
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
