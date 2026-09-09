"""واجهة REST لمنصّة سِلك — FastAPI service exposing the Silk engine.

Lazy-imports FastAPI/pydantic inside create_app() so that `import api` works
offline and even when fastapi is absent (founding principle: graceful degrade,
never crash, never fabricate). Module-level `app` is None when fastapi is missing.

Run:  python3 api.py   (needs `pip install fastapi uvicorn`).
"""
import dataclasses
import hashlib
import hmac
import json
import logging
import re
import os
import silk_context
import silk_research_runtime
import threading
import time
import weakref

import silk_i18n

log = logging.getLogger(__name__)

_PIP_HINT = "FastAPI/uvicorn not installed — run: pip install fastapi uvicorn"


def _to_jsonable(obj: object) -> object:
    """حوّل DataPoint وغيره إلى JSON — make DataPoints/dataclasses JSON-safe."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


def _rmtree_bg(tmpdir: str):
    """BackgroundTask تحذف مجلّد تصدير مؤقّت **بعد** إرسال الردّ (البند #8،
    تدقيق v2 الموجة ٣) — FileResponse يبثّ الملف لا مجلّده، فبلا هذا يتراكم
    كل mkdtemp على قرص النشر الفاني حتى إعادة النشر. حذفٌ صامت (ignore_errors)."""
    import shutil
    from starlette.background import BackgroundTask
    return BackgroundTask(shutil.rmtree, tmpdir, ignore_errors=True)


def _index_search(q: str = "", limit: int = 20) -> list[dict]:
    """فهرس بحث المنتجات للوحة المعلومات — product search index for the dashboard
    combobox. Returns [{"name", "hs", "analyzed"}]; empty q -> a small default
    list. Pure/offline (the HS CSV load is lru_cached). Never fabricates.
    """
    import silk_hs_resolver as resolver
    from silk_hs_confirm import _code_desc

    def _row(r: dict) -> dict:
        return {"name": _code_desc(r) or r.get("hs_code"),
                "hs": r.get("hs_code"), "analyzed": False}

    rows = resolver.load_hs_codes()
    q = (q or "").strip().lower()
    if not q:
        # الاقتراحات الافتراضية من رأس البذرة المنسّقة (منتجات سعودية فعلية)
        # لا رأس القائمة الرسمية الرقمي (خيولٌ وحميرٌ حيّة بالإنجليزية).
        curated = resolver.load_hs_codes("data/hs_codes.csv") or rows
        return [_row(r) for r in curated[:12]]

    out: list[dict] = []
    for r in rows:
        hay = " ".join([
            (r.get("description_en") or ""), (r.get("keywords_ar") or ""),
            (r.get("name_ar") or ""), (r.get("name_en") or ""),
            (r.get("keywords") or ""),
        ]).lower()
        if q in hay:
            out.append(_row(r))
        if len(out) >= max(1, limit):
            break
    return out


def _platform_db_path() -> str | None:
    """مسار قاعدة المنصّة المحلول — resolved platform DB path for /health.

    None حين لا تكون الحزمة متوفّرة (المنصّة إضافة اختيارية استيراداً).
    """
    try:
        import silk_platform.db as _pdb
        return _pdb.db_path()
    except Exception:  # noqa: BLE001 — الكشف أفضل جهد؛ لا يُسقط /health
        return None


_VERSION_CACHE: dict | None = None


_HEALTH_APPS: "weakref.WeakSet" = weakref.WeakSet()
_HEALTH_LOCK = threading.Lock()
_HEALTH_REFRESH_HUNG_S = 120.0       # تجديدٌ لا ينتهي في هذه المهلة = قرصٌ متجمّد ⇒ degraded


def _truthy_env(name: str) -> bool:
    """قراءةُ علَمٍ بيئيّ صادق — مصدرٌ واحد (مراجعة R9: كان التحليل مكرّراً أربع مرّات)."""
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _persist_guard_on() -> bool:
    return _truthy_env("SILK_REQUIRE_PERSISTENT_DATA_DIR")


def _body_limit_bytes() -> int:
    """سقفُ حجم جسم الطلب بالبايت — `SILK_MAX_BODY_BYTES` (٢٠ ميغابايت). R9 (API-8)."""
    raw = os.environ.get("SILK_MAX_BODY_BYTES", "").strip()
    try:
        n = int(raw) if raw else 0
    except ValueError:
        n = 0
    return n if n > 0 else 20 * 1024 * 1024


class _BodyLimitMiddleware:
    """R9 (تدقيق 2026-09-01، API-8): وسيطُ ASGI خالص يرفض الجسمَ الأكبر من السقف
    **قبل** قراءته — `Content-Length` المعلَن يُرفَض فوراً بـ413، والجسمُ المقطَّع
    (بلا حجمٍ معلَن) يُعَدّ عند الاستقبال ويُقطع عند السقف. يُركَّب **آخرَ** الوسطاء
    (بعد تركيب المنصّة) فيكون الأبعدَ فعلاً: لا كوكي يُقرأ ولا قاعدةٌ تُفتح قبل الرفض.
    الرفضُ في المسار المقطَّع يُرسَل من `receive` مباشرةً — لا استثناءٌ يعبر وسطاءَ
    `BaseHTTPMiddleware` (كان يصل مجموعةَ استثناءات فيصير 400 «خطأ في الجسم»)."""

    def __init__(self, app):
        self.app = app

    @staticmethod
    def _detail(limit: int) -> dict:
        return {"error": "body_too_large", "max_bytes": limit,
                "message": "حجمُ الطلب يتجاوز السقفَ المسموح"}

    async def _reject(self, send, limit: int) -> None:
        body = json.dumps({"detail": self._detail(limit)},
                          ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode("ascii")),
                                (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        limit = _body_limit_bytes()
        declared = None
        for k, v in scope.get("headers") or ():
            if k == b"content-length":
                try:
                    declared = int(v)
                except ValueError:
                    declared = None
                break
        if declared is not None and declared > limit:
            await self._reject(send, limit)
            return
        seen = 0
        started = False
        rejected = False

        async def _send(msg):
            nonlocal started
            if rejected:
                return                      # 413 على السلك أصلاً — ردُّ التطبيق يُبتلَع
            if msg.get("type") == "http.response.start":
                started = True
            await send(msg)

        async def _receive():
            nonlocal seen, rejected
            msg = await receive()
            if msg.get("type") == "http.request":
                seen += len(msg.get("body") or b"")
                if seen > limit and not rejected and not started:
                    rejected = True
                    await self._reject(send, limit)
                    return {"type": "http.disconnect"}
            return msg
        try:
            await self.app(scope, _receive, _send)
        except Exception:
            if rejected:
                return                      # الردُّ أُرسل؛ ما بعده ضجيجُ قطع الاتصال
            raise


def _health_probe() -> dict:
    """الجزءُ البطيء من فحص الصحّة — استيرادٌ وقرصٌ وقاعدةُ المنصّة وسقفُ الإنفاق.
    يُحسَب بعد تركيب المنصّة في `create_app()` ويُجدَّد من دورة الحاصد
    (`silk_research_runtime.tick`) أو عند قراءةٍ تجده متقادماً أو من `/ready`؛ `/health`
    لا يلمسه لكلّ طلب. R9 (CONC-3/CI-3): كان مسبارُ Railway يقف في طابور مجمّع الخيوط."""
    import silk_storage
    import silk_usage
    deps = {}
    for name in ("fastapi", "uvicorn", "pytrends", "streamlit", "requests"):
        try:
            __import__(name)
            deps[name] = True
        except Exception:  # noqa: BLE001
            deps[name] = False
    probe: dict = {"deps": deps, "version": _running_version(),
                   "platform_ready": _platform_readiness(), "pstatus": None,
                   "cap_exhausted": False}
    try:
        probe["pstatus"] = silk_storage.persistence_status()
    except Exception as _e:  # noqa: BLE001 — تشخيص لا شرط
        log.debug("storage health probe skipped: %s", _e)
    try:
        probe["cap_exhausted"] = bool(silk_usage.would_exceed_cap(1))
    except Exception as _e:  # noqa: BLE001
        log.debug("usage cap probe skipped: %s", _e)
    return probe


def refresh_health_snapshot(app) -> dict:
    """أعد الفحصَ البطيء الآن — دالّةٌ حرّة بلا إغلاقٍ يحمل `app` (مراجعة R9: دورةُ
    المراجع كانت تُبقي تطبيقاتِ الاختبارات في `_HEALTH_APPS` حتى GC الدوري)."""
    snap = {"data": _health_probe(), "at": time.monotonic()}
    app.state.health_snapshot = snap
    return snap


def _health_snapshot(app) -> dict:
    """لقطةُ `/health` لهذا التطبيق — تُبنى عند الإقلاع وتُجدَّد لاحقاً."""
    snap = getattr(app.state, "health_snapshot", None)
    if snap is None:
        snap = refresh_health_snapshot(app)
    return snap


def _health_max_age_s() -> float:
    """عمرُ اللقطة الأقصى قبل تجديدٍ عند القراءة — دورةُ الحاصد، أو ٦٠ ث حين يكون مطفأً."""
    return max(float(silk_research_runtime.reap_interval_s() or 0.0), 60.0)


def _health_refresh_hung(app) -> "str | None":
    started = getattr(app.state, "health_refresh_started", None)
    if started is not None and time.monotonic() - started > _HEALTH_REFRESH_HUNG_S:
        return "health probe has been running for too long (storage stalled?)"
    return None


def _kick_health_refresh(app) -> None:
    """تجديدٌ خلفيّ أحاديّ (single-flight) على خيطٍ مستقلّ عن مجمّع الطلبات — يُنادى حين
    تتجاوز اللقطةُ عمرَها الأقصى (الحاصدُ مطفأ أو متأخّر). مراجعة R9."""
    st = app.state
    with _HEALTH_LOCK:
        if getattr(st, "health_refresh_started", None) is not None:
            return
        st.health_refresh_started = time.monotonic()

    def _run() -> None:
        try:
            refresh_health_snapshot(app)
        except Exception as exc:  # noqa: BLE001
            log.debug("health snapshot refresh failed: %s", exc)
        finally:
            st.health_refresh_started = None
    threading.Thread(target=_run, name="silk-health-refresh", daemon=True).start()


def _refresh_all_health_snapshots() -> None:
    """خطّافُ دورة الحاصد (`silk_research_runtime.tick`) — يجدّد لقطاتِ التطبيقات الحيّة."""
    for app in list(_HEALTH_APPS):
        try:
            refresh_health_snapshot(app)
        except Exception as exc:  # noqa: BLE001 — اللقطةُ قناةٌ جانبية لا تُسقط الحاصد
            log.debug("health snapshot refresh failed: %s", exc)


_PERSIST_ALARM = {
    "unconfigured": "persist guard on but no persistent store is configured",
    "unwritable": "persist guard on but the data dir is not writable",
    "nonmount": "persist guard on but the data dir is not a mounted volume",
}


def _storage_alarm(pstatus: "dict | None") -> "str | None":
    """سببُ 503: مصيدةُ القرص الدائم مفعّلة واللقطةُ تقول «فانٍ» — نفسُ قاعدة حارس
    الإقلاع (`silk_storage.persistence_violation`) فلا ينحرفان."""
    if not _persist_guard_on() or not pstatus:
        return None
    import silk_storage
    return _PERSIST_ALARM.get(silk_storage.persistence_violation(
        pstatus, allow_nonmount=_truthy_env("SILK_ALLOW_NONMOUNT_PERSIST")))


def _running_version() -> dict:
    """نسخةُ الشيفرة العاملة — مصدرها معلَن، وغيابها `None` لا اختلاق.

    تُحسَب مرّةً وتُخزَّن: `/health` نقطةٌ عامّة بلا مصادقة، وتفريعُ `git` عند
    كل نداء سطحُ إبطاءٍ مجّاني (مراجعة ذاتية §58). النسخة لا تتغيّر داخل
    العملية أصلاً. Computed once; the running code cannot change mid-process.
    """
    global _VERSION_CACHE
    if _VERSION_CACHE is not None:
        return _VERSION_CACHE
    _VERSION_CACHE = _detect_version()
    return _VERSION_CACHE


def _detect_version() -> dict:
    """اكتشاف النسخة فعلياً — env أولاً ثم `git` ثم فجوة معلَنة."""
    for env_key in ("RAILWAY_GIT_COMMIT_SHA", "SOURCE_COMMIT", "GIT_COMMIT",
                    "SILK_BUILD_SHA"):
        sha = os.environ.get(env_key, "").strip()
        if sha:
            return {"commit": sha[:12], "source": env_key}
    try:                       # نشرٌ من مستودع كامل (تطوير/حاوية بـ.git)
        import subprocess
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=3,
                             cwd=os.path.dirname(os.path.abspath(__file__)))
        sha = (out.stdout or "").strip()
        if out.returncode == 0 and sha:
            return {"commit": sha[:12], "source": "git"}
    except Exception:  # noqa: BLE001 — الكشف أفضل جهد؛ لا يُسقط /health
        pass
    return {"commit": None, "source": None,
            "note": "لا مصدر نسخة متاح في هذه البيئة — اضبط SILK_BUILD_SHA"}


def _platform_readiness() -> dict | None:
    """جهوزيّة المنصّة لِـ/health — None حين لا تتوفّر الحزمة استيراداً.

    يفتح اتصالاً للقراءة فقط ويغلقه؛ أي فشل يعود None بدل إسقاط `/health`
    (نفس عقد `_platform_db_path`). Best-effort; never breaks /health.
    """
    try:
        from silk_platform import bootstrap as _pboot, db as _pdb
        conn = _pdb.connect()
        try:
            return _pboot.readiness(conn)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return None


def _cors_origins() -> list[str]:
    """أصول CORS المسموحة — allowed origins from CORS_ORIGINS; [] = same-origin only.

    الموجة ٠: الافتراضي لم يعد "*" — بلا ضبط صريح لا يُركَّب CORS إطلاقاً
    (الواجهة تُقدَّم من نفس الأصل). Wildcard requires an explicit opt-in.
    """
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if not raw:
        return []
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


_OWNER_ENV_ONLY = ("ANTHROPIC_API_KEY",)   # R7 (SEC-13): لا يُخزَّن من الواجهة أبداً
_TOKEN_QS_RX = re.compile(r"((?:token|sig)=)[^&\s\"']+")   # مراجعة: `sig=` للروابط الموقّعة


class _QueryTokenFilter(logging.Filter):
    """R7 (تدقيق 2026-09-01، SEC-6): سجلُّ وصول uvicorn كان يكتب رابطَ إعادة التعيين
    كاملاً (`/reset-password?token=…`) فيبقى الرمزُ الخام في سجلّات Railway. يُنقَّح
    هنا لا بإطفاء السجلّ — إجراءُ قراءة عنوان النظير (DEPLOY_RAILWAY) يحتاجه."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if isinstance(record.args, tuple):
                record.args = tuple(_TOKEN_QS_RX.sub(r"\1<redacted>", a)
                                    if isinstance(a, str) else a for a in record.args)
            if isinstance(record.msg, str) and "token=" in record.msg:
                record.msg = _TOKEN_QS_RX.sub(r"\1<redacted>", record.msg)
        except Exception:  # noqa: BLE001 — مرشّحُ سجلّ لا يُسقط طلباً أبداً
            pass
        return True


def _hsts_enabled() -> bool:
    """R7 (SEC-1): HSTS مع `SILK_HSTS=1` أو أيّ إشارة إنتاجٍ للمنصّة؛ `SILK_HSTS=0` يُطفئه."""
    flag = os.environ.get("SILK_HSTS", "").strip()
    if flag == "0":
        return False
    if flag == "1":
        return True
    return (os.environ.get("SILK_PLATFORM_SECURE_COOKIES") == "1"
            or os.environ.get("SILK_PLATFORM_REQUIRE_SECRET") == "1")


def _redact_text(text: str) -> str:
    """نقِّ نصَّ استثناءٍ قبل أن يبلغ جسمَ ردّ أو صفَّ قاعدة — R7 (API-9/SEC-10)."""
    try:
        from silk_diagnostics import _redact
        return _redact(str(text or ""))
    except Exception:  # noqa: BLE001 — التنقيةُ لا تُسقط الطلب؛ الأصلُ يُبتر لا يُعاد
        return "<unredactable>"


def _key_matches(got: str, expected: str) -> bool:
    """مقارنةٌ ثابتةُ الزمن **آمنةٌ للمدخلات** — مراجعة R7: `hmac.compare_digest` يرفع
    TypeError على نصٍّ غير ASCII فكانت ترويسةٌ مشوَّهة 500 لا 401."""
    if not got or not expected or not got.isascii():
        return False
    return hmac.compare_digest(got, expected)


def _api_key_expected() -> str:
    """مفتاح الخدمة المتوقع — the API key required by /analyze ('' = auth off).

    الموجة ٠: يُضبط SILK_API_KEY في الإنتاج فيصير كل طلب /analyze بلا ترويسة
    X-API-Key مطابقة = 401 **قبل تشغيل أي وكيل**. غير مضبوط => وضع تطوير مفتوح.
    """
    return os.environ.get("SILK_API_KEY", "").strip()


# الطبقات المدفوعة الخاضعة للسقف — paid layers counted against the daily cap.
_PAID_FLAGS = ("with_localprice", "with_volza", "with_explee", "with_ai")

# مفاتيح البيئة المدفوعة — the paid-provider key env vars (503 guard below).
_PAID_KEY_ENVS = ("LOCALPRICE_API_KEY", "VOLZA_API_KEY",
                  "EXPLEE_API_KEY", "ANTHROPIC_API_KEY")


def _unprotected_paid_keys() -> list[str]:
    """مفاتيح مدفوعة بلا مصادقة — paid keys present while SILK_API_KEY is unset.

    الإغلاق المسبق قبل الموجة ٤: مفتاح مدفوع في البيئة + مصادقة معطّلة =
    خدمة عامة تصرف رصيداً مدفوعاً لأي مجهول. القاعدة: وضع التطوير المفتوح
    مشروع فقط عند غياب المفاتيح المدفوعة **كلها**؛ وجود أي منها يوجب ضبط
    SILK_API_KEY وإلا رُفض تشغيل الطبقات المدفوعة بـ503 وسبب واضح.
    """
    if _api_key_expected():
        return []
    return [k for k in _PAID_KEY_ENVS if os.environ.get(k, "").strip()]


def _apply_production_cost(card: dict | None, cost) -> dict | None:
    """ادمج تكلفة الإنتاج المُدخلة في بطاقة المنتج — أو ابنِ بطاقة منها وحدها.

    هدف الدراسة الاحترافية (البند ٢): التكلفة رقمُ المصدّر نفسه، تصل من حقل
    الطلب المباشر (`production_cost_per_unit`) أو من حقل دراسة المنصّة —
    وحين تصل تغلب تكلفةَ الكتالوج (طلبٌ صريح أحدث يفوز). قيمة غير رقمية أو
    ≤0 تُتجاهَل فيبقى ما كان (لا اختلاق ولا إسقاط بطاقة قائمة)."""
    try:
        val = float(cost)
    except (TypeError, ValueError):
        return card
    if val <= 0:
        return card
    out = dict(card or {})
    out["cost_per_unit"] = val
    return out


def _early_halt_enabled() -> bool:
    """علم الإيقاف المبكر (هدف الدراسة الاحترافية، البند ٨) — افتراضه مفعّل.

    حين تخرج أعمدة قرار المحرك المحسوبة من البعثات دون الحد الأدنى، النتيجة
    محسومة سلفاً «بيانات غير كافية» (`silk_decision` فرع insufficient_pillars)
    ولا يغيّرها المحلل ولا الكاتب — فيُتخطّى أغلى نداءين معلَنَين. مخرج
    التعطيل: `SILK_EARLY_HALT=0`."""
    return os.environ.get("SILK_EARLY_HALT", "1").strip().lower() not in (
        "0", "false", "no", "off")


# طريقةُ «رمزٌ صريحٌ باسمِ منتجٍ فارغ» — وسمٌ خاصّ بطبقة الـAPI: خطُّ التصنيف
# نفسُه (`silk_hs_pipeline`) لا يعرف هذا المسار لأنه لا اسمَ لديه يقيس عليه.
_METHOD_EXPLICIT_UNVERIFIED = "explicit_unverified"


def _explicit_code_only_contract(hs_code: object) -> dict:
    """عقدُ «رمزٌ صريحٌ باسمِ منتجٍ فارغ» — فحصُ مرجعٍ حتميّ لا `empty_product`.

    الحادثة (مراجعة #254): `POST /analyze {"product": "", "hs_code": ...}`
    كان يصل `classify("", ...)` فيسقط في فرع الاسم الفارغ ويُرفَض
    `empty_product` — سببٌ كاذب (رمزٌ صريحٌ في الطلب) لسلوكٍ كان قبل الموجة
    يمضي على الرمز المكتوب. القرار (افتراضٌ معلَن أقرّه المالك، خطة
    2026-08-31): فحصٌ حتميّ على المرجع الرسمي (`silk_hs_confirm._find_row`):

    - موجودٌ ⇒ يُعتمَد بوسم `explicit_unverified` وثقة **0.0**: لا اسمَ
      يُقاس عليه فلا يُختلَق اتفاقٌ لم يُقَس (نفسُ `ev.get("score") or 0.0`
      في مسار `hs_confirmed=true` حين لا تقييم — البند ٤: الثقة رقمٌ دائماً)،
      والأصلُ يعلن أن الاتفاق غير مقيس. بوّاباتُ ما بعد التصنيف تُكرِّم هذا
      الاعتمادَ عبر `_hs_explicitly_settled` كما تُكرِّم `hs_confirmed=true`.
    - غائبٌ ⇒ رفضٌ بسببه الحقيقي («ليس في المرجع الرسمي») لا `empty_product`.

    اسمٌ فارغ **بلا** رمزٍ لا يمرّ من هنا أصلاً — `empty_product` هناك صادق.
    """
    import silk_hs_pipeline as _pipe
    from silk_hs_confirm import _find_row
    raw = str(hs_code or "").strip()
    code = _pipe._valid_hs6(raw)
    row = _find_row(code) if code else None
    if row is None:
        return _pipe._contract(
            classification_status=_pipe.REQUIRES_CONFIRMATION,
            refusal_code=_pipe.REFUSAL_CATALOG_REJECTED,
            catalog_hs_code=code or (raw or None),
            catalog_hs_status=_pipe.CATALOG_REJECTED,
            provenance=[{"step": "explicit_reference_check",
                         "source": "data/hscodes_full.csv",
                         "detail": f"{raw}: غائب عن المرجع"}],
            reason=(f"الرمز {raw} ليس في المرجع الرسمي — واسمُ المنتج فارغٌ "
                    "فلا اسمَ يُصنَّف بديلاً. صحّح الرمزَ أو اكتب اسمَ "
                    "المنتج كما هو على العبوة."))
    return _pipe._contract(
        final_hs_code=code,
        official_hs_description=_pipe._official_description(code),
        # لا اسمَ قيسَ عليه شيء — الثقةُ رقمٌ (البند ٤) ولا تُختلَق 1.00.
        confidence=0.0,
        classification_status=_pipe.APPROVED,
        classification_method=_METHOD_EXPLICIT_UNVERIFIED,
        catalog_hs_code=code,
        catalog_hs_status=_pipe.CATALOG_AUTO_APPROVED,
        provenance=[{"step": "decision", "source": "explicit_code",
                     "detail": "لا اسمَ يُقاس عليه — وُجد الرمزُ في المرجع "
                               "فقط؛ الاتفاقُ مع المنتج غير مقيس"}],
        reason="رمزٌ صريحٌ باسمِ منتجٍ فارغ: وُجد في المرجع الرسمي فاعتُمد، "
               "والاتفاقُ مع المنتج غير مقيس — لا اسمَ يُقاس عليه.")


def _hs_explicitly_settled(contract: object) -> bool:
    """هل اعتُمد الرمزُ على مسار «صريحٌ باسمٍ فارغ»؟

    بوّاباتُ ما بعد التصنيف (`preflight_resolve`: بوّابتا الثقة والدلالة
    والمحور) تقيس الرمزَ على **اسم المنتج** — ولا اسمَ هنا أصلاً، فإعادةُ
    القياس على فراغٍ تُعيد إنتاجَ الرفض الكاذب من بابٍ آخر. الاعتمادُ
    المعلَن أعلاه يُكرَّم عندها كما يُكرَّم `hs_confirmed=true` — نفسُ
    الميكانيكا، بوسمٍ يبقي «غير مقيس» على وجه العقد.
    """
    return bool(isinstance(contract, dict) and contract.get(
        "classification_method") == _METHOD_EXPLICIT_UNVERIFIED)


def create_app():
    """أنشئ تطبيق FastAPI — build the FastAPI app, or raise if fastapi is absent."""
    try:
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel, Field
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise RuntimeError(_PIP_HINT) from exc

    import silk_engine
    import silk_hs_resolver
    import silk_storage
    import silk_usage

    # صفحات التوثيق التفاعلي (`/docs` و`/redoc` و`/openapi.json`) كانت مكشوفة
    # بلا مصادقة (تدقيق 2026-08-27، البند ٢٧): لا أسرار فيها، لكنها تُهدي
    # الماسحَ خريطةَ سطحِ الهجوم كاملةً (كل نقطة نهاية وشكل كل حمولة). القاعدة
    # نفسها التي تحرس النقاط تحرس فهرسها: مضبوطٌ `SILK_API_KEY` (أي نشرٌ
    # حقيقي) ⇒ تُطفأ الصفحات الثلاث؛ وضع التطوير المفتوح يبقيها كما هي.
    # `SILK_PUBLIC_DOCS=1` مخرجٌ صريح لمن يريدها عامةً عمداً — قرار لا صمت.
    # Interactive docs are disabled once an API key is configured.
    _docs_public = (not os.environ.get("SILK_API_KEY", "").strip()
                    or os.environ.get("SILK_PUBLIC_DOCS") == "1")
    app = FastAPI(title="Silk Market Intelligence API",
                  description="Real public-data export-market analysis "
                              "(UN Comtrade + World Bank). Preliminary, never fabricated.",
                  **({} if _docs_public
                     else {"docs_url": None, "redoc_url": None,
                           "openapi_url": None}))

    # Stage 2A: حمّل مفاتيح المصادر المحفوظة إلى بيئة العملية عند الإقلاع —
    # متغير بيئة النشر يفوز (overwrite=False). Best-effort: فشلها لا يمنع الإقلاع.
    try:
        import silk_store as _store
        _store.migrate()
        _store.load_settings_into_env()
    except Exception as _e:  # noqa: BLE001
        log.debug("settings bootstrap skipped: %s", _e)

    # القرص الدائم: هيّئ قاعدة التحليلات ومجلد ذاكرة الطلبات على مساراتهما
    # الموجَّهة (SILK_DB/SILK_CACHE_DIR أو SILK_DATA_DIR على Railway volume)
    # عند الإقلاع — إنشاء المجلدات إن غابت، فلا يفاجأ أول طلب بكتابة فاشلة.
    # Persistent volume: init the analyses DB and cache dir at startup so the
    # first request never trips over a missing directory. Best-effort.
    try:
        silk_storage.init_db()
        import silk_cache as _cache
        os.makedirs(_cache._cache_dir(), exist_ok=True)
    except Exception as _e:  # noqa: BLE001
        log.warning("storage bootstrap failed (continuing): %s", _e)

    # قوانين LESSONS.md البند ٤ (فقدان تحليلات مدفوعة على قرص Railway الفاني):
    # مصيدة إقلاع صريحة. حين يضبط المشغّل SILK_REQUIRE_PERSISTENT_DATA_DIR
    # (على النشر الإنتاجي) بلا توجيه أيّ مخزن دائم (SILK_DATA_DIR أو SILK_DB)،
    # ترفض الخدمة الإقلاع بصوت عالٍ بدل أن تكتب على قرص يُمحى عند إعادة النشر
    # التالية فتُفقَد كل التحليلات (وبيانات المخزن/الاستخدام/الذاكرة المؤقتة)
    # بصمت. مطفأة افتراضياً — نفس عقد المشروع «غير مضبوط = وضع تطوير مفتوح»
    # (كـSILK_API_KEY/SILK_PAID_DAILY_CAP)، فالمجموعة الهرمتية والتطوير بلا
    # مفاتيح لا يتأثران؛ تحذير /health الدائم يبقى قائماً في كلتا الحالتين.
    #
    # تقوية (بلاغ المالك الحيّ — «الدراسة تروح بعد كل دبلوي رغم ضبط المتغيّر»):
    # الفحص القديم اكتفى بأن المتغيّر **غير فارغ**، فمرّ سيناريو `SILK_DATA_DIR`
    # مضبوط بلا وحدة تخزين مركّبة على مساره فعلًا — الكتابة تذهب لجذر الحاوية
    # الفاني والحارس نائم. الآن نتحقّق من الحالة الفعلية: مركَّب (is_mount) +
    # قابل للكتابة (writable). المخرج الوحيد لغير-المركَّب هو SILK_ALLOW_NONMOUNT_
    # PERSIST=1 (لمضيفٍ قرصه الجذري دائم أصلًا) — قرار مشغّل صريح لا صمت.
    if _persist_guard_on():
        _pst = silk_storage.persistence_status()
        # مراجعة R9: القاعدةُ الواحدة في `silk_storage.persistence_violation` — يقرؤها هذا
        # الحارسُ و`/health` (`_storage_alarm`) فلا ينحرف أحدُهما عن الآخر.
        _violation = silk_storage.persistence_violation(
            _pst, allow_nonmount=_truthy_env("SILK_ALLOW_NONMOUNT_PERSIST"))
        if _violation == "unconfigured":
            raise RuntimeError(
                "SILK_REQUIRE_PERSISTENT_DATA_DIR مضبوط لكن لا SILK_DATA_DIR ولا "
                "SILK_DB موجَّه إلى تخزين دائم — الحاوية ستفقد كل التحليلات "
                "(والمخزن/الاستخدام/الذاكرة المؤقتة) عند إعادة النشر التالية. "
                "اضبط SILK_DATA_DIR=/data (وحدة تخزين Railway) قبل الإقلاع، أو "
                "أزِل SILK_REQUIRE_PERSISTENT_DATA_DIR إن كان التخزين الفاني مقصوداً.")
        if _violation == "unwritable":
            raise RuntimeError(
                "SILK_REQUIRE_PERSISTENT_DATA_DIR مضبوط لكن مسار التخزين "
                f"'{_pst['path']}' غير قابل للكتابة — تعذّر إنشاء ملف مجسّ فيه. "
                "تأكّد أن وحدة التخزين مركّبة وصلاحياتها صحيحة قبل الإقلاع.")
        if _violation == "nonmount":
            raise RuntimeError(
                "SILK_REQUIRE_PERSISTENT_DATA_DIR مضبوط لكن مسار التخزين "
                f"'{_pst['path']}' ليس وحدة تخزين مركّبة (أقرب نقطة تركيب = "
                f"'{_pst['mountpoint']}' = جذر الحاوية الفاني) — بياناتك ستُمحى "
                "عند إعادة النشر رغم ضبط المتغيّر. تأكّد أن Mount Path لوحدة "
                "Railway يساوي SILK_DATA_DIR تمامًا، أو اضبط "
                "SILK_ALLOW_NONMOUNT_PERSIST=1 إن كان القرص الجذري للمضيف دائمًا.")

    # حاصد التشغيلات اليتيمة عند الإقلاع — إعادة النشر تقتل عمليةً منتصف
    # تشغيلة /research، فيبقى صفّها 'running' أبداً وحجزُ الدولار المسبق بلا
    # مصالحة يسدّ السقف اليومي. المكنَس يوسم العالق 'failed' ويصالح حجزه إلى
    # الفعلي-حتى-الآن. الإقلاع أهمّ نقطة تشغيل (يلتقط ما خلّفته العملية الميتة).
    try:
        import silk_storage
        _reaped = silk_storage.reap_orphan_research_runs()
        if _reaped:
            log.warning("startup orphan reaper marked %d stale runs failed: %s",
                        len(_reaped), _reaped)
    except Exception as _e:  # noqa: BLE001 — الحصاد لا يُسقِط الإقلاع أبداً
        log.warning("startup orphan reaper failed: %s", _e)
    # R2b (تدقيق 2026-09-01، API-3): حاصدٌ دوريّ **مستقلّ** عن `SILK_REFRESH_HOURS`
    # — كان يدور مع التحديث الدوري وحده، فبلا `SILK_REFRESH_HOURS` (الافتراض) لا
    # يُحصَد صفٌّ عالق إلا عند الإقلاع التالي.
    silk_research_runtime.start_reaper()
    _access_log = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _QueryTokenFilter) for f in _access_log.filters):
        _access_log.addFilter(_QueryTokenFilter())

    # التحديث الدوري داخل العملية (SILK_REFRESH_HOURS) — قرص Railway يُركَّب
    # على خدمة واحدة، فالمُجدول خيط خلفي هنا لا خدمة cron منفصلة. معطّل بلا
    # المتغير — الاختبارات والتطوير لا تتأثر. In-process scheduled refresh.
    # (الحلقة الدورية تحصد اليتيمة أيضاً — راجع silk_collectors._loop).
    try:
        import silk_collectors
        silk_collectors.start_scheduler()
    except Exception as _e:  # noqa: BLE001
        log.warning("refresh scheduler not started: %s", _e)

    # النسخ الاحتياطي الدوري (SILK_BACKUP_HOURS، مطفأ افتراضاً — قرار مالك):
    # نفس نمط خيط التحديث أعلاه، ولنفس سبب «خدمة واحدة على الوحدة». يدوياً:
    # GET /ops/backup (محروسة). Periodic SQLite backup, opt-in, in-process.
    try:
        import silk_backup
        silk_backup.start_scheduler()
    except Exception as _e:  # noqa: BLE001
        log.warning("backup scheduler not started: %s", _e)

    # CORS (الموجة ٠): الافتراضي صار **نفس الأصل فقط** (الواجهة تُقدَّم من نفس
    # الخدمة فلا تحتاج CORS). للواجهات المنفصلة (Netlify) اضبط CORS_ORIGINS
    # بقائمة أصول مفصولة بفواصل؛ "*" لم يعد افتراضياً ويتطلب ضبطاً صريحاً.
    allow = _cors_origins()
    if allow:
        app.add_middleware(CORSMiddleware, allow_origins=allow,
                           allow_methods=["*"], allow_headers=["*"])

    # ضغط gzip لكل الردود الكبيرة — لازمة هيرو silkhero (2026-08-18): الكرة
    # الأورثوغرافية المضمّنة ضاعفت هبوط المنصّة إلى ~140KB، والضغط يعيده
    # ~4x أصغر على الشبكات الضعيفة (يفيد كل الصفحات وJSON الكبير أيضاً).
    from fastapi.middleware.gzip import GZipMiddleware
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # ترويسات أمان على كل ردّ (L-2) — security headers on every response.
    # CSP خطّ أساس يسمح بأنماط/سكربتات الصفحة المضمّنة وخطوط Google (الواجهة
    # ملف واحد بأنماط وسكربت مضمّنين)؛ التشديد (nonces / خط ذاتي الاستضافة =
    # L-3) لاحقاً. nosniff يمنع تخمين نوع المحتوى؛ Referrer-Policy يحدّ التسريب.
    # الخطوط صارت مستضافة ذاتياً (task 12) — لا مضيف خطوط خارجي في السياسة.
    _CSP = ("default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; "
            "base-uri 'self'; frame-ancestors 'none'; "
            # R7 (SEC-9): لا نماذجَ تُرسَل لغير الأصل، ولا كائناتٍ مضمَّنة.
            "form-action 'self'; object-src 'none'")

    @app.middleware("http")
    async def _security_headers(request, call_next):  # noqa: ANN001, ANN201
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers.setdefault("Content-Security-Policy", _CSP)
        # R6 (تدقيق 2026-09-01، FE-16): صفحاتُ الواجهة ملفٌّ واحد يتغيّر مع كل نشرة —
        # بلا Cache-Control كانت نسخةٌ قديمة تعلق في المتصفّح بعد النشر (ETag يُعيد
        # التحقّق لكنّ الكاش الاستكشافي كان يخدم القديم بلا سؤال). JSON لا يُمَسّ.
        if (resp.headers.get("content-type") or "").startswith("text/html"):
            resp.headers.setdefault("Cache-Control", "no-cache")
        if _hsts_enabled():
            resp.headers.setdefault("Strict-Transport-Security",
                                    "max-age=31536000; includeSubDomains")
        return resp

    class ProductCard(BaseModel):
        """بطاقة المنتج (الموجة ٤، vision §2) — اختيارية، تفعّل محرّك التقاطع."""
        cost_per_unit: float
        unit: str | None = None
        tier: str | None = None            # premium|standard|economy
        monthly_capacity: float | None = None
        shipping_per_unit: float | None = None  # افتراض شحن معلَن قابل للتعديل
        certifications: list[str] | None = None  # مثال: HALAL, ISO22000, SFDA

    class AnalyzeRequest(BaseModel):
        """طلب تحليل منتج (المسار العادي) — analyze request body.

        الموجة ٢: حقول الطبقات المدفوعة أُزيلت نهائياً من هذا النموذج —
        إرسالها يُتجاهَل بنيوياً (pydantic يسقط الحقول الزائدة)، فالمسار
        العادي **يستحيل** أن يشغّل طبقة مدفوعة. التعميق عبر POST /deepen.
        """
        product: str
        year: int | None = None
        with_trends: bool = False
        with_tariffs: bool = False
        with_faostat: bool = False
        with_maps: bool = False
        with_websearch: bool = False
        with_competitors: bool = False
        with_channels: bool = False
        with_importers: bool = False
        with_requirements: bool = False
        with_trend: bool = False          # مدى السنوات — multi-year import trend
        trend_span: int = 5
        product_card: ProductCard | None = None
        hs_code: str | None = None
        # مصدرُ الرمز المُرسَل (حادثة الدراسة #10 — رمزٌ كتالوجيّ قديم عومل
        # كإجابة مشغّلٍ حاضرة): "catalog" = رمزٌ أُعيد من سجلّ منتجٍ/دراسةٍ
        # مخزَّن لا اختيارُ إنسانٍ في هذا الطلب — لا يُعامَل user_supplied في
        # بوّابات HS (اختصارُ محور preflight_block:692 لا يسري عليه). الغياب/
        # أيّ قيمة أخرى = سلوك اليوم حرفياً.
        hs_source: str | None = None
        markets: list[str] | None = None  # ISO3s لتضييق المرشّحين؛ فارغ = كل الأسواق
        # P3: توجيهات درج «إعدادات الوكلاء» — {agent_key: {on: bool, cmd: str}}.
        # تُطبَّع شكلياً في _clean_agent_prefs؛ الأمر يوجّه تركيز برومبتات
        # كلود حصراً داخل العزل — لا يغيّر رقماً ولا يصل وكيل بيانات.
        agent_prefs: dict | None = None
        persist: bool = False
        # hs_confirmed=true بعد مراجعة المستخدم يتجاوز بوّابة تأكيد HS
        # (الموجة ٢ — نفس عقد /research، silk_hs_confirm.preflight_block).
        hs_confirmed: bool = False
        # سماتُ بطاقة العبوة الرقمية من استخلاص الصورة (بلاغ المُشرِف):
        # [{name, value, unit}] — تحسم عتبةَ الترويسة (نسبة دهن/سعة/وزن) قبل
        # عرض أيّ حوارٍ يسأل التاجرَ عن رقمٍ يُجيب عنه المنتجُ نفسُه. غيابها
        # => المسارُ كما كان (ويبٌ ثم حوار).
        label_attributes: list[dict] | None = None

    class IntakeRequest(BaseModel):
        """طلب استقبال منتج متعدّد الوسائط — {name} أو {image_base64,kind}.

        محوّلٌ أماميّ (الميزة ب): لا يبدأ أيّ تحليل — يُعيد اسماً مؤكَّداً/قابلاً
        للتعديل يدخل بعده المسارَ القائم. لا حقول مدفوعة/تحليل هنا بنيوياً.
        """
        name: str | None = None
        image_base64: str | None = None
        kind: str = "product"                 # "product" | "ingredients_label"
        media_type: str = "image/jpeg"        # jpeg/png/webp

    class ClassifyRequest(BaseModel):
        """طلب تصنيف HS (Wave 1) — {product, ingredients?, category?}.

        خطوةٌ ما قبل التشغيل: تُعيد **اقتراح** HS6 (حتمي واثق، أو نداءُ كلود
        مقيسٌ مُرسًى على المرجع، أو منتقٍ يدوي) — لا تبدأ تحليلًا ولا تحجز شيئًا
        هنا؛ المستخدم يؤكّد الرمز ثم يدخل `/research`.
        """
        product: str | None = None
        ingredients: list[str] | None = None      # من استخلاص الصورة إن وُجد
        category: str | None = None

    class DeepenRequest(BaseModel):
        """طلب تعميق (المسار المدفوع) — the /deepen request body (wave 2).

        المسار الوحيد القادر على تفعيل الطبقات المدفوعة، ويعمل داخل
        silk_context.deepen_context() فيسمح حارس BaseAgent البنيوي بالتنفيذ.

        `hs_confirmed` (بلاغ «حليب نادك»): لم يكن هذا الحقل موجوداً هنا
        إطلاقاً — لأنّ `/deepen` لم تكن له بوّابةُ HS أصلاً، فلا مَخرجَ يحتاجه.
        أُضيف مع البوّابة كي يملك المستخدمُ نفسَ حقّ التأكيد الصريح المتاح على
        `/analyze` و`/research` (LAW: المالك آخِر مؤكِّد، لا طريقٌ مسدود).
        """
        product: str
        year: int | None = None
        # تأكيدُ المستخدم الصريح يتجاوز بوّابةَ HS — نفس عقد المسارين الآخرين.
        hs_confirmed: bool = False
        # قياساتُ بطاقة العبوة — نفس عقد `/analyze` و`/research` حرفياً
        # (اللائحة ٦٥): المسارُ المدفوع لا يُترَك خارج نقطة القياس.
        label_attributes: list[dict] | None = None
        with_trends: bool = False
        with_tariffs: bool = False
        with_faostat: bool = False
        with_maps: bool = False
        with_websearch: bool = False
        with_localprice: bool = False
        own_price: float | None = None
        with_volza: bool = False
        with_explee: bool = False
        with_ai: bool = False
        with_competitors: bool = False
        with_channels: bool = False
        with_importers: bool = False
        with_requirements: bool = False
        with_trend: bool = False          # مدى السنوات — multi-year import trend
        trend_span: int = 5
        product_card: ProductCard | None = None
        hs_code: str | None = None
        # نفس عقد `/analyze`/`/research` (اللائحة ٦٥ — لا مسار خارج النقطة):
        # "catalog" = رمزٌ مخزَّن مُعادٌ لا اختيارُ إنسانٍ في هذا الطلب.
        hs_source: str | None = None
        persist: bool = False

    # ══════════ التصنيف: نقطةُ الحقيقة الواحدة قبل أيّ إنفاق ══════════════
    #
    # حادثة «حلاوة طحينية» (2026-08-30): كانت الثقةُ تُشتقّ من **مصدر الرمز** لا
    # من مطابقته — رمزُ كتالوجٍ مُعادٌ يأخذ `None` ابتداءً، وفرعُ المُحلِّل
    # محروسٌ بـ`if not hs_code` فلا يُسأل عنه أصلاً. النتيجة: بوّابةُ الثقة
    # تحجب رمزاً كان المُحلِّلُ نفسُه سيمنحه 1.00. الآن **كلُّ** رمزٍ — كتالوجاً
    # كان أو مكتوباً — يمرّ بـ`silk_hs_pipeline.classify` فيُقاس بالدليل.
    def _hs_candidate_public(cand: dict) -> dict:
        """مرشّحٌ بالشكل الذي تعرضه الواجهة — لا مفتاحَ داخليّ يعبر.

        يوسّع شكلَ `silk_hs_dialog.build_candidates` بما يحتاجه المصنعُ ليقرّر
        (البند ١٧): الوصفُ الرسميّ، ولماذا هو مرشّح، وما يناقضه إن وُجد.
        """
        return {
            "hs6": cand["hs6"],
            "description_ar": cand.get("description") or "",
            "official_description": cand.get("official_description") or "",
            "band_ar": cand.get("band_ar") or "",
            "reason_ar": cand.get("reason_ar") or "",
            "confidence": cand.get("score"),
            "matched_attributes": cand.get("matched_attributes") or [],
            "contradictions": cand.get("contradictions") or [],
        }

    def _hs_classification_summary(contract):
        """ملخّصُ العقد للنتيجة — `None` حين لا عقد (استئنافٌ مثلاً)."""
        if not isinstance(contract, dict) or not contract:
            return None
        import silk_hs_pipeline as _pipe
        return _pipe.result_summary(contract)

    def _classify_product_hs(product, hs_code, req, gl=None):
        """صنِّف/تحقّق قبل أيّ بوّابة — يعيد (رمز، ثقة، عقدُ التصنيف، حجب).

        `حجب` قاموسُ تفاصيل ٤٢٢ حين لا يُحسَم التصنيف، وإلا `None`. الثقةُ
        **رقمٌ دائماً** (البند ٤): لا `None` صامتة تُقرأ لاحقاً «غير معلومة».
        """
        import silk_hs_pipeline as _pipe
        if not str(product or "").strip() and str(hs_code or "").strip():
            # رمزٌ صريحٌ باسمِ منتجٍ فارغ (قرارُ المالك 2026-08-31): كان
            # يسقط في `empty_product` — سببٌ كاذبٌ لطلبٍ فيه رمز. فحصٌ
            # حتميّ على المرجع بدل الرفض باسمِ فراغٍ غير قائم — التفاصيل
            # في `_explicit_code_only_contract`.
            out = _explicit_code_only_contract(hs_code)
        else:
            out = _pipe.classify(
                product, hs_code,
                # تأكيدُ إنسانٍ صريح وحده يعبر — رمزُ الكتالوج لا يُصدَّق
                # لكونه مخزَّناً (البند ٢: `catalog_candidate` حتى يُتحقَّق
                # منه).
                hs_confirmed=bool(getattr(req, "hs_confirmed", False)),
                # رمزٌ كتبه إنسانٌ في هذا الطلب ≠ رمزُ كتالوجٍ مخزَّن (الدرس
                # ١٢٠): الأولُ يُجيب سؤالَ المحور، والثاني يواجه البوّاباتِ
                # كاملة.
                user_supplied=_hs_user_supplied(req),
                # القياسُ يسبق السؤال: بطاقةُ العبوة تحسم العتبةَ الرقمية
                # بلا حوار.
                label_attributes=getattr(req, "label_attributes", None),
                gl=gl,
                # المخرجُ الثالث (قرارُ المالك 2026-08-30): حين يعجز المعجمُ
                # ولا صورة، يُسأل المصنّفُ المُرسى بدل أن يبقى المصنعُ بلا
                # مخرج. الإذنُ رخيصٌ بلا حجز؛ الحجزُ الذرّي داخل
                # `classify_general`.
                allow_claude=_classify_general_allow_claude(),
                ingredients=getattr(req, "ingredients", None),
                category=getattr(req, "category", None))
        # البند ٢٢: لقطةٌ بنيويّة لكل تصنيف. **ليست خطأً** — سجلُّ الأخطاء
        # (`silk_ops_log`) يبقى للرفض وحده كي لا تُغرِق النجاحاتُ إشارتَه؛
        # الرفضُ يُسجَّل عند كل مستدعٍ أدناه بسببه ورمزه.
        try:
            log.info("hs_classification %s", json.dumps(
                _pipe.diagnostics(out), ensure_ascii=False, default=str))
        except Exception as _e:  # noqa: BLE001 — السجلّ قناةٌ جانبية
            log.debug("hs classification diagnostics skipped: %s", _e)
        if out["classification_status"] == _pipe.APPROVED:
            return out["final_hs_code"], float(out["confidence"]), out, None
        # رمزُ الرفض من خطّ التصنيف نفسه — لا خريطةٌ ثانية هنا تتباعد عنه.
        err = out.get("refusal_code")
        block = {
            "error": err or "hs_requires_confirmation",
            # سببُ الرفض الحقيقي (تعادل/محور/تعارض) من فرعه نفسه — الثقةُ
            # تبقى رقماً معروضاً لكنها **ليست السبب**: زوج hs_confidence/
            # min_confidence القديم كان يُقرأ «ثقة 1.00 فوق عتبة 0.80»
            # سبباً لرفضٍ سببُه التعادل، فدرجةُ أعلى مرشّحٍ تُعلَن باسمها.
            "message": out["reason"],
            "hs_code": out["catalog_hs_code"],
            "hs_confidence": float(out["confidence"]),
            "top_candidate_score": float(
                out.get("top_candidate_score") or 0.0),
            "candidates": [_hs_candidate_public(c)
                           for c in out["candidate_codes"] if c.get("offer")],
            "candidates_source": "pipeline",
            "classification": {k: out[k] for k in (
                "classification_status", "classification_method",
                "catalog_hs_status", "normalized_product", "contradictions",
                "requires_user_confirmation", "official_hs_description")},
        }
        return out["final_hs_code"], float(out["confidence"]), out, block

    def _hs_user_supplied(req) -> bool:
        """هل الرمزُ في هذا الطلب **اختيارُ إنسانٍ حاضر** (يستحق اختصار محور
        preflight_block:692) أم رمزٌ مُعادٌ من كتالوج/سجلّ مخزَّن؟

        حادثة الدراسة #10 (حليب/الأردن، 2026-08-24 — direct reproduction):
        جسرُ المنصّة مرّر رمزَ كتالوجٍ قديماً (040110) كأنه إدخالُ مستخدمٍ
        فمرّ اختصارُ «المستخدم سمّى بندَه بنفسه» وبُنيت دراسةٌ كاملة (1.80$)
        على بندٍ لا يطابق المنتج، بينما المُحلِّل يومَها يعيد 040120. الرمزُ
        الكتالوجيّ يواجه البوّابات كاملةً؛ `hs_confirmed=true` (تأكيدُ المصنع
        الصريح لبنده) يبقى المَخرجَ الشرعيّ كما هو."""
        return bool(getattr(req, "hs_code", None)) and (
            (getattr(req, "hs_source", None) or "user") != "catalog")

    def _json(payload: object):
        """رد JSON آمن للـ DataPoint — JSONResponse with DataPoint-safe payload."""
        return JSONResponse(content=_to_jsonable(payload))

    def _view(result: dict) -> dict:
        """القالب الموحّد (§10.1) — attach the canonical view (never crashes)."""
        try:
            from silk_render import build_view
            return build_view(result)
        except Exception as e:  # noqa: BLE001 — العرض لا يُسقط التحليل
            log.warning("view build failed: %s", e)
            return {"error": f"view error: {type(e).__name__}: {e}"}

    def _gmaps_health_status() -> str:
        """C1: حالة مكشطة الخرائط لـ/health — تعطيل نظيف إن غاب المتغيّر."""
        import silk_gmaps
        return silk_gmaps.health_status()

    def _health_verbose_allowed(request: Request) -> bool:
        """R7 (AUTH-18/API-20): مساراتُ المخازن والإصدارُ ونموذجُ كلود تشخيصٌ للمشغّل —
        تُعرَض للعموم في وضع التطوير فقط (بلا `SILK_API_KEY`) أو بمفتاحٍ صالح أو
        بـ`SILK_HEALTH_VERBOSE=1` الصريح."""
        expected = _api_key_expected()
        if not expected or os.environ.get("SILK_HEALTH_VERBOSE", "").strip() == "1":
            return True
        return _key_matches(request.headers.get("x-api-key", ""), expected)

    _HEALTH_APPS.add(app)
    silk_research_runtime.add_tick_hook(_refresh_all_health_snapshots)
    # (اللقطةُ الأولى تُحسَب **بعد** تركيب المنصّة وبذرها — أسفل `create_app`؛ مراجعة R9.)

    def _health_response(request: Request, snap: dict, *, live: bool):
        """يبني الردَّ من لقطة. `live=True` لمسبار `/health`: يطلق تجديداً خلفياً حين تتقادم
        اللقطةُ (لا اعتمادَ على الحاصد وحده) ويُنزل الحالةَ حين يعلق التجديد؛ `/ready`
        يمرّ بلقطةٍ طازجة أصلاً. سببُ الإنذار للمفتاح الصالح وحده (R7/AUTH-18)."""
        out = _health_full(snap["data"])
        age = max(0.0, time.monotonic() - snap["at"])
        out["probe_age_s"] = round(age, 1)
        verbose = _health_verbose_allowed(request)
        if not verbose:
            for _k in ("storage", "version", "ai_model"):
                out.pop(_k, None)
        alarm = _storage_alarm((snap["data"] or {}).get("pstatus"))
        if live:
            hung = _health_refresh_hung(app)
            if hung:
                alarm = alarm or hung
            elif age > _health_max_age_s():
                _kick_health_refresh(app)
        if alarm:
            out["status"] = "degraded"
            if verbose:
                out["storage_alarm"] = alarm
            return JSONResponse(status_code=503, content=_to_jsonable(out))
        return out

    @app.get("/health")
    async def health(request: Request):
        """فحصُ الصحّة — مسبارُ Railway: غيرُ متزامن ويقرأ لقطةً جاهزة (لا قرصَ ولا
        قاعدةَ لكلّ طلب) كي لا يقف خلف مجمّع الخيوط المشبَع؛ الحقولُ البيئية حيّة،
        و`probe_age_s` عمرُ اللقطة. R9 (CONC-3/CI-3)؛ الفحصُ الطازج في `/ready`."""
        return _health_response(request, _health_snapshot(app), live=True)

    @app.get("/ready")
    def ready(request: Request):
        """مسبارُ الجهوزية العميق — فحصٌ طازج للقرص والقاعدة في كلّ نداء (مخنوق بحدّ
        المعدّل)؛ 503 على سوء التهيئة. ليس مسارَ Railway (ذاك `/health`)."""
        _rate_limit(request)
        return _health_response(request, refresh_health_snapshot(app), live=False)

    _slow_s = os.environ.get("SILK_TEST_SLOW_ROUTE_S", "").strip()
    if _slow_s:
        # مراجعة R9: الرفضُ عند التعريف على إشارات إنتاج الجذر نفسِه (مفتاحُ API، مصيدةُ
        # القرص، إشارتا المنصّة) — حارسُ المنصّة وحده لا يغطّي بيئةَ Railway الموثَّقة.
        if (_api_key_expected() or _persist_guard_on()
                or _truthy_env("SILK_PLATFORM_REQUIRE_SECRET")
                or _truthy_env("SILK_PLATFORM_SECURE_COOKIES")):
            raise RuntimeError(
                "SILK_TEST_SLOW_ROUTE_S exposes a deliberately slow test route; refusing to "
                "boot with it set under a production signal.")
        try:
            _slow_seconds = float(_slow_s)
        except ValueError as _exc:
            raise RuntimeError(
                f"SILK_TEST_SLOW_ROUTE_S={_slow_s!r} is not a number of seconds") from _exc

        @app.get("/_test/slow")
        def _test_slow():
            """مسارُ إشباعٍ لرُتبة ٢ فقط (`SILK_TEST_SLOW_ROUTE_S`) — متزامنٌ عمداً
            ليشغل خيطاً من المجمّع؛ يُرفَض الإقلاعُ به تحت أيّ إشارة إنتاج."""
            time.sleep(_slow_seconds)
            return {"slept_s": _slow_seconds}

    def _health_full(probe: dict) -> dict:
        """الحمولةُ الكاملة لفحص الصحّة — من لقطةٍ بطيئة (`_health_probe`) وقراءاتٍ
        بيئية حيّة؛ `_health_response` يحجب حقولَ التشغيل للعموم."""
        health = {"status": "ok", "deps": dict(probe.get("deps") or {})}
        # P5: شفافية المصادر — أي طبقة قوقل/كلود فعّالة الآن ولماذا لا.
        # وجود/غياب فقط، لا قيم مفاتيح ولا نداءات حية (التحقيق العميق في
        # /diagnostics المحروس).
        from silk_websearch_agent import search_key as _sk
        _claude_key = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
        if not _claude_key:
            _claude = "off — ANTHROPIC_API_KEY غير مضبوط"
        elif _unprotected_paid_keys():
            _claude = ("blocked — ANTHROPIC_API_KEY بلا SILK_API_KEY؛ "
                       "اضبط SILK_API_KEY لتفعيل حكم كلود وطبقاته")
        else:
            _claude = "on"
        health["sources"] = {
            "comtrade": ("key" if os.environ.get("COMTRADE_API_KEY", "").strip()
                         else "preview — بلا COMTRADE_API_KEY (حدّ معدل منخفض؛ "
                              "أضِف المفتاح المجاني)"),
            "world_bank": "on — بلا مفتاح",
            "google_trends": "on — pytrends بلا مفتاح (حصة قوقل محدودة)",
            "google_search_serper": ("on" if _sk() else
                                     "off — SEARCH_API_KEY/SERPER_API_KEY غائب"),
            "google_maps": ("on" if os.environ.get(
                "GOOGLE_MAPS_API_KEY", "").strip()
                else "off — GOOGLE_MAPS_API_KEY غائب"),
            # C1 (SPEC-v2): مكشطة الخرائط خدمة Railway ثانية — حالة إخبارية
            # فقط (تعطيل نظيف؛ لا تحجب research_ready ولا تتأثر بها المهام).
            "gmaps_scraper": _gmaps_health_status(),
            "claude": _claude,
        }
        # أيّ نموذج تناديه هذه النشرة فعلاً — طلب المالك: «SILK_AI_MODEL من
        # صدفة Railway». اسم النموذج ليس سرّاً (لا مفتاح ولا قيمة حسّاسة)، وهو
        # لازم للتشخيص عن بُعد: قرار إرسال/إهمال معاملات المعاينة مبنيّ عليه
        # حصراً، فبلا رؤيته يبقى «هل الإصلاح فعّال إنتاجياً؟» تخميناً. القيمة
        # المحلولة (الافتراضية إن كان المتغيّر غير مضبوط)، لا نصّ المتغيّر.
        try:
            import silk_ai_judge as _judge
            import silk_llm_provider as _llm
            health["ai_model"] = {
                "resolved": _judge._MODEL,
                "env_set": bool(os.environ.get("SILK_AI_MODEL", "").strip()),
                "sends_sampling_params":
                    _llm._supports_sampling_params(_judge._MODEL),
                "no_sampling_params_prefixes":
                    list(_llm._no_sampling_params_prefixes()),
            }
        except Exception as _exc:  # noqa: BLE001 — فحص صحّة لا ينهار أبداً
            health["ai_model"] = {"error": f"{type(_exc).__name__}: {_exc}"}
        # جهوزية البحث العميق (/research) — بلاغ حي: كلود شرط تشغيل هناك لا
        # تحسين اختياري؛ حقل صريح هنا كي يتحقق المشغّل قبل أي طلب حي، لا
        # بعد تسليم هيكل فارغ (نفس فحص _research_readiness دون حجز ميزانية).
        # نسخة الشيفرة العاملة — بلا هذا كان السؤال «أي إصدار يعمل عندك؟»
        # يُوجَّه إلى المالك (بلاغ 2026-08-19: صفٌّ اكتمل في ٧٫٢ ث تبيّن أنه
        # أثرُ نسخةٍ سابقة للمسار العميق). Railway يحقن SHA؛ وإلا `git` محلياً؛
        # وإلا None **معلَنة** لا سلسلة مُخترَعة.
        health["version"] = probe.get("version")
        _rr_ready, _rr_reason = _research_readiness(check_cap=False)
        if _rr_ready and probe.get("cap_exhausted"):
            _rr_ready, _rr_reason = False, ("سقف الاستهلاك اليومي (SILK_PAID_DAILY_CAP) "
                                            "مستنفد — أعد المحاولة غداً أو ارفع السقف.")
        health["research_ready"] = _rr_ready
        if not _rr_ready:
            health["research_ready_reason"] = _rr_reason
        # القرص الدائم: المسارات المحلولة فعلاً لكل مخزن — للتحقق بعد النشر أن
        # كل شيء يكتب للقرص (persistent=true عندما يقع المسار تحت SILK_DATA_DIR
        # أو وُجّه بمتغير صريح). Resolved storage paths for volume verification.
        _warnings: list[str] = []
        try:
            import silk_cache as _cache
            import silk_store as _fact_store
            import silk_usage as _usage
            _base = os.environ.get("SILK_DATA_DIR", "").strip()
            _pstatus = probe.get("pstatus")
            if _pstatus is None:
                raise RuntimeError("storage probe unavailable")
            health["storage"] = {
                "data_dir": _base or None,
                "analyses_db": silk_storage._db_path(),
                "fact_store_db": _fact_store._db_path(),
                "usage_db": _usage._db_path(),
                "cache_dir": _cache._cache_dir(),
                # المخزن الخامس (منصّة المستأجرين/المصادقة/المحافظ) — بلا كشفه
                # لا يستطيع المالك التحقّق بعد النشر أن بيانات المستأجرين نزلت
                # على الوحدة المركَّبة لا على قرص الحاوية الفاني.
                # Fifth store: tenant/auth/wallet DB must be verifiable remotely.
                "platform_db": _platform_db_path(),
                # جهوزيّة المنصّة: جداولٌ سليمة و**صفر مستخدمين** كانت تجعل كل
                # دخول يُرفَض برسالة «بيانات غير صحيحة» لا تُميَّز عن كلمة مرور
                # خاطئة، فيستحيل التشخيص عن بُعد (بلاغ مالك حيّ: «ما يعمل»).
                # أعدادٌ فقط — بلا بريد ولا كلمة مرور؛ `/health` عامّة.
                # Tables-but-no-users was undiagnosable remotely: counts only.
                "platform_ready": probe.get("platform_ready"),
                # PART E (أمر العمل الرئيس): حالة مصيدة الإقلاع مرئية من
                # /health — كانت غير قابلة للتفتيش عن بُعد فلا يعرف المالك
                # إن كان صمّام «رفض الإقلاع على قرص فانٍ» مفعّلاً فعلاً.
                "persist_guard": _persist_guard_on(),
                # بلاغ المالك الحيّ: «المتغيّر مضبوط» لا يكفي — نكشف الحالة
                # الفعلية (قرص مركّب + قابل للكتابة) كي يرى المالك عن بُعد إن
                # كانت وحدة التخزين مركّبة حقًّا على مسار SILK_DATA_DIR.
                "is_mount": _pstatus["is_mount"],
                "writable": _pstatus["writable"],
                "mountpoint": _pstatus["mountpoint"],
            }
            # بلاغ حي (تدقيق تكلفة): تحليلات مكتملة مدفوعة الثمن كانت تختفي
            # بعد كل إعادة نشر — SILK_DATA_DIR فارغ يعني كل الأربعة مخازن
            # تقع تحت المسار النسبي الافتراضي داخل حاوية Railway الفانية (لا
            # وحدة تخزين ثابتة)، فتُمحى كل البيانات عند كل نشرة تالية. كان
            # هذا خطراً صامتاً (data_dir: null بلا أي تحذير مرئي) — الآن
            # تحذير صريح لا يفوّت مشغّلاً يفحص /health.
            if not (_base or os.environ.get("SILK_DB", "").strip()):
                _warnings.append(
                    "SILK_DATA_DIR غير مضبوط — التخزين على مسار نسبي داخل "
                    "حاوية Railway الفانية؛ كل التحليلات (والمخزن/الاستخدام/"
                    "الذاكرة المؤقتة) ستُفقَد عند إعادة النشر التالية ما لم "
                    "تُركَّب وحدة تخزين (Volume) وتُوجَّه إليها هذا المتغيّر")
            # بلاغ المالك الحيّ: المتغيّر مضبوط لكن لا وحدة مركّبة على مساره —
            # الكتابة على جذر الحاوية الفاني فتُمحى عند كل دبلوي رغم ضبط
            # المتغيّر. تحذير صريح حتى دون تفعيل مصيدة الإقلاع.
            elif _pstatus["configured"] and not _pstatus["is_mount"]:
                _warnings.append(
                    f"مسار التخزين '{_pstatus['path']}' مضبوط لكن ليس وحدة "
                    f"تخزين مركّبة (أقرب نقطة تركيب '{_pstatus['mountpoint']}' = "
                    "جذر الحاوية الفاني) — كل البيانات ستُمحى عند إعادة النشر. "
                    "اجعل Mount Path لوحدة Railway يساوي هذا المسار تمامًا")
        except Exception as _e:  # noqa: BLE001 — تشخيص لا شرط
            log.debug("storage health section skipped: %s", _e)
        # اللائحة ٤٣ (بلاغ حي متكرّر — رمز HS خاطئ رغم إصلاح المُصنِّف العام):
        # صمّام `SILK_HS_CLASSIFIER` نفسه لم يكن قابلاً للتفتيش عن بُعد، فلا
        # يعرف المالك أن الإصلاح المدموج فعلياً لا يعمل على النشر الفعلي —
        # نفس عائلة `persist_guard` أعلاه (سطح مراقبة، لا تخمين). فشل-آمنٌ
        # افتراضياً الآن، لكن يبقى قابلاً للتعطيل الصريح؛ هذا الحقل يُظهر
        # الحالة الفعلية الحيّة بدل انتظار بلاغٍ حيٍّ آخر لاكتشافها.
        try:
            import silk_hs_classifier as _hsc
            _hs_enabled = _hsc.enabled()
            health["hs_classifier"] = {"enabled": _hs_enabled}
            if not _hs_enabled and _claude_key:
                _warnings.append(
                    "SILK_HS_CLASSIFIER مُعطَّل صراحةً — المُصنِّف العام "
                    "(تصنيف HS الدقيق لمنتجات متعدّدة الصفات) لن يستدعي "
                    "كلود؛ يعتمد على جدول بحثٍ جزئي وحده وقد يُخطئ الفصل "
                    "(نفس عائلة بلاغ «زبدة الفول السوداني»)")
        except Exception as _e:  # noqa: BLE001 — تشخيص لا شرط
            log.debug("hs_classifier health section skipped: %s", _e)
        unprotected = _unprotected_paid_keys()
        if unprotected:
            _warnings.append(
                "paid keys present without SILK_API_KEY ("
                + ", ".join(unprotected)
                + ") — paid layers will refuse with 503 until SILK_API_KEY "
                  "is set (or the paid keys are removed)")
        if _warnings:
            health["warnings"] = _warnings
        return health

    @app.get("/resolve/{name}")
    def resolve(name: str, request: Request):
        """صنّف اسم منتج إلى HS6 — resolve a product name to an HS6 DataPoint."""
        _rate_limit(request)   # قراءة رخيصة لكنها ليست مجانية بلا حدود
        dp = silk_hs_resolver.resolve(name)
        return _json({"hs_code": dp.value, "confidence": dp.confidence,
                      "note": dp.note, "source": dp.source,
                      "retrieved_at": dp.retrieved_at})

    @app.get("/config")
    def config(request: Request):
        """أعلامُ الميزات العلنية للواجهة — public feature flags (لا أسرار).

        الواجهة تقرؤها مرّة عند الإقلاع لتفعيل تبويبات الصورة (الميزة ب) —
        القيَم أعلامٌ بيئية علنية لا مفاتيح، فآمنٌ كشفها بلا مصادقة."""
        _rate_limit(request)
        import silk_product_intake as intake
        import silk_hs_classifier as hsc
        from silk_market_ranker import _world_markets_enabled
        # أعلام Wave 1 العلنية — الواجهة تُفعّل خطوة التصنيف/الاستشارة بحسبها.
        return _json({"image_intake": intake.enabled(),
                      "hs_image_attributes": __import__("silk_hs_attributes").enabled(),
                      "world_markets": _world_markets_enabled(),
                      "hs_classifier": hsc.enabled(),
                      "producer_advisory": _producer_advisory_enabled(),
                      "require_hs6": _require_hs6(),
                      "prerun_advisories": __import__(
                          "silk_prerun").advisories_enabled()})

    def _intake_vision_allowed() -> tuple[bool, str]:
        """هل يُسمح نداء الرؤية الواحد؟ — (allowed, reason). يعكس منطق
        `_free_ai_extras_allowed`: نداء الرؤية مقيسٌ كأيّ نداء مدفوع (حجز
        تفعيلة واحدة ذرّياً من SILK_PAID_DAILY_CAP). الرفض يتدهور بصدق إلى
        «تعذّرت القراءة» — لا اختلاق منتج، ولا 429 على مسار مجاني أصلاً.

        بلا مفتاح كلود => لا رؤية ممكنة (تعذّر قراءة صادق، لا اختلاق). مفتاحٌ
        مدفوع بلا SILK_API_KEY => محجوب (حارس 503) بلا إنفاق. سقفٌ مستنفد =>
        محجوب. غير ذلك => تُحجَز تفعيلة واحدة قبل النداء."""
        # EXT-13: الحارسُ الواحد في `silk_usage.vision_allowed` (نفسُ الشروط حرفياً).
        return silk_usage.vision_allowed()

    @app.post("/products/intake")
    def products_intake(req: IntakeRequest, request: Request):
        """استقبال منتج متعدّد الوسائط — اسمٌ مكتوب أو صورة منتج/بطاقة مكوّنات.

        محوّلٌ أماميّ (الميزة ب): يُعيد اسماً مؤكَّداً/قابلاً للتعديل **بلا بدء
        تحليل**. مسار الصورة = نداء رؤية واحد مقيس؛ ثقةٌ منخفضة/غير مقروءة =>
        «تعذّرت القراءة — اكتب الاسم يدوياً» (لا اختلاق). الاسم المؤكَّد يدخل
        بعده `/resolve → /analyze|/research` القائم بلا تغيير.
        """
        _require_key(request)
        _rate_limit(request)
        import silk_product_intake as intake
        if not intake.enabled():
            raise HTTPException(status_code=404, detail={
                "error": "image_intake_disabled",
                "reason": "استقبال الصور مُعطَّل — اضبط SILK_IMAGE_INTAKE=1."})
        # مسار الاسم المكتوب: لا نداء كلود، لا حجز.
        if req.name and not req.image_base64:
            return _json(intake.intake_name(req.name))
        if not req.image_base64:
            raise HTTPException(status_code=422, detail={
                "error": "name_or_image_required",
                "reason": "مرّر name أو image_base64."})
        # مسار الصورة: تحقّق الحجم/النوع أولاً (لا حجز على إدخالٍ باطل)، ثم
        # احجز تفعيلة الرؤية الواحدة. الحجز يقع فقط حين نعتزم النداء فعلاً.
        raw, why = intake._decode_and_check(req.image_base64, req.media_type)
        if raw is None:
            return _json(intake.intake_image(req.image_base64, req.media_type,
                                             req.kind))
        allow, reason = _intake_vision_allowed()
        # البند #6 (تدقيق v2 الموجة ٢): نداء الرؤية كان مقيساً بالعدّاد فقط
        # (SILK_PAID_DAILY_CAP) لا بالدولار — يجري خارج أيّ `begin_data_counter`
        # فتُهمَل رموزه (`_record_usage` صامت)، فلا يظهر إنفاقه في السقف الدولاري
        # ولا في `?economics`. نفتح عدّاداً حول النداء، ثم نسجّل الكلفة الفعلية
        # في دفتر اليوم الدولاري (record_usd) — فيُحتسَب ضمن الحدّ اليومي المشترك
        # الذي يقرؤه /research، ويُصبح مرئياً. لا حجز مسبق (النداء الواحد الصغير
        # محكومٌ أصلاً بالعدّاد؛ التسجيل البعدي يجعله مرئياً/محسوباً بلا اختلاق).
        import silk_context
        if allow:
            silk_context.begin_data_counter()
        out = intake.intake_image(
            req.image_base64, req.media_type, req.kind,
            allow_vision=allow, blocked_reason=reason)
        if allow:
            try:
                from silk_pricing import estimate_cost_usd
                _c = silk_context.data_counter() or {}
                _cost = estimate_cost_usd(_c.get("llm_usage"))
                if _cost.get("total_usd"):
                    silk_usage.record_usd(_cost["total_usd"])
            except Exception as _e:  # noqa: BLE001 — القياس قناة جانبية لا تُسقط الردّ
                log.warning("intake vision cost metering failed: %s", _e)
        return _json(out)

    def _classify_general_allow_claude() -> bool:
        """هل نداءُ التصنيف العام (`silk_hs_classifier.classify_general`)
        مسموحٌ نظرياً؟ — فحصٌ رخيصٌ **بلا حجز**: يُستدعى على **كل** طلبٍ ذي
        رمزٍ مُعلَّم عند `preflight_block`، فحجزٌ هنا يُهدر تفعيلةً حتى حين
        يكفي المُحلِّل الحتمي (بذرة CSV) أو ذاكرة المنتج بلا أيّ نداء فعلي.
        الحجزُ الذرّي الحقيقي (count + dollar) يعيش **داخل**
        `silk_hs_classifier._reserve_llm_call` — نقطة اختناقٍ واحدة يستدعيها
        `classify_general` سواءً من `/classify_hs` أو من `preflight_block`
        (كلا مساري `/analyze`/`/research`)، فيُستدعى فقط حين يثبت فعلاً أن
        نداءً حياً لا مفرّ منه — لا ازدواج حجزٍ بين نقطتَي نهاية."""
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()) \
            and not _unprotected_paid_keys()

    @app.post("/classify_hs")
    def classify_hs(req: ClassifyRequest, request: Request):
        """صنّف منتجًا إلى HS6 — the general-purpose HS classifier step
        (الموجة ٣، systemic fix). لا يبدأ أيّ تحليل ولا يحجز ميزانيةَ بحث —
        الاقتراح فقط، لكنه **نفس عقد `classify_general`** الذي تستدعيه بوّابة
        `preflight_block` وقت الإرسال — نقطة اختناقٍ منطقية واحدة، لا نسخة
        مسبَقة أضيق تعطي نتيجةً مختلفة عمّا يراه المستخدم لاحقاً عند الحجب.

        الحجزُ الذرّي (count + dollar) يعيش الآن **داخل** `classify_general`
        نفسها (`_reserve_llm_call`) — لا حجزٌ استكشافيٌّ هنا؛ يُستدعى فقط حين
        يثبت فعلاً أن نداءً حياً لا مفرّ منه (لا إصابة ذاكرة ولا مُحلِّل حتمي
        كافٍ)."""
        _require_key(request)
        _rate_limit(request)
        import silk_hs_classifier as hsc
        product = (req.product or "").strip()
        if not product:
            raise HTTPException(status_code=422, detail={
                "error": "product_required", "reason": "مرّر اسم منتج."})
        out = hsc.classify_general(
            product, ingredients=req.ingredients, category=req.category,
            allow_claude=_classify_general_allow_claude())
        return _json(out)

    @app.get("/index")
    def index(request: Request, q: str = "", limit: int = 20):
        """فهرس المنتجات للبحث — product search index for the dashboard combobox.

        limit مُقيَّد إلى [1..100] (M0): قيمة ضخمة/سالبة لا تُمرَّر للبحث كما هي.
        """
        _rate_limit(request)
        return _json(_index_search(q, max(1, min(int(limit), 100))))

    @app.get("/markets")
    def markets_reference(request: Request):
        """مرجع الأسواق المرشَّحة — the candidate-market list for the target
        picker: {iso3, m49, name}. Same reference `rank_markets()` scores
        against — يُبنى مرة واحدة، لا نداء شبكة، ثابت لكل التشغيلات.
        """
        _rate_limit(request)
        from silk_market_ranker import (
            COUNTRIES, TIER2_LABEL, _world_markets_enabled)
        from silk_data_layer import partner_name
        from silk_narrative import COUNTRY_AR
        # P3 (بلاغ المالك): الاسم العربي إلى جانب الإنجليزي — الواجهة تعرض
        # العربية في وضعها العربي بدل أسماء إنجليزية خام.
        out = [{"iso3": c["iso3"], "m49": c["m49"],
                "name": partner_name(c["m49"]),
                "name_ar": COUNTRY_AR.get(c["iso3"], partner_name(c["m49"])),
                "tier": 1}
               for c in COUNTRIES]
        # تغطية العالم (SILK_WORLD_MARKETS): أضِف بقية دول العالم كفئة-٢ موسومة
        # «تغطية أساسية» ليجمعها منسدل الواجهة تحت «كل دول العالم». مُطفأ افتراضياً
        # => الرد نفسه حرفياً كاليوم (تغطية-١ فقط، بلا حقل tier مؤثِّر على العرض).
        if _world_markets_enabled():
            from silk_market_resolver import _load as _load_countries
            seen = {c["iso3"] for c in COUNTRIES}
            for row in _load_countries():
                iso3 = (row.get("iso3") or "").strip()
                if len(iso3) != 3 or iso3 in seen:
                    continue
                seen.add(iso3)
                out.append({
                    "iso3": iso3, "m49": row.get("m49", ""),
                    "name": row.get("name_en") or iso3,
                    "name_ar": row.get("name_ar") or row.get("name_en") or iso3,
                    "tier": 2, "coverage": TIER2_LABEL})
        return _json(out)

    def _require_key(request: Request) -> None:
        """حارس المصادقة — 401 when the key mismatches, constant-time (L-1).

        يُطبَّق على مسارات القراءة الحسّاسة أيضاً (C-1): التحليلات المحفوظة
        تحمل بطاقة المنتج الاقتصادية، ومعرّفاتها متسلسلة — بلا هذا الحارس
        يقرؤها أي مجهول بالتعداد. المقارنة عبر hmac.compare_digest لتفادي
        تسريب التوقيت. غير مضبوط SILK_API_KEY => وضع تطوير مفتوح (لا انحدار).
        """
        expected = _api_key_expected()
        if not expected:
            return
        got = request.headers.get("x-api-key", "")
        if not _key_matches(got, expected):          # constant-time (L-1)، آمنٌ للمدخلات
            raise HTTPException(status_code=401,
                                detail="missing or invalid API key "
                                       "(send X-API-Key header)")

    # تحديد معدّل بسيط بالذاكرة (M-1) — in-memory fixed-window rate limit.
    # نافذة ثابتة لكل هوية (X-API-Key إن وُجد وإلا IP)؛ التجاوز = 429.
    # يكفي أداةً داخلية (لا Redis)؛ الحالة لكل نسخة تطبيق (تُعاد تهيئتها في
    # الاختبارات). SILK_RATE_LIMIT=0 يعطّله؛ الافتراضي 120 طلباً/60 ثانية.
    _rl_max = int(os.environ.get("SILK_RATE_LIMIT", "120") or "120")
    _rl_window = max(1, int(os.environ.get("SILK_RATE_WINDOW", "60") or "60"))
    _rl_lock = threading.Lock()
    _rl_hits: dict[str, tuple[int, int]] = {}

    def _rate_limit(request: Request) -> None:
        """حدّ المعدّل — raise 429 when a client exceeds the window budget."""
        if _rl_max <= 0:
            return
        # R7 (API-7/RC-4): مفتاحٌ **مُتحقَّقٌ منه** فقط ينال دلوَه؛ كلُّ قيمةٍ مزوَّرة
        # كانت تنال دلواً جديداً فيُلغى الحدُّ بتدوير الترويسة.
        _got = request.headers.get("x-api-key") or ""
        _exp = _api_key_expected()
        if _key_matches(_got, _exp):
            ident = "key:" + hashlib.sha256(_got.encode("utf-8")).hexdigest()[:16]
        else:
            ident = "ip:" + (request.client.host if request.client else "anon")
        win = int(time.time()) // _rl_window
        with _rl_lock:
            w, c = _rl_hits.get(ident, (win, 0))
            if w != win:
                w, c = win, 0
            c += 1
            _rl_hits[ident] = (w, c)
            if len(_rl_hits) > 4096:
                # سدّ النمو بلا تصفير شامل (مراجعة المشروع): .clear() كان
                # يمحو نوافذ كل العملاء، فيستطيع مهاجم إرسال 4096 هوية
                # زائفة ليصفّر عدّاده هو. الآن: تُقلَّم النوافذ المنتهية
                # فقط؛ وإن بقي الفيض (هجوم هويات في نافذة واحدة) تُطرد
                # هويات أخرى — عدّاد الهوية الحالية لا يُمسّ أبداً.
                stale = [k for k, (w0, _c0) in _rl_hits.items() if w0 != win]
                for k in stale:
                    del _rl_hits[k]
                if len(_rl_hits) > 4096:
                    for k in list(_rl_hits):
                        if k != ident:
                            del _rl_hits[k]
                        if len(_rl_hits) <= 4096:
                            break
        if c > _rl_max:
            raise HTTPException(
                status_code=429,
                detail=f"rate limit exceeded ({_rl_max}/{_rl_window}s) — "
                       "slow down or raise SILK_RATE_LIMIT")

    def _guard_paid(req) -> None:
        """حارسا المدفوع — 503 لمفاتيح غير محمية، ثم 429 للسقف، ثم التسجيل."""
        paid_requested = sum(1 for f in _PAID_FLAGS if getattr(req, f, False))
        if paid_requested:
            unprotected = _unprotected_paid_keys()
            if unprotected:
                raise HTTPException(
                    status_code=503,
                    detail="paid provider keys are set ("
                           + ", ".join(unprotected)
                           + ") but SILK_API_KEY is not — refusing to run "
                             "paid layers unauthenticated. Set SILK_API_KEY "
                             "(and send X-API-Key) or unset the paid keys.")
        # فحص السقف والتسجيل في معاملة ذرّية واحدة — لا نافذة سباق بين
        # القراءة والكتابة (طلبان متزامنان لا يتجاوزان السقف معًا).
        # Atomic check-and-reserve: no TOCTOU window between read and write.
        if paid_requested and not silk_usage.try_reserve_paid_calls(
                paid_requested):
            # ITEM 5ب: رفض حجز بحالة السقف — نص خادمي بحت، لا محتوى كلود.
            import silk_ops_log
            silk_ops_log.record_error(
                "reservation_refused",
                "بلغ سقف التفعيلات المدفوعة اليومي (SILK_PAID_DAILY_CAP)",
                context={"requested": paid_requested,
                        "today_activations": silk_usage.paid_calls_today()})
            raise HTTPException(
                status_code=429,
                detail="daily paid-layer cap reached (SILK_PAID_DAILY_CAP) — "
                       "retry tomorrow or raise the cap")

    def _source_policy() -> dict:
        """سياسة المصادر الخادمية (Stage 2A) — server decides, never UI flags.

        القاعدة الصلبة: كل مصدر مجاني بلا مفتاح يُحاول دائماً؛ والمفتاحيّ المجاني
        يُحاول متى وُجد مفتاحه في بيئة الخادم. أعلام العميل لا تُعطّل مصدراً —
        كانت البوابة المشتقة من لوحة مفاتيح المتصفح سببَ إظلام 8/12 مصدراً
        (docs/SOURCE_AUDIT.md). المدفوع يبقى بنيوياً في /deepen فقط.

        قرار المالك (مراجعة التشغيل الحي، 2026-07-06): with_competitors/
        with_channels/with_importers (الموجة ٣) عُطِّلت هنا نهائياً — صارت
        زائدة عن حاجتها بعد `with_research` (المرحلة ٣، §4b): CompetitorAgent
        وSupplierAgent يبحثان نفس السؤال (منافسون/موزّعون بالاسم) عبر
        Serper/Maps، فتضاعف الاستهلاك بلا فائدة وتكرّر نفس المحتوى في قسمين
        مختلفين من التقرير الواحد (وquotas Serper/Trends محدودة — لاحظنا
        429 من Google Trends في التشغيل الحي). الوكيلان القائمان (silk_
        competitors_agent.py، silk_channels_agent.py، silk_importers_agent.py)
        يبقيان دون حذف — silk_engine.analyze لا يزال يقبل هذه الأعلام
        مباشرة (اختبارات test_wave3_agents.py)، فقط سياسة الخادم توقفت عن
        تفعيلها تلقائياً.
        """
        return {
            "with_trends": True, "with_tariffs": True, "with_faostat": True,
            "with_requirements": True, "with_trend": True,
            "with_competitors": False, "with_channels": False,
            "with_importers": False, "with_risk": True, "with_research": True,
            "with_dynamics": True,
            "with_websearch": bool(__import__("silk_websearch_agent")
                                   .search_available()),
            "with_maps": bool(os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()),
        }

    def _free_ai_extras_allowed() -> tuple[bool, str]:
        """هل تُسمح إضافات كلود على المسار المجاني؟ — (allowed, reason).

        **الموجة B (البند G-05):** السياسةُ نفسُها انتقلت إلى
        `silk_usage.free_ai_extras_allowed` — الوحدةِ التي تملك السقفَ
        اليوميّ والحجزَ أصلاً — كي يستهلكها سطحُ المصنع أيضاً بدل أن ينسخها
        (وقد كان ينسخها فعلاً، موثِّقاً السبب: «closure لا يُستورد»).
        السلوك لم يتغيّر حرفاً: لا مفتاح ⇒ سماحٌ بلا إنفاق؛ نشرٌ غيرُ محميّ
        ⇒ حجب؛ وإلا حجزٌ ذرّيٌّ واحد من نفس العدّاد. الرفضُ يتدهور بملاحظةٍ
        معلنة — لا 429 لمسارٍ مجانيٍّ في أصله.
        """
        return silk_usage.free_ai_extras_allowed()

    def _research_readiness(check_cap: bool = True) -> tuple[bool, str]:
        """جهوزية البحث العميق — (ready, reason). فحص قراءة بلا حجز (M-2 نمط
        would_exceed_cap، لا try_reserve_paid_calls) — الحجز الذرّي الفعلي
        يبقى في _free_ai_extras_allowed أثناء التنفيذ؛ هذا فحص مسبق رخيص.

        بلاغ حي (أول تشغيلة إنتاجية): /research بلا كلود ينتج هيكلاً فارغاً
        لا تقريراً — الاثنتا عشرة بعثة + المحلل + التوليف مرحلة ٢ + الكاتب/
        المراجع كلها نداءات كلود، خلافاً لـ/analyze حيث كلود تحسين اختياري.
        الفرق: هنا كلود **شرط تشغيل**، فيُرفض غيابه صراحة (409) قبل تشغيل
        أي بعثة — لا يُسلَّم هيكل فارغ كأنه المنتج. `allow_degraded=true`
        فتحة هروب صريحة تطلبها الجهة المستهلكة، لا تدهوراً افتراضياً.
        """
        import silk_ai_judge
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            return False, ("ANTHROPIC_API_KEY غير مضبوط — البحث العميق "
                           "يتطلب كلود لكل الاثنتي عشرة بعثة والمحلل "
                           "والكاتب؛ بلا مفتاح لا تقرير حقيقي ممكن.")
        unprotected = _unprotected_paid_keys()
        if unprotected:
            return False, ("ANTHROPIC_API_KEY مضبوط بلا SILK_API_KEY — "
                           "طبقة كلود محجوبة (حارس 503) حتى تُضبط "
                           "SILK_API_KEY في بيئة النشر.")
        if not silk_ai_judge.available():
            return False, ("طبقة كلود محجوبة سياقياً (block_ai_extras) في "
                           "هذا الطلب — راجع سياق التشغيل الحالي.")
        if check_cap and silk_usage.would_exceed_cap(1):
            return False, ("سقف الاستهلاك اليومي (SILK_PAID_DAILY_CAP) "
                           "مستنفد — أعد المحاولة غداً أو ارفع السقف.")
        return True, ""

    def _research_ambiguity_gate_enabled() -> bool:
        """بوّابةُ الالتباس على `/research` (`SILK_RESEARCH_AMBIGUITY_GATE`).

        مفعّلةٌ افتراضياً (فشل-آمن، كبقية بوّابات HS): سؤالٌ واحدٌ قبل تشغيلةٍ
        تكلّف دولاراتٍ أرخص من تقريرٍ كاملٍ على رمزٍ خاطئ. تُطفأ صراحةً."""
        raw = os.environ.get("SILK_RESEARCH_AMBIGUITY_GATE", "").strip().lower()
        return raw not in ("0", "false", "no", "off")

    def _require_hs6() -> bool:
        """صمّام البوّابة الصلبة (Wave 1) — SILK_REQUIRE_HS6=1 يرفض بدءَ /research
        برمز HS فارغ (422). افتراضيًا مُطفأ => السلوك كاليوم (تُقبَل فجوة معلنة)."""
        return os.environ.get("SILK_REQUIRE_HS6", "0").strip() == "1"

    def _producer_advisory_enabled() -> bool:
        """صمّام استشارة بلد المنشأ (Wave 1) — SILK_PRODUCER_ADVISORY=1 يفعّل
        تحذيرَ «سوق منتِجة» (422 حتى موافقة). افتراضيًا مُطفأ => السلوك كاليوم."""
        return os.environ.get("SILK_PRODUCER_ADVISORY", "0").strip() == "1"

    def _market_in_coverage(hs_code, iso3: str) -> tuple[bool, bool]:
        """هل السوق ضمن التغطية لهذا الرمز؟ — (covered, determinable).

        اتفاق المالك: التغطية = Tier-1 المنسّقة **أو** الظهور ضمن مجموعة أكبر
        مستوردي هذا الرمز (Tier-1+Tier-2 الديناميكية من نداء العالم الواحد).
        سوقٌ خارجها => لا دراسة هزيلة بل رسالة صادقة. تعذّر تحديد المجموعة (بلا
        رمز/ميزانية كومتريد منفدة/شبكة) => (True, False): نفتح البوّابة (يعمل
        كاليوم، فجوات معلنة) بدل حجب سوقٍ مشروع على عطلٍ عابر — فشلٌ آمن.
        """
        from silk_market_ranker import (COUNTRIES, world_import_totals_resolved,
                                        _TIER1_N, _TIER2_MAX)
        if iso3 in {c["iso3"] for c in COUNTRIES}:
            return True, True               # Tier-1 منسّقة — مغطّاة دائماً
        if not hs_code:
            return True, False              # لا رمز => لا يمكن حساب المجموعة
        # تدقيق v2 (الموجة ١): استطلاع بسُلَّم fallback (سنة-١ → سنة-٢ → سنة-٣ →
        # سنة الدراسة الافتراضية) بدل سنة اليوم-١ وحدها — كومتريد يتأخّر فكانت
        # ٢٠٢٥ تعود فارغةً دوماً فتفشل البوّابة مفتوحةً (لا تُغلَق أبداً). الآن تشترك
        # البوّابة والدراسة في **أساس مستوردين واحد** (نفس السُّلَّم، نفس السنة).
        try:
            totals, _yr = world_import_totals_resolved(hs_code)
        except Exception as e:  # noqa: BLE001 — عطل قياس لا يحجب سوقاً
            log.warning("coverage probe failed: %s", e)
            totals = []
        if not totals:
            return True, False              # تعذّر التحديد => فتح البوّابة (آمن)
        covered = {t["iso3"] for t in totals[:_TIER1_N + _TIER2_MAX]}
        return iso3 in covered, True

    @app.post("/analyze")
    def analyze(req: AnalyzeRequest, request: Request):
        """حلّل منتجًا عبر الأسواق (المسار العادي، مجاني حصراً) — free-only path.

        الموجة ٢: لا حقول مدفوعة في النموذج أصلاً — الحصر بنيوي. التعميق عبر
        POST /deepen. Stage 2A: طبقات المصادر تُقرَّر بسياسة الخادم حصراً
        (_source_policy) — علم العميل لا يستطيع إطفاء مصدر مجاني.
        """
        _require_key(request)
        _rate_limit(request)
        # بوّابة تأكيد رمز HS (الموجة ٢، تدقيق المُشرِف 2026-07-21 — نفس
        # نقطة الاختناق المشتركة `silk_hs_confirm.preflight_block` التي
        # يستدعيها `/research`؛ إصلاحٌ سابقٌ اقتصر على `/research` وحده
        # فعاود الظهور — «إصلاحٌ على مسارٍ واحد نصفُ إصلاح» — LESSONS ٣٦).
        # رمزٌ صريح يُفحَص كما هو؛ رمزٌ غائب يُحسَم حتميّاً (بلا نداء كلود،
        # نفس مُحلِّل `/research`) قبل أيّ عملٍ فعليّ. تُتخطّى بتأكيد المستخدم
        # الصريح (hs_confirmed=True) — لا يُنفَق زمن/ميزانية كومتريد على
        # فئة مجاورة خاطئة دلالياً.
        # نفسُ نقطة الاختناق التي يستدعيها `/research` — إصلاحٌ على مسارٍ
        # واحد نصفُ إصلاح (الدرسان ٣٥/٣٧). كان هذا المسارُ يستدعي المُحلِّلَ
        # المجرّد ويُهمِل الثقةَ تماماً، فبوّابةُ الثقة لا تعمل عليه إطلاقاً.
        _analyze_hs_code, _analyze_conf, _analyze_cls, _analyze_block = \
            _classify_product_hs(req.product, req.hs_code, req)
        if _analyze_block is not None:
            import silk_ops_log
            silk_ops_log.record_error(
                _analyze_block["error"],
                f"لم يُحسَم البند الجمركي لمنتج {req.product!r}: "
                f"{_analyze_block['message']}",
                context={"product": req.product,
                         "hs_code": _analyze_block.get("hs_code"),
                         "hs_confidence": _analyze_block.get("hs_confidence"),
                         "top_candidate_score":
                             _analyze_block.get("top_candidate_score")})
            raise HTTPException(status_code=422, detail=_analyze_block)
        # بلاغ المُشرِف («حليب نادك كامل الدسم؟»): البنودُ داخل الترويسة
        # الواحدة تتمايز بعتبةٍ رقمية — تُقاس قبل أن يُسأل المستخدم عنها
        # (`silk_hs_confirm.preflight_resolve`: بطاقةُ العبوة ثم استعلامُ
        # ويبٍ واحد). حُسِمت => يُستعمَل الرمزُ المقيس ويُوسَم بمصدره؛ لم
        # تُحسَم => نفسُ الـ٤٢٢ السابق مضافاً إليه `attribute_probe`.
        from silk_hs_confirm import preflight_resolve
        _analyze_hs_code, _hs_prov, _blocked = preflight_resolve(
            req.product, _analyze_hs_code,
            # اعتمادُ «رمزٌ صريحٌ باسمٍ فارغ» يُكرَّم كما يُكرَّم تأكيدُ
            # المصنع الصريح — لا اسمَ أصلاً تُعيد البوّابةُ قياسَه عليه.
            req.hs_confirmed or _hs_explicitly_settled(_analyze_cls),
            allow_claude=_classify_general_allow_claude(),
            # الثقةُ المقيسة تُمرَّر — كانت تُحسَب هنا ثمّ **تُرمى**، فتبقى
            # بوّابةُ الثقة على هذا المسار مُعطَّلةً (`_UNSET`) بينما تعمل على
            # `/research`. وهو بعينه نمطُ «حُسِبت ثمّ أُهمِلت» الذي كُتبت هذه
            # الموجةُ لإغلاقه — التقطته المراجعةُ الذاتية (اللائحة ٥٨).
            hs_confidence=_analyze_conf,
            label_attributes=req.label_attributes,
            # المهمة ١٤: العقدُ المحسوم للتوّ يُمرَّر — البوّابةُ تؤدّي
            # ما تملكه وحدَها ولا تعيد تشغيل الآلة التصنيفية كاملة.
            settled_contract=_analyze_cls,
            # رمزٌ كتبه المستخدم في الطلب: إن كان أحدَ مرشّحي المحور فهو
            # إجابةُ السؤال لا سببٌ لإعادة طرحه، ولا يُستبدَل بمجسٍّ صامتاً.
            # رمزُ كتالوجٍ مُعاد (hs_source="catalog") ليس تلك الإجابة —
            # حادثة الدراسة #10.
            user_supplied=_hs_user_supplied(req))
        if _blocked is not None:
            import silk_ops_log
            silk_ops_log.record_error(
                "hs_confirmation_blocked",
                f"رُفض بدءُ تحليلٍ برمز HS غير مؤكَّد لمنتج {req.product!r}: "
                f"{_blocked['hs_confirmation'].get('reason')}",
                context={"product": req.product, "hs_code": _analyze_hs_code,
                         "attribute_probe": _blocked.get("attribute_probe"),
                         "missing_terms":
                             _blocked["hs_confirmation"].get("missing_terms")})
            raise HTTPException(status_code=422, detail=_blocked)
        if _hs_prov is not None:
            import silk_ops_log
            silk_ops_log.record_error(
                "hs_auto_resolved",
                f"حُسِم رمزُ HS آلياً لمنتج {req.product!r} => "
                f"{_analyze_hs_code} ({_hs_prov.get('resolved_from')})",
                context={"product": req.product, "hs_code": _analyze_hs_code,
                         "resolved_from": _hs_prov.get("resolved_from"),
                         "value": _hs_prov.get("value"),
                         "source_url": _hs_prov.get("source_url")})
        policy = _source_policy()
        ai_ok, ai_note = _free_ai_extras_allowed()
        # P5 (بلاغ المالك: «كلود العادي يتفوق على المنصة»): حكم كلود
        # (المرحلة ٢ من التوليف) وتقريره يعملان على المسار الرئيسي متى كان
        # المفتاح مضبوطاً ومحمياً — نفس بوابة H2 ونفس الحجز من السقف؛ لا
        # مسار حكم موازٍ (التوليف يبقى نقطة الدخول الوحيدة، §9.3).
        policy["with_ai"] = ai_ok and bool(
            os.environ.get("ANTHROPIC_API_KEY", "").strip())
        import contextlib
        import silk_context
        ctx = (contextlib.nullcontext() if ai_ok
               else silk_context.block_ai_extras())
        # لوحة إعدادات الوكلاء: طلبٌ بلا agent_prefs يرث الإعدادات المحفوظة
        # خادمياً — فتسري على الإدخال والدردشة معاً حتى من عميل لا يرسلها.
        prefs = _clean_agent_prefs(req.agent_prefs)
        if prefs is None:
            prefs = _saved_agent_settings()
        with ctx, silk_context.agent_prefs_context(prefs):
            result = silk_engine.analyze(
                req.product, year=req.year,
                countries=_target_countries(req.markets),
                trend_span=req.trend_span,
                product_card=(req.product_card.model_dump()
                              if req.product_card else None),
                # رمزٌ حُسِم آلياً بالسمة الرقمية يتقدّم على مُحلِّل المحرّك
                # (وإلا لَعاد المحرّكُ إلى نفس الرمز الملتبِس)؛ بلا حسمٍ آليّ
                # يبقى السلوكُ حرفياً كما كان.
                hs_code=(_analyze_hs_code if _hs_prov is not None
                         else req.hs_code),
                persist=req.persist, **policy)
        if not ai_ok:
            result["ai_extras_note"] = ai_note   # الغياب مُعلَن لا صامت
        if _hs_prov is not None:
            result["hs_provenance"] = _hs_prov   # يعرضه التقريرُ كمصدرٍ للرمز
        result["view"] = _view(result)
        # R2b (API-12): `persist=true` بلا معرّف = فشلُ حفظٍ مُعلَن لا 200 صامت —
        # التحليلُ نفسُه صحيح ويُسلَّم، والفجوةُ تُسمّى (`persist_error`).
        if req.persist and not result.get("analysis_id"):
            result["analysis_id"] = None
            result.setdefault("persist_error", "unknown")
        _attach_watchdog(result, result.get("analysis_id"), "analyze")
        return _json(result)

    def _clean_agent_prefs(raw: dict | None) -> dict | None:
        """طبّع توجيهات الوكلاء شكلياً (P3) — {key: {on: bool, cmd: str<=500}}.

        أي شكل آخر يُتجاهل بصمت (إعداد عميل لا بيانات)؛ الأمر نص حر يذهب
        حصراً إلى برومبتات كلود داخل عزل _isolate — لا يمسّ وكلاء الأرقام.
        """
        if not isinstance(raw, dict):
            return None
        out = {}
        for k, v in list(raw.items())[:24]:
            if not isinstance(v, dict):
                continue
            out[str(k)[:40]] = {"on": bool(v.get("on", True)),
                                "cmd": str(v.get("cmd") or "")[:500]}
        return out or None

    def _target_countries(iso3s: list[str] | None):
        """ضيّق قائمة الأسواق المرشّحة — an explicit ISO3 subset of COUNTRIES,
        أو None (الافتراضي: كل الأسواق ‎— سلوك الاكتشاف القائم بلا تغيير).

        رموز غير معروفة تُتجاهَل بصمت (لا اختلاق سوق غير موجود في المرجع)؛
        قائمة فارغة بعد الترشيح => None (لا نُسقط التحليل إلى صفر أسواق).
        """
        if not iso3s:
            return None
        from silk_market_ranker import COUNTRIES
        wanted = {s.strip().upper() for s in iso3s if s and s.strip()}
        filtered = [c for c in COUNTRIES if c["iso3"] in wanted]
        return filtered or None

    def _saved_agent_settings() -> dict | None:
        """إعدادات الوكلاء المحفوظة خادمياً — sanitized, or None (لا حفظ)."""
        try:
            import silk_store
            return _clean_agent_prefs(silk_store.load_agent_settings())
        except Exception as e:  # noqa: BLE001 — الإعدادات تحسين لا شرط
            log.debug("saved agent settings unavailable: %s", e)
            return None

    class AgentSettingsBody(BaseModel):
        """جسم إعدادات الوكلاء — {agent_key: {on: bool, cmd: str}} فقط.

        **لا مفاتيح مصادر هنا** — pydantic يسقط أي حقل آخر، والقاموس يمرّ
        على _clean_agent_prefs (on/cmd حصراً) فلا يمكن تهريب مفتاح عبر
        هذه اللوحة؛ مفاتيح المصادر تُضبط في بيئة النشر (Railway env).
        """
        settings: dict | None = None

    @app.get("/settings/agents")
    def get_agent_settings(request: Request):
        """سجل الوكلاء + الإعدادات السارية — the catalog and effective settings.

        الواجهة تبني اللوحة من هذا الرد (سجل واحد قانوني في silk_agents —
        لا قائمة موازية في الواجهة تنحرف عنه).
        """
        _require_key(request)
        _rate_limit(request)
        import silk_missions  # noqa: F401 — يسجّل صفوف البعثات الاثنتي عشر
        from silk_agents import AGENT_CATALOG, default_agent_settings
        merged = default_agent_settings()
        saved = _saved_agent_settings() or {}
        for k, v in saved.items():
            if k in merged:
                merged[k] = v
        return {"agents": AGENT_CATALOG, "settings": merged,
                "saved": bool(saved)}

    @app.post("/settings/agents")
    def set_agent_settings(body: AgentSettingsBody, request: Request):
        """احفظ إعدادات الوكلاء خادمياً — persist per-agent {on, cmd}.

        جسم فارغ = استعادة الافتراضي (يمحو المحفوظ فتسري الافتراضيات).
        """
        _require_key(request)
        _rate_limit(request)
        clean = _clean_agent_prefs(body.settings) or {}
        import silk_store
        silk_store.migrate()
        silk_store.save_agent_settings(clean)
        return {"saved": True, "count": len(clean)}

    class KeysBody(BaseModel):
        """جسم حفظ مفاتيح المصادر — allow-listed server-side key settings."""
        keys: dict[str, str]

    @app.post("/settings/keys")
    def set_keys(body: KeysBody, request: Request):
        """احفظ مفاتيح المصادر في الخادم (Stage 2A) — the settings panel finally
        persists somewhere real: allow-listed keys go to the unified store AND the
        process env (agents pick them up immediately). القيم لا تُعاد أبداً —
        الاستجابة وجود/رفض فقط. متغير بيئة النشر يبقى الأعلى سلطة عند الإقلاع.
        """
        _require_key(request)
        _rate_limit(request)
        import silk_store
        silk_store.migrate()
        saved, rejected, owner_only = [], [], []
        for k, v in (body.keys or {}).items():
            v = (v or "").strip()
            if k in _OWNER_ENV_ONLY:
                # R7 (SEC-13): مفتاحُ كلود سرُّ المالك في بيئة النشر وحدها — لا يُكتب
                # في المخزن ولا في بيئة العملية من لوحةٍ خلف مفتاح API واحد.
                owner_only.append(k)
                continue
            if v and silk_store.set_setting(k, v):
                os.environ[k] = v
                saved.append(k)
            elif v:
                rejected.append(k)
        return {"saved": saved, "rejected": rejected, "owner_env_only": owner_only}

    @app.post("/deepen")
    def deepen(req: DeepenRequest, request: Request):
        """عمّق التحليل (المسار المدفوع الوحيد) — the only paid-layer path.

        يعمل داخل silk_context.deepen_context() فيسمح حارس BaseAgent البنيوي
        بتشغيل الوكلاء المدفوعين (localprice/volza/explee) — خارجه يستحيل
        تنفيذهم حتى مع مفاتيح مضبوطة. حارسا الموجة ٠ (401 المصادقة، 429
        السقف) يعملان قبل أي وكيل.
        """
        _require_key(request)
        _rate_limit(request)
        _guard_paid(req)
        # بوّابة HS الصلبة على المسار **المدفوع** (بلاغ «حليب نادك»، الثغرة
        # الأولى): كان `/deepen` يمرّر `req.hs_code` مباشرةً إلى المحرّك بلا
        # أيّ فحص — المسار الوحيد القادر على صرف رصيدٍ مدفوع، وهو الوحيد الذي
        # كان بلا بوّابة. والأسوأ: `DeepenRequest.hs_confirmed` كان مُعلَناً
        # بتعليقٍ يوحي بوجود بوّابة، و**لا يُقرأ إطلاقاً** — حقلٌ ميت يوحي
        # بأمانٍ غير قائم. الآن يُقرأ هنا كما في `/analyze` و`/research`
        # تماماً، فتصير نقطةُ الاختناق ثلاثةَ مسارات لا اثنين.
        # موجةُ خطّ التصنيف: المسارُ المدفوع يمرّ بنفس نقطة الاختناق — كان
        # يمنح رمزَه الصريحَ ثقةَ 1.0 لمجرّد وجوده (`1.0 if req.hs_code`)،
        # وهي بعينُها العلّةُ التي أُغلِقت على `/research`. الآن يُقاس.
        _deepen_hs, _deepen_conf, _deepen_cls, _deepen_block = \
            _classify_product_hs(req.product, req.hs_code, req)
        if _deepen_block is not None:
            import silk_ops_log
            silk_ops_log.record_error(
                _deepen_block["error"],
                f"لم يُحسَم البند الجمركي لمنتج {req.product!r} على المسار "
                f"المدفوع: {_deepen_block['message']}",
                context={"product": req.product,
                         "hs_code": _deepen_block.get("hs_code"),
                         "hs_confidence": _deepen_block.get("hs_confidence"),
                         "top_candidate_score":
                             _deepen_block.get("top_candidate_score")})
            raise HTTPException(status_code=422, detail=_deepen_block)
        from silk_hs_confirm import preflight_resolve as _preflight_deepen
        _deepen_hs, _deepen_prov, _blocked = _preflight_deepen(
            req.product, _deepen_hs,
            # اعتمادُ «رمزٌ صريحٌ باسمٍ فارغ» يُكرَّم كما يُكرَّم التأكيدُ
            # الصريح — نفسُ الميكانيكا على المسار المدفوع (لا نصفَ إصلاح).
            req.hs_confirmed or _hs_explicitly_settled(_deepen_cls),
            allow_claude=_classify_general_allow_claude(),
            hs_confidence=_deepen_conf,
            label_attributes=req.label_attributes,
            # المهمة ١٤: نفسُ العقد على المسار المدفوع — لا نصفَ إصلاح.
            settled_contract=_deepen_cls,
            # رمزُ كتالوجٍ مُعاد ليس اختيارَ إنسانٍ حاضر (حادثة الدراسة #10).
            user_supplied=_hs_user_supplied(req))
        if _deepen_prov is not None:
            import silk_ops_log
            silk_ops_log.record_error(
                "hs_auto_resolved",
                f"حُسِم رمزُ HS آلياً على المسار المدفوع لمنتج {req.product!r} "
                f"=> {_deepen_hs} ({_deepen_prov.get('resolved_from')})",
                context={"product": req.product, "hs_code": _deepen_hs,
                         "path": "/deepen",
                         "resolved_from": _deepen_prov.get("resolved_from"),
                         "source_url": _deepen_prov.get("source_url")})
        if _blocked is not None:
            import silk_ops_log
            _cd = _blocked.get("hs_confirmation") or {}
            silk_ops_log.record_error(
                _blocked.get("error") or "hs_confirmation_blocked",
                f"رُفض تعميقٌ مدفوع برمز HS غير محسوم لمنتج {req.product!r}: "
                f"{_cd.get('reason') or _blocked.get('message')}",
                context={"product": req.product, "hs_code": _deepen_hs,
                         "path": "/deepen",
                         "hs_confidence": _blocked.get("hs_confidence"),
                         "missing_terms": _cd.get("missing_terms")})
            raise HTTPException(status_code=422, detail=_blocked)
        import silk_context
        with silk_context.deepen_context():
            result = silk_engine.analyze(
                req.product, year=req.year, with_trends=req.with_trends,
                with_tariffs=req.with_tariffs, with_faostat=req.with_faostat,
                with_maps=req.with_maps, with_websearch=req.with_websearch,
                with_localprice=req.with_localprice, own_price=req.own_price,
                with_volza=req.with_volza, with_explee=req.with_explee,
                with_ai=req.with_ai,
                with_competitors=req.with_competitors,
                with_channels=req.with_channels,
                with_importers=req.with_importers,
                with_requirements=req.with_requirements,
                with_trend=req.with_trend, trend_span=req.trend_span,
                product_card=(req.product_card.model_dump()
                              if req.product_card else None),
                hs_code=(_deepen_hs if _deepen_prov is not None
                         else req.hs_code),
                persist=req.persist)
        if _deepen_prov is not None:
            result["hs_provenance"] = _deepen_prov
        result["view"] = _view(result)
        return _json(result)

    class ResearchRequest(BaseModel):
        """طلب بحث عميق (الموجة ٤، V5) — ١٢ بعثة كلود + محلل شامل + تقرير.

        لا حقول مدفوعة (كـ AnalyzeRequest تماماً) — مسار مجاني حصراً. `market`
        نص حر (اسم عربي/إنجليزي أو ISO3) يُحلّ عبر silk_market_resolver؛
        مطابقة ضعيفة/غامضة = 422 مع اقتراحات، لا تخمين سوق.

        حادثة نقطة تفتيش/استئناف + تشغيل خلفي (P0): `resume` يستأنف تشغيلة
        سابقة بمعرّفها — `product`/`market` يصيران اختياريَين عندها (تُقرَآن
        من الطلب المخزَّن وقت الإنشاء)، وإلا إلزاميان كالسابق. `async_run`
        يُعيد `analysis_id` فوراً (202) ويكمل المعالجة في خيط خلفي — تجاوز
        مهلة بوّابة/وكيل عكسي لا يقتل التشغيلة أو يُيتّمها بعد اليوم.
        """
        product: str | None = None
        market: str | None = None
        hs_code: str | None = None
        # "catalog" = رمزٌ أُعيد من سجلّ منتجٍ/دراسةٍ مخزَّن (جسر المنصّة) لا
        # اختيارُ إنسانٍ في هذا الطلب — لا يستحق اختصارَ محور
        # preflight_block:692 (حادثة الدراسة #10: 040110 كتالوجيّ قديم مرّ
        # كإجابة مشغّل وبُنيت عليه دراسةٌ كاملة). الغياب = سلوك اليوم.
        hs_source: str | None = None
        product_card: ProductCard | None = None
        own_price: float | None = None  # سعرك المستهدف — كـAnalyzeRequest
        # هدف الدراسة الاحترافية (البند ٢): تكلفة إنتاج **وحدة السوق** —
        # أرخص مدخل يحوّل التقرير من وصف إلى حساب (يفتح الهامش والتعادل
        # وأقصى الخسارة). اختياري؛ يغلب تكلفة البطاقة عند الاجتماع.
        # ≤0 يُرفض تحقُّقاً (422 قبل أي حجز ميزانية) — صفر تكلفة اختلاق.
        production_cost_per_unit: float | None = Field(default=None, gt=0)
        persist: bool = True
        agent_prefs: dict | None = None
        # بلاغ حي — بوابة ما قبل التشغيل (409) ترفض تشغيلة بلا كلود صراحة؛
        # هذا الحقل فتحة هروب صريحة تطلبها الجهة المستهلكة (لا تدهور
        # افتراضي): تسليم تقرير موسوم بوضوح "متدهور" بدل رفضه كلياً.
        allow_degraded: bool = False
        resume: int | None = None
        async_run: bool = False
        # استشارة بلد المنشأ (Wave 1): موافقةٌ صريحة على إكمال دراسةِ سوقٍ من
        # أكبر مصدّري هذا الرمز عالميًا. غيابها + سوقٌ منتِجة + الصمّام مُفعَّل
        # => 422 استشاري قبل أيّ حجز؛ إرسالها بعد موافقة المستخدم يُكمِل التشغيلة.
        producer_ack: bool = False
        # سماتُ بطاقة العبوة الرقمية من استخلاص الصورة — نفس عقد
        # `AnalyzeRequest` حرفياً (المسارَان معاً، لا إصلاحَ نصفيّ: الدرس ٣٥).
        label_attributes: list[dict] | None = None
        # موافقةٌ صريحة موحّدة على أشقّاء استشارات ما قبل التشغيل (Wave 1.5،
        # عائلة A): تصدير إلى بلد المنشأ / سوق تحت عقوبات / فصل مقيَّد قانونيًا.
        # لوحةُ «جاهزية الدراسة» تجمعها؛ زرّ التأكيد الواحد يرسلها true.
        advisories_ack: bool = False
        # تأكيدٌ صريح على رمز HS رغم تحذير التطابق (Wave 1.2): بوّابةُ تأكيد
        # الرمز تُرجِع 422 حين لا تشمل صفةُ الرمز صفةَ المنتج المميّزة؛ إرسالُ
        # hs_confirmed=true بعد مراجعة المستخدم يُكمِل التشغيلة على مسؤوليته.
        hs_confirmed: bool = False
        # نمط كتابة التقرير (طلب المالك 2026-07-23): "academic" يجعل الكاتب
        # يكتب بسجلٍّ بحثيٍّ علمي (نفس الأقسام/الحكم/قواعد الصدق، النثر وحده
        # يتغيّر). غيابه => الافتراضي من البيئة `SILK_REPORT_STYLE`
        # (المضبوط "academic"). قيمة صريحة في الطلب تتقدّم على البيئة.
        report_style: str | None = None
        # موافقةٌ صريحة على تحذير معقولية بلد المورّد (البند أ٢): حين يكشف
        # الفحص الاقتصادي تفكّكًا شبه تامٍّ بين موردي السوق وأكبر مصدّري الرمز
        # عالميًا => 422 استشاري حتى يؤكّد المستخدم الرمز أو يعيد تصنيفه.
        a2_ack: bool = False
        # الموجة ٠ — لغة تقرير المصنع: **لقطة** الدراسة (`studies.report_language`)
        # تصل الكاتب والمراجع والعرض من هنا. لا تُقرأ من ترويسة ولا من لغة
        # واجهة ولا من تفضيل مستخدم — يمرّرها جسر المنصّة وحده من لقطته.
        # الغياب ⇒ عربي (الافتراض الآمن: لا ينقلب تقريرٌ كان عربياً بصمت).
        lang: str | None = None



    def _attach_quality_gate(result: dict, trace_id: str | None) -> None:
        """شغّل بوابة الجودة على القالب الموحّد وألحِق نتيجتها — الموجة ١٠،
        مستخرَجة كي يستدعيها كل من مسار /research الكامل ونقطة إعادة توليد
        التقرير وحدها (POST /analyses/{id}/report) بلا ازدواج منطق."""
        try:
            import silk_quality_gate
            gate_out = silk_quality_gate.run_quality_gate(result["view"])
            result["view"]["deep_research"]["quality_gate"] = gate_out
            if trace_id:
                import silk_trace
                silk_trace.append_event(
                    trace_id, event="quality_gate", verdict=gate_out["verdict"],
                    finding_count=len(gate_out["findings"]))
        except Exception as e:  # noqa: BLE001 — البوابة تحسين لا شرط تسليم
            log.warning("quality gate skipped: %s", e)

    def _block_client_export_if_gate_failed(
            view: dict, analysis_id: int, found: dict, fmt: str,
            request: "Request") -> None:
        """يرفع 409 إن رصدت بوابة الجودة FAIL على قالب تصدير العميل.

        **الموجة B (البند G-01):** السياسةُ نفسُها انتقلت إلى
        `silk_export_gate` كي يستهلكها **سطحا التصدير معاً** — هذا (المشغّل)
        وسطحُ المصنع في `silk_platform/api.py`. هنا يبقى ما يخصّ هذا السطح
        وحدَه: قراءةُ `?override=1` وترويسةِ المالك، ورسالةُ 409 التقنية.
        لا منطقَ بوابةٍ ثانٍ.

        `?override=1` يتخطّى الحجب بسلطة المالك المنفصلة فقط (WP-7 §1:
        ترويسة `X-Owner-Key` المطابقة لـ`SILK_OWNER_KEY`؛ مفتاح API العادي
        وحده = 403). `internal=1` لا يمرّ من هنا إطلاقاً (يبقى متاحاً دوماً
        للمدقّق)."""
        import silk_export_gate as _eg

        # WP-2 §3: قبل البوابة — حضِّر نثر الصياغة التجارية للأقسام بلا سرد
        # كاتب. نجاحه يملأ dr["client_fallback_prose"] فيمرّ القسم من
        # البوابة؛ فشله يترك القسم خاوياً فتُفشِله البوابة (409) — لا بنود
        # `dp.value` خام تصل العميل. النداءُ يمرّ ببوابة إضافات كلود نفسها
        # (`_free_ai_extras_allowed`) فلا نداءَ غيرَ محكوم.
        _dr = view.get("deep_research") or {}
        _ai_ok = False
        # WP-2 §3 (تصحيح مراجعة §58): يُحجَز نصيبُ إضافات كلود **فقط** حين
        # يوجد قسمُ عميلٍ بلا سردٍ يستدعي الصياغة فعلاً. كان الحجزُ يقع لكلّ
        # تصديرٍ فيه `deep_research`، فيَستنزف السقفَ اليوميّ ولو لم يُطلَق
        # كلود قطّ (كلُّ أقسامِ العميل تحمل سردَ الكاتب ⇒ `needs` فارغة).
        if (_dr and not _dr.get("client_fallback_prose")
                and _eg.client_prose_needed(_dr)):
            _ai_ok, _ = _free_ai_extras_allowed()
        _eg.prepare_fallback_prose(view, ai_allowed=_ai_ok, found=found,
                                   analysis_id=analysis_id)

        decision = _eg.evaluate(view)
        if not _eg.is_blocked(decision):
            return
        findings, digest = decision["findings"], decision["digest"]
        market_name = (found.get("market") or {}).get("name_en")
        override = str(request.query_params.get("override") or "").lower() in (
            "1", "true", "yes")
        if override:
            if not _eg.override_authorized(request.headers.get("X-Owner-Key")):
                raise HTTPException(status_code=403, detail={
                    "error": "owner_override_required",
                    "message": "تجاوز بوابة الجودة يتطلّب سلطة المالك "
                               "المنفصلة (ترويسة X-Owner-Key المطابقة لـ"
                               "SILK_OWNER_KEY على الخادم) — مفتاح API "
                               "العادي لا يكفي.",
                })
            _eg.record_override(analysis_id, found.get("product"),
                                market_name, findings, fmt)
            return
        _eg.record_block(analysis_id, found.get("product"), market_name,
                         findings, digest, fmt, surface="operator",
                         fail_drivers=decision.get("fail_drivers"))
        raise HTTPException(status_code=409, detail=_eg.operator_detail(
            digest, fail_drivers=decision.get("fail_drivers")))

    def _operator_artifact_gate_409(exc, analysis_id: int,
                                    fmt: str) -> HTTPException:
        """رفضُ بوابةِ نصّ المُنتَج النهائي على السطح الجذري ⇒ 409 منظّم.

        صيد الفجوات ٣ (G-04 كان نصفَ إصلاح): المنصةُ وحدَها كانت تحوّل
        `ClientArtifactGateError` إلى 409 `quality_gate_fail` وتُسجّل الحجب،
        بينما هذا السطحُ يعيده 501/503 بنصٍّ خام — فتقرؤه أداةُ فحص النشر
        «docx unavailable» ويتباعد عدُّ الحجب بين السطحين. نفسُ العقد الآن:
        كلُّ ملاحظات البوابة قائدةٌ بالبناء (كما `_artifact_gate_409` هناك)."""
        import silk_export_gate as _eg
        digest = list(getattr(exc, "findings", None) or [])
        # C4 موجة #14: قائمة هذا المسار كلها قائدة بالبناء — تُمرَّر للحمولة
        # أيضاً لا للسجل وحده، وإلا بقي سطر «قائد الحجب» أعمى على هذا السطح.
        _drivers = [str(d.get("check") or "") for d in digest
                    if isinstance(d, dict)]
        try:
            _found = silk_storage.get_analysis(analysis_id) or {}
            _eg.record_block(analysis_id, _found.get("product"),
                             (_found.get("market") or {}).get("name_en"),
                             digest, digest, fmt, surface="operator",
                             fail_drivers=_drivers)
        except Exception:  # noqa: BLE001 — التسجيلُ تحسينيّ لا شرط
            pass
        return HTTPException(status_code=409,
                             detail=_eg.operator_detail(
                                 digest, fail_drivers=_drivers))

    def _attach_override_history(view: dict, analysis_id: int | None) -> None:
        """WP-7 §1: حمِّل سجلّات تجاوز المالك (إن وُجدت) على القالب قبل بناء
        النسخة الداخلية — يختمها `silk_reports._render_research_docx` بسطر
        «سُلِّمت نسخة عميل بتجاوز مالكٍ — ملاحظات البوابة مرفقة»."""
        try:
            import silk_watchdog
            ov = silk_watchdog.override_records_for(analysis_id)
            if ov:
                view["owner_override_history"] = ov[:3]
        except Exception as e:  # noqa: BLE001 — الختم توثيق، لا شرط تصدير
            log.warning("override history attach failed: %s", e)

    def _attach_watchdog(result: dict, analysis_id: int | None,
                         kind: str) -> None:
        """نقطةُ اختناقٍ مشتركةٌ واحدة يستدعيها **كلا** المسارين (/analyze
        و/research) — الحارس («كاميرا مراقبة»، طلب المُشرِف): سجلّ صحّةٍ
        حتميٌّ (صفر نداء كلود) يُخزَّن في مخزنه المستقل (`silk_watchdog.py`)
        لسطح مالكٍ منفصل تماماً («تقرير الحارس»). **لا يمسّ `result` إطلاقاً**
        (لا حقل يُضاف لنتيجة التحليل) — مبدأ عدم التلوّث: صفر سطر حارسٍ يصل
        أي سطح عميل. فشلها الداخلي مُعزولٌ بالفعل (`silk_watchdog.observe`
        لا ترفع أبداً)؛ هذا `try` طبقة حمايةٍ إضافية فقط."""
        try:
            import silk_watchdog
            silk_watchdog.observe(result, kind, analysis_id)
        except Exception as e:  # noqa: BLE001 — مراقبة لا تُسقِط تحليلاً أبداً
            log.warning("watchdog skipped: %s", e)

    # جسم التشغيلة الثقيل انتقل لوحدته (تدقيق 2026-08-27، البند ٧) — نقلٌ
    # حرفيّ بلا تغيير منطق؛ `build` يحقن المساعِدين الخمسة الذين كان العنقود
    # يقرؤهم من هذا النطاق، فتبقى دلالة الإغلاق كما هي بلا دورة استيراد.
    # The heavy body now lives in silk_research_pipeline (literal move).
    import silk_research_pipeline
    _run_research_pipeline = silk_research_pipeline.build(
        view_fn=_view, attach_quality_gate=_attach_quality_gate,
        attach_watchdog=_attach_watchdog, to_jsonable=_to_jsonable,
        early_halt_enabled=_early_halt_enabled)




    _TRANSIENT_LLM_ERROR_TYPES = frozenset(
        {"ReadTimeout", "ConnectTimeout", "ConnectionError", "ChunkedEncodingError",
         "StreamTotalTimeout"})

    def _expected_run_usd() -> float:
        """التقدير المحجوز لتشغيلة بحث — المصدر الواحد `silk_usage.expected_
        run_usd()` (درس 188، F9: كان أربع نسخ بحرفيّة 3.0 قد تتباعد)."""
        return silk_usage.expected_run_usd()



    def _research_stale_minutes() -> int:
        from silk_storage import orphan_stale_minutes
        return orphan_stale_minutes()

    def _research_row_is_fresh(row: dict) -> bool:
        """هل نبضةُ الصفّ (`updated_at`) أحدثُ من نافذة الحاصد؟ — القاعدةُ نفسها
        `silk_storage.orphan_stale_cutoff` (مقارنةٌ نصّية على البادئة)."""
        from silk_storage import orphan_stale_cutoff
        stamp = str(row.get("updated_at") or "")[:19]
        if not stamp:
            return False
        return stamp >= orphan_stale_cutoff()[:19]

    def _finish_research_run(analysis_id: int | None, result: dict) -> None:
        """خزّن النتيجة النهائية وحدّث حالة التشغيلة — نفس معرّف الإنشاء
        (P0: نتيجة الاستئناف تنتهي بنفس analysis_id الذي بدأت به).

        `analysis_id` يُضاف لِـ`result` **قبل** التخزين لا بعده — بلاغ حي
        (اختبار استئناف تشغيلة مكتملة): إضافته بعد `save_analysis` تعني
        أن النسخة المخزَّنة لا تحمله أبداً، فقراءتها لاحقاً عبر استئناف أو
        `GET /analyses/{id}` تفتقد الحقل رغم ظهوره في الرد الأصلي المباشر.
        """
        if analysis_id is None:
            return
        result["analysis_id"] = analysis_id
        from silk_storage import save_analysis
        save_analysis(result, analysis_id=analysis_id)

    def _research_background(market_ref, product, hs_code, hs_note,
                             product_card_dict, ai_ok, ai_note, prefs,
                             ready, ready_reason, analysis_id,
                             resume_reports, report_style=None,
                             hs_confidence=None, hs_provenance=None,
                             lang="ar", resume_stages=None,
                             hs_classification=None) -> None:
        """جسم الخيط الخلفي (async_run=true) — يُغلَّف باستثناء شامل عمداً:
        خيط بايثون غير المُمسوك يفشل صامتاً (لا كسر عملية، لا تحديث حالة)
        فتبقى التشغيلة عالقة على 'running' للأبد — بلاغ التحقيق (P0) يمنع
        هذا صراحة. نقاط تفتيش البعثات المكتملة فعلاً تبقى مخزَّنة بصرف
        النظر عن نتيجة هذه المحاولة — استئناف لاحق يقرأها."""
        _rh = silk_research_runtime.handle(analysis_id)
        try:
            with silk_context.cancel_context(_rh.cancel if _rh else None):
                result = _run_research_pipeline(
                    market_ref, product, hs_code, hs_note, product_card_dict,
                    ai_ok, ai_note, prefs, ready, ready_reason, analysis_id,
                    resume_reports, report_style, hs_confidence=hs_confidence,
                    hs_classification=hs_classification,
                    hs_provenance=hs_provenance, lang=lang,
                    resume_stages=resume_stages)
            _finish_research_run(analysis_id, result)
        except Exception as e:  # noqa: BLE001 — خيط خلفي: هذا آخر حزام أمان
            log.error("background /research run %s failed: %s", analysis_id, e)
            from silk_storage import mark_research_failed, reconcile_failed_run_usd
            mark_research_failed(analysis_id, _redact_text(f"{type(e).__name__}: {e}")[:500])
            # البند #3 (تدقيق v2 الموجة ٢): تشغيلةٌ تفشل رشيقاً تُصالِح حجزها
            # الدولاري للفعلي-حتى-الآن، فلا يبقى محجوزاً يسدّ السقف حتى الدوران.
            reconcile_failed_run_usd(analysis_id)
        finally:
            silk_research_runtime.release(analysis_id)   # R2b: المقبضُ والفتحة

    def _readiness_checks(product: str, market_ref, hs_code) -> list[dict]:
        """لوحةُ «جاهزية الدراسة» (Wave 1.5، عائلة D) — كلُّ تدهورٍ معروفٍ **قبل
        الحجز** كسطرٍ ✓/⚠/✗، فلا يعرف المالكُ تدهورًا **بعد** الدفع أبدًا.

        كلُّ سطر `{key, label_ar, status, detail_ar, blocking}`:
        status ∈ {ok, advisory, blocked, info}؛ blocking=True => يمنع التشغيل
        (رمز HS/خارج التغطية)؛ advisory => يتطلّب موافقة؛ info => إخباري فقط.
        قراءةٌ فقط — لا حجز ولا إنفاق. يشارك api البوّابةَ نفسها (مصدر واحد).
        """
        import datetime as _dt
        checks: list[dict] = []
        iso3 = getattr(market_ref, "iso3", "") or ""
        year = _dt.date.today().year - 1
        # (١) رمز HS محسوم — حجرُ الأساس (بوّابة صلبة).
        checks.append({
            "key": "hs_resolved", "label_ar": "رمز HS محسوم",
            "status": "ok" if hs_code else "blocked",
            "detail_ar": (f"HS {hs_code}" if hs_code
                          else "لم يُحسَم رمز HS — صنِّف المنتج أو اختر يدويًا"),
            "blocking": not bool(hs_code)})
        # (١ب) رمز HS **مؤكَّد دلالياً** — البلاغ الحيّ 2026-07-21 (زبدة الفول
        # السوداني/040510): رمزٌ محسومٌ لكنه خاطئ دلالياً كان يمرّ كـ«ok» لأن
        # اللوحة تفحص الحسم لا المطابقة. البوّابة (فشل-آمن) تحجبه الآن؛ فتظهر
        # هنا **قبل** الحجز اتّساقاً مع بوّابة `/research` (لا تدهورٌ بعد الدفع).
        if hs_code:
            from silk_hs_confirm import confirm_hs, is_flagged, gate_enabled
            _c = confirm_hs(product or "", hs_code)
            if is_flagged(_c):
                checks.append({
                    "key": "hs_confirmed", "label_ar": "مطابقة رمز HS للمنتج",
                    "status": "blocked" if gate_enabled() else "advisory",
                    "detail_ar": (f"رمز HS {hs_code} («{_c.get('code_desc')}») "
                                  "قد لا يطابق المنتج — صفة مميّزة غير مشمولة: "
                                  + "، ".join(_c.get("missing_terms") or [])),
                    "blocking": gate_enabled()})
        # (٢) السوق ضمن التغطية.
        from silk_market_ranker import _world_markets_enabled
        if _world_markets_enabled() and hs_code and iso3:
            _cov, _det = _market_in_coverage(hs_code, iso3)
            checks.append({
                "key": "coverage", "label_ar": "السوق ضمن التغطية",
                "status": "ok" if (not _det or _cov) else "blocked",
                "detail_ar": ("ضمن التغطية" if (not _det or _cov)
                              else "خارج التغطية الحالية — تواصل معنا لإضافتها"),
                "blocking": bool(_det and not _cov)})
        # (٣) استشارةُ بلد المنشأ (Wave 1) — سوقٌ من أكبر المصدّرين.
        if _producer_advisory_enabled() and hs_code and len(iso3) == 3:
            from silk_market_ranker import is_top_world_exporter
            _is_top, _top = is_top_world_exporter(hs_code, iso3, year)
            checks.append({
                "key": "producer_country", "label_ar": "بلد المنشأ",
                "status": "advisory" if _is_top else "ok",
                "detail_ar": ("من أكبر مصدّري هذا الرمز عالميًا — دخول تنافسي جدًّا"
                              if _is_top else "ليست من كبار المصدّرين"),
                "blocking": False})
        # (٣ب) معقولية بلد المورّد (البند أ٢) — إشارةٌ اقتصادية: هل ملفُّ موردي
        # السوق يطابق الرمز؟ تفكّكٌ شبه تامٌّ => تحذيرٌ استشاري (لا حجب نهائي).
        from silk_market_ranker import _a2_plausibility_enabled
        if _a2_plausibility_enabled() and hs_code and len(iso3) == 3:
            from silk_market_ranker import supplier_plausibility
            _a2r = supplier_plausibility(
                hs_code, iso3, getattr(market_ref, "m49", ""), year)
            if _a2r is not None:
                _bad = bool(_a2r.get("implausible"))
                checks.append({
                    "key": "supplier_plausibility",
                    "label_ar": "معقولية بلد المورّد",
                    "status": "advisory" if _bad else "ok",
                    "detail_ar": (
                        "موردو السوق الفعليون لا يطابقون أكبر مصدّري الرمز "
                        "عالميًا — راجع التصنيف" if _bad
                        else "ملفّ الموردين متّسقٌ مع مصدّري الرمز عالميًا"),
                    "blocking": False})
        # (٤) أشقّاء عائلة A (Wave 1.5) — بلد المنشأ نفسه/عقوبات/فصل مقيَّد.
        import silk_prerun
        if silk_prerun.advisories_enabled() and len(iso3) == 3:
            for a in silk_prerun.sibling_advisories(hs_code, iso3):
                checks.append({
                    "key": a["kind"],
                    "label_ar": {"self_origin": "بلد المنشأ نفسه",
                                 "sanction": "عقوبات/حظر",
                                 "restricted_chapter": "فئة مقيَّدة قانونيًا"
                                 }.get(a["kind"], a["kind"]),
                    "status": "advisory",
                    "detail_ar": a.get("detail") or a.get("message") or "",
                    "blocking": False})
        # (٥) ميزانية كومتريد (إخباري — لا يمنع، لكن يُعلَن قبل الدفع).
        try:
            from silk_collectors import comtrade_budget_left
            _left = comtrade_budget_left()
            checks.append({
                "key": "comtrade_budget", "label_ar": "ميزانية كومتريد اليومية",
                "status": "ok" if _left > 0 else "advisory",
                "detail_ar": f"المتبقّي ~{_left} نداء",
                "blocking": False})
        except Exception:  # noqa: BLE001 — قياس اختياري
            pass
        # (٦) حالة مكشطة الخرائط (إخباري).
        _scraper = bool(os.environ.get("SILK_GMAPS_SCRAPER_URL", "").strip())
        checks.append({
            "key": "scraper_state", "label_ar": "مكشطة جهات الاتصال",
            "status": "ok" if _scraper else "info",
            "detail_ar": ("مُهيَّأة" if _scraper
                          else "غير مُهيَّأة — هواتف/عناوين قد تغيب"),
            "blocking": False})
        # (٧) حماية المفاتيح المدفوعة (إخباري/تحذيري).
        _unprot = _unprotected_paid_keys()
        checks.append({
            "key": "key_protection", "label_ar": "حماية المفاتيح",
            "status": "advisory" if _unprot else "ok",
            "detail_ar": ("مفاتيح مدفوعة بلا SILK_API_KEY — نداءات محجوبة"
                          if _unprot else "محميّة"),
            "blocking": False})
        return checks

    @app.get("/research/readiness")
    def research_readiness(request: Request, product: str = "",
                           market: str = "", hs_code: str = ""):
        """جاهزيةُ الدراسة قبل الحجز — the pre-reservation readiness panel (D).

        قراءةٌ فقط (لا حجز/إنفاق): تُعيد كلَّ تدهورٍ معروفٍ كسطرٍ ✓/⚠/✗ +
        `can_run`/`needs_ack` كي تعرضها الواجهة **قبل زرّ التأكيد**. رمزُ HS
        يُحلّ حتميًا إن غاب (بلا نداء كلود)."""
        # صيد الفجوات ٣: كان السطحَ الوحيد في عائلة /research بلا مفتاح،
        # وقد يُطلِق جلباً حياً من ميزانية كومتريد المشتركة حين تُفعَّل
        # تغطية العالم — لوحة المشغّل المفتاحية هي مستدعيه الوحيد.
        _require_key(request)
        _rate_limit(request)
        from silk_market_resolver import resolve_market
        market_ref, suggestions = resolve_market(market) if market else (None, [])
        hs = (hs_code or "").strip()
        if not hs and product:
            from silk_hs_resolver import resolve as _rhs
            hs = _rhs(product).value or ""
        if market_ref is None:
            return _json({"checks": [{
                "key": "market", "label_ar": "السوق المستهدفة",
                "status": "blocked",
                "detail_ar": "سوق غير معروفة/غامضة — اختر من القائمة",
                "blocking": True}], "can_run": False, "needs_ack": False,
                "suggestions": suggestions})
        checks = _readiness_checks(product, market_ref, hs)
        return _json({
            "checks": checks,
            "can_run": not any(c["blocking"] for c in checks),
            "needs_ack": any(c["status"] == "advisory" for c in checks)})

    def _research_impl(req: ResearchRequest, on_allocated=None):
        """بحث عميق — ١٢ بعثة كلود بالأدوات + محلل شامل + حكم + تقرير مراجَع.

        (قرار 2026-08-18 — توصيل المنصّة بالمحرك الحقيقي): الجسم كله هنا في
        مغلقة مستقلة عن HTTP كي يستدعيه مساران بلا ازدواج: نقطة `POST /research`
        أدناه (بعد حارسَي المفتاح/المعدل)، وجسر دراسات المنصّة عبر
        `silk_research_gateway` (تسجيل أسفل `create_app`). سلوك النقطة لم
        يتغير حرفاً — الحارسان فقط انتقلا إلى الغلاف.

        مسار مجاني حصراً (نموذج بلا حقول مدفوعة، كـ/analyze) — إضافات كلود
        (البعثات + المحلل + توليف المرحلة ٢ + الكاتب/المراجع) تمرّ عبر نفس
        بوابة H2 (`_free_ai_extras_allowed`) وحجزها الذرّي الواحد من
        SILK_PAID_DAILY_CAP (كنداء AI إضافي واحد على /analyz تماماً) — لا
        مسار كلود موازٍ. الحجم الفعلي لعدد النداءات عبر التحليل بأكمله
        محكوم بسقف منفصل (`SILK_RESEARCH_MAX_LLM_CALLS`/`_MAX_TOOL_CALLS`،
        افتراضياً ٤٠/١٠٠) يُطبَّق حياً داخل `silk_llm_runtime._run_loop` —
        إنهاء رشيق لا كسر عند تجاوزه، ومُلخَّص علوياً في
        `deep_research.budget_status` (P1، حادثة نفاد الاعتمادات).

        بوابة ما قبل التشغيل (بلاغ حي): كلود هنا **شرط تشغيل** لا تحسين
        اختياري — بلا مفتاح فعّال كل الاثنتي عشرة بعثة تفشل بصفر نتائج
        والتقرير هيكل فارغ. `_research_readiness()` يرفض هذا صراحة بـ409
        قبل تشغيل أي بعثة، إلا أن يمرّر الطالب `allow_degraded=true` —
        عندها تُشغَّل التشغيلة وتُوسَم النتيجة `degraded=true` مع سبب واضح
        (`degraded_reason`)، فتحمل كل مشتقات التقرير (docx/مختصر/لوحة)
        لافتة تحذير حمراء بدل تسليم هيكل فارغ بصمت كأنه المنتج.

        نقطة تفتيش/استئناف + تشغيل خلفي (P0، حادثة نفاد الاعتمادات —
        `docs/DEEP_RESEARCH_DECISIONS.md`): `persist=true` (الافتراضي)
        يخصّص `analysis_id` **قبل** تشغيل أي بعثة، وكل بعثة تُخزَّن فور
        اكتمالها — عطل/إعادة نشر منتصف الطريق لا يخسر البعثات المكتملة.
        `resume=<analysis_id>` يعيد فتح تشغيلة سابقة (مكتملة/فاشلة/عالقة)
        ويُشغّل فقط البعثات الناقصة + المحلل/الكاتب من جديد؛ إن كانت
        مكتملة أصلاً يعيدها كما هي بلا أي نداء كلود جديد (لا حرق اعتمادات
        مضاعف). `async_run=true` يعيد `{analysis_id, status:"running"}`
        فوراً (202) ويكمل المعالجة في خيط خلفي — تجاوز مهلة بوّابة/وكيل
        عكسي يعود يقطع اتصال العميل فقط، لا التشغيلة نفسها، ولا يُيتّمها:
        استطلع `GET /research/{analysis_id}/status` حتى `status=="completed"`
        ثم `GET /analyses/{analysis_id}` للنتيجة الكاملة.
        """
        resume_reports: dict | None = None
        resume_stages: dict | None = None   # p6/T4: نقاط تفتيش المراحل
        analysis_id: int | None = None
        stored_request: dict = {}
        run_row: dict | None = None   # R2b: يُملأ في فرع الاستئناف فقط

        if req.resume is not None:
            from silk_storage import get_analysis, get_research_run, \
                load_mission_checkpoints, mission_status_map
            run_row = get_research_run(req.resume)
            if run_row is None:
                raise HTTPException(status_code=404, detail={
                    "error": "resume_not_found",
                    "reason": f"research run {req.resume} not found"})
            if run_row.get("kind") != "research":
                raise HTTPException(status_code=400, detail={
                    "error": "not_a_research_run",
                    "reason": f"analysis {req.resume} is not a /research "
                              "run — resume only applies to /research"})
            stored_request = run_row.get("request") or {}
            from silk_request_identity import resume_mismatches
            mismatches = resume_mismatches(req.model_dump(exclude_unset=True), stored_request)
            if mismatches:
                raise HTTPException(status_code=409, detail={
                    "error": "resume_identity_mismatch", "fields": mismatches,
                    "reason": "تغيّر المنتج أو مدخلات الدراسة؛ أنشئ دراسة جديدة."})
            # R2b (تدقيق 2026-09-01، API-4): استئنافٌ على صفٍّ **جارٍ** (نبضتُه
            # طازجة، أو مسجَّلٌ في هذه العملية) كان يبدأ خطَّ أنابيب ثانياً على
            # المعرّف نفسه بحجزٍ دولاريّ ثانٍ — 409 معلَن بصاحب التشغيلة ونافذة
            # التقادم، والحكمُ للنبضة لا للهويّة (إقلاعٌ آخر قد يكون حيّاً).
            # مراجعة R2b: المقبضُ الحيّ في هذه العملية يحكم **قبل** حالة الصفّ —
            # صفٌّ حصده حاصدٌ آخر بينما خيطُه يعمل هنا لا يُستأنف فوقه.
            _mine = silk_research_runtime.is_running(int(req.resume))
            if _mine or (run_row.get("status") == "running"
                         and _research_row_is_fresh(run_row)):
                raise HTTPException(status_code=409, detail={
                    "error": "resume_still_running",
                    "owner": "this_process" if _mine else "other_process",
                    "updated_at": run_row.get("updated_at"),
                    "stale_after_minutes": _research_stale_minutes(),
                    "reason": (f"analysis {req.resume} is still running — "
                               "poll /research/{id}/status, cancel it, or "
                               "wait for the heartbeat to go stale before "
                               "resuming")})
            # بوّابة نطاق السوق (البلاغ الحي — تسرّب اليمن↔الكويت،
            # 2026-07-21) — **تسبق** مسار «مكتملة => أعِدها كما هي» أدناه
            # عمداً: ذلك المسار كان يُعيد نتيجة اليمن المخزَّنة بصمتٍ متجاهلاً
            # `req.market="Kuwait"` (لا تسريب تسمية، لكن تجاهل صامت لطلب
            # المستخدم يخفي بالضبط الخطأ الذي أدّى للحادثة الحية عبر مسارٍ
            # آخر — تشغيلة غير مكتملة استؤنفت بسوقٍ مختلف). رفضٌ صريح هنا
            # أوضح من إرجاعٍ صامت لبيانات سوقٍ لم يُطلَب.
            _stored_iso3 = stored_request.get("market_iso3")
            if req.market and _stored_iso3:
                from silk_market_resolver import resolve_market as _rm_check
                _req_ref, _ = _rm_check(req.market)
                if (_req_ref is not None and _req_ref.iso3
                        and _req_ref.iso3 != _stored_iso3):
                    raise HTTPException(status_code=409, detail={
                        "error": "resume_market_mismatch",
                        "reason": (f"analysis {req.resume} was created for "
                                  f"market {_stored_iso3}, not "
                                  f"{_req_ref.iso3} — resuming under a "
                                  "different market would reuse that "
                                  "market's mission checkpoints. start a "
                                  "fresh /research run instead."),
                        "stored_market_iso3": _stored_iso3,
                        "requested_market_iso3": _req_ref.iso3})
            if run_row.get("status") == "completed":
                # مكتملة فعلاً — أعِدها كما هي، لا إعادة تشغيل ولا حرق
                # اعتمادات إضافي (استئناف مكتمل يجب أن يكون آمناً للتكرار)
                # — **إلا** إن حملت التشغيلة بعثةً نقطتها فاشلة (بلاغ
                # Nadec/اليمن #7): التشغيلة تُوسَم "completed" حتى لو فشلت
                # بعثة (429/مهلة)، فكان هذا المسار يُعيد النتيجة المخزَّنة
                # بصمتٍ ولا يبلغ `run_all_missions` حيث تُعاد الفاشلة (#180)
                # — فبدا `resume` بلا أثر (updated_at ثابت، صفر نداء، تكلفة
                # كما هي). الآن: وجود أيّ بعثة فاشلة يُسقط مسار الإعادة
                # الصامتة فتُستأنف التشغيلة فعلاً وتُعاد الفاشلة وحدها؛
                # التشغيلة الناجحة كاملةً تبقى إعادةَ تسليمٍ صرفةً (idempotent).
                _status_map = mission_status_map(req.resume)
                _has_failed = any(v == "failed" for v in _status_map.values())
                if not _has_failed:
                    existing = get_analysis(req.resume)
                    # الموجة p6 (T4): الإعادة الصرفة **بنصّ تقرير فقط**. تشغيلة
                    # «مكتملة» بلا نصّ (الفرع ب: فشل الكاتب/المحلل) كانت تُعاد
                    # كما هي — فبدا الاستئناف بلا أثر وأُجبر المستخدم على
                    # تشغيلة كاملة جديدة تعيد دفع البعثات والمحلل. الآن تسقط
                    # إلى مسار الاستئناف: البعثات والمحلل المحفوظان يُعاد
                    # استعمالهما، والكاتب وحده يُعاد.
                    _existing_text = (((existing or {}).get("deep_research")
                                       or {}).get("report") or {}).get("report")
                    if existing is not None:
                        if _existing_text:
                            return _to_jsonable(existing)
                        # انحدارٌ رُصد بمقارنة الأساس (المراجعة §58): تشغيلةٌ
                        # مكتملةٌ بلا نصّ تقرير صارت تسقط إلى المسار الحيّ —
                        # وحين لا يكون المحرّك جاهزاً (بلا مفتاح كلود) ردّت
                        # بوّابةُ الجهوزية **409** على مجرّد استئناف. رفضٌ صلب
                        # يحوّل جزئياً قابلاً للإنقاذ إلى طريقٍ مسدود ويحجب
                        # المحفوظ. القاعدة: يُعاد المحفوظ (٢٠٠) بسببٍ معلَن حين
                        # يتعذّر إنتاج التقرير؛ وحين يكون المحرّك جاهزاً يمرّ
                        # الاستئناف فيعيد الذيل وحده (بعثات ومحلل مُعادُ
                        # استعمالهما) — وهو مقصد T4.
                        _rdy, _rdy_reason = _research_readiness()
                        if not _rdy and not req.allow_degraded:
                            _out = dict(existing)
                            _out["resume_note"] = (
                                "أُعيد تسليم المحفوظ كما هو: التقرير النصّي ما "
                                "زال ناقصاً ولا يمكن توليده الآن — "
                                f"{_rdy_reason}. البعثات والتحليل محفوظة؛ "
                                "أعد الاستئناف بعد تهيئة المحرّك ليُكتَب "
                                "التقرير وحده بلا إعادة دفع.")
                            log.info("resume %s replayed the saved partial "
                                     "(engine not ready: %s)", req.resume,
                                     _rdy_reason)
                            return _to_jsonable(_out)
            analysis_id = req.resume
            # القراءة ليست مطالبة: لا نغيّر الحالة أو المصالحة قبل اجتياز
            # التحقق والجهوزية والسقف. المطالبة الذرّية في ذيل القبول أدناه.
            # نقاط تفتيش البعثات تُحمَّل **بعد** حسم السوق أدناه (لا هنا) —
            # كي تُفلتَر بسوق التشغيلة المحسوم لا تُقرأ خاماً هنا. راجع
            # البوّابة أسفل حسم market_ref.

        product = req.product or stored_request.get("product")
        market_name = req.market or stored_request.get("market")
        if not product or not market_name:
            raise HTTPException(status_code=422, detail={
                "error": "product_and_market_required",
                "reason": "product/market are required unless resuming an "
                         "existing analysis_id that already has them"})

        from silk_market_resolver import resolve_market
        market_ref, suggestions = resolve_market(market_name)
        if market_ref is None:
            raise HTTPException(status_code=422, detail={
                "error": f"unknown or ambiguous market {market_name!r}",
                "suggestions": suggestions})

        if req.resume is not None:
            # نقاط تفتيش البعثات تُحمَّل هنا بعد حسم `market_ref` — مُفلترة
            # بسوقه (شبكة أمان بنيوية، `silk_storage.load_mission_checkpoints`)
            # فوق بوّابة الرفض الصريحة أعلاه (البلاغ الحي — تسرّب اليمن↔الكويت):
            # حتى لو مرّت بوّابة الرفض بطريقةٍ ما (تعارض غير مُكتشَف)، أيّ صفّ
            # مختوم بسوقٍ آخر لن يُعاد من المخزن أصلاً.
            from silk_storage import (load_mission_checkpoints,
                                      load_stage_checkpoints)
            resume_reports = load_mission_checkpoints(
                req.resume, market_iso3=market_ref.iso3)
            # p6/T4: المحلل/الحكم/الروابط المحفوظة — نفس حارس السوق.
            resume_stages = load_stage_checkpoints(
                req.resume, market_iso3=market_ref.iso3)

        # ── تحديد رمز HS مرّةً واحدة قبل أيّ بوّابة/حجز (Wave 1) ──────────────
        # نظامٌ عام: كلُّ البوّابات (التغطية، بلد المنشأ، الحجز الدولاري) تعمل
        # على رمزٍ محسوم — لا دراسةَ على HS مجهول. صريحٌ/مخزَّن أولًا، وإلا
        # المُحلِّل الحتمي (لا اختلاق رمز عند فشله — فجوة معلنة في hs_note).
        hs_code = req.hs_code or stored_request.get("hs_code")
        hs_note = None
        # ثقةُ التصنيف تُحمَل ولا تُهدَر (بلاغ «حليب نادك»): كان يُؤخَذ
        # `dp.value` وحده وتُرمى `dp.confidence`، فلا تصل النتيجةَ إطلاقاً —
        # ومن هناك جاء «ثقة التصنيف —» في جدول التقرير (silk_render.py:2046
        # يقرأ `result["hs_confidence"]` الغائب فيعرض شرطة الفجوة). رمزٌ
        # صريحٌ/مخزَّن = اختيارُ مستخدمٍ معلومُ المصدر (1.0)، كعقد المحرّك.
        # مراجعة §58 (الدرس ١٢٠): «معلومُ المصدر» يشترط إنساناً حاضراً —
        # كتب الرمزَ الآن (`_hs_user_supplied`)، أو أكّده صراحةً
        # (`hs_confirmed`)، أو حسمه وقتَ إنشاء تشغيلةٍ يُستأنف منها. رمزُ
        # كتالوجٍ مُعادٌ بلا أيٍّ من ذلك ثقتُه **غير معلومة** (None) — لا
        # تُختلَق 1.00 على وجه التقرير، وبوّابةُ الثقة (فشل-آمن: None تحجب
        # بمرشّحين) تسبق المحور فيُسأل المصنعُ قبل أيّ إنفاق.
        # **الاستئنافُ وحده يحتفظ برمزه**: تشغيلةٌ محفوظة حُسِم رمزُها وقت
        # إنشائها ودُفِع ثمنُها؛ إعادةُ تصنيفها تُفقِد المالكَ عملاً مكتملاً.
        # ما عداه — كتالوجاً كان أو رمزاً مكتوباً — يُقاس على اسم المنتج.
        hs_classification = None
        if req.resume is not None:
            hs_confidence = 1.0 if hs_code else None
        else:
            hs_code, hs_confidence, hs_classification, _cls_block = \
                _classify_product_hs(product, hs_code, req,
                                     gl=(market_ref.iso2 or None))
            if _cls_block is not None:
                import silk_ops_log
                silk_ops_log.record_error(
                    _cls_block["error"],
                    f"لم يُحسَم البند الجمركي لمنتج {product!r}: "
                    f"{_cls_block['message']}",
                    context={"product": product,
                             "market_iso3": market_ref.iso3,
                             "hs_code": _cls_block.get("hs_code"),
                             "hs_confidence": _cls_block.get("hs_confidence"),
                             "top_candidate_score":
                                 _cls_block.get("top_candidate_score"),
                             "candidates": [c["hs6"] for c
                                            in _cls_block["candidates"]]})
                raise HTTPException(status_code=422, detail=_cls_block)
            if hs_code is None:
                hs_note = (hs_classification or {}).get("reason")

        # بوّابة HS الصلبة (Wave 1، عائلة unresolved-hs-silent-spend): رفضُ
        # الحجز/الإنفاق ما دام hs6 فارغًا — 422 **قبل** أيّ تفعيلة أو دولار.
        # تُغلق حادثةَ الفيتوتشيني (أُنفِق $ والغلاف «—» والركيزة التجارية فجوة
        # حرجة): لا تعود ممكنة حين يُفعَّل الصمّام. المُصنِّف (`/classify_hs`)
        # يمنع الوصولَ لهنا فارغًا في التدفّق. مُطفأ افتراضيًا (SILK_REQUIRE_HS6)
        # => السلوك كاليوم. يُتخطّى عند الاستئناف (رمزُه محسومٌ وقت الإنشاء).
        if req.resume is None and not hs_code and _require_hs6():
            import silk_ops_log
            silk_ops_log.record_error(
                "unresolved_hs_blocked",
                f"رُفض بدءُ بحثٍ برمز HS غير محسوم لمنتج {product!r} "
                f"(السوق {market_ref.iso3})",
                context={"product": product, "market_iso3": market_ref.iso3,
                         "hs_note": hs_note})
            raise HTTPException(status_code=422, detail={
                "error": "unresolved_hs",
                "message": "تعذّر تحديد رمز HS لهذا المنتج — صنِّفه أولًا "
                           "(/classify_hs) أو اختر الرمز يدويًا قبل بدء البحث.",
                "hs_note": hs_note})

        # بوّابة تأكيد رمز HS (Wave 1.2، عائلة unresolved-hs-silent-spend
        # موسَّعةً — تدقيق زبدة الفول السوداني/اليمن؛ الموجة ٢ (2026-07-21):
        # المنطق يعيش الآن في `silk_hs_confirm.preflight_block` — نقطة
        # اختناق واحدة يستدعيها **كل** من `/research` و`/analyze` (أدناه)
        # بلا نسخ؛ إصلاحٌ سابق على `/research` وحده عاود الظهور فتوحّد
        # هنا). رمزٌ محسومٌ لكنه **خاطئ دلالياً** يُوقِف **قبل** أيّ حجز/دولار
        # ويطلب تأكيد المستخدم. فشل-آمن: مفعّلة افتراضياً (`gate_enabled`).
        # تُتخطّى عند الاستئناف وعند تأكيد المستخدم الصريح (hs_confirmed=True).
        hs_provenance: dict | None = None
        if req.resume is None:
            # بلاغ المُشرِف: تُقاس العتبةُ الرقمية (بطاقةُ العبوة ثم استعلامُ
            # ويبٍ واحد) قبل عرض أيّ حوار — نفسُ نقطة الاختناق التي يستدعيها
            # `/analyze` (لا إصلاحَ على مسارٍ واحد، الدرسان ٣٥/٣٧).
            from silk_hs_confirm import preflight_resolve
            _resolved_hs, hs_provenance, _blocked = preflight_resolve(
                product, hs_code,
                # اعتمادُ «رمزٌ صريحٌ باسمٍ فارغ» يُكرَّم كما يُكرَّم
                # التأكيدُ الصريح — المسارُ الثالث من الثلاثة نفسِها.
                (getattr(req, "hs_confirmed", False)
                 or _hs_explicitly_settled(hs_classification)),
                allow_claude=_classify_general_allow_claude(),
                # بوّابة الثقة تُفحَص هنا أيضاً — **قبل** الحجز والدولار.
                hs_confidence=hs_confidence,
                label_attributes=req.label_attributes,
                gl=(market_ref.iso2 or None),
                # المهمة ١٤: عقدُ التصنيف المحسوم يُمرَّر (الاستئنافُ بلا
                # عقدٍ أصلاً — `hs_classification=None` فيبقى كما كان).
                settled_contract=hs_classification,
                # رمزٌ صريحٌ في الطلب = اختيارُ مشغّلٍ مقصود (بلاغ 040120) —
                # إلا رمزَ كتالوجٍ مُعاداً (hs_source="catalog"): ليس إجابةَ
                # سؤال المحور فيواجه البوّابات كاملةً (حادثة الدراسة #10).
                user_supplied=_hs_user_supplied(req))
            if hs_provenance is not None:
                # رمزٌ مقيسٌ بدليلٍ موسوم يحلّ محلّ الملتبِس، وثقتُه من دليله
                # لا من مطابقةٍ لفظية (صورةُ عبوةٍ ١٫٠، رابطُ ويبٍ ثانويّ).
                hs_code = _resolved_hs
                hs_confidence = hs_provenance.get("confidence")
                import silk_ops_log
                silk_ops_log.record_error(
                    "hs_auto_resolved",
                    f"حُسِم رمزُ HS آلياً لمنتج {product!r} => {hs_code} "
                    f"({hs_provenance.get('resolved_from')})",
                    context={"product": product, "hs_code": hs_code,
                             "market_iso3": market_ref.iso3,
                             "resolved_from": hs_provenance.get("resolved_from"),
                             "value": hs_provenance.get("value"),
                             "source_url": hs_provenance.get("source_url")})
            if _blocked is not None:
                import silk_ops_log
                # البوّابة صارت بوّابتين (ثقة + تطابق دلالي) بشكلَي ردٍّ
                # مختلفَين — السجلّ يقرأ ما هو موجود فعلاً، لا مفتاحاً بعينه.
                _conf_detail = _blocked.get("hs_confirmation") or {}
                silk_ops_log.record_error(
                    _blocked.get("error") or "hs_confirmation_blocked",
                    f"رُفض بدءُ بحثٍ برمز HS غير محسوم لمنتج {product!r}: "
                    f"{_conf_detail.get('reason') or _blocked.get('message')}",
                    context={"product": product, "hs_code": hs_code,
                             "market_iso3": market_ref.iso3,
                             "hs_confidence": _blocked.get("hs_confidence"),
                             "min_confidence": _blocked.get("min_confidence"),
                             "attribute_probe": _blocked.get("attribute_probe"),
                             "missing_terms": _conf_detail.get("missing_terms")})
                raise HTTPException(status_code=422, detail=_blocked)

        # بوّابةُ الالتباس داخل الترويسة (البند ٣ — تحصينٌ وقائيّ لا إصلاحُ
        # عطلٍ مُثبَت). تصحيحُ المالك مُسجَّل: حادثةُ «نادك» **لم تكن** التباساً
        # — `resolve` أعاد 040120 الصحيح؛ الرمزُ الخاطئ دخل عبر مسارٍ بلا
        # بوّابة (أُغلِق في البند ١). هذه البوّابة تعالج خطراً **مختلفاً** لم
        # يقع بعد: 040110/040120/040150 تتمايز بنسبةِ دسمٍ رقمية لا بكلمة،
        # فالمُحلِّل الحتمي قد يحسم واحداً منها بثقةٍ عالية وهو مخطئ.
        # `silk_hs_classifier.classify_general` يملك القاعدةَ الصحيحة أصلاً
        # (`_clearly_auto`: لا حسمَ تلقائيّ حين يتقارب المرشّحان ضمن
        # `_AUTO_MARGIN`) — لكنّ المسارَين كانا يتجاوزانه إلى `resolve` المجرّد.
        # هنا يُوصَل على `/research` **وحده** (المسار الأغلى؛ سؤالٌ واحدٌ قبله
        # أرخص من تقريرٍ كاملٍ على رمزٍ خاطئ)، وبلا أيّ نداء كلود
        # (`allow_claude=False`) فيبقى مجانياً وحتمياً.
        # صمّام: SILK_RESEARCH_AMBIGUITY_GATE=0 يعطّله.
        if (req.resume is None and not req.hs_code
                and not getattr(req, "hs_confirmed", False)
                and _research_ambiguity_gate_enabled()):
            import silk_hs_classifier as _hsc
            _cls = _hsc.classify_general(product or "", allow_claude=False)
            if _cls.get("tier") != "auto" and (_cls.get("candidates") or []):
                import silk_ops_log
                # بلاغ المُشرِف — هذه هي البوّابةُ التي أنتجت السؤالَ حرفياً
                # («إن كان … كامل الدسم (أكثر من ٦٪)»). العتبةُ التي كانت
                # تُسأل تُقاس هنا أولاً: بطاقةُ العبوة ثم استعلامُ ويبٍ واحد.
                from silk_hs_confirm import resolve_or_probe, _probe_public
                _probe = resolve_or_probe(
                    product or "", _cls.get("candidates") or [],
                    label_attributes=req.label_attributes,
                    gl=(market_ref.iso2 or None))
                if _probe.get("hs6"):
                    hs_code = _probe["hs6"]
                    hs_confidence = _probe.get("confidence")
                    hs_provenance = _probe
                    silk_ops_log.record_error(
                        "hs_auto_resolved",
                        f"حُسِم التباسُ رمز HS آلياً لمنتج {product!r} => "
                        f"{hs_code} ({_probe.get('resolved_from')})",
                        context={"product": product, "hs_code": hs_code,
                                 "market_iso3": market_ref.iso3,
                                 "resolved_from": _probe.get("resolved_from"),
                                 "value": _probe.get("value"),
                                 "source_url": _probe.get("source_url")})
                else:
                    silk_ops_log.record_error(
                        "hs_ambiguous_blocked",
                        f"رُفض بدءُ بحثٍ لالتباسِ رمز HS لمنتج {product!r} — "
                        f"مرشّحون: "
                        f"{[c.get('hs6') for c in _cls['candidates']]}",
                        context={"product": product, "hs_code": hs_code,
                                 "market_iso3": market_ref.iso3,
                                 "attribute_probe": _probe_public(_probe),
                                 "tier": _cls.get("tier")})
                    raise HTTPException(status_code=422, detail={
                        "error": "hs_ambiguous",
                        "message": (
                            f"«{product}» يطابق أكثر من رمزٍ مقبول بفارقٍ غير "
                            "حاسم — والفارقُ بين البنود قياسٌ رقميّ حاولنا "
                            "قراءته من صورة العبوة ومن مصادر الويب ولم نجده. "
                            "أرفِق صورة العبوة أو اختر البند المطابق أدناه."),
                        "hs_code_deterministic": hs_code,
                        "candidates": _cls.get("candidates") or [],
                        "candidates_source": _cls.get("source"),
                        "attribute_probe": _probe_public(_probe),
                    })

        # بوابة «خارج التغطية» (اتفاق المالك) — تسبق الجهوزية/الحجز: مع تفعيل
        # تغطية العالم، سوقٌ ليس Tier-1 ولا ضمن مجموعة أكبر مستوردي هذا الرمز
        # (Tier-2 الديناميكية) يُعاد برسالةٍ صادقة «تواصل معنا لإضافتها» بدل
        # دراسةٍ هزيلة، ويُسجَّل إشارةَ طلبٍ في سجلّ العمليات (طلب فعلي غير مغطّى).
        # الصمّام مُطفأ => السلوك كاليوم (أيّ دولة تعمل، فجوات معلنة) بلا انحدار.
        from silk_market_ranker import _world_markets_enabled
        if _world_markets_enabled():
            _covered, _determinable = _market_in_coverage(
                hs_code, market_ref.iso3)
            if _determinable and not _covered:
                import silk_ops_log
                silk_ops_log.record_error(
                    "out_of_coverage_demand",
                    f"طلب بحث لسوقٍ خارج التغطية الحالية: "
                    f"{market_ref.name_en} ({market_ref.iso3}) "
                    f"لرمز HS {hs_code}",
                    context={"product": product,
                             "market_iso3": market_ref.iso3,
                             "hs_code": hs_code})
                raise HTTPException(status_code=422, detail={
                    "error": "out_of_coverage",
                    "message": "هذه السوق خارج التغطية الحالية — "
                               "تواصل معنا لإضافتها"})

        # استشارة بلد المنشأ (Wave 1، قاعدة عامّة مبنيّة على البيانات): سوقٌ من
        # أكبر مصدّري هذا الرمز عالميًا => تحذيرٌ استشاري (422) حتى موافقةٍ صريحة
        # (`producer_ack`). زيرو نداء مدفوع (كلود/سقف) — كومتريد فقط بميزانيته.
        # الاستشارة تُسجَّل (shown/consent). الصمّام مُطفأ (SILK_PRODUCER_ADVISORY)
        # => السلوك كاليوم. يُتخطّى عند الاستئناف (وافق المستخدم وقت الإنشاء).
        if req.resume is None and hs_code and _producer_advisory_enabled():
            import silk_ops_log
            import datetime as _dt
            from silk_market_ranker import is_top_world_exporter
            _is_top, _top = is_top_world_exporter(
                hs_code, market_ref.iso3, _dt.date.today().year - 1)
            if _is_top and not req.producer_ack:
                silk_ops_log.record_error(
                    "producer_advisory_shown",
                    f"استشارةُ بلد المنشأ: {market_ref.iso3} من أكبر مصدّري "
                    f"HS {hs_code} عالميًا — دراسةُ دخولها تنافسية جدًّا",
                    context={"product": product,
                             "market_iso3": market_ref.iso3, "hs_code": hs_code,
                             "top_exporters": [t["iso3"] for t in _top]})
                raise HTTPException(status_code=422, detail={
                    "error": "producer_country_advisory",
                    "message": "⚠ هذه الدولة من أكبر مصدّري هذا المنتج عالميًا "
                               "— دراسة دخولها تنافسية جدًّا. أكمل؟",
                    "top_exporters": [t["iso3"] for t in _top],
                    "needs_ack": True})
            if _is_top and req.producer_ack:
                silk_ops_log.record_error(
                    "producer_advisory_consent",
                    f"موافقةٌ صريحة على دراسة {market_ref.iso3} (من أكبر "
                    f"مصدّري HS {hs_code} عالميًا)",
                    context={"product": product,
                             "market_iso3": market_ref.iso3, "hs_code": hs_code})

        # البند أ٢ — معقولية بلد المورّد (إشارةٌ اقتصاديةٌ مُعاضِدةٌ لتأكيد الرمز):
        # تفكّكٌ شبه تامٌّ بين موردي السوق الفعليين وأكبر مصدّري الرمز عالميًا =>
        # الرمز قد يصف عائلةً مختلفة (حادثة زبدة الفول السوداني/الألبان). تحذيرٌ
        # حاجبٌ (422) حتى موافقةٍ صريحة (`a2_ack`) تؤكّد الرمز أو تعيد التصنيف —
        # لا رفضٌ نهائي (قد يعرف المستخدم رمزه صحيح). صفر نداء مدفوع (كومتريد
        # فقط بميزانيته). مُطفأ افتراضيًا (SILK_A2_PLAUSIBILITY) => السلوك كاليوم.
        # يُتخطّى عند الاستئناف (وافق المستخدم وقت الإنشاء). المذكّرة:
        # docs/DESIGN_A2_SUPPLIER_PLAUSIBILITY.md.
        if req.resume is None and hs_code:
            from silk_market_ranker import (_a2_plausibility_enabled,
                                            supplier_plausibility)
            if _a2_plausibility_enabled():
                import datetime as _dt2
                _a2 = supplier_plausibility(
                    hs_code, market_ref.iso3, market_ref.m49,
                    _dt2.date.today().year - 1)
                if _a2 and _a2.get("implausible") and not req.a2_ack:
                    import silk_ops_log
                    silk_ops_log.record_error(
                        "a2_plausibility_shown",
                        f"معقولية بلد المورّد ({market_ref.iso3}): موردو السوق "
                        f"{_a2['market_suppliers']} لا يظهرون بين أكبر مصدّري "
                        f"HS {hs_code} عالميًا {_a2['world_exporters']}",
                        context={"product": product,
                                 "market_iso3": market_ref.iso3,
                                 "hs_code": hs_code, "overlap": _a2["overlap"]})
                    raise HTTPException(status_code=422, detail={
                        "error": "supplier_plausibility_advisory",
                        "message": "⚠ كبار موردي هذه السوق لهذا الرمز لا يظهرون "
                                   "بين أكبر مصدّري الرمز عالميًا — قد يكون الرمز "
                                   "يصف عائلة منتجٍ مختلفة. راجع التصنيف أو أكّد "
                                   "الرمز للمتابعة.",
                        "market_suppliers": _a2["market_suppliers"],
                        "world_exporters": _a2["world_exporters"],
                        "overlap": _a2["overlap"],
                        "needs_ack": True})
                if _a2 and _a2.get("implausible") and req.a2_ack:
                    import silk_ops_log
                    silk_ops_log.record_error(
                        "a2_plausibility_consent",
                        f"موافقةٌ صريحة على رمز HS {hs_code} رغم تحذير معقولية "
                        f"بلد المورّد ({market_ref.iso3})",
                        context={"product": product,
                                 "market_iso3": market_ref.iso3,
                                 "hs_code": hs_code})

        # أشقّاء عائلة «الدراسة بالاتجاه الخاطئ» (Wave 1.5، عائلة A): تصدير إلى
        # بلد المنشأ / سوق تحت عقوبات / فصل مقيَّد قانونيًا — config-driven، صفر
        # نداء مدفوع. تحذيرٌ (422) حتى موافقةٍ موحّدة (`advisories_ack`). مُطفأ
        # افتراضيًا (SILK_PRERUN_ADVISORIES) => السلوك كاليوم. يُتخطّى عند الاستئناف.
        if req.resume is None:
            import silk_prerun
            if silk_prerun.advisories_enabled():
                _sib = silk_prerun.sibling_advisories(hs_code, market_ref.iso3)
                if _sib and not req.advisories_ack:
                    import silk_ops_log
                    silk_ops_log.record_error(
                        "prerun_advisory_shown",
                        f"استشارةُ ما قبل التشغيل ({market_ref.iso3}): "
                        + "؛ ".join(a["kind"] for a in _sib),
                        context={"product": product,
                                 "market_iso3": market_ref.iso3,
                                 "hs_code": hs_code,
                                 "kinds": [a["kind"] for a in _sib]})
                    raise HTTPException(status_code=422, detail={
                        "error": "prerun_advisory",
                        "message": _sib[0]["message"],
                        "advisories": _sib, "needs_ack": True})
                if _sib and req.advisories_ack:
                    import silk_ops_log
                    silk_ops_log.record_error(
                        "prerun_advisory_consent",
                        f"موافقةٌ صريحة على أشقّاء استشارة {market_ref.iso3}",
                        context={"product": product,
                                 "market_iso3": market_ref.iso3,
                                 "hs_code": hs_code,
                                 "kinds": [a["kind"] for a in _sib]})

        # بوابة ما قبل التشغيل بعد التحقق من صحة الإدخال (422 على خطأ
        # الطالب يسبق 409 على جهوزية الخادم — خطأ العميل يستحق أن يُشرَح
        # حتى لو كان الخادم متدهوراً الآن) وقبل تشغيل أي بعثة أو حجز ميزانية.
        ready, ready_reason = _research_readiness()
        if not ready and not req.allow_degraded:
            raise HTTPException(status_code=409, detail={
                "error": "research_not_ready", "reason": ready_reason,
                "hint": "اضبط ANTHROPIC_API_KEY (وSILK_API_KEY إن لزم) ثم "
                        "أعد المحاولة، أو مرّر allow_degraded=true لتسليم "
                        "تقرير موسوم صراحة كمتدهور (غير مُنصَح به تسليمياً)."})

        # H6 (تدقيق): بوابة الميزانية الدولارية اليومية — تحجز تكلفة التشغيلة
        # المتوقَّعة ذرّيًا قبل بدئها (try_reserve_usd، لا فحص قراءة فقط)، فلا
        # يمكن لتشغيلتين متزامنتين قرب السقف أن تمرّا معًا وتتجاوزا الحدّ (سباق
        # TOCTOU مسدود — نفس نمط عدّاد التفعيلات الذرّي). السقف غير مضبوط => لا
        # حجب. الإنفاق الفعلي يُصالَح بعد التشغيلة في _run_research_pipeline
        # (reconcile_usd) فيحمل الدفتر المُنفَق الحقيقي لا التقدير. تسبق حجز
        # عدّاد التفعيلات كي لا تُستهلك تفعيلة على طلب مرفوض. الاستئناف المكتمل
        # رجع مبكراً قبل هنا.
        # R2b (API-14/CONC-4): سقفُ تشغيلات HTTP المتزامنة — تشغيلاتُ المنصّة
        # (تصل عبر `on_allocated`) مسقوفةٌ في `study_runtime` فلا تمرّ من هنا.
        # الفتحةُ تُحجَز **قبل** الحجز الدولاري ويُحرَّر كلاهما عند أيّ رفضٍ لاحق.
        _run_origin = "platform" if on_allocated is not None else "http"
        if _run_origin == "http" and not silk_research_runtime.try_acquire():
            raise HTTPException(status_code=503, detail={
                "error": "research_busy", "retry_after_s": 60,
                "reason": (f"{silk_research_runtime.max_concurrent()} deep-research "
                           "runs are already executing — retry shortly")},
                headers={"Retry-After": "60"})
        _slot_held = _run_origin == "http"
        # مراجعة R2b: مالكٌ واحد للفتحة — الذيلُ يعلن `owned` حين يصير تحريرُها
        # مسؤوليّتَه (تسجيلُ الخيط الخلفي، أو دخولُ التشغيلة المتزامنة)؛ قبل ذلك
        # يحرّرها هذا الغلاف. كان يحرّرها **ثانيةً** بعد `finally` الذيل (متغيّرُ
        # `analysis_id` هنا None) فيقبل السقفُ واحداً زيادة.
        _adm = {"owned": False}
        try:
            return _research_impl_after_admission(
                req, on_allocated, _run_origin, run_row, stored_request,
                resume_reports, resume_stages, analysis_id, market_ref,
                market_name, product, hs_code, hs_note, hs_confidence,
                hs_provenance, hs_classification, ready, ready_reason,
                _adm=_adm)
        except BaseException:
            if _slot_held and not _adm["owned"]:
                silk_research_runtime._release_slot()
            raise

    def _research_impl_after_admission(req, on_allocated, _run_origin, run_row,
                                       stored_request, resume_reports,
                                       resume_stages, analysis_id, market_ref,
                                       market_name, product, hs_code, hs_note,
                                       hs_confidence, hs_provenance,
                                       hs_classification, ready, ready_reason,
                                       _adm=None):
        """ذيلُ `_research_impl` بعد قبول التشغيلة في السقف — الحجزُ الدولاري،
        صفُّ التشغيلة، ثم التشغيل (خلفياً أو متزامناً) تحت سجلّ `silk_research_runtime`."""
        _expected_usd = _expected_run_usd()   # مراجعة §58 #11: قراءة محروسة
        if not silk_usage.try_reserve_usd(_expected_usd):
            # ITEM 5ب: رفض حجز بحالة السقف — نص خادمي بحت، لا محتوى كلود.
            import silk_ops_log
            silk_ops_log.record_error(
                "reservation_refused",
                f"الميزانية اليومية بالدولار أوشكت على النفاد — "
                f"أُنفِق {round(silk_usage.usd_spent_today(), 2)}$ اليوم",
                context={"expected_usd": _expected_usd,
                        "spent_today_usd": round(silk_usage.usd_spent_today(), 2)})
            raise HTTPException(status_code=429, detail={
                "error": "daily_usd_budget_exhausted",
                "reason": f"الميزانية اليومية بالدولار أوشكت على النفاد — "
                          f"أُنفِق {round(silk_usage.usd_spent_today(), 2)}$ اليوم؛ "
                          f"تشغيلة /research متوقَّعة بنحو {_expected_usd}$."})

        if req.resume is not None:
            from silk_storage import claim_research_resume
            try:
                claimed = claim_research_resume(analysis_id, expected=run_row)
            except Exception as exc:
                silk_usage.reconcile_usd(reserved=_expected_usd, actual=0.0)
                raise HTTPException(status_code=500, detail={
                    "error": "resume_claim_failed", "error_type": type(exc).__name__,
                    "analysis_id": analysis_id,
                    "reason": "تعذّر حجز الاستئناف — لم يبدأ التنفيذ"}) from exc
            if not claimed:
                silk_usage.reconcile_usd(reserved=_expected_usd, actual=0.0)
                raise HTTPException(status_code=409, detail={
                    "error": "resume_still_running", "analysis_id": analysis_id,
                    "reason": "تغيّرت التشغيلة أثناء الطلب — حدّث حالتها قبل الاستئناف"})
            if on_allocated is not None:
                try:
                    on_allocated(analysis_id)
                except Exception as exc:
                    log.warning("on_allocated failed for %s: %s", analysis_id, exc)

        # (رمز HS + hs_note حُسِما أعلاه قبل البوّابات والحجز — Wave 1.)
        ai_ok, ai_note = _free_ai_extras_allowed()
        prefs = _clean_agent_prefs(req.agent_prefs)
        if prefs is None:
            prefs = stored_request.get("agent_prefs") or _saved_agent_settings()

        # بطاقة المنتج — بلاغ حي (الموجة ٩): كانت تُقبَل في النموذج ولا تصل
        # أي بعثة أو المحلل إطلاقاً، فيغيب "الموقع التنافسي"/هامش المضاهاة
        # من كل تقرير بحث عميق رغم إرسال المستخدم للبطاقة فعلياً.
        product_card_dict = (req.product_card.model_dump() if req.product_card
                             else stored_request.get("product_card"))
        # هدف الدراسة الاحترافية (البند ٢): تكلفة الإنتاج المُدخلة تُدمج في
        # البطاقة (أو تبنيها وحدها) — الطلب الصريح يغلب الكتالوج المخزَّن.
        _prod_cost = (req.production_cost_per_unit
                      if req.production_cost_per_unit is not None
                      else stored_request.get("production_cost_per_unit"))
        if _prod_cost is not None:
            product_card_dict = _apply_production_cost(product_card_dict,
                                                       _prod_cost)
        own_price = (req.own_price if req.own_price is not None
                    else stored_request.get("own_price"))
        if product_card_dict is not None and own_price is not None:
            product_card_dict = dict(product_card_dict)
            product_card_dict["own_price"] = own_price

        if analysis_id is None and req.persist:
            from silk_storage import create_research_run
            request_snapshot = {
                "product": product, "market": market_name,
                # الموجة ٢ (بوّابة نطاق السوق أعلاه): iso3 مُخزَّن بنيوياً —
                # لا استنتاج لاحق من اسمٍ عربي/إنجليزي غامض عند الاستئناف.
                "market_iso3": market_ref.iso3, "hs_code": hs_code,
                "product_card": product_card_dict, "own_price": own_price,
                "production_cost_per_unit": _prod_cost,
                "agent_prefs": prefs, "allow_degraded": req.allow_degraded}
            try:
                analysis_id = create_research_run(
                    product, market_ref.iso3, hs_code, request_snapshot,
                    market_name=market_ref.name_ar or market_ref.name_en)
            except Exception as _cre:  # noqa: BLE001 — R2b (API-16)
                # الحجزُ الدولاري سبق صفَّ التشغيلة — عطبٌ هنا كان يترك حجزاً بلا
                # صفٍّ يصالحه أحد (لا حاصدَ يراه). يُعوَّض فوراً ثم يُعلَن.
                silk_usage.reconcile_usd(reserved=_expected_usd, actual=0.0)
                log.error("create_research_run failed: %s", _cre)
                raise HTTPException(status_code=500, detail={
                    "error": "research_run_create_failed",
                    "error_type": type(_cre).__name__,
                    "reason": "تعذّر تسجيل صفّ التشغيلة — أُعيد الحجز الدولاري "
                              "ولم يُنفَق شيء"}) from _cre
            # R2: المعرّف يُربَط بصفّ تشغيلة المنصّة **قبل** أيّ بعثة — فموتُ
            # العملية بعد الحفظ وقبل الربط لا يُيتّم تحليلاً مدفوعاً.
            if on_allocated is not None:
                try:
                    on_allocated(analysis_id)
                except Exception as _oa:  # noqa: BLE001 — ربطٌ تحسيني لا شرطُ تشغيل
                    log.warning("on_allocated failed for %s: %s", analysis_id, _oa)

        # الموجة ٠: لغة هذه التشغيلة — من لقطة الدراسة التي يمرّرها جسر
        # المنصّة حصراً؛ الغياب ⇒ عربي. لا ترويسة ولا لغة واجهة ولا تفضيل
        # مستخدم يصل هنا بأيّ مسار (يُقفَل بحارس AST في الاختبارات).
        _req_lang = silk_i18n.normalize(getattr(req, "lang", None))

        # R2b (CONC-10): هويّةُ الإقلاع على لقطة التقدّم — تسمّي صاحبَ التشغيلة
        # في 409 `resume_still_running` وسطرِ الحاصد؛ الحكمُ يبقى للنبضة.
        if analysis_id is not None:
            try:
                from silk_storage import update_research_progress as _urp
                _urp(analysis_id, boot_id=silk_research_runtime.boot_id())
            except Exception as _bi:  # noqa: BLE001 — لقطةٌ تحسينية
                log.warning("boot_id stamp failed for %s: %s", analysis_id, _bi)

        if req.async_run:
            if analysis_id is None:
                raise HTTPException(status_code=400, detail={
                    "error": "async_requires_persist",
                    "reason": "async_run=true needs persist=true (or an "
                             "existing resume target) — otherwise there is "
                             "no analysis_id to poll a status for."})
            # R2b (API-14): التشغيلةُ تُسجَّل **قبل** بدء الخيط — فالسجلّ يراها من
            # أوّل لحظة، والإلغاءُ/الإغلاقُ يجدان مقبضَها.
            _rh = silk_research_runtime.register(analysis_id, origin=_run_origin)
            if _adm is not None:
                _adm["owned"] = True
            _t = threading.Thread(
                target=_research_background,
                args=(market_ref, product, hs_code, hs_note, product_card_dict,
                     ai_ok, ai_note, prefs, ready, ready_reason, analysis_id,
                     resume_reports, req.report_style, hs_confidence,
                     hs_provenance, _req_lang, resume_stages,
                     # ملخّصُ التصنيف يُمرَّر **كوسيط** لا يُلتقَط من نطاقٍ
                     # خارجيّ: الخيطُ الخلفي دالّةٌ مستقلّة، والالتقاطُ هناك
                     # `NameError` يقع داخل خيطٍ فيُبتلَع سبباً غامضاً.
                     _hs_classification_summary(hs_classification)),
                daemon=True)
            _rh.thread = _t
            try:
                _t.start()
            except Exception as _ts:  # noqa: BLE001 — مراجعة R2b: حدُّ الخيوط
                # في حاويةٍ ضيّقة: المقبضُ كان يبقى مسجَّلاً للأبد (409 دائم،
                # إلغاءٌ لخيطٍ لا وجود له) والصفُّ `running` حتى الحاصد.
                silk_research_runtime.release(analysis_id)
                from silk_storage import (mark_research_failed,
                                          reconcile_failed_run_usd)
                mark_research_failed(
                    analysis_id, f"thread start failed: {type(_ts).__name__}: {_ts}")
                reconcile_failed_run_usd(analysis_id)
                log.error("background research thread for %s could not start: %s",
                          analysis_id, _ts)
                raise HTTPException(status_code=500, detail={
                    "error": "research_thread_start_failed",
                    "error_type": type(_ts).__name__,
                    "analysis_id": analysis_id,
                    "reason": "تعذّر بدءُ خيط التشغيلة الخلفي — وُسم الصفُّ فاشلاً "
                              "وصولح الحجز؛ أعد المحاولة أو استأنف بـresume"}) from _ts
            return JSONResponse(status_code=202, content={
                "analysis_id": analysis_id, "status": "running",
                "async": True,
                "poll_url": f"/research/{analysis_id}/status"})

        _stage = "pipeline"
        _rh = (silk_research_runtime.register(analysis_id, origin=_run_origin)
               if analysis_id is not None else None)
        if _adm is not None:
            _adm["owned"] = True
        try:
            # R2b (API-14): حدثُ الإلغاء من السجلّ — أو حدثُ المنصّة إن كنّا داخل
            # سياق إلغاءٍ قائم (تشغيلةُ جسر المنصّة تحمل حدثَها من `study_runtime`).
            _outer = silk_context._cancel.get()
            if _rh is not None:
                _rh.outer = _outer
            with silk_context.cancel_context(_outer or (_rh.cancel if _rh else None)):
                result = _run_research_pipeline(
                    market_ref, product, hs_code, hs_note, product_card_dict,
                    ai_ok, ai_note, prefs, ready, ready_reason, analysis_id,
                    resume_reports, req.report_style, hs_confidence=hs_confidence,
                    hs_provenance=hs_provenance, lang=_req_lang,
                    hs_classification=_hs_classification_summary(hs_classification),
                    resume_stages=resume_stages)
            # R2b (API-5): الحفظُ النهائي **داخل** try — فشلُه كان 500 عارياً يترك
            # الصفّ `running` ويُضيع تقريراً مدفوعاً لم يُحفَظ نقطةَ تفتيش قطّ.
            _stage = "save"
            _finish_research_run(analysis_id, result)  # no-op إن persist=false
        except Exception as e:  # noqa: BLE001 — P0: فشل لا يخسر البعثات المكتملة
            log.error("sync /research run %s failed at %s: %s", analysis_id, _stage, e)
            if analysis_id is not None:
                from silk_storage import (mark_research_failed,
                                          reconcile_failed_run_usd)
                # R7 (API-9/SEC-10): نصُّ الاستثناء الخام قد يحمل رابطاً بمفتاحٍ أو
                # جزءَ ردٍّ من مزوّد — يُنقَّح قبل التخزين ولا يبلغ الجسمَ أصلاً؛
                # الجسمُ يسمّي الصنفَ وجملةً عامّة.
                mark_research_failed(
                    analysis_id, _redact_text(f"{type(e).__name__}: {e}")[:500])
                reconcile_failed_run_usd(analysis_id)  # البند #3 الموجة ٢
                raise HTTPException(status_code=500, detail={
                    "error": "research_run_failed",
                    "stage": _stage,
                    "error_type": type(e).__name__,
                    "reason": "تعذّرت التشغيلة — البعثات المكتملة محفوظة ويمكن "
                              "الاستئناف؛ التفصيلُ في سجلّ الخادم",
                    "analysis_id": analysis_id,
                    "hint": f"البعثات المكتملة قبل العطل محفوظة — أعد "
                            f"المحاولة بـ resume={analysis_id} بدل تشغيلة "
                            "كاملة جديدة (لا حرق اعتمادات مضاعف)."}) from e
            raise
        finally:
            if _rh is not None:
                silk_research_runtime.release(analysis_id)
            elif _run_origin == "http":
                # مراجعة R2b: تشغيلةٌ متزامنة بلا صفّ (persist=false) لا مقبضَ لها
                # — فتحتُها كانت تتسرّب عند كلّ نجاح.
                silk_research_runtime._release_slot()
        # §58 موجة A: يعيد الجسمُ الحمولةَ قاموساً جاهزاً للتسلسل (لا JSONResponse)
        # — فمستهلك البوابة (جسر المنصّة) يقرؤها مباشرة بلا دورة تسلسل/تفكيك
        # لنتيجةٍ بمئات الكيلوبايتات، والنقطة أدناه تغلّفها للردّ.
        return _to_jsonable(result)

    @app.post("/research")
    def research(req: ResearchRequest, request: Request):
        """نقطة البحث العميق — حارسا المفتاح/المعدل ثم الجسم المشترك أعلاه."""
        _require_key(request)
        _rate_limit(request)
        key = request.headers.get("Idempotency-Key")
        if not key or req.resume is not None:
            out = _research_impl(req)
            return out if isinstance(out, JSONResponse) else JSONResponse(content=out)
        if len(key) > 200 or not key.strip():
            raise HTTPException(422, detail={"error": "invalid_idempotency_key"})
        from silk_request_identity import claim, bind, finish, release_unallocated
        identity, prior, mismatch = claim(key, request.headers.get("X-API-Key", "local"), req.model_dump())
        if mismatch:
            raise HTTPException(409, detail={"error": "idempotency_payload_mismatch"})
        if prior is not None:
            if prior["response_json"] is not None:
                return JSONResponse(content=json.loads(prior["response_json"]), status_code=prior["status_code"])
            if prior["analysis_id"]:
                aid = prior["analysis_id"]
                return JSONResponse(status_code=202, content={"analysis_id": aid, "status": "accepted", "replayed": True}, headers={"Location": f"/research/{aid}/status"})
            raise HTTPException(409, detail={"error": "idempotency_request_pending", "reason": "الطلب محفوظ؛ لم يبدأ طلب ثانٍ. يلزم فحص الطلب إذا انقطع الخادم قبل التخصيص."})
        with bind(identity):
            try:
                out = _research_impl(req)
            except HTTPException as exc:
                # لا تُثبّت رفضاً عابراً قبل بدء الدراسة على المفتاح للأبد.
                released = (exc.status_code in {429, 500, 502, 503, 504}
                            and release_unallocated(identity))
                if not released:
                    finish(identity, {"detail": exc.detail}, exc.status_code)
                raise
        if isinstance(out, JSONResponse):
            finish(identity, json.loads(out.body), out.status_code)
        else:
            finish(identity, out, 200)
        return out if isinstance(out, JSONResponse) else JSONResponse(content=out)

    def _platform_deep_run(product: str, market: str,
                           hs_code: str | None = None,
                           hs_confirmed: bool = False,
                           lang: str = "ar",
                           resume: int | None = None,
                           hs_source: str | None = None,
                           product_card: dict | None = None,
                           advisories_ack: bool = False,
                           on_allocated=None) -> dict:
        """تشغيلة بحث عميق لدراسة منصّة — نفس جسم `/research` حرفياً.

        R2: `on_allocated(analysis_id)` — نداءٌ اختياري من جسر المنصّة يُستدعى
        لحظة تخصيص معرّف التشغيلة (قبل أيّ بعثة) ليُربَط بصفّ `study_runs`.

        استدعاء متزامن من خيط جسر المنصّة (لا HTTP، لا مفتاح — المصادقة تمت
        في طبقة المنصّة والحصّة حُجزت قبل الوصول هنا). كل بوابات الجسم تسري
        كما هي: حسم/تأكيد رمز HS، التغطية، الجهوزية (409)، حجز الميزانية
        الدولارية (429)، النقاط المرجعية والاستئناف. `HTTPException` تصعد
        للجسر فيحوّلها سبب فشلٍ معلَناً على الدراسة (draft + run_error).
        """
        # `hs_confirmed` يصل من جسر المنصّة حين يكون المصنع قد اختار بندَه من
        # قائمة المرشّحين المعروضة (لا كتابةً عمياء) — بدونه كانت بوّابةُ
        # التأكيد ترفض الاختيارَ نفسَه الذي عرضتْه، فتُغلق الحلقة على المصنع
        # (بلاغ 2026-08-19، أُعيد إنتاجه: «حليب» ⇒ 040120 ⇒ الرسالة ذاتها).
        # هدف الدراسة الاحترافية (البند ٢) — سدُّ الثغرة الحاملة: كانت
        # البطاقة تُبنى في جسر المنصّة ثم تسقط هنا صامتةً لأن التوقيع بلا
        # `product_card` (`_runner_takes` يرفضها) — فلا هامش ولا «أرقام
        # قرار» محسوبة لأي دراسة مصنع مهما أدخل من تكلفته.
        req = ResearchRequest(product=product, market=market,
                              hs_code=(hs_code or None),
                              # جسرُ المنصّة يمرّر رمزَ الكتالوج بمصدره —
                              # فلا يُعامَل اختيارَ إنسانٍ حاضر (دراسة #10).
                              hs_source=(hs_source or None),
                              hs_confirmed=bool(hs_confirmed),
                              product_card=(product_card or None),
                              # R4.8: إقرارُ المصنع الصريح بتنبيه ما قبل
                              # التشغيل (مختومٌ على الدراسة، الترحيل ٠١٩) —
                              # بدونه كانت كلُّ دراسة منصّةٍ لها شقيقُ تحذير
                              # ترتدّ 422 `prerun_advisory` بلا أيّ مخرج.
                              advisories_ack=bool(advisories_ack),
                              lang=lang,
                              # p6/T10: استئناف تشغيلة محفوظة (نفس بوّابات
                              # /research: تطابق السوق، إعادة الكاتب فقط…)
                              resume=(int(resume) if resume else None),
                              persist=True, async_run=False)
        out = _research_impl(req, on_allocated=on_allocated)
        # `async_run=False` وبلا `resume` ⇒ الجسم يعيد قاموس النتيجة حصراً.
        assert isinstance(out, dict), type(out).__name__
        return out

    import silk_research_gateway
    silk_research_gateway.register(run=_platform_deep_run,
                                   readiness=_research_readiness)

    # تسمية عربية للمرحلة الحيّة (GET /status) — مرآة نصّية لقيم `stage` التي
    # تُسجَّلها silk_context.snapshot_research_progress (missions/analyst/
    # writer/reviewer/done). قيمة غير معروفة (تشغيلة قديمة قبل هذه الميزة،
    # بلا لقطة بعد) تعرض None لا تسمية مُخترَعة.
    _STAGE_LABEL_AR = {
        "missions": "بحث البعثات", "analyst": "تحليل شامل",
        "gap_recovery": "سدّ الفجوات",
        "enrich_leads": "إكمال بيانات المستوردين",
        "writer": "كتابة التقرير", "reviewer": "مراجعة التقرير",
        "done": "اكتمل"}

    @app.post("/research/{analysis_id}/cancel")
    def research_cancel(analysis_id: int, request: Request):
        """إلغاءٌ تعاونيّ لتشغيلة `/research` جارية — R2b (API-14). يُنفَّذ عند نقطة
        التفتيش التالية (بداية مرحلة/بعثة)؛ النداءُ الجاري يُكمِل مهلته. 202 عند
        التسجيل، 404 لصفٍّ غير موجود، 409 لتشغيلةٍ ليست حيّة في هذه العملية."""
        _require_key(request)
        _rate_limit(request)
        from silk_storage import get_research_run
        row = get_research_run(analysis_id)
        if row is None or row.get("kind") != "research":
            raise HTTPException(status_code=404,
                                detail=f"research run {analysis_id} not found")
        _h = silk_research_runtime.handle(analysis_id)
        if _h is not None and _h.origin == "platform":
            # مراجعة R2b: تشغيلةُ دراسةٍ في المنصّة يملكها `study_runtime` —
            # إلغاؤها من الجذر يتجاوز دفترَه (تنتهي «فشلاً» بلا سببِ إلغاء).
            raise HTTPException(status_code=409, detail={
                "error": "platform_owned_run", "status": row.get("status"),
                "reason": "this run belongs to a platform study — cancel the "
                          "study through the platform, not the root API"})
        if not silk_research_runtime.cancel(analysis_id, "requested"):
            raise HTTPException(status_code=409, detail={
                "error": "research_not_running", "status": row.get("status"),
                "reason": "the run is not executing in this process"})
        return JSONResponse(status_code=202, content={
            "analysis_id": analysis_id, "status": "cancelling"})

    @app.get("/research/{analysis_id}/status")
    def research_status(analysis_id: int, request: Request):
        """حالة تشغيلة بحث عميق — تقدّم لكل بعثة من الاثنتي عشرة + الحالة
        العامة (P0، حادثة نفاد الاعتمادات) — اللوحة تستطلعها دورياً بدل
        انتظار اتصال HTTP واحد طويل قد تقطعه بوّابة عكسية.

        تقدّم حيّ (المرحلة/الزمن المنقضي/التكلفة حتى الآن): من لقطة
        `silk_storage.get_research_progress` — نفس عدّادات `data_economics`
        النهائية نفسها تُقرأ أثناء التشغيل بدل عدّاد جديد. التكلفة **مُقدَّرة
        من دفتر أسعار مُسعَّر فقط** (`silk_pricing`) — نموذج غير مُسعَّر يظهر
        في `cost_unpriced_models` صراحةً بدل أن يُحتسَب صفراً بصمت (لا اختلاق).
        """
        _require_key(request)
        _rate_limit(request)
        from silk_missions import MISSION_ORDER
        from silk_storage import (get_analysis, get_research_run,
                                  mission_status_map, get_research_progress)
        run_row = get_research_run(analysis_id)
        if run_row is None or run_row.get("kind") != "research":
            raise HTTPException(status_code=404,
                                detail=f"research run {analysis_id} not found")
        done = mission_status_map(analysis_id)
        missions = {key: done.get(key, "pending") for key in MISSION_ORDER}
        progress = get_research_progress(analysis_id)
        stage = progress.get("stage")
        elapsed_seconds = None
        started_at = progress.get("started_at")
        if started_at:
            try:
                import datetime as _dt
                elapsed_seconds = round(
                    (_dt.datetime.now() - _dt.datetime.fromisoformat(started_at))
                    .total_seconds())
            except Exception:  # noqa: BLE001 — طابع زمني فاسد = فجوة لا استثناء
                elapsed_seconds = None
        # R3 (تدقيق 2026-09-01، API-6): «اكتملت» لم تكن تقول **هل ثمّة تقرير**
        # — تشغيلةٌ نجت بعثاتُها وسقط كاتبُها تُوسَم `completed` بلا نصّ، فيرى
        # المستطلِعُ نجاحاً ويجد صفحةً فارغة. القراءةُ الثقيلة (البلوب الكامل)
        # على النهائيات وحدها: الاستطلاع يقع أثناء التشغيل فلا يُحمَّل مسارُه
        # الساخن. `skip_reason` سببُ الفشل المحفوظ كما هو — لا اختلاق.
        _st = run_row.get("status")
        report_present, degraded, skip_reason = False, False, None
        if _st in ("completed", "failed"):
            try:
                _blob = get_analysis(analysis_id) or {}
            except Exception:  # noqa: BLE001 — تعذّرت القراءة = لا ادّعاء
                _blob = {}
            report_present = bool(
                ((_blob.get("deep_research") or {}).get("report") or {}
                 ).get("report"))
            degraded = _st == "completed" and not report_present
            if _st == "failed":
                skip_reason = _blob.get("error") or None
        return _json({
            "analysis_id": analysis_id, "status": run_row.get("status"),
            "product": run_row.get("product"), "hs_code": run_row.get("hs_code"),
            "created_at": run_row.get("created_at"),
            "updated_at": run_row.get("updated_at"),
            "report_present": report_present, "degraded": degraded,
            "skip_reason": skip_reason,
            # R2b (API-14): طلبُ الإلغاء معلَن للمستطلِع حتى ينفّذه الخطّ عند نقطة تفتيشه.
            "cancel_requested": silk_research_runtime.cancel_requested(analysis_id),
            "cancel_reason": (getattr(silk_research_runtime.handle(analysis_id),
                                      "reason", "") or None),
            "stage": stage, "stage_label": _STAGE_LABEL_AR.get(stage),
            "elapsed_seconds": elapsed_seconds,
            "llm_calls": progress.get("llm_calls"),
            "tool_calls": progress.get("tool_calls"),
            "cost_usd_estimate": progress.get("cost_usd_estimate"),
            "cost_unpriced_models": progress.get("cost_unpriced_models") or [],
            "missions": missions,
            "missions_completed": sum(1 for v in missions.values()
                                      if v != "pending"),
            "missions_total": len(missions),
        })

    class DiscoverRequest(BaseModel):
        """طلب اكتشاف الفرص المعكوس (الموجة ٥أ، vision §11) — سوق بدل منتج."""
        market_iso3: str
        year: int | None = None
        sector: str | None = None          # food|textile|industrial|None=الكل
        min_import_usd: float = 0.0
        with_seasonality: bool = False     # pytrends — تكميلية بوزن أدنى

    @app.post("/discover")
    def discover(req: DiscoverRequest, request: Request):
        """اكتشف فرص سوق — reverse discovery: "ما المطلوب في هذا السوق؟"

        مجاني (Comtrade + trends القائمان — صفر مصادر جديدة، §11.5-4)؛
        حارس المصادقة يعمل قبل أي جلب. كل فرصة تحمل hs_code يُمرَّر
        مباشرة إلى /analyze أو /deepen (زر "حلّل هذه الفرصة"، §11.5-3).
        """
        _require_key(request)
        _rate_limit(request)
        import silk_discovery
        return _json(silk_discovery.discover(
            req.market_iso3, req.year, sector=req.sector,
            min_import_usd=req.min_import_usd,
            with_seasonality=req.with_seasonality))

    class TrendRequest(BaseModel):
        """طلب خط الاتجاه متعدد السنوات — multi-year import-trend request."""
        hs_code: str
        market_iso3: str
        end_year: int | None = None
        span: int = 5

    @app.post("/trend")
    def trend(req: TrendRequest, request: Request):
        """خط اتجاه استيراد سوق لرمز عبر مدى سنوات — multi-year import trend.

        مجاني (Comtrade القائم — صفر مصادر جديدة)؛ حارس المصادقة يعمل قبل أي
        جلب. سنة بلا بيانات = فجوة معلنة لا صفر. نقطة API مباشرة (curl/أدوات)
        — لا سطح واجهة لها في `web/index.html` اليوم؛ خطّ الاتجاه داخل اللوحة
        يأتي من إثراء `with_trend` ضمن التحليل نفسه لا من هذه النقطة.
        (كان الوصف يدّعي «تغذّي تبويب الاتجاه في الواجهة» — تبويبٌ لا وجود له.)
        """
        _require_key(request)
        _rate_limit(request)
        import silk_trend
        from silk_data_layer import ISO3_TO_M49
        m49 = ISO3_TO_M49.get((req.market_iso3 or "").upper())
        if not m49:
            raise HTTPException(status_code=422,
                                detail=f"unknown market ISO3: {req.market_iso3}")
        end_year = req.end_year or 2023
        return _json(silk_trend.import_trend(req.hs_code, m49, end_year, req.span))

    @app.get("/diagnostics")
    def diagnostics(request: Request, year: int = 2022):
        """تشخيص المصادر الحيّ — probe each data source live with the server's keys.

        يفحص Comtrade والبنك الدولي وSerper وGoogle Maps وClaude فعلياً ويصنّف:
        متصل/فارغ/محجوب/بلا مفتاح مع تلميح إصلاح. للقراءة فقط، لا يُصدر 500.
        يخبرك على نشرك أيّ مفتاحٍ يعمل وأيّه لا.

        محروسة (مراجعة المشروع): كل نقرة تُطلق نداءاتٍ حيّةً بمفاتيح الخادم
        (Serper/Maps/Claude) — بلا مصادقةٍ وحدِّ معدّلٍ كانت باباً مفتوحاً
        لاستنزاف الرصيد من أي مجهول.
        """
        _require_key(request)
        _rate_limit(request)
        # البند ٣ (حزمة الإغلاق): /diagnostics يُطلق نداءات مدفوعة حيّة
        # (Serper/Maps/Claude) بمفاتيح الخادم، فيجب أن يحجز وحدة من السقف
        # المدفوع كأيّ مسار مدفوع — وإلا فهو ثقب يستنزف الرصيد تحت السقف. يُحجَز
        # فقط حين السقف مضبوط (بلا سقف: لا شيء يُحمى، فالسلوك الافتراضي غير
        # متأثّر). المالك يُعفيه صراحةً بـ SILK_DIAG_EXEMPT=1 (تشخيص متكرر أثناء
        # تصحيح النشر بلا استهلاك السقف — موثَّق في .env.example).
        # البند #5 (تدقيق v2 الموجة ٢) — لماذا لا حارس `_unprotected_paid_keys`
        # 503 هنا كبقية المسارات المدفوعة: قرارٌ مقصود موثَّق لا سهو. تلك
        # المسارات تُحجَب حين تُضبَط مفاتيح مدفوعة بلا SILK_API_KEY لأنها
        # إنتاجية العميل؛ أمّا /diagnostics فهو **أداة اختبار المفاتيح قبل ضبط
        # المصادقة** — غرضه أن يخبرك «أيّ مفتاح يعمل» على نشرٍ لم تُضبَط فيه
        # SILK_API_KEY بعد، فحجبُه عند غيابها يُبطِل وظيفته. حدّه الفعليّ حجزُ
        # السقف المدفوع أعلاه (اضبط SILK_PAID_DAILY_CAP حتى قبل SILK_API_KEY)
        # + حدّ المعدّل، لا حارس 503 — الفرق تعاقديّ لا ثغرة.
        _diag_exempt = os.environ.get("SILK_DIAG_EXEMPT", "").strip().lower() in (
            "1", "true", "yes", "on")
        if (not _diag_exempt and silk_usage.daily_cap() is not None
                and not silk_usage.try_reserve_paid_calls(1)):
            raise HTTPException(status_code=429, detail={
                "error": "daily_paid_cap_exhausted",
                "reason": "السقف المدفوع اليومي مُستنفَد — التشخيص يُطلق نداءات "
                          "مدفوعة حيّة فيُحجَز منه وحدة واحدة. اضبط "
                          "SILK_DIAG_EXEMPT=1 لإعفائه، أو ارفع SILK_PAID_DAILY_CAP."})
        import silk_diagnostics
        try:
            return silk_diagnostics.run_diagnostics(year)
        except Exception as e:  # noqa: BLE001 — diagnostics must never 500
            return {"overall": "unreachable", "agents_can_work": False,
                    "error": _redact_text(f"{type(e).__name__}: {e}"), "sources": []}

    @app.get("/ops/last-errors")
    def ops_last_errors(request: Request, n: int = 20):
        """ITEM 5ب (مذكّرة العمليات، تدقيق 2026-07-15): آخر n خطأ تشغيلي —
        فشل تصدير (docx 501)، فشل كاتب (تقرير None)، رفض حجز (429 بحالة
        السقف) — بلا حاجة لسجلات Railway (البروكسي يمنع الوصول لها من
        صندوق تطوير معزول عن الشبكة الحيّة؛ هذه النقطة تقطع تلك الحلقة).

        محروسة كبقية سطوح المشغّل (`/diagnostics`)؛ كل سبب مخزَّن **مُطهَّر
        مسبقاً** (`silk_render._strip_internal_plumbing`، راجع مواقع
        `silk_ops_log.record_error`) — لا `stop_reason`/تتبّع استثناء خام
        يصل هذا الردّ إطلاقاً.
        """
        _require_key(request)
        _rate_limit(request)
        import silk_ops_log
        return _json({"errors": silk_ops_log.last_errors(n)})

    @app.get("/ops/backup")
    def ops_backup(request: Request):
        """شغّل نسخاً احتياطياً الآن وأعِد المانيفست — سطح مشغّل محروس.

        يغلق فجوة «لا نسخ احتياطي إطلاقاً» (تدقيق 2026-08-17): نسخة متّسقة
        لكل المخازن القائمة عبر `sqlite3.backup` إلى `SILK_DATA_DIR/backups`
        بدورة أيام. المانيفست صادق: ما نُسخ بحجمه المقيس، وما فشل ولماذا.
        الجدولة الدورية صمّام مطفأ افتراضاً (`SILK_BACKUP_HOURS` — قرار مالك).
        """
        _require_key(request)
        _rate_limit(request)
        import silk_backup
        return _json(silk_backup.run_backup())

    @app.get("/ops/backup/{store_name}")
    def ops_backup_download(store_name: str, request: Request):
        """نزّل أحدث طبعة نسخ لمخزن مسمّى — كي يسحب المالك نسخة خارج Railway.

        المخازن حسّاسة (تحليلات مدفوعة، مستأجرو المنصّة) — نفس حارس سطوح
        المشغّل (`X-API-Key` + معدّل). اسم خارج القائمة أو بلا طبعة = 404
        صريحة، لا ملف فارغ مختلَق.
        """
        _require_key(request)
        _rate_limit(request)
        import silk_backup
        # القائمة من الوحدة نفسها لا نسخة محلية — هدف جديد هناك يظهر هنا تلقائياً.
        allowed = set(silk_backup.STORE_NAMES)
        if store_name not in allowed:
            raise HTTPException(status_code=404,
                                detail=f"unknown store: {store_name}")
        path = silk_backup.latest_backup(store_name)
        if not path:
            raise HTTPException(status_code=404,
                                detail=f"لا نسخة محفوظة بعد للمخزن {store_name}"
                                       " — شغّل GET /ops/backup أولاً")
        from fastapi.responses import FileResponse
        return FileResponse(path, media_type="application/octet-stream",
                            filename=os.path.basename(path))

    @app.get("/watchdog")
    def watchdog(request: Request, n: int = 50):
        """الحارس — سطحُ مالكٍ منفصلٌ تماماً (LAW: تسلسل القيادة، «تقرير
        الحارس» ليس جزءاً من أي تحليل). آخر `n` سجلّ صحّةٍ + الشارة العامة +
        اتجاهات آخر التشغيلات. محروسة كبقية سطوح المشغّل."""
        _require_key(request)
        _rate_limit(request)
        import silk_watchdog
        records = silk_watchdog.list_records(n)
        return _json({
            "badge": silk_watchdog.overall_badge(records),
            "records": records,
            "trend": silk_watchdog.trend_report(records),
            "known_backlog_note": silk_watchdog.KNOWN_OPEN_BACKLOG_NOTE,
        })

    @app.get("/watchdog/report.md")
    def watchdog_report_md(request: Request, n: int = 50):
        """تقرير مراقبة المنصّة — ملفٌّ مستقلٌّ تماماً بذاته (PART 2-2: لا
        علاقة بأي مُصدِّر تحليل/عميل). محروسة، نفس عقد `report.md`."""
        _require_key(request)
        _rate_limit(request)
        import silk_watchdog
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(silk_watchdog.render_report_md(n=n),
                                 media_type="text/markdown; charset=utf-8")

    @app.get("/sources")
    def sources(request: Request):
        """خريطة حالة طبقات المصادر الاثنتي عشرة — 12-layer data-source status map.

        For each layer: {name, type (free/paid), wired, key_env[, key_present]}.
        M0: عندما تكون المصادقة مفعّلة، أعلام key_present تُعرض لحامل المفتاح فقط
        — مجهول يرى قائمة الطبقات بلا كشف إعدادات الخادم (ANALYSIS.md §7-5).
        وضع التطوير (بلا SILK_API_KEY) يبقى كما كان: الأعلام ظاهرة.
        """
        _rate_limit(request)
        layers = [
            ("UN Comtrade", "free", None),
            ("World Bank", "free", None),
            ("FAOSTAT", "free", None),
            ("WITS", "free", None),
            ("Google Trends", "free", None),
            ("Google Maps", "free", "GOOGLE_MAPS_API_KEY"),
            ("Web Search", "free", "SEARCH_API_KEY"),
            ("Local retail prices", "paid", "LOCALPRICE_API_KEY"),
            ("Volza", "paid", "VOLZA_API_KEY"),
            ("explee", "paid", "EXPLEE_API_KEY"),
            ("Claude (AI judge)", "ai", "ANTHROPIC_API_KEY"),
            ("Requirements L1 reference (GCC + Saudi exit)", "free", None),
        ]
        expected = _api_key_expected()
        show_flags = (not expected) or hmac.compare_digest(
            request.headers.get("x-api-key", ""), expected)
        out = []
        for name, kind, key_env in layers:
            row = {"name": name, "type": kind, "wired": True, "key_env": key_env}
            if show_flags:  # أعلام المفاتيح للمصرَّح له (أو وضع التطوير) فقط
                row["key_present"] = (bool(os.environ.get(key_env))
                                      if key_env else False)
            out.append(row)
        return _json(out)

    @app.get("/analyses")
    def analyses(request: Request):
        """اسرد التحليلات المحفوظة — list persisted analyses (metadata only).

        C-1: محروسة بالمصادقة — الجرد يكشف ما يُحلَّل من منتجات/أسواق.

        `?limit=N` (تدقيق 2026-08-27، البند ٣٤): الوسيط كان موجوداً في
        `silk_storage.list_analyses` ولا يصله شيء من هنا، فكل نداء يُجسِّد
        الجدول كاملاً — ينمو بلا سقف مع كل تشغيلة. غير مضبوط = السلوك القديم
        حرفياً (الكل)، فلا كسر لأي مستهلك قائم.
        """
        _require_key(request)
        _rate_limit(request)
        raw = (request.query_params.get("limit") or "").strip()
        limit = None
        if raw:
            try:
                limit = max(1, int(raw))
            except ValueError:
                raise HTTPException(status_code=422, detail={
                    "error": "bad_limit",
                    "reason": "limit must be a positive integer"})
        return _json(silk_storage.list_analyses(limit=limit))

    @app.get("/analyses/{analysis_id}")
    def analysis(analysis_id: int, request: Request):
        """أعد تحليلًا محفوظًا — fetch one persisted analysis, or 404.

        C-1: محروسة — البلوب المخزّن يحمل بطاقة المنتج الاقتصادية،
        والمعرّفات متسلسلة، فبلا مصادقة يقرؤها مجهول بالتعداد.

        ITEM 5أ (خدمة ذاتية للمشغّل، تدقيق 2026-07-15): `?economics=1` يعيد
        ملخّص اقتصاد التشغيلة فقط (لا البلوب الكامل — قد يبلغ عشرات
        الكيلوبايتات) — يقطع حلقة «الصق لي بيانات Railway» التي كانت
        مستحيلة الإغلاق من صندوق تطوير معزول عن الشبكة الحيّة.
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        # HIGH#5 (تدقيق الواجهة 2026-07-15): البلوب الكلاسيكي (/analyze) يُخزَّن
        # داخل المحرّك (silk_engine.py:619) *قبل* إرفاق result["view"] (api.py:579،
        # بعد الحفظ)، فيصل هذا المسار بلا view — ونقر «التحليلات الأخيرة» على
        # تحليل كلاسيكي كان يفتح لوحةً فارغة («شغّل تحليلاً أولاً»). أعِد بناء
        # العرض عند غيابه فقط (مسار /research يحفظ *مع* view فلا يُمَسّ)، تماماً
        # كما تفعل مسارات القراءة الأخرى (brief/report.md/report.docx تبني
        # build_view(found) طازجاً). المعرّف كذلك يُضمَن للبلوبات الأقدم.
        found.setdefault("analysis_id", analysis_id)
        # الموجة p6 (T4): صفّ بحثٍ فاشل ببلوبٍ بلا بعثات (عطل قبل أيّ حفظ) —
        # أَلحِق ما هو محفوظ فعلاً (نقاط تفتيش البعثات + المراحل) وأعلِم
        # `partial` بدل فشلٍ فارغ. قراءةٌ فقط، لا كتابة على القاعدة.
        if found.get("status") == "failed" and not (
                (found.get("deep_research") or {}).get("missions")):
            try:
                _run_row = silk_storage.get_research_run(analysis_id) or {}
                if _run_row.get("kind") == "research":
                    _mx = silk_storage.load_mission_checkpoints(analysis_id)
                    _sx = silk_storage.load_stage_checkpoints(analysis_id)
                    if _mx or _sx:
                        dr_part = dict(found.get("deep_research") or {})
                        dr_part["missions"] = _to_jsonable(_mx)
                        dr_part["stages"] = _sx
                        found["deep_research"] = dr_part
                        found["partial"] = True
            except Exception as _pe:  # noqa: BLE001 — إلحاقٌ تحسيني لا يُسقِط القراءة
                log.warning("partial attach skipped for %s: %s", analysis_id, _pe)
        if not found.get("view"):
            found["view"] = _view(found)
        if str(request.query_params.get("economics") or "").strip().lower() \
                in ("1", "true", "yes"):
            return _json(_economics_summary(analysis_id, found))
        return _json(found)

    def _economics_summary(analysis_id: int, found: dict) -> dict:
        """ITEM 5أ: ملخّص اقتصاد تشغيلة واحدة — llm_usage/mission_usage
        (#96)/cost_usd_by_mission/العدّادات/التكلفة النهائية. تشغيلة سابقة
        لتفعيل الإسناد لكل بعثة تعرض `mission_usage`/`cost_usd_by_mission`
        فارغين صراحة (`mission_usage_available: false`) — فجوة معلنة، لا
        استثناء، ولا اختلاق رقم لتشغيلة أقدم من الميزة. `note` (نص حرّ
        بُنِي خادمياً) يمرّ عبر نفس مُطهِّر السباكة الداخلية دفاعاً بالعمق."""
        de = found.get("data_economics") or {}
        from silk_render import _strip_internal_plumbing
        note = de.get("note")
        return {
            "analysis_id": analysis_id,
            "llm_calls": de.get("llm_calls"),
            "tool_calls": de.get("tool_calls"),
            "store_hits": de.get("store_hits"),
            "cache_hits": de.get("cache_hits"),
            "live_fetches": de.get("live_fetches"),
            "llm_usage": de.get("llm_usage") or {},
            "mission_usage": de.get("mission_usage") or {},
            "mission_usage_available": bool(de.get("mission_usage")),
            "cost_usd_estimate": de.get("cost_usd_estimate"),
            "cost_usd_by_model": de.get("cost_usd_by_model") or {},
            "cost_usd_by_mission": de.get("cost_usd_by_mission") or {},
            "cost_unpriced_models": de.get("cost_unpriced_models") or [],
            "note": _strip_internal_plumbing(note) if note else None,
        }

    @app.get("/analyses/{analysis_id}/brief")
    def brief(analysis_id: int, request: Request):
        """المختصر (§10.4) — one-page mobile-style brief from the ONE template.

        C-1: محروسة — تشتق من التحليل المخزّن نفسه (بطاقة/هوامش).
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        from silk_render import build_view
        from silk_reports import render_brief
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(render_brief(build_view(found)))

    @app.get("/analyses/{analysis_id}/report.docx")
    def report_docx(analysis_id: int, request: Request):
        """تقرير Word — derived from the ONE view-model (build_view).

        فصل الجمهور (بلاغ المالك): نتيجة بحث عميق (/research) تُصدَّر بقالب
        **العميل** (`render_client_docx`) بمفردات تجارية بحتة بلا تِلِمِتري —
        هو ما يستلمه العميل الدافع. تِلِمِتري المشغّل (بعثات/حالات/اقتصاد
        بيانات) يبقى على اللوحة (web/index.html)، ويبقى التصدير التشغيلي
        الكامل للمدقّق متاحاً عبر `?internal=1`. نتيجة /analyze الكلاسيكية
        (بلا deep_research) تبقى على `render_docx` العادي.

        C-1: محروسة. 404 للتحليل المفقود؛ 501 بلا python-docx.
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        import tempfile
        from silk_render import build_view
        import silk_reports
        from silk_reports import render_client_docx, render_docx
        from fastapi.responses import FileResponse
        view = build_view(found)
        # التصدير الكامل التشغيلي للمدقّق فقط عند طلب صريح.
        internal = str(request.query_params.get("internal") or "").lower() in (
            "1", "true", "yes")
        # HF4.2: علِّم النموذجَ بالجمهور — سطرُ إفصاح التنقية للمدقّق فقط.
        view["internal"] = internal
        is_research = bool(view.get("deep_research"))
        if is_research and not internal:
            _block_client_export_if_gate_failed(
                view, analysis_id, found, "docx", request)
        if is_research and internal:
            _attach_override_history(view, analysis_id)
        # القالب الأكاديمي (قرار المالك 2026-07-22): ?style=academic يبدّل
        # ترتيب/نبرة تقرير العميل فقط — نفس النموذج القانوني ونفس بوابة
        # التسليم أعلاه ونفس مُطهِّرات العميل؛ صفر نداء كلود إضافي.
        # أسلوب مخزَّن مع السجل (إعادة توليد أكاديمية سابقة) = الافتراضي.
        style = (str(request.query_params.get("style") or "").lower()
                 or str((view.get("deep_research") or {})
                        .get("report_style") or "").lower())
        # البند #8 (تدقيق v2 الموجة ٣): مجلّد مؤقّت **واحد** يُنظَّف بعد إرسال
        # الردّ (BackgroundTask) — كان كلّ طلب يُنشئ mkdtemp لا يُحذَف أبداً
        # (FileResponse يبثّ الملف لا مجلّده)، فيتراكم على قرص النشر حتى الدوران.
        _td = tempfile.mkdtemp()
        try:
            if is_research and not internal and style == "academic":
                from silk_reports import render_academic_docx
                path = render_academic_docx(
                    view, os.path.join(_td, "report.docx"))
                fname = f"silk_academic_report_{analysis_id}.docx"
            elif is_research and not internal:
                path = render_client_docx(
                    view, os.path.join(_td, "report.docx"))
                fname = f"silk_client_report_{analysis_id}.docx"
            else:
                path = render_docx(
                    view, os.path.join(_td, "report.docx"))
                fname = f"silk_report_{analysis_id}.docx"
        except silk_reports.ClientArtifactGateError as exc:
            # صيد الفجوات ٣ (G-04 على السطح الجذري — عائلة «الإصلاح على مسار
            # واحد نصف إصلاح»): رفضُ جودةٍ من بوابة نصّ المُنتَج كان يُقدَّم
            # هنا 501 بنصّ خام (فتقرؤه أداة الفحص «منصة ناقصة») بينما المنصة
            # تعيده 409 `quality_gate_fail` منظّماً — توحيدٌ مع تسجيل الحجب.
            import shutil as _sh
            _sh.rmtree(_td, ignore_errors=True)
            raise _operator_artifact_gate_409(exc, analysis_id, "docx")
        except RuntimeError as e:
            # ITEM 5ب: سبب ثابت عام لا نص الاستثناء الخام — رسالة حارس
            # التصدير (`_client_assert_clean`) قد تقتبس فئة/شظية داخلية
            # (مثال: "algorithm_language: «درجة الثقة»") لا يلتقطها مُطهِّر
            # السباكة العام (يعرّب EN→AR، لا يحذف أسماء فئات عربية موجودة
            # أصلاً) — فبدل مطاردة كل شكل تسريب محتمل بتعبير نمطي جديد،
            # لا يصل /ops/last-errors نص الاستثناء إطلاقاً؛ ردّ الـHTTP نفسه
            # (الذي يخصّ الطالب لا سطحاً عاماً) يبقى يحمل str(e) كاملاً كما
            # كان دوماً — لا تغيير هناك.
            import shutil as _sh
            _sh.rmtree(_td, ignore_errors=True)   # البند #8: نظّف عند الفشل أيضاً
            import silk_ops_log
            silk_ops_log.record_error(
                "export_failure",
                "فشل تصدير docx (منصّة ناقصة أو محتوى رفضه حارس التصدير) — "
                "التفصيل الكامل في استجابة الطلب الأصلي، لا هنا",
                context={"analysis_id": analysis_id})
            raise HTTPException(status_code=501, detail=_redact_text(str(e)))
        return FileResponse(
            path, filename=fname,
            media_type="application/vnd.openxmlformats-officedocument"
                       ".wordprocessingml.document",
            background=_rmtree_bg(_td))

    @app.get("/analyses/{analysis_id}/report.pdf")
    def report_pdf(analysis_id: int, request: Request):
        """§3 (أمر العمل الرئيس): المُسلَّم النهائي PDF غير قابل للتحرير —
        يُبنى تقرير العميل docx (RTL، مُطهَّر) ثم يُحوَّل PDF ويُسلَّم الـPDF
        فقط. نفس فصل الجمهور: العميل افتراضاً، المدقّق عبر `?internal=1`.
        503 نظيف إن غاب محرّك التحويل أو فشل — لا docx بديل صامت، لا PDF جزئي.
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        import tempfile
        from silk_render import build_view
        import silk_reports
        from silk_reports import render_client_pdf, render_research_pdf
        from fastapi.responses import FileResponse
        view = build_view(found)
        internal = str(request.query_params.get("internal") or "").lower() in (
            "1", "true", "yes")
        # HF4.2: علِّم النموذجَ بالجمهور — سطرُ إفصاح التنقية للمدقّق فقط.
        view["internal"] = internal
        is_research = bool(view.get("deep_research"))
        if is_research and not internal:
            _block_client_export_if_gate_failed(
                view, analysis_id, found, "pdf", request)
        if is_research and internal:
            _attach_override_history(view, analysis_id)
        _td = tempfile.mkdtemp()   # البند #8: يُنظَّف بعد الإرسال (background)
        out = os.path.join(_td, "report.pdf")
        style = (str(request.query_params.get("style") or "").lower()
                 or str((view.get("deep_research") or {})
                        .get("report_style") or "").lower())
        try:
            if is_research and not internal and style == "academic":
                from silk_reports import render_academic_pdf
                path = render_academic_pdf(view, out)
                fname = f"silk_academic_report_{analysis_id}.pdf"
            elif is_research and not internal:
                path = render_client_pdf(view, out)
                fname = f"silk_client_report_{analysis_id}.pdf"
            else:
                path = render_research_pdf(view, out)
                fname = f"silk_report_{analysis_id}.pdf"
        except silk_reports.ClientArtifactGateError as exc:
            # صيد الفجوات ٣ (G-04 جذرياً): رفضُ جودةٍ ≠ عطلُ soffice — 409
            # منظّم كما على سطح المصنع، لا 503 بنص خام.
            import shutil as _sh
            _sh.rmtree(_td, ignore_errors=True)
            raise _operator_artifact_gate_409(exc, analysis_id, "pdf")
        except silk_reports.PdfBusy:
            # R9 (API-11/EXT-14): فتحاتُ LibreOffice مشغولة — 503 مسمّى مع Retry-After،
            # لا «محرّكٌ غائب» ولا خطأُ تصدير يُسجَّل.
            import shutil as _sh
            _sh.rmtree(_td, ignore_errors=True)
            raise HTTPException(
                status_code=503, detail=silk_reports.pdf_busy_detail(),
                headers={"Retry-After": str(silk_reports.PDF_RETRY_AFTER_S)})
        except RuntimeError as e:
            import silk_ops_log
            silk_ops_log.record_error(
                "pdf_export_failure",
                "فشل إنتاج PDF (محرّك التحويل غير متاح أو فشل) — التفصيل في "
                "استجابة الطلب الأصلي",
                context={"analysis_id": analysis_id})
            import shutil as _sh
            _sh.rmtree(_td, ignore_errors=True)   # نظّف عند الفشل أيضاً
            raise HTTPException(status_code=503, detail=_redact_text(str(e)))
        return FileResponse(path, filename=fname, media_type="application/pdf",
                            background=_rmtree_bg(_td))

    @app.get("/analyses/{analysis_id}/report.md")
    def report_md(analysis_id: int, request: Request):
        """التقرير الكامل Markdown (Stage 5، §7) — من القالب الموحّد نفسه.

        نفس عقد report.docx (محروسة، 404 للمفقود) لكن نصّ خالص بلا تبعيات —
        يعمل حيث لا python-docx، وهو مصدر اشتقاق PDF على النشر.
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        from silk_render import build_view
        from silk_reports import render_markdown
        from fastapi.responses import PlainTextResponse
        try:
            text = render_markdown(build_view(found))
        except RuntimeError as e:
            # نفس عقد report.docx (البند أعلاه): تناقض حكمٍ أو تسريبٌ يستحيل
            # تنقيته يُفشِل التوليد داخلياً — 501 نظيف لا 500 غير مُدار.
            import silk_ops_log
            silk_ops_log.record_error(
                "export_failure",
                "فشل تصدير Markdown (محتوى رفضه حارس التصدير) — التفصيل "
                "الكامل في استجابة الطلب الأصلي، لا هنا",
                context={"analysis_id": analysis_id})
            raise HTTPException(status_code=501, detail=_redact_text(str(e)))
        return PlainTextResponse(text,
                                 media_type="text/markdown; charset=utf-8")

    @app.get("/analyses/{analysis_id}/writer-diagnostics")
    def writer_diagnostics(analysis_id: int, request: Request):
        """أحداث `report_call` الخام لتشغيلة — الدليل غير المُطهَّر لفشل الكاتب.

        القضية المفتوحة (كاتب التقرير، PRs 69/70/71): كل سطوح الـHTTP الأخرى
        (`/ops/last-errors`، `/diagnostics`، متن التقرير) تُطهِّر `error_type`/
        `stop_reason`/`status_code` قبل العرض — فيستحيل على المالك قراءة نوع
        الاستثناء الفعلي عن بُعد، ويصير أي إصلاح تخميناً. هذه النقطة تكشف أحداث
        `report_call` كما كُتبت في الأثر (‏`data/traces/{trace_id}.jsonl`):
        `stage`/`timeout`/`elapsed_ms`/`success`/`error_type`/`error_message`/
        `status_code`/`response_body` — فيُميَّز ReadTimeout (المهلة فعلاً) من
        ConnectTimeout (شبكة) من 429/529 (حصّة/ازدحام) من 400 (حمولة). محروسة
        بالمفتاح كبقية سطوح المشغّل؛ الأحداث **مُنقّاة من الأسرار مسبقاً** عند
        الكتابة (`silk_trace._redacted`) فلا مفتاح يتسرّب — لكنها **غير مُطهَّرة
        من التفصيل التقني** عمداً: هذا هو الغرض (قياس لا تخمين).
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        trace_id = (found.get("deep_research") or {}).get("trace_id")
        report_calls: list = []
        if trace_id:
            import silk_trace
            report_calls = [e for e in silk_trace.read_trace(trace_id)
                            if e.get("kind") == "report_call"]
        # سبب الفشل كما هو مخزَّن (قد يكون مُطهَّراً في البلوب) — للمقارنة فقط.
        dr = found.get("deep_research") or {}
        rep = dr.get("report") if isinstance(dr.get("report"), dict) else {}
        return _json({
            "analysis_id": analysis_id,
            "trace_id": trace_id,
            "report_present": bool((rep or {}).get("report")),
            "failure_reason_stored": (rep or {}).get("failure_reason"),
            "report_calls": report_calls,
            "note": ("لا trace_id (تشغيلة أقدم من التتبّع أو تحليل كلاسيكي)"
                     if not trace_id else
                     ("لا أحداث report_call — الكاتب لم يُستدعَ أو الأثر مُنمَحٍ"
                      if not report_calls else None)),
        })

    @app.post("/analyses/{analysis_id}/report")
    def regenerate_report(analysis_id: int, request: Request):
        """أعد توليد التقرير الكامل من بحث محفوظ — نداء كاتب واحد (+مراجع)
        فقط، بلا إعادة تشغيل أي بعثة من الاثنتي عشرة ولا المحلل الشامل.

        بلاغ حي (تمور/هولندا): كاتب التقرير قد يفشل (مهلة/شبكة) رغم نجاح
        كل شيء آخر في تشغيلة مكلفة كاملة — هذه النقطة تُنقِذ تلك التشغيلة
        بتكلفة نداء واحد بدل إعادة البحث كله (§سنتات لا دولارات)، ومصدر
        اختبار رخيص لإصلاحات مهلة الكاتب. تقرأ نقاط تفتيش البعثات
        (`silk_storage.load_mission_checkpoints`، مخزَّنة فور اكتمال كل
        بعثة بصرف النظر عن مصير الكاتب لاحقاً) بدل إعادة بنائها من
        `json_blob` النهائي — نفس آلية استئناف `/research`، لا منطق موازٍ.
        تحدّث السجل المخزَّن بالتقرير الجديد وتعيد بناء القالب الموحّد +
        بوابة الجودة قبل الحفظ.
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        dr = found.get("deep_research")
        if not dr:
            raise HTTPException(
                status_code=400,
                detail=f"analysis {analysis_id} is not a /research run "
                       "(no deep_research section) — nothing to regenerate")
        # صيد الفجوات ٣: كان حجزُ وحدة السقف يسبق شرطَ نقاط التفتيش — كلُّ
        # استطلاعٍ لتحليلٍ بلا نقاط تفتيش يحرق وحدةً بلا أي نداء كلود
        # (الحجوزات غير قابلة للاسترداد عمداً — A7). الشرط الرخيص أولاً.
        mission_reports = silk_storage.load_mission_checkpoints(analysis_id)
        if not mission_reports:
            raise HTTPException(
                status_code=409,
                detail=f"no mission checkpoints stored for analysis "
                       f"{analysis_id} — cannot regenerate without them")
        ai_ok, ai_note = _free_ai_extras_allowed()
        if not ai_ok:
            return _json({"report": None, "note": ai_note})
        from silk_ai_judge import write_reviewed_report
        # Explicit repair option: refresh only the trends mission, keeping the
        # other eleven checkpoints. Default regeneration still makes no searches.
        from silk_report_refresh import prepare as _prepare_report_refresh
        found, mission_reports = _prepare_report_refresh(
            found, mission_reports,
            refresh_trends=request.query_params.get("refresh_trends") == "1",
            refresh_prices=request.query_params.get("refresh_prices") == "1")
        dr = found["deep_research"]
        analyst_summary = ((dr.get("analyst") or {}).get("report") or {}) \
            .get("summary", "")
        # الموجة p6 (T4): نقطة تفتيش المحلل (تُكتب فور عودته) تسبق البلوب —
        # بلوبٌ فقير بعد فشل ذيلٍ قديم لا يعني أن المحلل المدفوع ضاع.
        try:
            _stage_an = (silk_storage.load_stage_checkpoints(analysis_id)
                         .get("analyst") or {})
            if _stage_an.get("status") == "succeeded":
                _stage_summary = ((_stage_an.get("payload") or {})
                                  .get("analyst_input") or {}).get("summary")
                if _stage_summary:
                    analyst_summary = _stage_summary
        except Exception as _se:  # noqa: BLE001 — نقطة التفتيش تحسين لا شرط
            log.warning("analyst stage checkpoint unreadable for %s: %s",
                        analysis_id, _se)
        verdict = dr.get("verdict") or {}
        market_name = (found.get("market") or {}).get("name_en", "")
        trace_id = dr.get("trace_id")
        # قرار المالك (متابعة القالب الأكاديمي): ?style=academic يعيد كتابة
        # النثر نفسه بالسجل الأكاديمي (نداء كاتب واحد — قروش لا دولارات)؛
        # الأسلوب يُخزَّن مع السجل فتتبعه التصديرات افتراضياً.
        regen_style = str(request.query_params.get("style") or "").lower() \
            or None
        # نفسُ عقد `resume` (يمرّ ويُوسَم): إعادةُ التوليد تُعيد استعمال
        # `found["hs_code"]` المخزَّن بلا أيّ فحص — فتُعيد كتابةَ تقريرٍ كاملٍ
        # على رمزٍ ربّما صار خاطئاً. الوسمُ يُحفَظ مع السجلّ فيظهر في الحدود.
        try:
            from silk_hs_confirm import revalidate as _reval_fn
            _reval = _reval_fn(found.get("product", ""), found.get("hs_code"))
            if _reval:
                found["hs_revalidation"] = _reval
        except Exception as e:  # noqa: BLE001 — وسمٌ تحسينيّ لا يُسقِط الطلب
            log.warning("hs revalidation skipped on regen: %s", e)
        # PR A §A1: إعادة التوليد كانت لا تمرّر `hs_confirmation` للكاتب ولا
        # تُسقِّف الثقة — فتعيد إنتاج نفس تعارض §4«73%»/الغلاف«50%» في كل regen.
        # نحسب العقد ونُسقِّف الحكم من المصدر الواحد قبل الكاتب، ونمرّر العقد
        # كي يؤطّر الكاتب أرقام كومتريد سياقياً أيضاً (كان مفقوداً على هذا المسار).
        hs_conf_regen = None
        try:
            from silk_hs_confirm import (confirm_hs as _confirm_regen,
                                        cap_confidence_for_flagged_hs
                                        as _cap_regen)
            _hs_regen = found.get("hs_code")
            hs_conf_regen = (_confirm_regen(found.get("product", ""), _hs_regen)
                             if _hs_regen else None)
            verdict = _cap_regen(verdict, hs_conf_regen)
        except Exception as e:  # noqa: BLE001 — تسقيفٌ تحسينيّ لا يُسقِط الطلب
            log.warning("hs confidence cap skipped on regen: %s", e)
        # الاستئناف من الجزء على مسار regen (بلاغ تحليل 20): إن لم يوجد تقريرٌ
        # كاملٌ سابق ووُجدت مسوّدةٌ محفوظة، تُمرَّر بذرةً فيُكمِل الكاتبُ الأقسامَ
        # الباقية بدل إعادة التوليد الكامل — قروشٌ لا نداءُ مسوّدةٍ غالٍ. مع وجود
        # تقريرٍ كاملٍ سابق (regen لتغيير الأسلوب مثلاً) لا نبذر: يُعاد الكتابة كاملةً.
        #
        # مِفتاحُ التجاوز `?seed=0` (بلاغ تحليل 20 — شبكةُ أمانِ الموثوقية): مسارُ
        # البذرة يمرّ بحلقة الإكمال، وهي بالضبط ما أهدر ٦٤ألف رمزٍ وأضاف صفر قسمٍ
        # في تحليل 20 (الآلية `pending`). فإن عجز الإكمالُ عن إتمام الأقسام تكرّر
        # البذرُ من الجزء نفسِه في كلّ نداء (٨/١١ عالقة). `seed=0` يتخطّى البذرةَ
        # فيُعاد توليدُ مسوّدةٍ كاملةٍ من الصفر — ومع ميزانية ٢٤ألف (#232) تكتمل
        # ١١/١١ في نداءٍ واحدٍ يتفادى الإكمالَ الغامض (~٠٫٣$، تحت ١$). الافتراضُ
        # البذرُ (الأرخص)؛ `seed=0` مهربٌ موثوقٌ متى تعثّر.
        _seed_enabled = str(request.query_params.get("seed", "1")).strip().lower() \
            not in ("0", "false", "no")
        _seed_regen = None
        if _seed_enabled:
            try:
                _wp_regen = (silk_storage.load_stage_checkpoints(analysis_id)
                             .get("writer_partial") or {})
                if _wp_regen.get("status") == "partial" \
                        and not (dr.get("report") or {}).get("report"):
                    _seed_regen = (_wp_regen.get("payload") or {}).get("text") or None
            except Exception as _we:  # noqa: BLE001 — البذرة تحسينٌ لا شرط
                log.warning("writer_partial seed unreadable on regen for %s: %s",
                            analysis_id, _we)
        report_out = write_reviewed_report(
            mission_reports, analyst_summary, verdict,
            found.get("product", ""), market_name, trace_id=trace_id,
            hs_code=found.get("hs_code"), hs_confirmation=hs_conf_regen,
            style=regen_style, seed_draft=_seed_regen,
            importer_leads=dr.get("importer_leads"))
        if (dr.get("trend_refresh") or {}).get("status") == "failed":
            report_out.setdefault("unresolved_notes", []).append(
                "تعذر تحديث بيانات الاتجاهات؛ احتُفظ بالأدلة السابقة وفجواتها.")
        if (dr.get("price_refresh") or {}).get("status") == "failed":
            report_out.setdefault("unresolved_notes", []).append(
                "تعذر تحديث أسعار التجزئة؛ احتُفظ بالأدلة السابقة وفجواتها.")
        # H1 (تدقيق): إعادة التوليد كانت تطمس التقرير المخزَّن بـreport_out حتى
        # لو فشل الكاتب هذه المرة (report=None) — فيُفقَد تقرير سابق ناجح كلّفت
        # تشغيلته الكاملة، وهو بالضبط ما تُنقِذه هذه النقطة. الآن: لا نحفظ null
        # فوق تقرير سابق ناجح؛ نُبقي المخزَّن ونُبلّغ الفشل (السجل لا يُلمَس).
        from silk_render import _strip_internal_plumbing
        _prior_node = dr.get("report") or {}
        prior_report = _prior_node.get("report")
        prior_complete = bool(prior_report) and not _prior_node.get("incomplete")
        _new_report = report_out.get("report")
        _new_incomplete = bool(report_out.get("incomplete"))
        if not _new_report:
            # ITEM 5ب: فشل كاتب أثناء regen — يُسجَّل بصرف النظر عن وجود
            # تقرير سابق محفوظ أم لا (كلاهما فشل كاتب حقيقي يستحق الرصد).
            import silk_ops_log
            silk_ops_log.record_error(
                "writer_failure",
                _strip_internal_plumbing(report_out.get("failure_reason") or "")
                or "فشل الكاتب بلا سبب مسجَّل",
                context={"analysis_id": analysis_id, "regen": True,
                         "prior_preserved": bool(prior_report)})
        elif _new_incomplete:
            # بلاغ تحليل 20: إعادة توليدٍ ناقصة تُرصَد للمشغّل (نظير المسار
            # الرئيس) — قرارٌ وأقسامٌ مكتوبة سليمة، لا فشلٌ صلب.
            try:
                import silk_ops_log
                _miss = "، ".join(report_out.get("missing_sections") or [])
                silk_ops_log.record_error(
                    "writer_incomplete",
                    f"إعادة توليد غير مكتملة — أقسام غائبة: {_miss}",
                    context={"analysis_id": analysis_id, "regen": True,
                             "missing": report_out.get("missing_sections"),
                             "prior_complete": prior_complete})
            except Exception as _ie:  # noqa: BLE001 — سجلّ المشغّل قناة جانبية
                log.warning("ops log writer_incomplete (regen) skipped: %s", _ie)
        # حارس H1 (موسَّع، بلاغ تحليل 20): لا نطمس تقريراً **كاملاً** سابقاً
        # لا بـnull ولا بتقريرٍ ناقص — كلاهما أدنى من الكامل المدفوع المحفوظ.
        # (ناقصٌ فوق سابقٍ ناقص/غائب يُحفَظ: تقدّمٌ لا خسارة.)
        if (not _new_report and prior_report) or \
                (_new_incomplete and prior_complete):
            return _json({"report": None, "regenerated": False,
                          "note": ("تعذّر إنتاج تقرير كامل هذه المرة؛ التقرير "
                                   "السابق محفوظ كما هو دون تغيير."),
                          "failure_reason": _strip_internal_plumbing(
                              report_out.get("failure_reason") or "")})
        found["deep_research"]["report"] = report_out
        if regen_style:
            found["deep_research"]["report_style"] = regen_style
        found["analysis_id"] = analysis_id
        found["view"] = _view(found)
        _attach_quality_gate(found, trace_id)
        for _status_key, _mission in (("trend_refresh", "demand_trends"),
                                     ("price_refresh", "pricing_scout")):
            if (dr.get(_status_key) or {}).get("status") == "completed":
                silk_storage.save_mission_checkpoint(
                    analysis_id, _mission, mission_reports[_mission],
                    market_iso3=(found.get("market") or {}).get("iso3"))
        silk_storage.save_analysis(found, analysis_id=analysis_id)
        return _json(found)

    @app.post("/analyses/{analysis_id}/enrich-leads")
    def enrich_leads(analysis_id: int, request: Request):
        """أعد رصد جهات اتصال المستوردين لبحث محفوظ — كشط الخرائط فقط، بلا
        أيّ نداء كلود ولا إعادة تشغيل البعثات (المسار الرخيص).

        السياق (بلاغ UK الحي، أمر العمل الرئيس ITEM 2): المكشطة (`silk_gmaps`)
        نُشرت متأخّراً (SILK_GMAPS_SCRAPER_URL ضُبط بعد إنجاز تقارير سابقة)،
        فتقرير المالك القائم يحمل «فجوة معلنة» في جدول المستوردين رغم أن
        المكشطة صارت حيّة الآن. إعادة تشغيل /research كاملة تكلّف ~3$ (١٢ بعثة
        + محلل + كاتب) لمجرّد تعبئة هاتف/إيميل — هذه النقطة تُنجزها بقروش:
        تكشط الخرائط للسوق/المنتج المخزَّنَين، تدمج مرشّحي الويب من نقاط
        تفتيش البعثات المحفوظة، وتحدّث `importer_leads` في مكانه ثم تعيد بناء
        القالب الموحّد قبل الحفظ. لا نداء كلود، ولا حجز من السقف اليومي
        المدفوع — المكشطة خدمة منفصلة رخيصة. عقد عدم الاختلاق مقدَّس: فشل/غياب
        المكشطة = فجوة معلنة، لا صفّ مخترَع.
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        dr = found.get("deep_research")
        if not dr:
            raise HTTPException(
                status_code=400,
                detail=f"analysis {analysis_id} is not a /research run "
                       "(no deep_research section) — no importer leads to enrich")
        import silk_gmaps
        if not silk_gmaps.enabled():
            # تعطيل نظيف: المكشطة غير مُهيَّأة — لا نلمس التحليل المخزَّن، نُبلّغ.
            return _json({
                "enriched": False, "path": (dr.get("importer_leads") or {})
                .get("path", "gap"),
                "leads_count": len((dr.get("importer_leads") or {})
                                   .get("leads") or []),
                "note": "مكشطة الخرائط غير مُهيَّأة (SILK_GMAPS_SCRAPER_URL "
                        "غائب) — لم تُحدَّث الروابط."})

        product = found.get("product") or ""
        market_blob = found.get("market") or {}
        from silk_market_resolver import resolve_market
        market_ref, _sugg = resolve_market(
            market_blob.get("name_en") or market_blob.get("iso3") or "")
        if market_ref is None:
            raise HTTPException(
                status_code=422,
                detail=f"stored market {market_blob!r} could not be resolved "
                       "— cannot target the scraper")

        # مرشّحو الويب من نقاط تفتيش البعثات المحفوظة (اسم فقط، للمضاهاة/الدمج)
        # — تُقرأ من نفس آلية استئناف /research، لا إعادة تشغيل بعثة.
        mission_reports = silk_storage.load_mission_checkpoints(analysis_id) or {}
        web_cands = silk_gmaps.extract_web_candidates(mission_reports)

        # البند #4 (تدقيق v2 الموجة ٢): الكشط كان يحجب الطلب متزامناً حتى ٣٠٠ث،
        # فبوّابة النشر (Railway/بروكسي) تقطعه عند ~٣٠-٦٠ث فيصل العميل ٥٠٢/٥٠٤
        # بلا جسم — لا يُميّزه عن فشلٍ صلب. المهلة الآن **آمنة للبروكسي** افتراضياً
        # (٢٥ث)، وخيط الكشط يواصل ويخزّن نتائجه ذاتياً عند الاكتمال (silk_gmaps
        # `_worker`)، فإعادة الضغط تجلبها من المخزن فوراً (نمط 202-غير-حاجب رخيص
        # يعتمد التخزين القائم، بلا نظام مهامّ منفصل). env يظلّ ضابطاً لمن يريد أطول.
        grace = float(os.environ.get("SILK_GMAPS_ENRICH_GRACE_S", "25"))
        fut = silk_gmaps.submit_scrape_async(product, market_ref)
        new_leads = silk_gmaps.finalize_leads(
            fut, product, market_ref, web_cands, timeout_s=grace)

        # لا تطمس روابط قائمة بفجوة: نُحدّث فقط إن أتى الكشط بروابط فعلية.
        prev = dr.get("importer_leads") or {"leads": [], "path": "gap"}
        processing = False
        if new_leads.get("leads"):
            found["deep_research"]["importer_leads"] = new_leads
            found["analysis_id"] = analysis_id
            found["view"] = _view(found)
            silk_storage.save_analysis(found, analysis_id=analysis_id)
            enriched = True
            note = new_leads.get("note") or "حُدِّثت الروابط عبر كشط الخرائط."
        else:
            # لا روابط ضمن المهلة الآمنة — نُبقي المخزَّن كما هو (لا اختلاق، لا
            # طمس). الكشط **قد يكون ما زال جارياً** في الخلفية ويخزّن نتائجه عند
            # الاكتمال، فنُصرّح بذلك ونقترح إعادة المحاولة (لا نزعم «لا شيء»).
            enriched = False
            processing = True
            note = ("لم تكتمل جهات الاتصال ضمن المهلة الآمنة — قد يكون الكشط "
                    "ما زال جارياً في الخلفية؛ أعد الضغط بعد قليل لجلب ما اكتمل. "
                    "الروابط السابقة محفوظة كما هي دون تغيير.")

        current = found["deep_research"].get("importer_leads") or prev
        return _json({
            "processing": processing,
            "enriched": enriched,
            "path": current.get("path", "gap"),
            "leads_count": len(current.get("leads") or []),
            "importer_leads": current,
            "note": note})

    class AskRequest(BaseModel):
        """سؤال فوق تحليل قائم (10b) — question over a stored analysis."""
        question: str

    @app.post("/analyses/{analysis_id}/ask")
    def ask_analysis(analysis_id: int, req: AskRequest, request: Request):
        """دردشة سياقية فوق تحليل مخزّن (10b) — من الذاكرة حصراً.

        لا إعادة تشغيل وكلاء، لا نداء خارجي سوى نداء كلود الواحد؛ الأرضية
        سياق التحليل المحسوب (analysis_context) والسؤال داخل العزل. ما ليس
        في السياق يُعلن «غير متوفر في هذا التحليل» — لا اختلاق. نفس حارس
        إضافات كلود المجانية (H2): نشر غير محمي يحجبها، والمحمي يحجز من
        السقف اليومي.
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        ai_ok, ai_note = _free_ai_extras_allowed()
        if not ai_ok:
            return _json({"answer": None, "note": ai_note})
        from silk_ai_judge import answer_about_analysis, failure_reason
        from silk_render import _strip_internal_plumbing, analysis_context
        import silk_context as _sctx
        _sctx.begin_data_counter()
        out = answer_about_analysis(req.question, analysis_context(found))
        try:   # EXT-8: نداءُ السؤال مقيسٌ دولارياً كنداء الرؤية (نمطُ `/products/intake`)
            from silk_pricing import estimate_cost_usd
            _c = _sctx.data_counter() or {}
            _cost = estimate_cost_usd(_c.get("llm_usage"))
            if _cost.get("total_usd"):
                silk_usage.record_usd(_cost["total_usd"])
        except Exception as _e:  # noqa: BLE001 — القياس قناة جانبية لا تُسقط الردّ
            log.warning("ask cost metering failed: %s", _e)
        if out is None:
            # بلاغ حي (بحث "تمور/هولندا"): None لا يعني بالضرورة غياب
            # المفتاح — قد يكون فشل نداء فعلي (مهلة/شبكة) رغم مفتاح فعّال.
            # H3 (تدقيق): كان يعيد failure_reason() خاماً — يحمل
            # empty_response/stop_reason/«راجع سجلّات الخادم». يمرّ الآن عبر
            # نفس مُطهِّر طبقة العرض (H4 يُعرّب تلك الرموز).
            return _json({"answer": None,
                          "note": _strip_internal_plumbing(failure_reason())})
        # سدّ تسريب: جواب كلود يمرّ بلا أي مُطهِّر مباشرة للعميل — كلود قد
        # يقتبس مفتاحاً داخلياً حرفياً من السياق رغم تعريب السياق نفسه، أو
        # يستخدم رمز حكم خام بنفسه؛ نفس مُطهِّر طبقة العرض (مرة واحدة).
        if out.get("answer"):
            out["answer"] = _strip_internal_plumbing(out["answer"])
        return _json(out)

    class OutcomeRequest(BaseModel):
        """جسم تسجيل النتيجة الفعلية — actual-outcome body (wave 1)."""
        outcome: str

    @app.patch("/analyses/{analysis_id}/outcome")
    def set_outcome(analysis_id: int, req: OutcomeRequest, request: Request):
        """سجّل ما حدث فعلاً لتحليل — record the real-world outcome (wave 1).

        يبني سجل المصداقية التراكمي (عمودا outcome/outcome_date). 404 إن لم
        يوجد التحليل؛ لا يغيّر بيانات التحليل نفسها إطلاقاً.
        M0: خلف المصادقة وتحديد المعدّل — كانت الوحيدة المكشوفة، فكان بوسع أي
        مجهول الكتابة فوق سجل النتائج بالتعداد (ANALYSIS.md §7-1).
        """
        _require_key(request)
        _rate_limit(request)
        outcome = (req.outcome or "").strip()
        if not outcome:
            raise HTTPException(status_code=422, detail="outcome must be non-empty")
        if not silk_storage.set_outcome(analysis_id, outcome):
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        return {"id": analysis_id, "outcome": outcome, "recorded": True}

    # منصّة SaaS متعددة المستأجرين (PR-1: مصادقة + عزل) تحت /platform — تُركَّب
    # قبل الواجهة الثابتة وبأمان: أي فشل استيراد يُسجَّل ولا يُسقِط المحرّك القائم
    # (مبدأ «لا انهيار»). النقاط تحت /platform مستقلّة عن مسارات المحرّك أعلاه.
    # حارس الإقلاع **يصعد** ولا يُبتلَع: `boot_config_guard` يرفع RuntimeError
    # عند إشارة إنتاج بلا سرّ توقيع، وابتلاعه هنا كان يعني إقلاعاً «أخضر»
    # و/platform غائبة صامتة (404 من الملفات الثابتة) — نفس عائلة «الفقدان
    # الصامت» التي يمنعها SILK_REQUIRE_PERSISTENT_DATA_DIR بالفشل العالي.
    # Only a missing/broken import degrades; a config RuntimeError refuses boot.
    try:
        import silk_platform
    except ImportError:  # المنصّة غير متوفّرة استيراداً · optional at import time
        log.warning("silk_platform not importable — router not mounted", exc_info=True)
    else:
        if silk_platform.mount(app):   # RuntimeError من الحارس يصعد عمداً
            log.info("silk_platform router mounted at /platform")

    # R9 (API-8): سقفُ حجم الجسم — يُضاف **بعد** تركيب المنصّة فيكون الأبعدَ فعلاً
    # (`add_middleware` يدرج في المقدّمة): 413 قبل أن تقرأ `_load_auth` الكوكي أو
    # يفتح أحدٌ قاعدةً (مراجعة R9).
    app.add_middleware(_BodyLimitMiddleware)
    # مراجعة R9: لقطةُ `/health` الأولى **بعد** تركيب المنصّة وبذرها — كانت تُحسَب قبله
    # فتقول `platform_ready` «بلا مستخدمين» حتى أوّل دورة حاصد بعد كلّ نشرة.
    refresh_health_snapshot(app)

    # الواجهة الثابتة على نفس الخدمة — serve the static frontend at "/" so one
    # Render service hosts BOTH the API and the UI (same origin, no CORS needed).
    # Registered last so the API routes above take precedence over static files.
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    if os.path.isdir(web_dir):
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    # R2b (API-3/CONC-5): ختمُ الإغلاق لتشغيلات `/research` الجذرية الحيّة — نفسُ
    # معالج المنصّة (`app.router.add_event_handler` يعمل على Starlette القديم والجديد).
    app.router.add_event_handler("shutdown", silk_research_runtime.shutdown)
    return app


# تطبيق على مستوى الوحدة — module-level app, None when fastapi is unavailable.
# استثناء مصيدة التخزين (LESSONS.md البند ٤) لا يُبتلَع: fastapi غائبة => app=None
# ليبقى الاستيراد يعمل؛ أما رفض التخزين الفاني الإنتاجي فيُعاد رفعه ليفشل
# استيراد `api:app` بصوت عالٍ على Railway (رفض الإقلاع المقصود، لا خدمة صامتة).
try:
    app = create_app()
except RuntimeError as _exc:
    if str(_exc) == _PIP_HINT:  # fastapi absent: keep import working, hold None.
        app = None
        log.warning(_PIP_HINT)
    else:  # مصيدة التخزين الدائم أو أي رفض إقلاع صريح آخر — أفشِل بصوت عالٍ.
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        import uvicorn
    except ImportError:
        print(_PIP_HINT)
    else:
        uvicorn.run(create_app(), host="127.0.0.1", port=8000)
