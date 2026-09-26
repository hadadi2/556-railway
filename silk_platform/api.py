"""واجهة REST للمنصّة — FastAPI router for auth + tenancy (PR-1).

يُحمَّل fastapi/pydantic بكسل داخل المصنع كي يستورد الوحدة دون اعتمادية (نفس
نمط api.py الجذر). كل نقطة مُستأجَرة تشتقّ account_id من سياق الجلسة حصراً —
لا تقرأ owner من الطلب أو الاستعلام أبداً، فلا يمكن العبور بتلاعب المعاملات.

Lazy-imports FastAPI. Tenant scope always comes from the session context, never
from request/query params — query-param manipulation cannot cross tenants.
Cross-tenant reads return 404 (no existence leak); role walls return 403.
"""
# ملاحظة: لا `from __future__ import annotations` هنا عمداً — FastAPI يحلّ
# التلميحات النصّية مقابل globals الوحدة، وأنواع fastapi (Request) مستورَدة
# محلّياً داخل mount() كي تبقى الوحدة قابلة للاستيراد دون fastapi؛ فالتقييم
# الفوري (كائنات حقيقية) هو ما يجعل FastAPI يميّز Request عن معامل استعلام.
import datetime
import json
import logging
import os
import sqlite3
import time
import uuid

# وحدات التنقيب (funnels/email_queue/unsubscribe/reporting/settings/crypto)
# حُذفت نهائياً بقرار المالك 2026-08-17 — المنصّة لدراسات السوق حصراً.
import silk_hs_from_image
import silk_i18n
import silk_product_intake

from . import factory_settings as fsettings
from . import (auth, audit, billing, bootstrap, engine_bridge, entitlements,
               lifecycle, notifications, passwords, pricing, quota, repository,
               scheduler, seed as seed_mod, smtp_transport, storage,
               study_runtime, throttle, tier_config, tokens, wallet)
from .db import connect, init_db
from .models import AuthContext, Role

log = logging.getLogger(__name__)

COOKIE_NAME = "silk_session"
_PREFIX = "/platform"

# خنق الدخول يعيش في قاعدة المنصّة لا في ذاكرة العملية (`silk_platform/throttle.py`):
# الحالة على مستوى الوحدة تنفصل لكل worker فيصير السقف ١٠×عددها، وتُمحى عند كل
# إعادة نشر. Throttle state is DB-backed ⇒ shared across workers, restart-durable.


# ── تحقّق من المدخلات · input coercion (client faults must be 4xx, never 500) ─
def _as_int(value, field: str, *, minimum: int | None = None,
            maximum: int | None = None, default: int | None = None):
    """حوّل مدخلاً إلى صحيح أو ارفعه 422 — coerce to int or raise a 422.

    يرفض النصّ غير الرقمي والعائم (المال بالسنتات الصحيحة: 250.75 لا تُقتطَع
    صمتاً إلى 250) والمنطقي. Rejects non-numeric, float, and bool inputs.
    """
    from fastapi import HTTPException
    if value is None or value == "":
        if default is not None:
            return default
        raise HTTPException(status_code=422, detail=f"{field} is required")
    if isinstance(value, bool) or isinstance(value, float):
        raise HTTPException(status_code=422,
                            detail=f"{field} must be an integer, got {value!r}")
    try:
        out = int(str(value).strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=422,
                            detail=f"{field} must be an integer, got {value!r}")
    if minimum is not None and out < minimum:
        raise HTTPException(status_code=422, detail=f"{field} must be >= {minimum}")
    if maximum is not None and out > maximum:
        raise HTTPException(status_code=422, detail=f"{field} must be <= {maximum}")
    return out


def _require_fields(body: dict, *names: str) -> None:
    """اطلب حقولاً غير فارغة — 422 for a missing NOT NULL field (never a 500)."""
    from fastapi import HTTPException
    missing = [n for n in names if body.get(n) in (None, "")]
    if missing:
        raise HTTPException(status_code=422,
                            detail=f"missing required field(s): {', '.join(missing)}")


def _err(status: int, code: str, message: str, **extra):
    """رفضٌ منظَّم `{error, message}` — R6 (تدقيق 2026-09-01، FE-6): كان نحوُ أربعين
    رفضاً يصل المصنعَ نصّاً إنجليزياً خاماً (`detail="…"`) بينما الصفحةُ تترجم رمزَ
    `error` عبر ERR_AR/ERR_EN وتعرض `message` حين يغيب الرمز من خريطتها. الحقولُ
    الإضافية (`state`، `max_bytes`…) تُلحَق بالجسم كما هي."""
    from fastapi import HTTPException
    detail = {"error": code, "message": message}
    detail.update(extra)
    return HTTPException(status_code=status, detail=detail)


# ── أدوات · helpers (fastapi-free so they stay unit-testable) ────────────────
def _open():
    """افتح اتصالاً وهيّئ القاعدة عند اللزوم — per-request connection."""
    init_db()
    return connect()


def _bearer(headers) -> str:
    raw = headers.get("authorization") or headers.get("Authorization") or ""
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return ""


def _client_ip(request) -> str | None:
    return request.client.host if request.client else None


def _sweep_grace_s(run_stats_raw) -> int | None:
    """نافذةُ سماح الكنس لهذا الصفّ — أو None حين لا كنسَ يعمل (R3، FE-4).

    الواجهة كانت تقول «تجاوزت المدة المعتادة» ولا تقول **ما الذي سيحدث**،
    والعميل لا يعرف النافذة أصلاً (تدقيق 2026-09-01، FE-4). نرسلها كي يقول
    النصُّ إنّ المنصّة ستُعيد الدراسة تلقائياً — و**لا نرسلها** حين يكون
    `SILK_PLATFORM_ORPHAN_SWEEP=0`، فوعدُ تعافٍ بلا كانسٍ اختلاقٌ صريح
    (عقد عدم الاختلاق: لا ادّعاءَ لا يسنده شيء).
    """
    from . import scheduler
    if not scheduler.sweeper_enabled():
        return None
    return engine_bridge._orphan_grace_s(engine_bridge._run_mode(run_stats_raw))


def boot_config_guard() -> None:
    """حارس إقلاع — fail fast if the signing secret is missing in production.

    غير مضبوط في التطوير = وضع مفتوح (سرّ عابر لكل عملية). لكن مع أي إشارة
    إنتاج (`SILK_PLATFORM_REQUIRE_SECRET=1` أو `SILK_PLATFORM_SECURE_COOKIES=1`)
    يجب أن يكون `SILK_PLATFORM_SECRET` مضبوطاً — وإلا نرفض الإقلاع بصوت عالٍ بدل
    الخدمة بسرّ عابر يجعل اعتماد SMTP غير قابل للفكّ بعد إعادة التشغيل ويُبطل
    الروابط الموقّعة. Fail-fast in prod; never silently serve with an ephemeral
    secret. (Mirrors the engine's SILK_REQUIRE_PERSISTENT_DATA_DIR pattern.)
    """
    secret = os.environ.get("SILK_PLATFORM_SECRET", "").strip()
    prod_signal = (os.environ.get("SILK_PLATFORM_REQUIRE_SECRET") == "1"
                   or os.environ.get("SILK_PLATFORM_SECURE_COOKIES") == "1")
    if not secret and prod_signal:
        raise RuntimeError(
            "SILK_PLATFORM_SECRET must be set when a production signal is active "
            "(SILK_PLATFORM_REQUIRE_SECRET=1 or SILK_PLATFORM_SECURE_COOKIES=1); "
            "refusing to boot with an ephemeral per-process secret.")
    # عامل عمل مُخفَّض لا يصل الإنتاج أبداً: التخفيض أداةُ اختبارات، فلو تسرّب
    # `SILK_PLATFORM_BCRYPT_ROUNDS` إلى بيئة إنتاجية نرفض الإقلاع بصوت عالٍ بدل
    # تجزئة كلمات مرور حقيقية بعاملٍ ضعيف صامتاً.
    # A reduced work factor can never reach production — it refuses to boot.
    from .passwords import bcrypt_rounds, _BCRYPT_MIN_PRODUCTION
    if prod_signal and bcrypt_rounds() < _BCRYPT_MIN_PRODUCTION:
        raise RuntimeError(
            f"SILK_PLATFORM_BCRYPT_ROUNDS={bcrypt_rounds()} is below the "
            f"production minimum ({_BCRYPT_MIN_PRODUCTION}); it is a test-only "
            "knob. Refusing to boot with a weakened password work factor.")
    # R4.3 (تدقيق 2026-09-01، API-3): `SILK_PLATFORM_EXPOSE_RESET_TOKEN=1`
    # يُعيد رمزَ إعادة التعيين في جسم الردّ — مفتاحُ اختباراتٍ خالص. تسرّبُه
    # إلى بيئةٍ إنتاجية يجعل «نسيت كلمة السر» سبيلَ استيلاءٍ على أيّ حساب
    # بطلبٍ واحد بلا بريد. نفسُ عائلة حارس عامل العمل أعلاه: مفتاحُ اختبارٍ
    # لا يصل الإنتاجَ أبداً — يرفض الإقلاعَ بصوتٍ عالٍ لا يخدم بصمت.
    if prod_signal and os.environ.get("SILK_PLATFORM_EXPOSE_RESET_TOKEN") == "1":
        raise RuntimeError(
            "SILK_PLATFORM_EXPOSE_RESET_TOKEN=1 returns password-reset tokens "
            "in the API response; it is a test-only knob. Refusing to boot "
            "with it enabled under a production signal.")
    # مراجعة §58 على R4 (2026-09-05): مقعدُ الرُتبتين ٢–٣ يقدّم عيّنةً مصطنعة
    # بدل المحرّك (`engine_bridge.fake_engine_enabled`) — تسرّبُه إلى الإنتاج
    # يجعل كلَّ دراسةٍ مدفوعة تقريراً مختلَقاً بصمت. نفسُ العائلة، نفسُ الرفض.
    if prod_signal and os.environ.get(
            "SILK_PLATFORM_FAKE_ENGINE", "").strip() in ("1", "deep"):
        raise RuntimeError(
            "SILK_PLATFORM_FAKE_ENGINE serves a fabricated sample instead of "
            "the engine; it is a rung-2/3 test seam. Refusing to boot with it "
            "enabled under a production signal.")
    # R7 (AUTH-14): بلا bcrypt يسقط التجزئةُ إلى scrypt الاحتياطي — مقبولٌ في
    # التطوير، مرفوضٌ بصوتٍ عالٍ مع أيّ إشارة إنتاج (المواصفة تسمّي bcrypt).
    from . import passwords as _pw
    if prod_signal and _pw._bcrypt is None:
        raise RuntimeError(
            "bcrypt is not importable; the platform would hash production passwords "
            "with the scrypt fallback. Install `bcrypt` (requirements.txt) — refusing "
            "to boot under a production signal.")
    # R9 (CONC-3): مسارُ الإشباع `GET /_test/slow` أداةُ رُتبة ٢ فقط — لا يعيش تحت
    # أيّ إشارة إنتاج.
    if prod_signal and os.environ.get("SILK_TEST_SLOW_ROUTE_S", "").strip():
        raise RuntimeError(
            "SILK_TEST_SLOW_ROUTE_S exposes a deliberately slow test route; refusing to "
            "boot with it set under a production signal.")


def _secure_cookies() -> bool:
    """هل يُرسَل كوكي الجلسة بعلم `Secure`؟ — Secure flag for the session cookie.

    **تدقيق 2026-08-27 (البند ١٤):** كان العلم مربوطاً بـ
    `SILK_PLATFORM_SECURE_COOKIES=1` وحده، فنشرٌ يضبط إشارة الإنتاج الأخرى
    (`SILK_PLATFORM_REQUIRE_SECRET=1`) كان يخدم كوكي الجلسة **بلا** Secure —
    أي يقبل المتصفّح إرساله على http. وحارس الإقلاع أعلاه يعامل المتغيّرين
    إشارتَي إنتاج **متكافئتين** بالفعل، فالتفاوت كان انجرافاً لا قراراً:
    أيّ إشارة إنتاج ⇒ كوكي Secure.

    Either production signal implies a Secure cookie (the boot guard already
    treats the two as equivalent).
    """
    return (os.environ.get("SILK_PLATFORM_SECURE_COOKIES") == "1"
            or os.environ.get("SILK_PLATFORM_REQUIRE_SECRET") == "1")


def create_platform_app():
    """أنشئ تطبيق المنصّة المستقلّ — standalone FastAPI app for tests/dev."""
    from fastapi import FastAPI
    # نفس قاعدة إطفاء صفحات التوثيق في `api.py` (تدقيق البند ٢٧) — هذا التطبيق
    # المستقل يُستعمل في الاختبارات/التطوير، لكن إن ضُبط مفتاح API فالنيّة نشرٌ.
    _docs_public = (not os.environ.get("SILK_API_KEY", "").strip()
                    or os.environ.get("SILK_PUBLIC_DOCS") == "1")
    app = FastAPI(title="Silk Platform (PR-1: auth + tenancy)",
                  **({} if _docs_public
                     else {"docs_url": None, "redoc_url": None,
                           "openapi_url": None}))
    mount(app)
    return app


def mount(app) -> bool:
    """ركّب كل نقاط المنصّة على `app` تحت /platform — returns True on success."""
    boot_config_guard()   # افشل بصوت عالٍ على سوء تهيئة الإنتاج · fail fast
    try:
        from fastapi import Request, Response
        from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
    except Exception:  # noqa: BLE001 — بلا fastapi لا تركيب (استيراد بلا انهيار)
        log.warning("fastapi unavailable — platform router not mounted")
        return False

    from fastapi import Body, File, Form, HTTPException, UploadFile
    from starlette.concurrency import run_in_threadpool

    def _resolve_token(token: str):
        """حُلّ الرمز في اتصال خاص — blocking; runs in the threadpool."""
        conn = _open()
        try:
            return auth.resolve_session(conn, token)
        finally:
            conn.close()

    # ── وسيط تحميل السياق · context-loading middleware ───────────────────────
    @app.middleware("http")
    async def _load_auth(request: Request, call_next):
        """حمّل current_user/current_account/current_role في سياق الطلب.

        أفضل جهد: لا يرفع أبداً؛ الرمز الغائب/المنتهي => state.auth = None،
        والنقاط المحميّة هي من تفرض 401/403. Best-effort; guards enforce.

        عمل SQLite الحاجب يُنفَّذ في مجمّع خيوط لا على حلقة الأحداث — الوسيط
        يعمل لكل طلب، وحجبُ الحلقة هنا كان يعطّل خدمة المحرّك المُركَّبة معه.
        The blocking DB read runs off the event loop (shared app!).
        """
        request.state.auth = None
        request.state.auth_via = None
        if request.url.path.startswith(_PREFIX):
            _b = _bearer(request.headers)
            token = _b or request.cookies.get(COOKIE_NAME, "")
            # R7 (AUTH-8): كيف وصلت الهويّة — حاملُ رمزٍ صريح أم كوكي المتصفّح.
            request.state.auth_via = "bearer" if _b else ("cookie" if token else None)
            if token:
                request.state.auth = await run_in_threadpool(_resolve_token, token)
            # مراجعة R7: الحارسُ في الوسيط لكلّ GET بالكوكي تحت `/platform` — كان اختياريّاً
            # لثلاثة مسارات (بقي `report.docx` و`signed-url` مكشوفَين) وبـ`Sec-Fetch-Site` وحده.
            if request.method == "GET" and request.state.auth_via == "cookie":
                try:
                    _reject_cross_site_cookie_get(request)
                except HTTPException as exc:
                    return JSONResponse(status_code=exc.status_code,
                                        content={"detail": exc.detail})
        return await call_next(request)

    # ── حرّاس الأدوار · role guards ──────────────────────────────────────────
    def _ctx(request: Request) -> AuthContext:
        ctx = getattr(request.state, "auth", None)
        if ctx is None:
            raise _err(401, "auth_required", "سجّل الدخول أولاً")
        return ctx

    def _require(request: Request, *roles: Role) -> AuthContext:
        ctx = _ctx(request)
        if ctx.role not in roles:
            raise _err(403, "forbidden_role", "هذا الإجراء ليس ضمن صلاحيات دورك")
        return ctx

    def _is_cross_site(request: Request) -> bool:
        """`Sec-Fetch-Site` أوّلاً؛ وبغيابها (متصفّحٌ قديم) مضيفُ `Origin`/`Referer` مقابل
        مضيف الطلب — تطابقٌ = نفسُ الموقع."""
        sfs = request.headers.get("sec-fetch-site", "").strip().lower()
        if sfs:
            return sfs == "cross-site"
        from urllib.parse import urlsplit
        host = (request.headers.get("host") or "").split(":")[0].strip().lower()
        for h in ("origin", "referer"):
            v = request.headers.get(h)
            if v:
                other = (urlsplit(v).hostname or "").lower()
                return bool(other) and other != host
        return False

    def _reject_cross_site_cookie_get(request: Request) -> None:
        """R7 (تدقيق 2026-09-01، AUTH-8): GET ذاتُ أثرٍ (تشخيصٌ يصرف مسابيرَ مدفوعة،
        تقريرٌ/PDF مخنوق) بكوكي المتصفّح من موقعٍ آخر تُرفَض — `SameSite=Lax` يمرّر
        الكوكي مع GET العلوي عبر المواقع، فرابطٌ خبيث كان يستهلك الميزانيةَ باسم
        الأدمِن. حاملُ الرمز الصريح (`Authorization`) لا يُحجَب."""
        if (request.method == "GET"
                and getattr(request.state, "auth_via", None) == "cookie"
                and _is_cross_site(request)):
            raise HTTPException(status_code=403, detail={
                "error": "cross_site_get_refused",
                "message": "هذا الطلب لا يُقبل عبر المواقع بكوكي الجلسة — افتح المنصّة "
                           "مباشرةً ثم أعد المحاولة"})

    # مفاتيحُ الجسم التي تغيّر «ما يُقَرّ به» (R4.8، مراجعة §58): الزوجُ (رمز، سوق)
    # والمنتجُ الذي يحسم المحرّكُ منه البندَ حين لا رمز.
    _ADVISORY_PAIR_KEYS = ("hs_code", "market_pref", "product", "product_id")

    def _json_body(data: dict | None) -> dict:
        return data if isinstance(data, dict) else {}

    def _str_or_none(value):
        """نصٌّ أو None — قائمةُ JSON مكان العنوان كانت تصل SQLite فتنفجر 500."""
        return None if value is None else str(value)

    # ── نقطة عزل عامّة · shared tenant-scoped fetch with 404/403 semantics ────
    def _product_code_changed(conn, row: dict) -> bool:
        """P3 (BIZ-10): رمزُ المنتج في الكتالوج تغيّر بعد أن حملت الدراسةُ رمزَها —
        الدراسةُ صحيحةٌ لرمزها القديم، والصمتُ يجعل المصنعَ يقرأ نتيجةً على بندٍ لم يعد
        بندَه. لا تعديلَ تلقائيّ: إعلانٌ فقط."""
        pid, code = row.get("product_id"), (row.get("hs_code") or "").strip()
        if not pid or not code:
            return False
        try:
            # الكتالوجُ يملكه `account_id` (لا `owner_id` كما في الدراسات) — والخلطُ
            # بينهما كان يُسقط الاستعلامَ في `except` صامتٍ فيبدو الإعلانُ «مطفأً».
            cur = conn.execute(
                "SELECT hs_code FROM products WHERE id = ? AND account_id = ?",
                (int(pid), int(row.get("owner_id") or 0))).fetchone()
        except sqlite3.Error:
            # إعلانٌ تحسينيّ لا يُسقط الصفّ — لكنّه **يُسمَع**: عطلٌ هنا يعني عموداً
            # تغيّر اسمُه، وهو بالضبط ما أخفاه `except Exception` الصامت.
            log.warning("BIZ-10: تعذّر فحصُ رمز المنتج للدراسة %s", row.get("id"),
                        exc_info=True)
            return False
        now = (cur["hs_code"] if cur else "") or ""
        return bool(now.strip()) and now.strip() != code


    def _mark_changed_product_codes(conn, rows: list, account_id: int) -> None:
        """النسخةُ المجمّعة لقائمة الدراسات — استعلامٌ واحد لا واحدٌ لكلّ صفّ.

        الواجهةُ ترسم الدراسات من **القائمة** لا من التفصيل، فإعلانٌ يعيشُ في
        التفصيل وحده إعلانٌ لا يراه أحد (P3/BIZ-10)."""
        pids = {int(r["product_id"]) for r in rows
                if r.get("product_id") and (r.get("hs_code") or "").strip()}
        if not pids:
            return
        try:
            marks = {int(x["id"]): (x["hs_code"] or "").strip() for x in conn.execute(
                "SELECT id, hs_code FROM products WHERE account_id = ? AND id IN (%s)"
                % ",".join("?" * len(pids)),
                (int(account_id), *sorted(pids)))}
        except sqlite3.Error:
            log.warning("BIZ-10: تعذّر فحصُ رموز المنتجات للقائمة", exc_info=True)
            return
        for r in rows:
            pid = r.get("product_id")
            code = (r.get("hs_code") or "").strip()
            now = marks.get(int(pid)) if pid else None
            r["product_code_changed"] = bool(now and code and now != code)

    def _tenant_detail(request: Request, repo_factory, row_id: int,
                       resource_type: str) -> dict:
        """اجلب صفّاً مُستأجَراً بدلالة الدور — enforce the isolation matrix.

        - analyst: 403 (مجمّعات فقط).
        - admin: يرى **الدراسات** كلها (قرار المالك 2026-08-19: «المفروض
          الأدمن يشوف الدراسات») وكلُّ فتحٍ يُقيَّد تدقيقاً باسمه؛ وما عدا
          الدراسات من محتوى المصانع (الصور، بريد المستخدمين) => 403 كما كان.
        - factory: حسابه فقط؛ صفّ حساب آخر => 404 (+ تدقيق محاولة عبور).

        يُغلق اتصاله بنفسه ويرجّع الصفّ فقط — تسليم الاتصال للمُنادي كان عقداً
        قابلاً للتسريب بلا فائدة. Owns and closes its connection; returns the row.
        """
        ctx = _ctx(request)
        conn = _open()
        try:
            repo = repo_factory(conn)
            if ctx.is_silk_analyst:
                raise _err(403, "analyst_aggregates_only", "المحلّل يرى المجاميع فقط")
            row = repo.get(ctx.account_id, row_id)
            if row is not None:
                return row
            # غير مملوك للمنادي · not owned by the caller.
            foreign = repo.exists_anywhere(row_id)
            if ctx.is_silk_admin:
                if foreign:
                    if resource_type == "study":
                        # إشرافٌ مأذونٌ به صراحةً — والقيدُ التدقيقي شرطُ
                        # الإذن لا زينته: من فتح، وأيّ دراسة، ومتى.
                        row = repo.get_unscoped(row_id)
                        if row is None:   # حُذفت بين الفحص والقراءة — 404 لا 500
                            raise _err(404, "not_found", "غير موجود")
                        audit.record(conn, action="admin_study_view",
                                     user_id=ctx.user_id,
                                     account_id=ctx.account_id,
                                     resource_type=resource_type,
                                     resource_id=row_id,
                                     ip_address=_client_ip(request))
                        conn.commit()
                        return row
                    audit.record_denied(conn, action="admin_pii_wall",
                                        user_id=ctx.user_id, account_id=ctx.account_id,
                                        resource_type=resource_type, resource_id=row_id,
                                        ip_address=_client_ip(request))
                    raise _err(403, "admin_pii_wall",
                               "الإدارة لا تطّلع على محتوى المصانع وبياناتهم الشخصية")
                raise _err(404, "not_found", "غير موجود")
            # factory
            if foreign:
                audit.record_denied(conn, action="cross_tenant_read",
                                    user_id=ctx.user_id, account_id=ctx.account_id,
                                    resource_type=resource_type, resource_id=row_id,
                                    ip_address=_client_ip(request))
            raise _err(404, "not_found", "غير موجود")
        finally:
            conn.close()

    def _deny_write_404(conn, request: Request, ctx: AuthContext, repo,
                        row_id: int, resource_type: str, action: str):
        """دلالة رفض الكتابة عبر المستأجر — one place for the write-denial rule.

        صفر صفوف متأثّرة يعني: إمّا الصفّ غير موجود أو لحسابٍ آخر. الحالتان 404
        (لا تسريب وجود)، ومحاولة العبور تُسجَّل تدقيقاً. كانت هذه الكتلة منسوخة
        في خمسة مواضع، فتُنسى في السادس. Single definition of the denial semantics.
        """
        if repo.exists_anywhere(row_id):
            audit.record_denied(conn, action=action, user_id=ctx.user_id,
                                account_id=ctx.account_id,
                                resource_type=resource_type, resource_id=row_id,
                                ip_address=_client_ip(request))
        raise _err(404, "not_found", "غير موجود")

    # ═══════════════════ البادئة تقود إلى الشاشة · prefix → page ═════════════
    @app.get(_PREFIX)
    def platform_root():
        """`/platform` ⇒ صفحة الهبوط التعريفية (طلب المالك 2026-08-17).

        كانت تحويلاً 307 إلى البوابة مباشرةً (إصلاح بلاغ «404 بصيغة JSON»)؛
        المالك طلب «لاند بيج احترافية وفيها زر الدخول إلى البورتال» — فالبادئة
        تخدم صفحة الهبوط، وزرّها يقود إلى `/platform.html` (البوابة كما هي).
        غياب الملف (نشرٌ ناقص) يتراجع للتحويل القديم — لا 404 أبداً.
        """
        import pathlib
        page = (pathlib.Path(__file__).resolve().parent.parent
                / "web" / "platform-landing.html")
        if page.exists():
            return FileResponse(str(page), media_type="text/html")
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/platform.html", status_code=307)

    def _effective_pricing() -> dict:
        """القيم الفعّالة للباقات — نفس مصدر `GET /platform/pricing` بالضبط."""
        conn = _open()
        try:
            return tier_config.effective_pricing(conn)
        finally:
            conn.close()

    @app.get(_PREFIX + "/pricing")
    def public_pricing():
        """باقات المنصّة وأسعارها — عامة عمداً بلا توثيق ولا تقييد معدل.

        لماذا يجوز فتحها (قائمة فحص النقاط): ملف `config/pricing.yaml` الثابت
        + ثوابت `TIER_LIMITS` + **قراءةٌ واحدة** من جدول `tier_settings`
        (تجاوزات المالك، 2026-08-20) — بلا أثر جانبي ولا سرّ ولا PII: أربعة
        صفوف أسعارٍ معروضة للعموم أصلاً على صفحة الباقات. تقرؤها صفحتا الهبوط
        والدفع وقت التشغيل، فالمصدر الواحد يبقى واحداً (لا أرقام منسوخة في
        HTML تنحرف عند تعديل المالك).

        **حدٌّ معلَن (مراجعة ذاتية §58):** هذه أوّل قراءة قاعدةٍ على نقطةٍ
        عامّة بلا تقييد معدل. الاستعلام صفوفٌ أربعة بمفتاحٍ أساسي في استعلامٍ
        واحد، والقاعدة على وضع journal الافتراضي — فإغراقٌ من قرّاء غير
        موثَّقين يزاحم الكُتّاب حتى مهلة `busy_timeout`. تحويل القاعدة إلى WAL
        قرارٌ تشغيليّ مستقلّ لم يُتَّخذ في هذه الموجة.
        """
        return pricing.public_pricing()

    def _duplicate_checkout(conn, email: str, plan: str, cycle: str) -> bool:
        """هل هذا الطلبُ تكرارٌ لطلبٍ قريب؟ — P3 (BIZ-7، تدقيق 2026-09-01): نقرتان على
        «اشترك» كانتا قيدَي تدقيقٍ منفصلَين، فيقرأ الأدمِن طلبين حيث طلبٌ واحد ويتّصل
        مرّتين بالعميل نفسِه. النافذةُ `SILK_PLATFORM_CHECKOUT_DEDUPE_MIN` (١٤٤٠ دقيقة).

        المقارنةُ تفكّ JSON في بايثون ولا تستعمل `LIKE`: مراجعةُ §58 على هذا الإصلاح
        وجدت فخّين في النسخة الأولى — طابعُ `isoformat()` ينتهي بـ`+00:00` بينما
        `created_at` ينتهي بـ`Z` فالمقارنةُ النصّية تنزلق عند الحدّ؛ و`%` أو `_` في
        بريدِ العميل حرفا بدلٍ في `LIKE` فيُبتلَع طلبٌ **مختلف** بلا قيدِ تدقيق.
        """
        try:
            minutes = int(os.environ.get("SILK_PLATFORM_CHECKOUT_DEDUPE_MIN", "1440")
                          or "1440")
        except ValueError:
            minutes = 1440
        if minutes <= 0:
            return False
        # نفسُ صيغة `db.now_iso` حرفياً — مقارنةُ نصٍّ بين صيغتين مختلفتين ليست مقارنة.
        since = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            rows = conn.execute(
                "SELECT changes FROM audit_log WHERE action = 'checkout_requested' "
                "AND created_at >= ? ORDER BY id DESC LIMIT 500", (since,)).fetchall()
        except sqlite3.Error:
            log.warning("BIZ-7: تعذّر فحصُ تكرار الطلب", exc_info=True)
            return False   # تكرارٌ غيرُ مؤكَّد ⇒ سجِّل كالمعتاد (لا نبتلع قيداً بالشكّ)
        for r in rows:
            try:
                ch = json.loads(r["changes"] or "{}")
            except (TypeError, ValueError):
                continue
            if (ch.get("plan") == plan and ch.get("cycle") == cycle
                    and str((ch.get("contact") or {}).get("email") or "") == email):
                return True
        return False

    @app.post(_PREFIX + "/billing/checkout")
    def billing_checkout(request: Request, body: dict = Body(default=None)):
        """طلب اشتراك من صفحة الدفع — عامة عمداً (الاهتمام يسبق وجود حساب:
        الحسابات تُنشئها إدارة سِلك، فمشترِك جديد لا يملك جلسة أصلاً).

        الحوكمة: تقييد معدل لكل IP (نفس `throttle` القائم — يحمي سجلّ
        التدقيق من الإغراق)، السعر **خادمي** من `config/pricing.yaml` (سعر
        العميل لا يُؤتمَن ولا يُقرأ أصلاً)، وقيد تدقيق `checkout_requested`
        يسجّل الطلب فيراه الأدمِن («طلبات الاشتراك» في نظرة عامة).
        **لا دفع وهمي**: مزوّد غير مهيأ = ردّ معلَن `payment_not_configured`
        مع `recorded: true` — لا قيد دفتر ولا توسيع Operation (ترحيل
        SUBSCRIPTION مؤجَّل عمداً حتى مزوّد حقيقي — قرار مقيَّد في السجل).
        """
        body = _json_body(body)
        plan = str(body.get("plan") or "").strip().lower()
        # السعر **الفعّال** لا سعر الملف (§58 على موجة E): منذ صار المالك
        # يعدّل الأسعار من لوحة الأدمِن (2026-08-20) كانت هذه النقطة وحدها ما
        # زالت تقرأ `config/pricing.yaml`، بينما صفحتا الباقات والاشتراك
        # تعرضان قيمة القاعدة عبر `GET /platform/pricing` — فيُسجَّل في التدقيق
        # سعرٌ غير الذي رآه العميل ووافق عليه. مصدرٌ واحد لمسار المال والعرض.
        eff = _effective_pricing()
        if plan not in eff:
            raise HTTPException(status_code=422, detail={
                "error": "unknown_plan",
                "message": f"باقة غير معروفة: {plan or '—'}"})
        cycle = str(body.get("billing_cycle") or "monthly").strip().lower()
        if cycle not in ("monthly", "annual"):
            raise HTTPException(status_code=422, detail={
                "error": "unknown_cycle",
                "message": "الدورة المتاحة: شهرية (monthly) أو سنوية (annual)"})
        # اتساق العرض: باقة مدفوعة شهرياً بلا سعر سنوي = السنوي غير معروض —
        # يُرفض بدل تسجيل «اهتمام سنوي بصفر ريال» لم يُعرَض أصلاً.
        if (cycle == "annual"
                and int(eff[plan]["price_annual"]) <= 0
                < int(eff[plan]["price"])):
            raise HTTPException(status_code=422, detail={
                "error": "annual_not_available",
                "message": "هذه الباقة تُشترى شهرياً فقط حالياً"})
        contact = {
            "name": str(body.get("name") or "").strip()[:200],
            "email": str(body.get("email") or "").strip().lower()[:200],
            "phone": str(body.get("phone") or "").strip()[:200],
            "factory": str(body.get("factory") or "").strip()[:200],
        }
        opportunity_hs = str(body.get("opportunity_hs") or "").strip()
        if opportunity_hs and (len(opportunity_hs) != 6 or not opportunity_hs.isascii()
                               or not opportunity_hs.isdigit()):
            raise _err(422, "invalid_hs_code", "رمز HS يجب أن يتكون من ستة أرقام إنجليزية")
        if not contact["email"] or "@" not in contact["email"]:
            raise _err(422, "checkout_email_required", "بريدُ تواصلٍ صالح مطلوب")
        ip = _client_ip(request)
        # السعر خادمي حصراً — بحسب الدورة، من نفس القيم الفعّالة أعلاه.
        price_sar = int(eff[plan]["price_annual" if cycle == "annual"
                                  else "price"])
        conn = _open()
        try:
            # §58 H1: حدود مستقلة عن عدّاد الدخول (وسقف أعلى — سطح إيرادات
            # عام). **افتراض بيئي معلن:** `request.client.host` لا يكون عنوان
            # الزائر الحقيقي إلا إذا شغّل uvicorn بـ`--proxy-headers` خلف
            # بروكسي الحافة (Dockerfile/railway.json يضبطانه) — وإلا صار
            # المفتاح عنوان البروكسي الواحد فينقفل الدلو عالمياً على الجميع.
            ident = f"checkout|{ip or '-'}"
            limits = throttle.named_limits("CHECKOUT", 30)
            # R7 (AUTH-20): عدّادُ بريدٍ مستقلّ عن IP — قصفُ سجلّ التدقيق ببريدٍ واحد
            # من عناوين كثيرة كان بلا سقف.
            eident = f"checkout-email|{contact['email']}"
            elimits = throttle.named_limits("CHECKOUTEMAIL", 5, 3600)
            if throttle.is_throttled(conn, ident, limits) or \
                    throttle.is_throttled(conn, eident, elimits):
                raise _err(429, "checkout_throttled", "طلباتُ اشتراكٍ كثيرة — حاول لاحقاً")
            throttle.record_failure(conn, ident, limits)   # عدّاد طلبات، لا «فشل»
            throttle.record_failure(conn, eident, elimits)
            # BIZ-7: الفحصُ **بعد** محاسبة الخنق (فلا يصير التكرارُ التفافاً عليه):
            # طلبٌ مكرَّر يُجاب بنفس الردّ مع `duplicate: true` وبلا قيدِ تدقيقٍ ثانٍ.
            _dup = _duplicate_checkout(conn, contact["email"], plan, cycle)
            if not _dup:
                audit.record(conn, action="checkout_requested",
                             resource_type="subscription",
                             changes={"plan": plan, "cycle": cycle,
                                      "price_sar": price_sar, "contact": contact,
                                      "opportunity_hs": opportunity_hs or None},
                             ip_address=ip)
            conn.commit()
        finally:
            conn.close()
        try:
            from . import payments
            provider = payments.provider_from_env()
            if provider is None:
                raise payments.ProviderNotConfigured()
            out = provider.create_checkout(plan, cycle, contact)
        except Exception as exc:
            from .payments import ProviderNotConfigured
            if not isinstance(exc, ProviderNotConfigured):
                raise
            return {"ok": True, "configured": False, "recorded": True,
                    "duplicate": _dup,          # BIZ-7
                    "error": "payment_not_configured",
                    "message_ar": exc.message_ar, "message_en": exc.message_en}
        # (مستقبلاً — مزوّد حقيقي مبني): تحويل فعلي لصفحة الدفع الخارجية.
        return {"ok": True, "configured": True, "recorded": True,
                "duplicate": _dup,              # BIZ-7
                "url": out.get("url"), "reference": out.get("reference")}

    @app.get("/checkout")
    def checkout_page(request: Request):
        """`/checkout?plan=…` ⇒ صفحة الدفع الثابتة بسلسلة الاستعلام كما هي
        (نفس نمط `/reset-password`)."""
        from fastapi.responses import RedirectResponse
        q = request.url.query
        return RedirectResponse("/checkout.html" + (f"?{q}" if q else ""),
                                status_code=307)

    @app.get("/reset-password")
    def reset_password_page(request: Request):
        """`/reset-password?token=…` ⇒ الصفحة الثابتة، بسلسلة الاستعلام كما هي.

        بريد إعادة التعيين يبني الرابط بلا لاحقة `.html` (`_send_password_reset_
        email`)، والملفّات الثابتة تخدم `/reset-password.html` فقط — فكان رابط
        البريد الفعليّ يقود إلى 404 لأول مستخدم ينسى كلمته. التحويل يحفظ
        `?token=` كي تقرأه الصفحة.
        """
        from fastapi.responses import RedirectResponse
        q = request.url.query
        return RedirectResponse("/reset-password.html" + (f"?{q}" if q else ""),
                                status_code=307)

    # ══════════════════════════ AUTH ════════════════════════════════════════
    # ملاحظة على `def` بلا `async` في كل ما يلي: هذه المعالجات تُنفِّذ عملاً
    # حاجباً (bcrypt عامل ١٢ ≈ ٢٥٠ms، وSQLite بمهلة انتظار قفل). FastAPI يشغّل
    # المعالجات المتزامنة في مجمّع خيوط تلقائياً، فلا تُحجَب حلقة الأحداث —
    # وهي حلقة **مشتركة** مع خدمة المحرّك المُركَّبة على نفس التطبيق.
    # Sync handlers ⇒ FastAPI runs them in its threadpool, off the shared loop.
    @app.post(_PREFIX + "/auth/login")
    def login(request: Request, body: dict = Body(default=None)):
        body = _json_body(body)
        # R4.5 (تدقيق 2026-09-01، API-5): إكراهٌ نصّيّ كما في `billing_checkout`
        # و`change_my_password` — قائمةُ JSON مكان النصّ كانت `AttributeError`
        # داخلياً (500) لا عيبَ عميلٍ معلَناً.
        email = str(body.get("email") or "").strip()
        password = str(body.get("password") or "")
        ip = _client_ip(request)
        # درس 190: هويّةٌ محجوزة الفضاء (F1 — لا يزوّرها بريدٌ = «pwreset»)
        # + عدّادُ IP تجميعيّ (F6 — يحدّ الرشَّ عبر حساباتٍ كثيرة من مصدرٍ واحد).
        ident = throttle.login_identity(email, ip)
        ip_ident = throttle.login_ip_identity(ip)
        ip_limits = throttle.named_limits("LOGINIP", 50)
        # R7 (AUTH-1/API-7): عدّادٌ ثالث بالبريد وحده — تدويرُ IP كان يتجاوز الأوّلَين.
        email_ident = throttle.login_email_identity(email)
        email_limits = throttle.named_limits("LOGINEMAIL", 30, 900)
        conn = _open()
        try:
            # الخنق يُقرأ من القاعدة فيراه كل worker فوراً (لا حالة في الذاكرة).
            if (throttle.is_throttled(conn, ident)
                    or throttle.is_throttled(conn, ip_ident, ip_limits)
                    or throttle.is_throttled(conn, email_ident, email_limits)):
                raise _err(429, "login_throttled", "محاولاتٌ فاشلة كثيرة — حاول لاحقاً")
            user = auth.authenticate(conn, email, password)
            if not user:
                throttle.record_failure(conn, ident)
                throttle.record_failure(conn, ip_ident, ip_limits)
                throttle.record_failure(conn, email_ident, email_limits)
                # لا تعداد مستخدمين: نفس الرسالة والتوقيت للمجهول والخطأ.
                raise _err(401, "invalid_credentials", "بيانات الدخول غير صحيحة")
            # امسح عدّاد البريد عند النجاح؛ عدّادُ IP يبقى ضمن نافذته (حمايةُ
            # الرشّ لا تُصفَّر بحسابٍ صحيحٍ واحد يملكه المهاجم).
            throttle.clear(conn, ident)
            throttle.clear(conn, email_ident)
            raw = auth.create_session(
                conn, user["id"], ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent"))
            audit.record(conn, action="login", user_id=user["id"],
                         account_id=user["account_id"], resource_type="session",
                         ip_address=_client_ip(request))
            conn.commit()
            payload = {"token": raw, "user": {
                "id": user["id"], "email": user["email"], "role": user["role"],
                "account_id": user["account_id"],
                "language_preference": user["language_preference"]}}
        finally:
            conn.close()
        resp = JSONResponse(payload)
        # secure عبر البيئة: HTTPS في الإنتاج، http في التطوير المحلي.
        # R7 (AUTH-6): طلبٌ وصل عبر https ⇒ Secure ولو غابت إشارةُ الإنتاج — لا أضعف أبداً.
        resp.set_cookie(COOKIE_NAME, raw, httponly=True, samesite="lax",
                        secure=_secure_cookies() or request.url.scheme == "https")
        return resp

    @app.post(_PREFIX + "/auth/logout")
    def logout(request: Request):
        ctx = _ctx(request)
        conn = _open()
        try:
            if ctx.session_id:
                auth.destroy_session(conn, ctx.session_id)
        finally:
            conn.close()
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE_NAME)
        return resp

    @app.get(_PREFIX + "/me")
    def me(request: Request):
        ctx = _ctx(request)
        conn = _open()
        try:
            row = conn.execute(
                "SELECT first_name, last_name, language_chosen_at, created_at "
                "FROM users WHERE id = ?",
                (ctx.user_id,)).fetchone()
            # اسم المنشأة (النمط العالمي 2026-08-19: بطاقة الحساب في «الملف
            # التعريفي» تعرض هوية المصنع) — عرضٌ فقط؛ تعديله صلاحية أدمِن.
            acct = conn.execute(
                "SELECT name FROM accounts WHERE id = ?",
                (ctx.account_id,)).fetchone() if ctx.account_id else None
            # لغة تقارير المصنع (الموجة ٠) — إعدادٌ **مستقلّ تماماً** عن لغة
            # واجهة المستخدم أدناه: هذه تحكم لغة التقارير المولَّدة، وتلك تحكم
            # لغة الشاشة. لا يُشتقّ أحدهما من الآخر ولا يُستبدَل به.
            fac_lang = (fsettings.factory_language(conn, ctx.account_id)
                        if ctx.account_id else silk_i18n.DEFAULT_LANG)
            fac_chosen = (fsettings.factory_language_chosen(conn, ctx.account_id)
                          if ctx.account_id else False)
        finally:
            conn.close()
        # §58 M4: التفضيل يُطبَّق عبر الأجهزة فقط إن كان اختياراً صريحاً —
        # الختم يكتبه PATCH /me/language حصراً؛ غيابه = افتراض مخطط يُتجاهل.
        chosen = bool(row and row["language_chosen_at"])
        return {"user_id": ctx.user_id, "account_id": ctx.account_id,
                "role": ctx.role.value, "email": ctx.email,
                # بيانات الملف التعريفي (2026-08-18) — يعرضها قسم «الملف التعريفي».
                "first_name": (row["first_name"] if row else None),
                "last_name": (row["last_name"] if row else None),
                "account_name": (acct["name"] if acct else None),
                "member_since": (row["created_at"] if row else None),
                "language_preference": ctx.language_preference,
                "language_chosen": chosen,
                "factory_language": fac_lang,
                "factory_language_chosen": fac_chosen}

    @app.patch(_PREFIX + "/account/language")
    def set_factory_language(request: Request, body: dict = Body(default=None)):
        """لغة **تقارير المصنع** — مصدر الحقيقة الوحيد للغة أيّ تقريرٍ قادم.

        مرآةٌ حرفية لـ`PATCH /me/language` في كل شيء عدا الهدف: هناك
        `users.language_preference` (لغة الشاشة لكل مستخدم)، وهنا
        `accounts.language_preference` (لغة تقارير المصنع كلّه). الإعدادان
        **لا يُستبدَل أحدهما بالآخر أبداً** — مستخدمٌ يقرأ الشاشة بالإنجليزية
        قد يريد تقارير عربية لمصنعه، والعكس.

        ذاتية النطاق بالبناء (`ctx.account_id` لا معرّفٌ من الطلب) فلا عبور
        مستأجرين. الدراسات الجارية لا تتأثّر: لغتها لُقِطت عند إطلاقها.
        """
        ctx = _require(request, Role.SILK_ADMIN, Role.SILK_ANALYST, Role.FACTORY)
        body = _json_body(body)
        lang = str(body.get("language_preference") or "").strip().lower()
        if not fsettings.valid(lang):
            raise _err(422, "bad_language", "اللغة المتاحة: ar أو en")
        if not ctx.account_id:
            raise _err(422, "no_account", "لا حسابَ مرتبطاً بهذا المستخدم")
        conn = _open()
        try:
            fsettings.set_factory_language(conn, ctx.account_id, lang)
            audit.record(conn, action="account_language_changed",
                         user_id=ctx.user_id, account_id=ctx.account_id,
                         resource_type="account", resource_id=ctx.account_id,
                         changes={"language": lang})
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "factory_language": lang}

    @app.patch(_PREFIX + "/me/language")
    def set_my_language(request: Request, body: dict = Body(default=None)):
        """اختيار لغة الواجهة — أي دورٍ، صفُّه الذاتي حصراً (2026-08-17).

        قرار المالك: «لغة المنصة لغتين عربي وانجليزي». العمود
        `users.language_preference` موجود منذ الترحيل 001 بلا مستهلك؛
        و`PATCH /users/{id}` قاصر على دور المصنع فما كان للأدمِن/المحلّل
        سبيلٌ لحفظ لغته — هذه النقطة ذاتية النطاق بالبناء (`ctx.user_id`
        لا معرّف من الطلب) فلا عبور مستأجرين أصلاً.
        """
        ctx = _require(request, Role.SILK_ADMIN, Role.SILK_ANALYST, Role.FACTORY)
        body = _json_body(body)
        lang = str(body.get("language_preference") or "").strip().lower()
        if lang not in ("ar", "en"):
            raise _err(422, "bad_language", "اللغة المتاحة: ar أو en")
        conn = _open()
        try:
            now = auth.now_iso()
            conn.execute("UPDATE users SET language_preference = ?, "
                         "language_chosen_at = ?, updated_at = ? "
                         "WHERE id = ?",
                         (lang, now, now, ctx.user_id))
            audit.record(conn, action="language_changed", user_id=ctx.user_id,
                         account_id=ctx.account_id, resource_type="user",
                         resource_id=ctx.user_id, changes={"language": lang})
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "language_preference": lang}

    @app.patch(_PREFIX + "/me")
    def patch_me(request: Request, body: dict = Body(default=None)):
        """تعديل البيانات الشخصية — أي دورٍ، صفُّه الذاتي حصراً (بروفايل 2026-08-18).

        `PATCH /users/{id}` قاصر على دور المصنع؛ هذه النقطة ذاتية النطاق
        بالبناء (`ctx.user_id`) فتخدم الأدوار الثلاثة. الاسمان فقط — البريد
        هوية دخول لا يُعدَّل ذاتياً، والدور/الحساب نظاميان.
        """
        ctx = _require(request, Role.SILK_ADMIN, Role.SILK_ANALYST, Role.FACTORY)
        body = _json_body(body)
        fields = {}
        for col in ("first_name", "last_name"):
            if col in body:
                fields[col] = str(body.get(col) or "").strip()[:100] or None
        if not fields:
            raise _err(422, "profile_name_required", "الاسم الأول أو الأخير مطلوب")
        conn = _open()
        try:
            # جملتان ثابتتان (لا f-string) كي يراهما حارس العزل AST حرفياً.
            row = conn.execute(
                "SELECT first_name, last_name FROM users WHERE id = ?",
                (ctx.user_id,)).fetchone()
            conn.execute(
                "UPDATE users SET first_name = ?, last_name = ?, "
                "updated_at = ? WHERE id = ?",
                (fields.get("first_name", row["first_name"] if row else None),
                 fields.get("last_name", row["last_name"] if row else None),
                 auth.now_iso(), ctx.user_id))
            audit.record(conn, action="profile_updated", user_id=ctx.user_id,
                         account_id=ctx.account_id, resource_type="user",
                         resource_id=ctx.user_id,
                         changes={"fields": sorted(fields)})
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, **fields}

    @app.post(_PREFIX + "/me/password")
    def change_my_password(request: Request, body: dict = Body(default=None)):
        """تغيير كلمة المرور ذاتياً — بروفايل 2026-08-18 (كان الحذف بمساعدة
        الأدمِن فقط). الحالية تُتحقَّق أولاً؛ السياسة تُفرَض؛ بقية الجلسات
        تُبطَل وجلسة الطلب تبقى (أثبتت نفسها للتو).
        """
        from .passwords import PasswordError
        ctx = _require(request, Role.SILK_ADMIN, Role.SILK_ANALYST, Role.FACTORY)
        body = _json_body(body)
        conn = _open()
        try:
            # §58: تخمين «الحالية» من جلسةٍ مسروقة كان بلا خنق — نفس خانق
            # الدخول (قاعدة البيانات، كل الـworkers) على هوية المستخدم نفسه.
            ident = throttle.identity(f"pwchange|{ctx.user_id}",
                                      _client_ip(request))
            if throttle.is_throttled(conn, ident):
                raise _err(429, "password_change_throttled", "محاولاتٌ فاشلة كثيرة — حاول لاحقاً")
            try:
                ok = auth.change_password(
                    conn, ctx.user_id,
                    str(body.get("current_password") or ""),
                    str(body.get("new_password") or ""),
                    keep_session_id=ctx.session_id)
            except PasswordError as exc:
                raise _err(422, "password_policy", str(exc))     # R6 (FE-6)
            if not ok:
                throttle.record_failure(conn, ident)
                conn.commit()
                raise HTTPException(status_code=403, detail={
                    "error": "wrong_current_password",
                    "message": "كلمة المرور الحالية غير صحيحة"})
            # درس 190 (F3): قيد التدقيق **قبل** `throttle.clear` — clear يلتزم
            # الاتصال المشترك، و`auth.change_password` لا يلتزم عمداً كي يكون
            # التغيير وقيدُه ذرّيين. كان clear يفلش التغيير قبل تسجيل القيد،
            # فتعطّلٌ بينهما يترك كلمةً مبدَّلةً وجلساتٍ مقتولةً بلا أثر تدقيق.
            # الآن الالتزام الوحيد (داخل clear) يفلش التغيير + القيد + مسح
            # العدّاد معاً.
            audit.record(conn, action="password_changed", user_id=ctx.user_id,
                         account_id=ctx.account_id, resource_type="user",
                         resource_id=ctx.user_id, ip_address=_client_ip(request))
            throttle.clear(conn, ident)   # DELETE + commit ذرّي للكلّ
        finally:
            conn.close()
        return {"ok": True}

    def _deliver_reset_email(cfg: dict, to_email: str, subject: str, body: str,
                             msg_id: str) -> str | None:
        """أرسل رسالةَ إعادة تعيينٍ واحدة وسجّل نتيجتها على اتصالٍ خاصّ — يعيد نصَّ الخطأ
        المنقّح عند الفشل أو None عند النجاح؛ لا يرفع أبداً."""
        conn2 = _open()
        try:
            try:
                smtp_transport.send(host=cfg["host"], port=cfg["port"],
                                    use_tls=cfg["use_tls"], username=cfg["username"],
                                    password=cfg["password"],
                                    from_email=cfg["from_email"],
                                    from_name=cfg["from_name"], to_email=to_email,
                                    subject=subject, body=body, msg_id=msg_id)
            except Exception as exc:  # noqa: BLE001 — يُسجَّل لا يُخفى ولا يُرفَع
                err = smtp_transport.safe_error(exc)
                audit.record(conn2, action="password_reset_email_failed",
                             resource_type="user", changes={"error": err})
                conn2.commit()
                return err
            audit.record(conn2, action="password_reset_email_sent", resource_type="user")
            conn2.commit()
            return None
        finally:
            conn2.close()

    def _deliver_reset_email_async(cfg: dict, to_email: str, subject: str, body: str,
                                   msg_id: str) -> None:
        """R7 (AUTH-3): الإرسالُ في خيطٍ خلفيّ للمسار **العامّ** — نداءُ SMTP المتزامن كان
        يجعل زمنَ الردّ يفضح وجودَ البريد (قناةُ توقيت)."""
        smtp_transport.send_async(
            lambda: _deliver_reset_email(cfg, to_email, subject, body, msg_id))

    def _send_password_reset_email(email: str, lang: str, raw_token: str,
                                   *, sync: bool = False) -> str | None:
        """أرسل بريد إعادة التعيين — best-effort؛ لا يرفع أبداً للمنادي.

        غياب تهيئة SMTP التشغيلية (`operator_config_from_env`) أو فشل الإرسال
        يُسجَّل تدقيقاً فقط؛ ردّ العميل يبقى `{"ok": true}` بصرف النظر — رفعُ
        عطلٍ هنا كان سيصنع قناةً جانبية (توقيت/حالة استثناء) تُميّز بريداً
        موجوداً عن غائب. Never raises — a failure here must not become a
        side-channel that reveals whether the email exists.
        """
        cfg = smtp_transport.operator_config_from_env()
        if cfg is None:
            return None
        reset_url = f"{smtp_transport.base_url()}/reset-password?token={raw_token}"
        if lang == "ar":
            subject = "إعادة تعيين كلمة المرور — سِلك"
            body = ("لإعادة تعيين كلمة مرورك اضغط الرابط التالي (صالح لفترة محدودة):\n"
                    f"{reset_url}\n\nإن لم تطلب هذا فتجاهل الرسالة.")
        else:
            subject = "Password reset — Silk"
            body = ("Reset your password using the link below (valid for a "
                    f"limited time):\n{reset_url}\n\nIf you did not request this, "
                    "ignore this email.")
        msg_id = f"<platform-password-reset-{tokens.hash_token(raw_token)[:16]}@silk-platform.local>"
        if sync:   # مسارُ الأدمِن المُصادَق: النتيجةُ تُعاد صدقاً (مراجعة R7)
            return _deliver_reset_email(cfg, email, subject, body, msg_id)
        _deliver_reset_email_async(cfg, email, subject, body, msg_id)
        return None

    @app.post(_PREFIX + "/auth/password-reset/request")
    def reset_request(request: Request, body: dict = Body(default=None)):
        body = _json_body(body)
        email = str(body.get("email") or "").strip().lower()   # R4.5
        raw = None
        conn = _open()
        try:
            # صيد الفجوات ٣: كان السطح العام الوحيد الحسّاس بلا خانق إطلاقاً
            # — قصفُ بريدِ أي مصنع برسائل إعادة تعيين بلا حدّ + سكُّ رموزٍ
            # بلا سقف. الهوية بعنوان IP وحده (لا البريد): تدوير البريد كان
            # سيتجاوز عدّاداً بريديّ الهوية. نفس نمط الأشقاء: عدّاد مسمّى
            # بالقاعدة يراه كل worker.
            # دورة C4: عدّادان معاً — IP وحده قابل للانتحال عبر XFF خلف
            # `--forwarded-allow-ips=*` (railway.json)، والبريد وحده يُتجاوز
            # بتدويره؛ اجتماعهما يسقف قصف بريدٍ واحد وسكّ الرموز معاً.
            limits = throttle.named_limits("PWRESET", 5, 3600)
            # درس 190 (F2): عدّاد البريد بعتبةٍ أعلى مستقلّة — العتبة الموحّدة
            # 5/ساعة جعلت 5 طلباتٍ تسمّي ضحيةً تقفل استعادتها؛ رفعُها لعدّاد
            # البريد وحده (15/ساعة) يرفع كلفة القفل المستهدف ويُبقي عدّاد IP
            # المشدود (5/ساعة) لقصف مصدرٍ واحد. مستخدمٌ شرعيّ لا يطلب 15/ساعة.
            email_limits = throttle.named_limits("PWRESETEMAIL", 15, 3600)
            ident_ip = throttle.identity("pwreset", _client_ip(request))
            ident_email = throttle.identity(f"pwreset|{email}", None)
            if throttle.is_throttled(conn, ident_ip, limits) or \
                    throttle.is_throttled(conn, ident_email, email_limits):
                raise _err(429, "reset_throttled", "طلباتُ إعادة تعيينٍ كثيرة — حاول لاحقاً")
            # حدود كل عدّاد تُمرَّر للإدراج أيضاً (درس 187): بلا `limits` كان
            # الإدراج يشذّب صفوف الهوية على نافذة الدخول (300ث) بينما العدّ
            # أعلاه على الساعة — «5/ساعة» فعلياً ~4 كل 5 دقائق.
            throttle.record_failure(conn, ident_ip, limits)
            throttle.record_failure(conn, ident_email, email_limits)
            raw = auth.issue_reset_token(conn, email)
            if raw is not None:
                lang = auth.user_language_by_email(conn, email)
                _send_password_reset_email(email, lang, raw)
        finally:
            conn.close()
        # لا تفصح عن وجود المستخدم · never reveal whether the user exists.
        # أمنيّاً حرج: الرمز الخام لا يُعاد في الردّ إطلاقاً في الإنتاج — وإلا
        # لأمكن أي مهاجم طلب إعادة تعيين لأي بريد والاستيلاء على الحساب فوراً.
        # يُرسَل بالبريد أعلاه. يُكشف في الردّ فقط خلف علم بيئة صريح للاختبار.
        # SECURITY: the raw token is emailed, never returned in the response —
        # exposing it would allow trivial account takeover. Test-only env gate.
        out = {"ok": True}
        if raw is not None and os.environ.get("SILK_PLATFORM_EXPOSE_RESET_TOKEN") == "1":
            out["reset_token"] = raw
        return out

    @app.post(_PREFIX + "/auth/password-reset/confirm")
    def reset_confirm(request: Request, body: dict = Body(default=None)):
        from .passwords import PasswordError
        body = _json_body(body)
        conn = _open()
        try:
            # صيد الفجوات ٣: خانق التأكيد بهوية IP (لا بريد في الجسم) — رمز
            # 32 بايت عشوائي يجعل التخمين نظرياً، والخنق دفاع عمق كالأشقاء.
            ident = throttle.identity("pwreset-confirm",
                                      _client_ip(request))
            limits = throttle.named_limits("PWRESET", 5, 3600)
            if throttle.is_throttled(conn, ident, limits):
                raise _err(429, "reset_confirm_throttled", "محاولاتٌ كثيرة — حاول لاحقاً")
            throttle.record_failure(conn, ident, limits)   # درس 187 — كما أعلاه
            _raw_tok = str(body.get("token") or "")
            _owner = conn.execute(
                "SELECT u.email FROM password_reset_tokens t JOIN users u ON u.id = t.user_id "
                "WHERE t.token_hash = ?", (tokens.hash_token(_raw_tok),)).fetchone()
            try:
                ok = auth.consume_reset_token(
                    conn, _raw_tok,                                   # R4.5
                    str(body.get("new_password") or ""))
            except PasswordError as exc:
                raise _err(422, "password_policy", str(exc))     # R6 (FE-6)
            # درس 190 (F16): امسح العدّاد عند النجاح — كان يعدّ **كلَّ** محاولة
            # (والناجحة منها)، فخمسة موظّفين خلف NAT واحد يقفلون السادس عن
            # استعمال رمزٍ صالح. النجاح يبرّئ المصدر.
            if ok:
                throttle.clear(conn, ident)
                if _owner is not None:
                    # مراجعة R7: صاحبُ الحساب يستعيد دخولَه من قفل عدّاد البريد (٣٠ فشلاً
                    # من أيّ مكان) بإعادة تعيينٍ ناجحة — القفلُ لا يبقى أبدياً.
                    throttle.clear(conn, throttle.login_email_identity(str(_owner["email"])))
        finally:
            conn.close()
        if not ok:
            raise _err(400, "bad_reset_token", "الرمز غير صالح أو مستعمَل")
        return {"ok": True}

    # ═══════════ المنتجات · factory product catalog (2026-08-18) ═════════════
    _PRODUCT_FIELDS = ("name", "description", "hs_code", "image_id")

    def _product_fields(conn, ctx: AuthContext, body: dict,
                        *, require_name: bool,
                        stored: dict | None = None) -> dict:
        """حقول المنتج المتحقَّق منها — نفس عقود حقول الدراسة (رمز HS، ملكية الصورة).

        `stored` هو صفّ المنتج المخزون — يمرّره مسار **التحديث** وحده (حيث
        يوجد صفٌّ يُقارَن به) لتمييز الرمز المتغيّر فعلاً من المردَّد؛ مسار
        الإنشاء يتركه `None` فكلُّ رمزٍ فيه كتابةٌ أولى بمصدرها.
        """
        out: dict = {}
        if "name" in body or require_name:
            name = str(body.get("name") or "").strip()[:200]
            if not name:
                raise HTTPException(status_code=422, detail={
                    "error": "product_no_name",
                    "message": "المنتج بلا اسم — اكتب اسم المنتج"})
            out["name"] = name
        if "description" in body:
            out["description"] = str(body.get("description") or "").strip()[:2000]
        if "hs_code" in body:
            out["hs_code"] = _validated_hs_code(body)
            # الترحيل ٠١٧: رمزٌ يكتبه إنسانٌ في الكتالوج مصدرُه `manual` لا
            # «كتالوج» مجهولُ الأصل — الدرس ٢٠٩ («يُعتمَد كما هو») لم يكن له
            # موضعٌ يُكتَب فيه، فكان يتناقض مع الدرس ١٢٠ على المسار نفسه.
            # لكن **ردَّ الرمز المخزون ليس كتابةً يدوية**: نموذج التحرير يرسل
            # الرمز المعبّأ مسبقاً دائماً، فحضورُ المفتاح وحده لا يثبت قصداً —
            # عند التحديث (`stored` حاضر) رمزٌ يطابق المخزون يُبقي المصدرَ
            # والختمَ كما هما (لا ترقية ثقة صامتة لصفٍّ قديم — قاعدة الترحيل
            # نفسها)، والتغييرُ الحقيقي وحده — رمزٌ آخر أو مسحٌ صريح — يجدّدهما.
            if stored is None or ((out["hs_code"] or None)
                                  != (stored.get("hs_code") or None)):
                out["hs_source"] = "manual" if out["hs_code"] else "unknown"
                out["hs_set_at"] = auth.now_iso()
        if "image_id" in body:
            out["image_id"] = _validated_owned_image_id(conn, ctx, body)
        out.update(_product_economics_fields(body))
        return out

    _TIERS = ("premium", "standard", "economy")

    def _product_economics_fields(body: dict) -> dict:
        """الحقولُ الاقتصادية (الموجة C، E-04) — تُملأ بطاقةَ المنتج للمحرّك.

        **الفراغُ يبقى فراغاً.** حقلٌ غيرُ مُرسَلٍ لا يُكتَب، وحقلٌ مُرسَلٌ فارغاً
        يُمحى إلى `NULL` صراحةً — لا قيمةَ افتراضية ولا تقدير: تكلفةُ الوحدة
        رقمُ المصنع نفسه، وتقديرُها اختلاقٌ لبيانات العميل لا سدُّ فجوة.
        """
        out: dict = {}
        for key in ("cost_per_unit", "monthly_capacity", "shipping_per_unit",
                    "fixed_costs", "financing_rate_pct", "collection_days"):
            if key not in body:
                continue
            raw = body.get(key)
            if raw in (None, ""):
                out[key] = None
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                raise HTTPException(status_code=422, detail={
                    "error": "product_bad_number",
                    "message": f"«{key}» يجب أن يكون رقماً"})
            if val < 0:
                raise HTTPException(status_code=422, detail={
                    "error": "product_negative_number",
                    "message": f"«{key}» لا يكون سالباً"})
            # الدرس ٢٨٣: معدّلٌ سنويّ ٪ ومدّةٌ بالأيام — حدّان معقولان.
            _bound = {"financing_rate_pct": (100, "معدل التمويل السنوي"),
                      "collection_days": (730, "مدة التحصيل بالأيام")}.get(key)
            if _bound and val > _bound[0]:
                raise HTTPException(status_code=422, detail={
                    "error": "product_out_of_range",
                    "message": f"«{_bound[1]}» يجب ألا يتجاوز {_bound[0]}"})
            out[key] = val
        if "cost_unit" in body:
            out["cost_unit"] = str(body.get("cost_unit") or "").strip()[:40] or None
        if "cost_currency" in body:
            # تقرير ٧ §3.5: رمزُ ISO كما يصرّح به المصنع — لا تخمين عملة.
            cur = str(body.get("cost_currency") or "").strip().upper()
            if cur and not (len(cur) == 3 and cur.isalpha()):
                raise HTTPException(status_code=422, detail={
                    "error": "product_bad_currency",
                    "message": "عملةُ التكلفة رمزٌ من ثلاثة أحرف (مثل SAR)"})
            out["cost_currency"] = cur or None
        if "tier" in body:
            tier = str(body.get("tier") or "").strip().lower()
            if tier and tier not in _TIERS:
                raise HTTPException(status_code=422, detail={
                    "error": "product_bad_tier",
                    "message": "الشريحة: premium أو standard أو economy"})
            out["tier"] = tier or None
        if "certifications" in body:
            raw = body.get("certifications")
            items = raw if isinstance(raw, list) else str(raw or "").split(",")
            clean = [str(c).strip()[:40] for c in items if str(c).strip()]
            out["certifications"] = ",".join(clean[:12]) or None
        return out

    def _study_product_card(study: dict, ctx: AuthContext) -> dict | None:
        """بطاقةُ منتج الدراسة من الكتالوج — أو `None` بلا تقدير (E-04).

        تُقرأ باتصالٍ مستقلٍّ قصير **بعد** إغلاق اتصال المطالبة: البناءُ لا
        يجوز أن يطيل عمرَ القفل الذي تُختَم فيه الحصّةُ والرمز.
        """
        card = None
        pid = study.get("product_id")
        if pid:
            conn = _open()
            try:
                row = conn.execute(
                    "SELECT * FROM products WHERE id = ? AND account_id = ?",
                    (int(pid), ctx.account_id)).fetchone()
                card = engine_bridge.product_card_from_row(
                    dict(row) if row else None)
            except Exception as exc:  # noqa: BLE001 — إضافةٌ لا شرطُ إطلاق
                log.warning("product card read failed: %s", exc)
            finally:
                conn.close()
        # هدف الدراسة الاحترافية (البند ٢): تكلفة الدراسة نفسها تغلب تكلفة
        # الكتالوج — أو تبني بطاقة وحدها حين لا كتالوج.
        return engine_bridge.apply_study_cost(
            card, study, product=str(study.get("product") or ""))

    @app.get(_PREFIX + "/unit-hint")
    def unit_hint(request: Request, product: str = ""):
        """وحدة سوق المنتج لحقل التكلفة — المصدر الواحد `silk_economics.market_unit`
        (هدف الدراسة الاحترافية، البند ٢): «حليب» ⇒ لتر، «تمور» ⇒ كجم.
        الواجهة تسأل هنا بدل أن تحمل نسخة موازية من السجل."""
        _require(request, Role.SILK_ADMIN, Role.FACTORY)
        from silk_economics import market_unit
        code, label_ar = market_unit(product)
        return {"code": code, "label_ar": label_ar}

    @app.get(_PREFIX + "/products")
    def list_products(request: Request):
        """كتالوج منتجات الحساب + عدد دراسات كل منتج — يغذي قسم «المنتجات»."""
        ctx = _require(request, Role.FACTORY)
        conn = _open()
        try:
            rows = repository.products(conn).list(ctx.account_id, order="id DESC")
            counts = {int(r["product_id"]): int(r["c"]) for r in conn.execute(
                "SELECT product_id, COUNT(*) AS c FROM studies "
                "WHERE owner_id = ? AND product_id IS NOT NULL "
                "GROUP BY product_id", (ctx.account_id,)).fetchall()}
            for r in rows:
                r["studies_count"] = counts.get(int(r["id"]), 0)
        finally:
            conn.close()
        return {"products": rows}

    @app.post(_PREFIX + "/products")
    def create_product(request: Request, body: dict = Body(default=None)):
        ctx = _require(request, Role.FACTORY)
        body = _json_body(body)
        conn = _open()
        try:
            fields = _product_fields(conn, ctx, body, require_name=True)
            row = repository.products(conn).create(ctx.account_id, fields)
            audit.record(conn, action="product_created", user_id=ctx.user_id,
                         account_id=ctx.account_id, resource_type="product",
                         resource_id=row["id"], ip_address=_client_ip(request))
            conn.commit()
        finally:
            conn.close()
        return row

    def _vision_allowed_for_platform() -> tuple[bool, str]:
        """هل يُسمح نداءُ رؤيةٍ واحد؟ — (allowed, reason).

        يعكس `api._intake_vision_allowed` حرفياً في شروطه (مفتاح كلود،
        حارسُ المفاتيح المدفوعة بلا مصادقة، السقفُ اليوميّ المشترك) — لأن
        دفترَ الاستهلاك واحدٌ للسطحين. الرفضُ يتدهور بصدق إلى «أدخل الرمز»
        لا إلى عطلٍ يقرؤه المصنع.
        """
        import silk_usage
        # EXT-13: الحارسُ الواحد — الشروطُ نفسها التي كانت منسوخةً هنا حرفياً.
        return silk_usage.vision_allowed()

    @app.post(_PREFIX + "/products/{product_id}/classify-image")
    def classify_product_image(product_id: int, request: Request,
                               body: dict = Body(default=None)):
        """المسارُ الثاني (قرار المالك): صورةٌ ⇒ بندٌ جمركيّ يُكتَب على المنتج.

        بلا خيارات وبلا ثقة: إمّا يُحسَم الرمزُ فيُكتَب ويُعتمَد كما لو كتبه
        المصنع، أو تُعاد رسالةٌ واحدة تطلب الرمز يدوياً (المسار الأوّل).
        الحسمُ نفسُه في `silk_hs_from_image` — نقطةُ اختناقٍ واحدة يشترك فيها
        السطحان، وهذه الدالّة تملك الصلاحية والصورةَ والقياس فقط.
        """
        ctx = _require(request, Role.FACTORY)
        body = _json_body(body)
        conn = _open()
        try:
            # R4.1 (تدقيق 2026-09-01، API-1): **نفس** عدّاد الرؤية الذي يحرسه
            # شقيقُه `/classify-image` منذ الدرس ١٨٩ — الميزانية المدفوعة
            # واحدة (`_vision_allowed_for_platform` ⇒ `silk_usage`)، فبابٌ
            # مخنوق وبابٌ مفتوح على الميزانية نفسها = لا خانق. الهويّة نفسها
            # حرفياً كي يكون السقف مشتركاً لا سقفَين متوازيَين.
            _vident = f"vision|{ctx.account_id}"
            _vlimits = throttle.named_limits("VISION", 20)
            if throttle.is_throttled(conn, _vident, _vlimits):
                raise HTTPException(status_code=429, detail={
                    "error": "vision_throttled",
                    "message": "قراءة الصور مقيّدة المعدل — انتظر دقائق ثم أعد"})
            throttle.record_failure(conn, _vident, _vlimits)  # عدّاد نداء، لا «فشل»
            _prepo = repository.products(conn)
            prod = _prepo.get(ctx.account_id, product_id)
            if prod is None:
                # AUTH-13 (تدقيق 2026-09-01، إغلاق R4): دلالةُ الرفض نفسُها التي
                # تمرّ بها مواضعُ الكتابة الثمانية — 404 بلا تسريبِ وجود، وقيدُ
                # عبورٍ حين يكون المعرّف لحسابٍ آخر. كان 404 خاماً بلا أثر.
                _deny_write_404(conn, request, ctx, _prepo, product_id,
                                "product", "cross_tenant_write")
            # الصورةُ من الجسم أو من صورة المنتج المرتبطة — وكلتاهما تمرّان
            # بفحص الملكية نفسه (لا قراءةَ ملفٍّ لحسابٍ آخر).
            iid = (body.get("image_id") if "image_id" in body
                   else prod.get("image_id"))
            if iid is None:
                raise HTTPException(status_code=422, detail={
                    "error": "image_required",
                    "message": "أرفق صورة المنتج أو أدخل رمز HS يدوياً"})
            iid = _as_int(iid, "image_id", minimum=1)   # مراجعة §58: قائمةٌ كانت TypeError
            img = repository.images(conn).get(ctx.account_id, iid)
            if img is None:
                # AUTH-13: صورةُ حسابٍ آخر = قراءةٌ عابرة تُقيَّد (كسطح `_tenant_detail`).
                _deny_write_404(conn, request, ctx, repository.images(conn), iid,
                                "image", "cross_tenant_read")
        finally:
            conn.close()

        try:
            with open(storage.path_for(img["storage_key"]), "rb") as fh:
                raw = fh.read(silk_product_intake.MAX_IMAGE_BYTES + 1)
        except OSError as exc:
            log.warning("classify-image read failed for %s: %s", product_id, exc)
            raise HTTPException(status_code=422, detail={
                "error": "image_unreadable",
                "message": silk_hs_from_image.MANUAL_FALLBACK_MSG})

        import base64
        import silk_context
        # **لا حجزَ على مسارٍ لن يُنادى** (ملاحظة مراجعةٍ ذاتية §58، ونفسُ
        # ترتيب `api.products_intake`): الصمّامُ المُطفأ أو صورةٌ باطلة كانا
        # يحرقان تفعيلةً من السقف اليوميّ بصفر نداءات — نقرةٌ تُنقِص رصيدَ
        # المصنع بلا مقابل. الحجزُ بعد ثبوت أن النداء سيقع فعلاً.
        _b64 = base64.b64encode(raw).decode("ascii")
        _mime = str(img.get("mime_type") or "image/jpeg")
        if not silk_product_intake.enabled():
            return {"ok": False,
                    "message": silk_hs_from_image.MANUAL_FALLBACK_MSG}
        if silk_product_intake._decode_and_check(_b64, _mime)[0] is None:
            return {"ok": False,
                    "message": silk_hs_from_image.MANUAL_FALLBACK_MSG}
        allow, reason = _vision_allowed_for_platform()
        if allow:
            silk_context.begin_data_counter()
        out = silk_hs_from_image.classify_from_image(
            _b64, _mime, allow_vision=allow, blocked_reason=reason)
        if allow:
            # الكلفةُ الفعلية تدخل الدفترَ اليوميّ المشترك — نفس نمط
            # `api.products_intake`؛ فشلُ القياس قناةٌ جانبية لا تُسقِط الردّ.
            try:
                import silk_usage
                from silk_pricing import estimate_cost_usd
                _c = silk_context.data_counter() or {}
                _cost = estimate_cost_usd(_c.get("llm_usage"))
                if _cost.get("total_usd"):
                    silk_usage.record_usd(_cost["total_usd"])
            except Exception as _e:  # noqa: BLE001
                log.warning("classify-image cost metering failed: %s", _e)

        if not out.get("ok"):
            log.info("classify-image undecided for product %s: %s",
                     product_id, out.get("reason"))
            return {"ok": False, "message": out["message"]}

        conn = _open()
        try:
            # الترحيل ٠١٧: الرمزُ يُكتَب **بمصدره**. بلا هذا كان وعدُ هذه
            # النقطة («يُعتمَد كما لو كتبه المصنع») بلا موضعٍ يُكتَب فيه، فيصل
            # المحرّكَ موسوماً «كتالوج» ويواجه البوّاباتِ كما لو لم يُحسَم.
            repository.products(conn).update(
                ctx.account_id, product_id,
                {"hs_code": out["hs6"], "hs_source": "image",
                 "hs_set_at": auth.now_iso()})
            audit.record(conn, action="product_hs_from_image",
                         user_id=ctx.user_id, account_id=ctx.account_id,
                         resource_type="product", resource_id=product_id,
                         changes={"hs_code": out["hs6"],
                                  "product_name": out.get("product_name")})
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "hs_code": out["hs6"],
                "product_name": out.get("product_name") or "",
                "message": "حُدّد البند الجمركي من الصورة."}

    @app.patch(_PREFIX + "/products/{product_id}")
    def patch_product(product_id: int, request: Request,
                      body: dict = Body(default=None)):
        ctx = _require(request, Role.FACTORY)
        body = _json_body(body)
        conn = _open()
        try:
            repo = repository.products(conn)
            # صفُّ المقارنة لتمييز الرمز المردَّد من المتغيّر — غيابه (عبر
            # المستأجرين أو معرّف باطل) يبقى 404 من مسار `update` نفسه أدناه.
            fields = _product_fields(
                conn, ctx, body, require_name=False,
                stored=repo.get(ctx.account_id, product_id) or {})
            if not fields:
                # §58: جسمٌ بلا حقلٍ قابلٍ للكتابة كان يمرّ 200 ويكتب قيد
                # «product_updated» كاذباً في سجلٍّ يُقدَّم موثوقاً.
                raise _err(422, "product_patch_empty",
                           "لا تعديلَ في الطلب: الاسم أو الوصف أو الرمز أو الصورة")
            updated = repo.update(ctx.account_id, product_id, fields)
            if updated is None:
                _deny_write_404(conn, request, ctx, repo, product_id, "product",
                                "cross_tenant_write")
            audit.record(conn, action="product_updated", user_id=ctx.user_id,
                         account_id=ctx.account_id, resource_type="product",
                         resource_id=product_id)
            conn.commit()
        finally:
            conn.close()
        return updated

    @app.delete(_PREFIX + "/products/{product_id}")
    def delete_product(product_id: int, request: Request):
        """حذف منتج — دراساته تبقى (يُفكّ الربط فقط؛ لا حذف بيانات دراسة أبداً)."""
        ctx = _require(request, Role.FACTORY)
        conn = _open()
        try:
            repo = repository.products(conn)
            if repo.get(ctx.account_id, product_id) is None:
                _deny_write_404(conn, request, ctx, repo, product_id, "product",
                                "cross_tenant_delete")
            conn.execute(
                "UPDATE studies SET product_id = NULL, updated_at = ? "
                "WHERE owner_id = ? AND product_id = ?",
                (auth.now_iso(), ctx.account_id, product_id))
            repo.delete(ctx.account_id, product_id)
            audit.record(conn, action="product_deleted", user_id=ctx.user_id,
                         account_id=ctx.account_id, resource_type="product",
                         resource_id=product_id)
            conn.commit()
        finally:
            conn.close()
        return {"ok": True}

    # ═══════════ نظرة عامة المصنع · factory overview (2026-08-18) ════════════
    @app.get(_PREFIX + "/overview")
    def factory_overview(request: Request):
        """داشبورد الأسواق المدروسة — «اضف داشبورد عام عن الدراسات الاسواق».

        كل الأرقام من صفوف الحساب نفسه: عدّ الدراسات بالحالة، ودرجات الأسواق
        من قاعدة المحرّك عبر مؤشر `analysis_id` (قراءة فقط، تمرّ من
        `strip_cost_keys` ضمناً — لا مفتاح تكلفة في الحمولة أصلاً). تعذُّر
        قاعدة المحرّك = فجوة معلنة (`markets: []` + سبب)، لا اختلاق.
        """
        ctx = _require(request, Role.FACTORY)
        conn = _open()
        try:
            by_state = {r["state"]: int(r["c"]) for r in conn.execute(
                "SELECT state, COUNT(*) AS c FROM studies "
                "WHERE owner_id = ? GROUP BY state", (ctx.account_id,)).fetchall()}
            # سقف 200 يطابق سقف قارئ الدرجات — وتجاوزه فجوة **معلنة** أدناه
            # لا اقتطاعاً صامتاً (§58: عدّاد «أسواق مدروسة» كان سيكذب).
            aid_rows = conn.execute(
                "SELECT id, product, market_pref, analysis_id, completed_at "
                "FROM studies WHERE owner_id = ? AND state = 'completed' "
                "AND analysis_id IS NOT NULL ORDER BY id DESC LIMIT 200",
                (ctx.account_id,)).fetchall()
            recent = [dict(r) for r in conn.execute(
                "SELECT id, product, market_pref, state, completed_at, "
                "run_error FROM studies WHERE owner_id = ? "
                "ORDER BY id DESC LIMIT 5", (ctx.account_id,)).fetchall()]
        finally:
            conn.close()
        markets: list[dict] = []
        markets_note = ""
        markets_studied = 0
        ids = [int(r["analysis_id"]) for r in aid_rows]
        if ids:
            try:
                from silk_storage import market_scores_for_analyses
                by_iso: dict[str, dict] = {}
                for s in market_scores_for_analyses(ids):
                    iso = s.get("iso3") or s.get("country") or "?"
                    cur = by_iso.get(iso)
                    if cur is None or (s.get("total_score") or 0) > (
                            cur.get("score") or 0):
                        by_iso[iso] = {"iso3": s.get("iso3"),
                                       "country": s.get("country"),
                                       "score": s.get("total_score"),
                                       "confidence": s.get("confidence")}
                # العدّاد قبل أي قصّ — المخطط وحده يقتصر على أفضل 12 معلَناً.
                markets_studied = len(by_iso)
                markets = sorted(by_iso.values(),
                                 key=lambda m: -(m.get("score") or 0))[:12]
                if markets_studied > len(markets):
                    markets_note = (f"يعرض المخطط أفضل {len(markets)} سوقاً "
                                    f"من أصل {markets_studied} مدروسة")
                if len(aid_rows) == 200:
                    markets_note = (markets_note + " — " if markets_note else "") + \
                        "التجميع يشمل آخر 200 دراسة مكتملة"
            except Exception as exc:  # noqa: BLE001 — فجوة معلنة لا انهيار
                log.warning("overview market scores unavailable: %s", exc)
                markets_note = "درجات الأسواق غير متاحة من قاعدة المحرّك حالياً"
        return {
            "studies": {
                "total": sum(by_state.values()),
                "completed": by_state.get("completed", 0),
                "in_progress": by_state.get("in_progress", 0),
                "draft": by_state.get("draft", 0),
                "archived": by_state.get("archived", 0),
            },
            "markets": markets,
            "markets_studied": markets_studied,
            "markets_note": markets_note,
            "best_market": (markets[0] if markets else None),
            "recent": recent,
        }

    # ══════════════════════════ STUDIES ═════════════════════════════════════
    @app.get(_PREFIX + "/studies")
    def list_studies(request: Request):
        ctx = _require(request, Role.SILK_ADMIN, Role.FACTORY)
        conn = _open()
        try:
            rows = repository.studies(conn).list(ctx.account_id)
            # ETA على القائمة مباشرةً (§58): كانت الواجهة تجلب تفاصيل كل دراسة
            # جارية على حدة كل ٥ ثوانٍ لرقمٍ لا يعتمد على الدراسة أصلاً —
            # حسابٌ واحد يُرفَق لكل الجاريات.
            if any(r.get("state") == "in_progress" for r in rows):
                eta, basis = engine_bridge.eta_seconds(conn)
                # R2: حالة التشغيلة النشطة (منتظرة/جارية/طُلب إلغاؤها) تُرفَق
                # للجاريات وحدها — مفاتيح الردّ القائمة كما هي.
                runs = study_runtime.run_view(
                    conn, [r["id"] for r in rows if r.get("state") == "in_progress"])
                for r in rows:
                    if r.get("state") == "in_progress":
                        r["eta_s"], r["eta_basis"] = eta, basis
                        _g = _sweep_grace_s(r.get("run_stats"))
                        if _g is not None:
                            r["grace_s"] = _g
                        if r["id"] in runs:
                            r["run"] = runs[r["id"]]
            # R3: المسودّة التي انتهت آخرُ محاولتها تحمل اسمَ نهايتها
            # (`interrupted`/`cancelled`/`failed`) — مفتاحٌ إضافيّ لا يستبدل
            # شيئاً؛ غيابُه (لم تُطلَق قطّ) يُبقي العرضَ القائم حرفياً.
            _mark_changed_product_codes(conn, rows, ctx.account_id)   # BIZ-10
            _drafts = [r["id"] for r in rows if r.get("state") == "draft"]
            if _drafts:
                last = study_runtime.last_run_view(conn, _drafts)
                for r in rows:
                    if r["id"] in last:
                        r["last_run"] = last[r["id"]]
        finally:
            conn.close()
        return {"studies": rows}

    def _validated_hs_code(body: dict) -> str | None:
        """رمز HS من جسم الطلب — 4–6 خانات **ASCII** أو None (§58: `isdigit()`
        وحدها تقبل «٠٨٠٤١٠» الهندية فيصل المحرّكَ رمزٌ لا يطابق شيئاً — نفس
        عائلة فخّ `isalpha()` في market_pref). مدقّق واحد للدراسات والمنتجات."""
        code = str(body.get("hs_code") or "").strip()
        if code and (not code.isascii() or not code.isdigit()
                     or not 4 <= len(code) <= 6):
            raise _err(422, "bad_hs_code", "رمز HS: من ٤ إلى ٦ أرقام")
        return code or None

    def _validated_owned_image_id(conn, ctx: AuthContext, body: dict):
        """صورة مملوكة لهذا الحساب أو None (مسح صريح) — مدقّق ملكية واحد."""
        if body.get("image_id") is None:
            return None
        iid = _as_int(body.get("image_id"), "image_id", minimum=1)
        if repository.images(conn).get(ctx.account_id, iid) is None:
            raise _err(422, "image_not_owned", "الصورة ليست لهذا الحساب")
        return iid

    def _study_research_fields(conn, ctx: AuthContext, body: dict) -> dict:
        """حقول طلب دراسة السوق المتحقَّق منها — التحوّل (قرار مالك 2026-08-17).

        - `product` نصّ مُشذَّب (إلزاميته عند **الإطلاق** لا الإنشاء — المسودّة
          الناقصة مشروعة، وصفوف عهد الحملات القديمة بلا منتج أصلاً).
        - `market_pref` رمز iso3 (٣ أحرف) أو فارغ؛ غير ذلك 422 — رمزٌ ملفّق
          كان سيُتجاهَل بصمت في جسر المحرّك فيظنّ المصنع سوقه مستهدفاً.
        - `hs_code` أرقام ٤–٦ خانات أو فارغ (نفس شكل رموز مرجع HS).
        - `image_id` صورة **مملوكة لهذا الحساب** أو 422 — لا ربط صور عابر
          للمستأجرين (نفس عقد `_validate_smtp_binding`).
        """
        out: dict = {}
        if "product" in body:
            out["product"] = str(body.get("product") or "").strip()[:200] or None
        if "market_pref" in body:
            pref = str(body.get("market_pref") or "").strip().upper()
            # ASCII صراحةً: `isalpha()` وحدها تقبل «دبي» (حروف عربية طولها ٣)
            # فيعبر نصٌّ ليس رمز iso3 ويُتجاهَل بصمت في جسر المحرّك لاحقاً.
            if pref and (len(pref) != 3 or not pref.isascii()
                         or not pref.isalpha()):
                raise _err(422, "bad_market_code", "رمزُ السوق ثلاثةُ أحرف (ISO3)")
            # سوقٌ مجهول في مراجعنا يُرفَض عند الإدخال (§58) — قبوله كان يعني
            # تقرير «كل الأسواق» موسوماً زوراً بسوق المصنع المختار.
            if pref and not engine_bridge.market_known(pref):
                # P3 (§58 على BIZ-14): البوّابةُ تفشل مغلقةً، والسببُ يُقال كما هو —
                # مرجعٌ متعذّر عطلٌ عندنا (503، أعِد المحاولة) لا رمزٌ خاطئ عند المصنع.
                if not engine_bridge.market_reference_available():
                    raise _err(503, "market_reference_unavailable",
                               "تعذّر التحقّق من السوق الآن — مرجعُ الأسواق لا يستجيب. "
                               "أعِد المحاولة، أو اترك السوق فارغاً لتغطية كلّ الأسواق.")
                raise HTTPException(status_code=422, detail={
                    "error": "unknown_market",
                    "message": f"السوق {pref} غير معروف في مرجع الأسواق"})
            out["market_pref"] = pref or None
        if "hs_code" in body:
            out["hs_code"] = _validated_hs_code(body)
        if "image_id" in body:
            # مسحٌ صريح («— بلا صورة —») — تجاهله كان يجعل فكّ الربط
            # مستحيلاً بلا أي خطأ (§58). create يسقط None فلا أثر هناك.
            out["image_id"] = _validated_owned_image_id(conn, ctx, body)
        if "product_id" in body:
            # ربط الدراسة بمنتج الكتالوج (ترحيل 010) — نفس عقد ملكية الصورة:
            # منتجٌ لحسابٍ آخر = 422، لا ربط عابر للمستأجرين.
            if body.get("product_id") is None:
                out["product_id"] = None
            else:
                pid = _as_int(body.get("product_id"), "product_id", minimum=1)
                if repository.products(conn).get(ctx.account_id, pid) is None:
                    raise _err(422, "product_not_owned", "المنتج ليس لهذا الحساب")
                out["product_id"] = pid
        if "production_cost" in body:
            # هدف الدراسة الاحترافية (البند ٢): تكلفة إنتاج وحدة السوق على
            # نموذج الدراسة نفسه — نفس عقد E-04: الفراغ يبقى فراغاً (NULL
            # صراحةً)، لا قيمة افتراضية ولا تقدير؛ رقم فاسد/سالب = 422.
            raw = body.get("production_cost")
            if raw in (None, ""):
                out["production_cost"] = None
            else:
                try:
                    val = float(raw)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=422, detail={
                        "error": "study_bad_production_cost",
                        "message": "«تكلفة الإنتاج» يجب أن تكون رقماً"})
                if val <= 0:
                    raise HTTPException(status_code=422, detail={
                        "error": "study_bad_production_cost",
                        "message": "«تكلفة الإنتاج» رقم موجب — الصفر "
                                   "والسالب ليسا تكلفة"})
                out["production_cost"] = val
        return out

    def _study_provenance_fields(body: dict, fields: dict, prior: dict | None = None) -> dict:
        """إقرار صريح لرمز محدد، لا استنتاج ثقة من إعادة حفظ نموذج قديم.

        A client may declare its own manual input, never server-side image proof.
        Product/code changes invalidate an earlier declaration unless renewed.
        """
        if "hs_source" in body:
            source = body["hs_source"]
            if source not in ("manual", "unknown"):
                raise _err(422, "bad_hs_source", "مصدر الرمز غير مقبول / Invalid HS source")
            if source == "manual" and not fields.get("hs_code"):
                raise _err(422, "hs_source_without_code",
                           "أدخل رمز المصنع مع الإقرار / Supply the factory HS code")
            return {"hs_source": source}
        if prior is None or any(
                key in fields and fields[key] != prior.get(key)
                for key in ("product", "hs_code", "product_id")):
            return {"hs_source": "unknown"}
        return {}

    @app.post(_PREFIX + "/studies")
    def create_study(request: Request, body: dict = Body(default=None)):
        ctx = _require(request, Role.SILK_ADMIN, Role.FACTORY)
        body = _json_body(body)
        conn = _open()
        try:
            # R6 (تدقيق 2026-09-01، FE-8 — قرار المالك 2026-09-05): حقولُ التنقيب الميتة
            # (`title_en`، `description_en`، `target_count`) لا تُقبَل بعد اليوم — الأعمدةُ
            # باقية (لا حذف) لكنّ الطلبَ لا يكتبها؛ الدراسةُ طلبُ دراسة سوقٍ لا حملة.
            fields = {k: _str_or_none(body.get(k)) for k in ("title_ar", "description_ar")}
            fields.update(_study_research_fields(conn, ctx, body))
            fields.update(_study_provenance_fields(body, fields))
            # عنوان تلقائي من المنتج — المصنع يكتب منتجه ولا يُلزَم بعنوان ثانٍ.
            if not (fields.get("title_ar") or "").strip():
                fields["title_ar"] = fields.get("product") or None
            fields["created_by_user_id"] = ctx.user_id
            row = repository.studies(conn).create(ctx.account_id, fields)
            audit.record(conn, action="study_created", user_id=ctx.user_id,
                         account_id=ctx.account_id, resource_type="study",
                         resource_id=row["id"], ip_address=_client_ip(request))
            conn.commit()
        finally:
            conn.close()
        return row

    @app.get(_PREFIX + "/studies/{study_id}")
    def get_study(study_id: int, request: Request):
        row = _tenant_detail(request, repository.studies, study_id, "study")
        conn = _open()
        try:   # BIZ-10: رمزُ الكتالوج تغيّر بعد أن حملت الدراسةُ رمزَها — يُعلَن
            row = {**row, "product_code_changed": _product_code_changed(conn, row)}
        finally:
            conn.close()
        # عدّاد الوقت (قرار المالك): المدة المتوقعة تُرفَق للدراسة الجارية فقط —
        # الواجهة تحسب «كم مضى» من `run_started_at` وتعرض المتبقي مع أساسه
        # (مقيس/تقديري). لا حساب خارج الحالة الجارية.
        if row.get("state") == "in_progress":
            conn = _open()
            try:
                eta, basis = engine_bridge.eta_seconds(conn)
                run = study_runtime.run_view(conn, [row["id"]]).get(row["id"])
            finally:
                conn.close()
            row = {**row, "eta_s": eta, "eta_basis": basis}
            _g = _sweep_grace_s(row.get("run_stats"))
            if _g is not None:
                row["grace_s"] = _g
            if run is not None:          # R2: حالة التشغيلة النشطة — إضافيّة
                row["run"] = run
        elif row.get("state") == "draft":
            # R3: تفصيلُ الدراسة يحمل حصيلةَ آخر محاولة كالقائمة تماماً — نافذةُ
            # التحرير كانت ترى «مسودّة» بلا اسمِ ما جرى.
            conn = _open()
            try:
                last = study_runtime.last_run_view(conn, [row["id"]]).get(row["id"])
            finally:
                conn.close()
            if last is not None:
                row = {**row, "last_run": last}
        return row

    @app.patch(_PREFIX + "/studies/{study_id}")
    def patch_study(study_id: int, request: Request, body: dict = Body(default=None)):
        ctx = _require(request, Role.SILK_ADMIN, Role.FACTORY)
        body = _json_body(body)
        # مراجعة §58 على R4 (٤ عالية): إقرارٌ مع تغيير المنتج/الرمز/السوق في
        # الطلب نفسه كان يُختَم للزوج الجديد الذي لم يُعرَض تنبيهُه قطّ — يُرفَض
        # كاملاً **قبل** أيّ كتابة (لا نصفَ طلب).
        if body.get("advisories_ack") is True and any(
                k in body for k in _ADVISORY_PAIR_KEYS):
            raise HTTPException(status_code=422, detail={
                "error": "advisory_ack_with_change",
                "message": "لا يُقبل الإقرار بالتنبيه مع تغيير المنتج أو الرمز "
                           "أو السوق في الطلب نفسه — احفظ التعديل أولاً"})
        conn = _open()
        try:
            fields = {k: _str_or_none(body[k]) for k in body if k in
                      ("title_ar", "description_ar")}     # R6 (FE-8): الحقولُ الميتة تُتجاهَل
            fields.update(_study_research_fields(conn, ctx, body))
            repo = repository.studies(conn)
            # الصفُّ المخزون **قبل** الكتابة — مرجعُ سؤال «هل تغيّر شيءٌ
            # فعلاً؟» (مراجعة PR #254): الصفُّ المحدَّث يحمل القيمَ الجديدة
            # دائماً فلا يصلح مرجعاً، ونموذجُ التحرير يردّد الرمزَ والمنتجَ
            # المعبَّأين مسبقاً في كل حفظ (`_studyBody`).
            prior = repo.get(ctx.account_id, study_id)
            fields.update(_study_provenance_fields(body, fields, prior))
            updated = repo.update(ctx.account_id, study_id, fields)
            if updated is None:
                _deny_write_404(conn, request, ctx, repo, study_id, "study",
                                "cross_tenant_write")
            if "hs_code" in body or "product" in body:
                # اختيارُ المصنع من قائمة المرشّحين المعروضة = تأكيدٌ بشريّ
                # صريح يعبر بوّابةَ تأكيد البند؛ إقرارُ الإدخال اليدوي الحديث
                # محفوظ مستقلاً في hs_source ولا يُستنتج من قائمة قديمة.
                # وتغييرُ **المنتج** يُسقِط التأكيد: البند أُقرّ لمنتجٍ آخر،
                # وإبقاؤه يُمرِّر تشغيلةً على رمزٍ لم يعد يطابق (مراجعة §58).
                # تدقيق 2026-08-30: إعادةُ حفظِ الدراسة بلا تغييرٍ كانت
                # تُرسِل الرمزَ المخزَّن نفسَه فيُطابق مرشّحاً معروضاً ويُرفَع
                # «تأكيداً» — تأكيدٌ مجّانيٌّ لا نقرةَ اختيارٍ خلفه، وهو ما
                # يقول هذا التعليقُ نفسُه إنه ممنوع. التأكيدُ يشترط أن يكون
                # الرمزُ المُرسَل **مذكوراً صراحةً** في الطلب.
                # مراجعة PR #254: الذكرُ الصريح وحده لا يكفي — النموذجُ يذكر
                # الرمزَ المخزونَ في كل حفظ. الفعلُ الحقيقيّ هو **التغيّر**:
                # لا تأكيدَ إلا لرمزٍ تغيّر إلى مرشّحٍ معروض، ولا كتابةَ
                # أصلاً حين لا يتغيّر رمزٌ ولا منتج.
                chosen = ("" if "hs_code" not in body
                          else str(body.get("hs_code") or "").strip())
                code_changed = ("hs_code" in body and chosen !=
                                str((prior or {}).get("hs_code") or "").strip())
                product_changed = (
                    "product" in body and
                    str(updated.get("product") or "").strip() !=
                    str((prior or {}).get("product") or "").strip())
                if code_changed or product_changed:
                    try:
                        cands = json.loads(updated.get("hs_candidates") or "[]")
                    except (TypeError, ValueError):
                        cands = []
                    confirmed = 1 if (code_changed and chosen and any(
                        isinstance(c, dict)
                        and str(c.get("hs6") or "").strip() == chosen
                        for c in cands)) else 0
                    # الترحيل ٠١٧: **كيف** حُسِم البند يُسجَّل لا يُستنتَج —
                    # اختيارٌ من قائمةٍ معروضة (`user_confirmed`) ليس ككتابةٍ
                    # يدويةٍ عمياء تبقى محكومةً بالبوّابة. وحفظٌ لا يغيّر
                    # رمزاً ولا منتجاً لا يمرّ من هنا أصلاً: كان يكتب NULL
                    # فوق مصدرٍ مسجَّل (`deterministic_exact`/`llm_grounded`)
                    # فيمحو الإفصاحَ الذي وُجد العمودُ ليحفظه.
                    method = "user_confirmed" if confirmed else None
                    conn.execute("UPDATE studies SET hs_confirmed = ?, "
                                 "hs_classification_method = ? "
                                 "WHERE id = ? AND owner_id = ?",
                                 (confirmed, method, study_id, ctx.account_id))
                    updated["hs_confirmed"] = confirmed
                    updated["hs_classification_method"] = method
            # R4.8 (تدقيق 2026-09-01، API-13؛ الترحيل ٠١٩): الإقرارُ بتنبيه ما
            # قبل التشغيل فعلُ المصنع لزوجِ (رمز، سوق) بعينه — تغييرُ أيٍّ منهما
            # يُسقِطه (إبقاؤه يوافق نيابةً عنه على تنبيهٍ لم يره)، والإقرارُ
            # الصريح يُختَم بوقته ويُقيَّد تدقيقاً. في الجسم نفسه: يُسقَط ثم
            # يُختَم للزوج الجديد.
            # مراجعة §58 (٦ متوسّطة): بلا رمزٍ صريح يحسم المحرّكُ البندَ من اسم
            # المنتج — فتغييرُ المنتج يغيّر التنبيهَ الساري ويُسقِط الإقرار أيضاً.
            _consent_keys = ("hs_code", "market_pref") + (
                ("product", "product_id")
                if not str(updated.get("hs_code") or "").strip() else ())
            if prior is not None and updated.get("advisories_ack_at") and any(
                    str(updated.get(k) or "").strip()
                    != str(prior.get(k) or "").strip()
                    for k in _consent_keys):
                _withdraw_advisory_ack(conn, ctx, study_id, updated, "pair_changed")
            _want_ack = body.get("advisories_ack")
            if _want_ack is True and not updated.get("advisories_ack_at"):
                # (٤ عالية) لا ختمَ بلا تنبيهٍ معلّق: إمّا تراه بوّابةُ ما قبل
                # المطالبة الآن، أو رفضته آخرُ تشغيلةٍ باسمه. وختمٌ قائم = لا
                # عملَ ولا قيدَ ثانٍ (٨ متوسّطة: نقرةٌ مكرّرة لا تُقيَّد مرّتين).
                if not _advisory_ack_applicable(conn, updated):
                    raise HTTPException(status_code=422, detail={
                        "error": "advisory_ack_not_applicable",
                        "message": "لا تنبيهَ معلّقاً على هذه الدراسة يحتاج إقراراً"})
                _ack_at = auth.now_iso()
                conn.execute("UPDATE studies SET advisories_ack_at = ? "
                             "WHERE id = ? AND owner_id = ?",
                             (_ack_at, study_id, ctx.account_id))
                updated["advisories_ack_at"] = _ack_at
                audit.record(conn, action="study_advisories_acked",
                             user_id=ctx.user_id, account_id=ctx.account_id,
                             resource_type="study", resource_id=study_id,
                             changes={"hs_code": updated.get("hs_code"),
                                      "market_pref": updated.get("market_pref"),
                                      "product": updated.get("product")})
            elif _want_ack is False and updated.get("advisories_ack_at"):
                _withdraw_advisory_ack(conn, ctx, study_id, updated, "explicit")
            audit.record(conn, action="study_updated", user_id=ctx.user_id,
                         account_id=ctx.account_id, resource_type="study",
                         resource_id=study_id)
            conn.commit()
        finally:
            conn.close()
        return updated

    @app.delete(_PREFIX + "/studies/{study_id}")
    def delete_study(study_id: int, request: Request):
        ctx = _require(request, Role.SILK_ADMIN, Role.FACTORY)
        conn = _open()
        try:
            repo = repository.studies(conn)
            # R2: سجلّ التشغيلات يشير إلى الدراسة (مفتاح أجنبي): تشغيلةٌ نشطة =
            # 409 معلَن (ألغِ أولاً)؛ والصفوف المنتهية تُحذف معها في المعاملة نفسها.
            # §58 #3: الفحصُ والحذفُ تحت `BEGIN IMMEDIATE` — إطلاقٌ متزامن يُدرج
            # صفّاً منتظراً بينهما كان يُسقِط الحذف بالمفتاح الأجنبي 500 لا 409.
            _busy = {"error": "study_running",
                     "message": "الدراسة قيد التنفيذ — ألغِ تشغيلتها أولاً ثم احذفها"}
            conn.commit()
            conn.execute("BEGIN IMMEDIATE")
            try:
                _row = repo.get(ctx.account_id, study_id)
                if _row is not None:
                    if study_runtime.has_active_run(conn, study_id):
                        raise HTTPException(status_code=409, detail=_busy)
                    # R3 (تدقيق 2026-09-01، ENG-7): صفٌّ «قيد الإعداد» **بلا**
                    # سجلّ تشغيلة نشط (قاعدةٌ قبل الترحيل 018، أو خيطٌ مات قبل
                    # أن يُدرِج صفَّه، أو سياجٌ أخطأ فأُغلق الصفّ وبقيت الدراسة)
                    # كان يُحذف بلا اعتراض — فيكتب خيطٌ حيّ في عمليةٍ أخرى
                    # نهايتَه على دراسةٍ لم تعد موجودة، وتضيع الحصّة المحجوزة.
                    if _row.get("state") == "in_progress":
                        # الفحصُ من القاعدة مباشرةً داخل المعاملة نفسها: صفٌّ
                        # نشطٌ أُدرِج بعد الفحص أعلاه (سباق الإطلاق المتزامن)
                        # رسالتُه رسالةُ «ألغِ تشغيلتها»؛ وغيابُه كلّياً حالةٌ
                        # أخرى مخرجُها الانتظار حتى يحسمها الكنس الدوري.
                        _active = conn.execute(
                            "SELECT 1 FROM study_runs WHERE study_id = ? AND "
                            "state IN ('queued','running') AND study_id IN "
                            "(SELECT id FROM studies WHERE owner_id = ?) LIMIT 1",
                            (study_id, ctx.account_id)).fetchone()
                        if _active is not None:
                            raise HTTPException(status_code=409, detail=_busy)
                        raise HTTPException(status_code=409, detail={
                            "error": "study_in_progress",
                            "message": "الدراسة قيد الإعداد — انتظر انتهاءها "
                                       "أو ألغِ تشغيلتها ثم احذفها"})
                    conn.execute("DELETE FROM study_runs WHERE study_id = ? "
                                 "AND state NOT IN ('queued','running')",
                                 (study_id,))
                    # R5 (تدقيق 2026-09-01، DB-3): صفوفُ عهد الحملات (مفاتيح أجنبية
                    # إلى `studies` بلا مسار كتابة اليوم) كانت تُسقِط الحذف 500 ثم
                    # 409 مضلِّلاً؛ تُفكّ داخل المعاملة نفسها بنطاق المالك، ويُنظَّف
                    # مؤشّرُ الإشعارات (بلا FK) كي لا يشير إلى فراغ. سجلُّ الموافقات
                    # (`consent_registry`) ملحقٌ قانونيّ لا يُمَسّ.
                    conn.execute("UPDATE comparison_funnels SET selected_study_id = NULL "
                                 "WHERE owner_id = ? AND selected_study_id = ?",
                                 (ctx.account_id, study_id))
                    conn.execute("DELETE FROM funnel_studies WHERE study_id = ? AND "
                                 "funnel_id IN (SELECT id FROM comparison_funnels "
                                 "WHERE owner_id = ?)", (study_id, ctx.account_id))
                    conn.execute("UPDATE drafts SET study_id = NULL "
                                 "WHERE owner_id = ? AND study_id = ?",
                                 (ctx.account_id, study_id))
                    conn.execute("UPDATE email_queue SET study_id = NULL "
                                 "WHERE account_id = ? AND study_id = ?",
                                 (ctx.account_id, study_id))
                    conn.execute("UPDATE platform_notifications SET study_id = NULL "
                                 "WHERE study_id = ? AND (account_id = ? OR account_id "
                                 "IN (SELECT id FROM accounts WHERE is_vault = 1))",
                                 (study_id, ctx.account_id))
                ok = repo.delete(ctx.account_id, study_id)   # يلتزم داخلياً
            except sqlite3.IntegrityError:
                conn.rollback()
                raise HTTPException(status_code=409, detail={
                    "error": "study_referenced",
                    "message": "الدراسة مرتبطة بسجلّاتٍ أخرى لا يمكن فكّها آلياً — "
                               "راجع الدعم"})
            except Exception:
                conn.rollback()
                raise
            if not ok:
                _deny_write_404(conn, request, ctx, repo, study_id, "study",
                                "cross_tenant_delete")
            audit.record(conn, action="study_deleted", user_id=ctx.user_id,
                         account_id=ctx.account_id, resource_type="study",
                         resource_id=study_id)
            conn.commit()
        finally:
            conn.close()
        return {"ok": True}

    def _study_hs_source(conn, ctx: AuthContext, study: dict) -> str:
        """إقرار الدراسة اليدوي أولاً، ثم مصدر منتجها، وإلا «catalog».

        R4.7 (تدقيق 2026-09-01، API-11؛ الترحيل ٠١٧): الرمزُ يرث مصدرَ المنتج
        (`manual` كتبه المصنعُ بيده | `image` حسمته الرؤيةُ من العبوة) **فقط**
        حين يطابق رمزَ المنتج حرفياً؛ `unknown` وصفوفُ ما قبل الترحيل ورمزٌ
        مخالف = «catalog» فتواجه البوّاباتِ كاملةً كما اليوم (لا ترقيةَ صامتة
        لثقةِ رمزٍ لم يُقرّ). كان الجسر يلصق «catalog» على الجميع فلا يصل
        الإفصاحُ الذي وُجد العمودُ لحفظه.
        """
        code = str(study.get("hs_code") or "").strip()
        # إقرار المصنع المحفوظ على الدراسة يسبق مصدر الكتالوج (الترحيل 021).
        # Explicit persisted manual input is independent of a catalog product.
        if code and study.get("hs_source") == "manual":
            return "manual"
        pid = study.get("product_id")
        if not code or not pid:
            return "catalog"
        row = conn.execute(
            "SELECT hs_code, hs_source FROM products "
            "WHERE id = ? AND account_id = ?",
            (int(pid), ctx.account_id)).fetchone()
        if row is None or str(row["hs_code"] or "").strip() != code:
            return "catalog"
        src = str(row["hs_source"] or "").strip()
        return src if src in engine_bridge._SETTLED_HS_SOURCES else "catalog"

    def _pending_advisories(study: dict) -> list[dict]:
        """تنبيهاتُ ما قبل التشغيل التي لم يُقرّ بها المصنع بعد — أو [].

        R4.8 (تدقيق 2026-09-01، API-13): المصدرُ الواحد
        `silk_prerun.sibling_advisories` (صفر نداء مدفوع، config-driven، مُطفأ
        افتراضاً بـ`SILK_PRERUN_ADVISORIES`). إقرارٌ مختوم (`advisories_ack_at`،
        الترحيل ٠١٩) = لا تنبيه. مراجعة §58 (٧ متوسّطة): بوّابةُ المنصّة لا تكون
        أشدَّ من المحرّك — المسار السريع لا يقيّم التنبيهات، والاستئنافُ يتخطّاها
        في الجسم، فلا رفضَ هنا لما لن يُرفَض هناك.
        """
        if study.get("advisories_ack_at"):
            return []
        if engine_bridge.study_mode() != "deep" or study.get("analysis_id"):
            return []
        import silk_prerun
        if not silk_prerun.advisories_enabled():
            return []
        iso3 = str(study.get("market_pref") or "").strip().upper()
        if len(iso3) != 3:
            return []
        return [dict(a) for a in silk_prerun.sibling_advisories(
            str(study.get("hs_code") or "").strip() or None, iso3)]

    def _advisory_ack_applicable(conn, study: dict) -> bool:
        """هل ثمّة ما يُقَرّ به؟ تنبيهٌ تراه بوّابةُ ما قبل المطالبة الآن، أو رفضٌ
        باسم `prerun_advisory` من المحرّك في آخر تشغيلةٍ منتهية (دراسةٌ بلا رمز
        يحسمه المحرّك من اسم المنتج فيجد شقيقاً لم تره البوّابة)."""
        if _pending_advisories(study):
            return True
        row = conn.execute(
            "SELECT error_code FROM study_runs WHERE study_id = ? "
            "AND state NOT IN ('queued','running') AND study_id IN "
            "(SELECT id FROM studies WHERE owner_id = ?) "
            "ORDER BY id DESC LIMIT 1",
            (int(study["id"]), int(study["owner_id"]))).fetchone()
        return bool(row and row["error_code"] == "prerun_advisory")

    def _withdraw_advisory_ack(conn, ctx: AuthContext, study_id: int,
                               updated: dict, reason: str) -> None:
        conn.execute("UPDATE studies SET advisories_ack_at = NULL "
                     "WHERE id = ? AND owner_id = ?", (study_id, ctx.account_id))
        updated["advisories_ack_at"] = None
        audit.record(conn, action="study_advisories_ack_withdrawn",
                     user_id=ctx.user_id, account_id=ctx.account_id,
                     resource_type="study", resource_id=study_id,
                     changes={"reason": reason})

    def _refuse_launch(conn, ctx: AuthContext, study_id: int, note: str,
                       exc: HTTPException):
        """اكتب سبب رفض الإطلاق على الصفّ ثم ارفع الاستثناء — لا رفض صامت.

        بلاغ المالك 2026-08-19 («المحرّك لا يعمل») ولوحته: رفضُ بوّابةٍ يقع
        **قبل** مطالبة الدراسة، فلا يترك أثراً في أي جدول — المصنع يضغط
        «إطلاق» فتومض رسالةٌ وتختفي، ولوحة الأدمِن تُظهر صفّاً بعمود ملاحظات
        فارغ فيبدو كأن شيئاً لم يحدث. هنا يُكتب السبب في `run_error` (الصفّ
        يبقى مسودّة، ولا حصّة تُحرَق) ويُقيَّد تدقيقاً، فيراه الطرفان.
        Every refusal leaves a readable trace on the row.
        """
        conn.execute("UPDATE studies SET run_error = ?, updated_at = ? "
                     "WHERE id = ? AND owner_id = ?",
                     (str(note)[:400], auth.now_iso(), study_id, ctx.account_id))
        audit.record(conn, action="study_launch_refused", user_id=ctx.user_id,
                     account_id=ctx.account_id, resource_type="study",
                     resource_id=study_id, changes={"reason": str(note)[:200]})
        conn.commit()
        raise exc

    @app.post(_PREFIX + "/studies/{study_id}/launch")
    def launch_study(study_id: int, request: Request, body: dict = Body(default=None)):
        """أطلق دراسة سوق — claim → quota → تشغيل المحرّك آلياً (قرار المالك).

        التحوّل (2026-08-17): الإطلاق يشغّل `silk_engine.analyze` في خيط جسر
        المحرّك — لا بريد ولا SMTP ولا فحص رصيد («الباقة فقط» بقرار المالك:
        الحصّة الشهرية + حدّ المستخدم هما البوابة الوحيدة).

        **ترتيب مقصود**: الانتقال draft→in_progress يُطالَب به ذرّياً (`AND
        state='draft'` + فحص rowcount) **قبل** حجز الحصّة، فنقرتان متزامنتان
        لا تُنتجان إلا رابحاً واحداً. وإن رُفضت الحصّة يُعاد الانتقال إلى draft
        (تعويض) فلا تُحرَق حصّة بدراسة لم تنطلق. Claim-then-reserve.

        خيط التشغيل يُطلَق **بعد** التزام المطالبة والحصّة وإغلاق الاتصال —
        فشل التشغيل لاحقاً يعيدها مسودّةً بسبب معلن ويُرجِع الحصّة (جسر المحرّك).
        """
        ctx = _require(request, Role.SILK_ADMIN, Role.FACTORY)
        conn = _open()
        try:
            repo = repository.studies(conn)
            study = repo.get(ctx.account_id, study_id)
            if study is None:
                _deny_write_404(conn, request, ctx, repo, study_id, "study",
                                "cross_tenant_launch")
            if study["state"] != "draft":
                raise _err(409, "study_not_draft", "الدراسة ليست مسودّة",
                           state=study["state"])
            # (١) منتجٌ حاضر — دراسة سوق بلا منتج لا معنى لتشغيلها (صفوف عهد
            # الحملات القديمة بلا منتج: 422 موجِّه، لا 500 لاحقاً في المحرّك).
            product = (study.get("product") or "").strip()
            if not product:
                _refuse_launch(
                    conn, ctx, study_id,
                    "الدراسة بلا منتج — عدِّلها وأضف اسم المنتج قبل الإطلاق",
                    HTTPException(status_code=422, detail={
                        "error": "study_no_product",
                        "message": "الدراسة بلا منتج — عدِّلها وأضف اسم المنتج "
                                   "قبل الإطلاق"}))
            # (١ب) بوابتا الوضع العميق (قرار المالك 2026-08-18 — دراسة المنصّة
            # تشغّل محرّك البحث العميق نفسه): تُفحصان **قبل** المطالبة والحصّة
            # فالرفض هنا لا يكلف المصنع شيئاً. لا تدهور صامت إلى الوضع السريع.
            if (engine_bridge.study_mode() == "deep"
                    and not engine_bridge.fake_engine_enabled()):
                if not (study.get("market_pref") or "").strip():
                    _refuse_launch(
                        conn, ctx, study_id,
                        "الدراسة العميقة تتطلب سوقاً مستهدفة — عدِّل الدراسة "
                        "واختر السوق قبل الإطلاق",
                        HTTPException(status_code=422, detail={
                            "error": "study_no_market_deep",
                            "message": "الدراسة العميقة تتطلب سوقاً مستهدفة — "
                                       "عدِّل الدراسة واختر السوق قبل الإطلاق"}))
                import silk_research_gateway
                ready, reason = silk_research_gateway.readiness()
                if not ready:
                    audit.record(conn, action="engine_not_ready",
                                 user_id=ctx.user_id, account_id=ctx.account_id,
                                 resource_type="study", resource_id=study_id,
                                 changes={"reason": reason[:200]})
                    _refuse_launch(
                        conn, ctx, study_id,
                        f"محرّك البحث العميق غير جاهز على الخادم: {reason}",
                        HTTPException(status_code=503, detail={
                            "error": "engine_not_ready", "reason": reason}))
            # (١ج) R4.8 (تدقيق 2026-09-01، API-13): تنبيهُ ما قبل التشغيل
            # بموافقةٍ حقيقية. جسمُ `/research` يرفض 422 `prerun_advisory` كلَّ
            # تشغيلةٍ لها شقيقُ تحذير حتى تصل `advisories_ack` — والجسر لم يكن
            # يمرّرها أبداً، فكانت الدراسة تُطالَب وتُحجَز حصّتُها ثم تعود
            # مسودّةً بسببٍ لا سبيلَ لحلّه. هنا يُرفَض **قبل** المطالبة والحصّة
            # بالتنبيه نفسه، والإقرارُ فعلُ المصنع (`PATCH advisories_ack`) لا
            # افتراضُ النظام (البديلُ الآليّ مرفوض: يوافق نيابةً عنه).
            _adv = _pending_advisories(study)
            if _adv:
                _adv_msg = (str(_adv[0].get("message") or "").strip()
                            or "تنبيهٌ قبل التشغيل يحتاج إقرارَك")
                _refuse_launch(
                    conn, ctx, study_id,
                    "تنبيهٌ قبل التشغيل يحتاج إقرارَك — " + _adv_msg,
                    HTTPException(status_code=422, detail={
                        "error": "prerun_advisory", "message": _adv_msg,
                        "advisories": _adv, "needs_ack": True}))
            # (٢) طالِب بالانتقال ذرّياً · atomically claim draft→in_progress.
            # الختم `launched_by_user_id` هو **حجز** حصّة المستخدم (العدّ يقرأه
            # ويشمل هذه الدراسة — الكتابة تسبق الفحص، اتجاه الدرس ٧٦). أختام
            # التشغيل تُصفَّر هنا: محاولة جديدة تبدأ سجلاً نظيفاً.
            now = auth.now_iso()
            # رمزُ هذه المحاولة — يملك كتاباتِ إنهائها وحده (مراجعة §58:
            # خيطُ تشغيلةٍ مكنوسة كان يكتب نتيجتَه على إطلاقةٍ جديدة).
            run_token = uuid.uuid4().hex
            # لقطة لغة التقرير (الموجة ٠) — تُكتب **داخل جملة المطالبة الذرّية
            # نفسها** لا قبلها ولا بعدها: تبديلُ المصنع لغتَه أثناء تشغيلةٍ حيّة
            # لا يجوز أن يُنتِج تقريراً نصفُه بلغةٍ ونصفُه بأخرى. ومن اللحظة
            # التي تُكتب فيها، لغة هذا التقرير محسومةٌ إلى الأبد — التقارير
            # المولَّدة لا تتغيّر لغتها بأثرٍ رجعيّ.
            snap_lang = fsettings.factory_language(conn, ctx.account_id)
            # ختم الوضع يُكتب مع المطالبة (§58 موجة A): كنس اليتيمات يقرأ
            # نافذته من وضع الصف لا من بيئة لحظة الكنس (سريع ٩٠٠ث/عميق ٣٦٠٠ث).
            claim = conn.execute(
                "UPDATE studies SET state = 'in_progress', launched_at = ?, "
                "launched_by_user_id = ?, run_started_at = ?, "
                "run_finished_at = NULL, run_error = NULL, run_stats = ?, "
                # مرشّحو البند الجمركي أثرُ محاولةٍ سابقة — محاولةٌ جديدة تبدأ
                # سجلاً نظيفاً (وإلا بقي حوار الاختيار معروضاً بعد حلّه).
                "hs_candidates = NULL, run_token = ?, "
                "report_language = ?, factory_language_at_generation = ?, "
                "updated_at = ? "
                "WHERE id = ? AND owner_id = ? AND state = 'draft'",
                (now, ctx.user_id, now, engine_bridge.launch_stamp_json(),
                 run_token, snap_lang, snap_lang, now, study_id, ctx.account_id))
            conn.commit()
            if claim.rowcount == 0:   # سبقنا طلبٌ متزامن · a concurrent launch won
                raise _err(409, "study_already_launching", "الدراسة تُطلَق الآن من طلبٍ آخر")
            # (٣) الحصّة: احجز (يزيد العدّاد) · quota reserve (increments counter).
            decision = quota.reserve_launch(conn, ctx.account_id,
                                            actor_user_id=ctx.user_id)
            if not decision.allowed:
                # تعويض: أعِد الدراسة مسودّةً فلا تُحرَق حصّة بلا إطلاق — ويُمسَح
                # ختم المُطلِق كي لا تُحتسَب في حصّة المستخدم دراسةٌ لم تنطلق.
                conn.execute("UPDATE studies SET state = 'draft', launched_at = NULL, "
                             "launched_by_user_id = NULL, run_started_at = NULL, "
                             "run_error = ?, "
                             "updated_at = ? WHERE id = ? AND owner_id = ?",
                             (f"لم تنطلق: {decision.reason} — الحصّة المستهلكة "
                              f"{decision.used} من {decision.limit}",
                              auth.now_iso(), study_id, ctx.account_id))
                audit.record(conn, action="study_launch_refused",
                             user_id=ctx.user_id, account_id=ctx.account_id,
                             resource_type="study", resource_id=study_id,
                             changes={"reason": decision.reason})
                conn.commit()
                detail = {"error": "quota_exceeded",
                          "reason": decision.reason,
                          "tier": decision.tier,
                          "limit": decision.limit,
                          "used": decision.used,
                          "upgrade": True}
                if decision.reason == "user_quota_exceeded":
                    # سقف المستخدم قرارُ أدمِن الحساب لا الطبقة — الترقية ليست
                    # الحلّ، فلا تُعرَض دعوتها (upgrade=False يوجّه الرسالة).
                    detail.update({"upgrade": False,
                                   "user_limit": decision.user_limit,
                                   "user_used": decision.user_used})
                raise HTTPException(status_code=403, detail=detail)
            # (٤) سجلّ التشغيلة الدائم (R2) + المدة المتوقعة + التدقيق — معاملة
            # واحدة بعد حجز الحصّة. أيّ عطلٍ هنا يُعوَّض (الدراسة مسودّةً والحصّة
            # مُرجَعة) بدل صفٍّ «قيد الإعداد» بلا تشغيلة ينتظر الكنس ساعةً.
            try:
                # لقطةُ وسائط التشغيل — نفس الوسائط التي كان الخيط يتلقّاها
                # مباشرةً (LESSONS ٧٩: تأكيدُ المصنع لبنده يصل الجسرَ دوماً).
                params = dict(
                    product=product,
                    hs_code=study.get("hs_code"),
                    market_pref=study.get("market_pref"),
                    hs_confirmed=bool(study.get("hs_confirmed")),
                    # الموجة ٠: **اللقطة** لا إعداد المصنع الحيّ — الصفّ خُتم
                    # للتوّ ذرّياً أعلاه، فتشغيلة جارية لا تتأثّر بتبديلٍ لاحق.
                    lang=snap_lang,
                    # p6/T10: تشغيلة محفوظة من إطلاقٍ سابق فشل ذيلُه — تُستأنف
                    # إن طابقت (الجسر يفحص التطابق عند التشغيل).
                    resume_analysis_id=study.get("analysis_id"),
                    # الموجة C (E-04): بطاقةُ المنتج من الكتالوج — تُبنى فقط إن
                    # أدخل المصنعُ تكلفةَ الوحدة. غيابُها **فجوةُ إدخالٍ معلنة**
                    # يقولها التقرير باسمها، لا تكلفةٌ مُقدَّرة تُنتِج هامشاً وهمياً.
                    product_card=_study_product_card(study, ctx),
                    # R4.7 (الترحيل ٠١٧): مصدرُ البند كما سُجِّل على المنتج —
                    # يصل المحرّكَ بدل «catalog» الملصَق على الجميع.
                    hs_source=_study_hs_source(conn, ctx, study),
                    # R4.8 (الترحيل ٠١٩): إقرارُ المصنع المختوم يصل جسمَ
                    # `/research` كما لو أرسله عميلٌ حاضر.
                    advisories_ack=bool(study.get("advisories_ack_at")),
                )
                study_runtime.create_run(conn, study_id=study_id,
                                         run_token=run_token,
                                         mode=engine_bridge.launch_mode(),
                                         params=params)
                eta_s, eta_basis = engine_bridge.eta_seconds(conn)
                audit.record(conn, action="study_launched", user_id=ctx.user_id,
                             account_id=ctx.account_id, resource_type="study",
                             resource_id=study_id,
                             changes={"product": product,
                                      "market_pref": study.get("market_pref"),
                                      "hs_code": study.get("hs_code")})
                conn.commit()
            except Exception:
                conn.rollback()
                conn.execute("UPDATE studies SET state = 'draft', launched_at = NULL, "
                             "launched_by_user_id = NULL, run_started_at = NULL, "
                             "run_error = ?, updated_at = ? "
                             "WHERE id = ? AND owner_id = ? "
                             "AND state = 'in_progress' AND run_token = ?",
                             ("لم تنطلق: عطل داخلي أثناء تسجيل التشغيلة — "
                              "أعد المحاولة", auth.now_iso(), study_id,
                              ctx.account_id, run_token))
                quota.release_launch(conn, ctx.account_id, launched_at=now)
                conn.commit()
                raise
            out = {"ok": True, "state": "in_progress",
                   "quota_used": decision.used, "quota_limit": decision.limit,
                   "eta_s": eta_s, "eta_basis": eta_basis}
        finally:
            conn.close()
        # (٥) المشرف يطالب بالتشغيلة ويبدأ خيطها إن توفّرت فتحة — بعد الالتزام
        # وإغلاق الاتصال حصراً؛ وإلا بقيت منتظرةً في القاعدة تُبدأ حين تفرغ
        # فتحة. `run_state` إضافيّ على الردّ القائم (queued | running | finished).
        # §58 #5: عطلٌ هنا (قفلٌ مشغول) لا يقلب إطلاقاً ملتزَماً إلى 500 — الصفّ
        # منتظرٌ في القاعدة والمشرف يطالب به في دورته التالية.
        try:
            study_runtime.dispatch()
            out["run_state"] = study_runtime.active_state(study_id) or "finished"
        except Exception as exc:  # noqa: BLE001 — الإطلاق ملتزَم؛ المطالبة تحسين
            log.warning("study_run dispatch after launch failed study_id=%s: %s",
                        study_id, exc)
            out["run_state"] = "queued"
        return out

    # ═══════════ تقرير العميل + قراءة الصورة · client report + vision ════════

    def _client_view_gated(row: dict, fmt: str, *, block: bool = True):
        """ابنِ عرضَ العميل للدراسة ثمّ **أخضِعه لبوّابة التسليم نفسها**.

        الموجة B (البنود G-01/G-02/G-04/G-05): كان هذا المسارُ يبني ويُرسل
        مباشرةً من `build_view` بصفر نداءات بوابة، بينما سطحُ المشغّل
        (`/analyses/{id}/report.docx|pdf`) محكومٌ ببوّابةٍ حاجزة — فالعميلُ
        الدافع يتسلّم ما لا يتسلّمه المشغّل. الآن كِلا السطحين يمرّان بـ
        `silk_export_gate` نفسِه؛ ولا سياسةَ بوابةٍ في هذه الوحدة إطلاقاً.

        يعيد `(view, decision)`. حين `block=True` (مسارا docx/pdf) يرفع 409
        برسالةٍ بلغةِ **عميل** لا بلغةِ نظام — رفضُ الجودة كان يُترجَم
        501/503 «وحدات المحرّك غير متاحة» فيُقرأ عطلاً تقنياً (G-04).
        ولا تجاوزَ من هذا السطح: التجاوزُ سلطةُ مالكٍ لا سلطةُ مصنع.
        """
        try:
            from silk_render import build_view
            from silk_storage import get_analysis
        except Exception:  # noqa: BLE001 — منصّة بلا محرّك: فجوة معلنة
            raise HTTPException(status_code=503, detail={
                "error": "engine_unavailable",
                "message": "وحدات المحرّك غير متاحة من هذه الخدمة"})
        found = get_analysis(int(row["analysis_id"]))
        if found is None:
            raise HTTPException(status_code=404, detail={
                "error": "analysis_missing",
                "message": "نتيجة التحليل غير موجودة في قاعدة المحرّك"})
        # الموجة ٠: لغة التقرير من **لقطة الدراسة** حصراً — لا من إعداد
        # المصنع الحيّ ولا من ترويسة ولا من لغة الواجهة.
        lang = fsettings.study_report_language(row)
        view = engine_bridge.sanitize_client_brief(
            engine_bridge.strip_cost_keys(build_view(found, lang)))

        import silk_export_gate as _eg
        # نثرُ الاحتياط يُحضَّر هنا أيضاً — كان يُولَّد على مسار المشغّل وحدَه،
        # فيتسلّم المصنعُ «السرد غير متاح» حيث يتسلّم المشغّلُ نثراً مُعادَ
        # صياغته (G-05). بوّابةُ إضافات كلود المجانية نفسُها تحكم النداء.
        ai_ok = False
        _dr = view.get("deep_research") or {}
        # نفسُ تصحيحِ مراجعة §58 على سطحِ المصنع: قراءةُ التقرير غيرُ الحاجبة
        # كانت تحجز وحدةً من السقف اليوميّ لكلّ استعراضٍ حتى بلا نداءِ صياغة،
        # فتُستنزَف السقفُ بإعادةِ فتحِ الصفحة ويُرَدّ `/deepen` بـ429. يُحجَز
        # الآن فقط حين يوجد قسمٌ بلا سردٍ يستدعي كلود فعلاً.
        if (_dr and not _dr.get("client_fallback_prose")
                and _eg.client_prose_needed(_dr)):
            try:
                import silk_usage
                ai_ok = bool(silk_usage.free_ai_extras_allowed()[0])
            except Exception:  # noqa: BLE001 — تعذّرت البوابة = لا نداء
                ai_ok = False
        _eg.prepare_fallback_prose(view, ai_allowed=ai_ok, found=found,
                                   analysis_id=int(row["analysis_id"]))

        decision = _eg.evaluate(view)
        if block and _eg.is_blocked(decision):
            _eg.record_block(int(row["analysis_id"]), row.get("product"),
                             row.get("market_pref"), decision["findings"],
                             decision["digest"], fmt, surface="factory",
                             fail_drivers=decision.get("fail_drivers"))
            raise HTTPException(status_code=409, detail=_eg.factory_detail(
                decision["digest"], lang,
                fail_drivers=decision.get("fail_drivers")))
        return view, decision

    def _artifact_gate_409(exc, row, fmt):
        """رفضُ بوّابةِ نصّ المُنتَج النهائيّ ⇒ 409 `quality_gate_fail` لا
        501/503 «الميزة معطّلة» ولا تسريبُ لغةِ البوّابةِ الداخلية للعميل
        (G-04). كان `render_client_docx`/`_pdf` يرفعان `RuntimeError` فيقرؤه
        سطحُ المصنع «docx/pdf unavailable» ويُظهِر نصَّ الفحص الداخليّ. الآن
        نوعٌ مستقلّ (`ClientArtifactGateError`) يُوجَّه عبر `factory_detail`،
        ويُسجَّل الحجبُ للمشغّل بالتفصيل الكامل (مراجعة §58)."""
        import silk_export_gate as _eg
        lang = fsettings.study_report_language(row)
        digest = list(getattr(exc, "findings", None) or [])
        # C4 موجة #14: قائمة هذا المسار كلها قائدة بالبناء — تُمرَّر للحمولة
        # أيضاً لا للسجل وحده، وإلا بقي سطر «قائد الحجب» أعمى على هذا السطح.
        _drivers = [str(d.get("check") or "") for d in digest
                    if isinstance(d, dict)]
        try:
            _eg.record_block(int(row.get("analysis_id") or 0),
                             row.get("product"), row.get("market_pref"),
                             digest, digest, fmt, surface="factory",
                             fail_drivers=_drivers)
        except Exception:  # noqa: BLE001 — التسجيلُ تحسينيّ لا شرط
            pass
        return HTTPException(status_code=409,
                            detail=_eg.factory_detail(
                                digest, lang, fail_drivers=_drivers))

    @app.get(_PREFIX + "/studies/{study_id}/report")
    def study_report(study_id: int, request: Request):
        """تقرير دراسة السوق — نسخة العميل من العرض القانوني الواحد.

        لا مسار عرض جديد (LAW §7): `silk_render.build_view` هو المصدر، وكل
        الحمولة تمرّ من `engine_bridge.strip_cost_keys` — **لا مفتاح تكلفة
        داخلية يبلغ مصنعاً** (قرار المالك، والقفل بنيوي في اختبار الرؤية).
        """
        row = _tenant_detail(request, repository.studies, study_id, "study")
        if not row.get("analysis_id"):
            raise HTTPException(status_code=409, detail={
                "error": "no_report_yet", "state": row.get("state"),
                "run_error": row.get("run_error"),
                "message": "لا تقرير بعد — الدراسة لم تكتمل"})
        # القراءةُ لا تُحجَب (المصنع يرى تقريره على الشاشة)، لكنّ حكمَ
        # البوّابة **يُعلَن** له: كان لا يصل أيَّ سطحٍ للمصنع إطلاقاً — لا
        # حجبٌ ولا حتى إخبار (البند G-02).
        view, decision = _client_view_gated(row, "json", block=False)
        import silk_export_gate as _eg
        _lang = fsettings.study_report_language(row)
        return {"study": {k: row.get(k) for k in
                          ("id", "product", "market_pref", "hs_code", "state",
                           "run_started_at", "run_finished_at",
                           "report_language",
                           "factory_language_at_generation")},
                "quality": _eg.client_quality_summary(decision, _lang),
                "view": view}

    @app.get(_PREFIX + "/studies/{study_id}/report.docx")
    def study_report_docx(study_id: int, request: Request):
        """تنزيل تقرير الدراسة Word — نفس تفريعة الجمهور في المحرّك (api.py
        الجذري): نتيجة `/analyze` تمرّ على `render_docx` الكلاسيكي (ملخّص
        تنفيذي ← أسواق بسطر مصدر لكل رقم ← «حدود هذا التقرير»)، ولو حملت
        `deep_research` يوماً فنسخة العميل `render_client_docx`. مجلد مؤقّت
        يُنظَّف بعد الإرسال (نفس انضباط البند #8 الجذري)."""
        row = _tenant_detail(request, repository.studies, study_id, "study")
        if not row.get("analysis_id"):
            raise HTTPException(status_code=409, detail={
                "error": "no_report_yet", "state": row.get("state"),
                "message": "لا تقرير بعد — الدراسة لم تكتمل"})
        view, _decision = _client_view_gated(row, "docx")
        import shutil
        import tempfile

        from starlette.background import BackgroundTask
        import silk_reports as _sr
        _td = tempfile.mkdtemp()
        try:
            _render = (_sr.render_client_docx if view.get("deep_research")
                       else _sr.render_docx)
            path = _render(view, os.path.join(_td, "report.docx"))
        except _sr.ClientArtifactGateError as exc:  # رفضُ جودةٍ لا عطلُ ميزة
            shutil.rmtree(_td, ignore_errors=True)
            raise _artifact_gate_409(exc, row, "docx")
        except RuntimeError as exc:  # python-docx غائب — فجوة معلنة لا 500
            shutil.rmtree(_td, ignore_errors=True)
            raise HTTPException(status_code=501, detail={
                "error": "docx_unavailable", "message": str(exc)})
        except Exception:
            shutil.rmtree(_td, ignore_errors=True)
            raise
        return FileResponse(
            path, filename=f"silk_study_{study_id}.docx",
            media_type=("application/vnd.openxmlformats-officedocument"
                        ".wordprocessingml.document"),
            background=BackgroundTask(shutil.rmtree, _td, ignore_errors=True))

    @app.get(_PREFIX + "/studies/{study_id}/report.pdf")
    def study_report_pdf(study_id: int, request: Request):
        """تنزيل تقرير الدراسة PDF — طلب المالك الحرفي (2026-08-17): «بالنسبة
        للتقرير اريده pdf».

        نفس عقيدة §3 الجذرية (`/analyses/{id}/report.pdf`): يُبنى docx القالب
        الموحّد (كل منطق RTL/التطهير فيه) ثم يُحوَّل عبر LibreOffice headless
        (`silk_reports.docx_to_pdf` — الحاوية تشحن soffice + الخط الرسمي)
        ويُسلَّم الـPDF فقط. العطلُ = 503 برمزٍ مسمّى (`pdf_error_detail`):
        `pdf_unavailable` لغياب المحرّك وحده، `pdf_failed` لفشل التحويل،
        `pdf_rejected` لرفض فحصٍ (الأقواس/المحتوى) — لا docx بديل صامت ولا PDF جزئي. نفس فصل الجمهور
        في نقطة docx أعلاه: نسخة العميل عند وجود `deep_research`.
        """
        row = _tenant_detail(request, repository.studies, study_id, "study")
        # §58 M5: تحويل soffice عملية كاملة على حاوية واحدة — جلسة مصنع
        # واحدة كانت تستطيع خنق كل المستأجرين بتنزيلات متوازية. عدّاد مسمى
        # لكل حساب (نفس نمط `diag|`).
        ctx = request.state.auth
        conn = _open()
        try:
            ident = f"pdf|{ctx.account_id}"
            limits = throttle.named_limits("PDF", 10)
            if throttle.is_throttled(conn, ident, limits):
                raise HTTPException(status_code=429, detail={
                    "error": "pdf_throttled",
                    "message": "تنزيلات PDF مقيّدة المعدل — انتظر دقائق ثم أعد"})
            throttle.record_failure(conn, ident, limits)
            conn.commit()
        finally:
            conn.close()
        if not row.get("analysis_id"):
            raise HTTPException(status_code=409, detail={
                "error": "no_report_yet", "state": row.get("state"),
                "message": "لا تقرير بعد — الدراسة لم تكتمل"})
        view, _decision = _client_view_gated(row, "pdf")
        import shutil
        import tempfile

        from starlette.background import BackgroundTask
        import silk_reports as _sr
        _td = tempfile.mkdtemp()
        try:
            _render_pdf = (_sr.render_client_pdf if view.get("deep_research")
                           else _sr.render_research_pdf)
            path = _render_pdf(view, os.path.join(_td, "report.pdf"))
        except _sr.ClientArtifactGateError as exc:  # رفضُ جودةٍ لا عطلُ ميزة
            shutil.rmtree(_td, ignore_errors=True)
            raise _artifact_gate_409(exc, row, "pdf")
        except _sr.PdfBusy:  # R9 (API-11/EXT-14): الفتحاتُ مشغولة — 503 مسمّى + Retry-After
            shutil.rmtree(_td, ignore_errors=True)
            raise HTTPException(status_code=503, detail=_sr.pdf_busy_detail(),
                                headers={"Retry-After": str(_sr.PDF_RETRY_AFTER_S)})
        except RuntimeError as exc:
            # البند ٢٨٤: كان كلُّ RuntimeError هنا `pdf_unavailable` («معطَّل على
            # الخادم — أبلغ الإدارة») — ومنه رفضُ فحص الأقواس بعد تحويلٍ ناجح،
            # بلا أيّ سطرٍ في السجلّ. الآن رمزٌ لكلّ نوع + أثرٌ للمشغّل
            # (`record_pdf_failure` — الدالةُ نفسُها في مسار المشغّل).
            shutil.rmtree(_td, ignore_errors=True)
            detail = _sr.record_pdf_failure(
                exc, "factory", {"study_id": study_id,
                                 "analysis_id": row.get("analysis_id")})
            raise HTTPException(status_code=503, detail=detail)
        except Exception:
            shutil.rmtree(_td, ignore_errors=True)
            raise
        return FileResponse(
            path, filename=f"silk_study_{study_id}.pdf",
            media_type="application/pdf",
            background=BackgroundTask(shutil.rmtree, _td, ignore_errors=True))

    @app.post(_PREFIX + "/classify-image")
    def classify_image(request: Request, body: dict = Body(default=None)):
        """اقرأ المنتج من صورة واقترح رمز HS — قرار المالك (2026-08-17).

        الجسم `{"image_id": N}` لصورة مرفوعة سلفاً لهذا الحساب. إعادة استخدام
        السلسلة القائمة (`silk_product_intake` ← `silk_hs_classifier`) بعقدها
        الصادق: تعذّر القراءة/ثقة منخفضة = رسالة معلنة، **لا اسم ولا رمز
        مختلَق أبداً**. النداء مقيس من نفس سقف الاستهلاك اليومي.
        """
        ctx = _require(request, Role.FACTORY)
        body = _json_body(body)
        iid = _as_int(body.get("image_id"), "image_id", minimum=1)
        conn = _open()
        try:
            # درس 189 (F10، قرار مالك 2026-08-27): خانقٌ لكل حساب — كل نداء
            # يحجز تفعيلة من السقف المدفوع **المشترك** (engine_bridge._vision_
            # allowed)، وبلا خانق كان مستأجرٌ واحد يستنزف ميزانية الكل بحلقةٍ
            # على صورةٍ مرفوعة (نفس عيب §58 M5 الذي عولج لـPDF وفات هنا).
            ident = f"vision|{ctx.account_id}"
            limits = throttle.named_limits("VISION", 20)
            if throttle.is_throttled(conn, ident, limits):
                raise HTTPException(status_code=429, detail={
                    "error": "vision_throttled",
                    "message": "قراءة الصور مقيّدة المعدل — انتظر دقائق ثم أعد"})
            throttle.record_failure(conn, ident, limits)   # عدّاد نداء، لا «فشل»
            repo = repository.images(conn)
            img = repo.get(ctx.account_id, iid)
            if img is None:
                _deny_write_404(conn, request, ctx, repo, iid, "image",
                                "cross_tenant_classify")
            audit.record(conn, action="image_classify_requested",
                         user_id=ctx.user_id, account_id=ctx.account_id,
                         resource_type="image", resource_id=iid,
                         ip_address=_client_ip(request))
            conn.commit()
        finally:
            conn.close()
        if not storage.exists(img["storage_key"]):
            raise _err(404, "image_file_missing", "ملفُّ الصورة مفقود")
        with open(storage.path_for(img["storage_key"]), "rb") as fh:
            content = fh.read()
        return engine_bridge.classify_image_flow(
            content, img.get("mime_type") or "application/octet-stream")

    # ═══════════════ دورة حياة الدراسة · study lifecycle transitions ═════════
    def _lifecycle(fn, study_id: int, request: Request, action: str):
        """جسم مشترك لانتقالَي الإنهاء والأرشفة — one body so they cannot drift."""
        ctx = _require(request, Role.SILK_ADMIN, Role.FACTORY)
        conn = _open()
        try:
            # R2 (§58 #1): دراسةٌ لها تشغيلة نشطة (منتظرة/جارية) لا تُغلَق ولا
            # تُؤرشَف من فوق تشغيلتها — كانت الأرشفةُ تترك صفّاً منتظراً يُنفَّذ
            # لاحقاً على دراسةٍ مؤرشفة بلا ربطٍ ولا إرجاع حصّة. المخرج: الإلغاء.
            if (repository.studies(conn).get(ctx.account_id, study_id) is not None
                    and study_runtime.has_active_run(conn, study_id)):
                raise HTTPException(status_code=409, detail={
                    "error": "study_running",
                    "message": "الدراسة قيد التنفيذ — ألغِ تشغيلتها أولاً"})
            try:
                out = fn(conn, account_id=ctx.account_id, study_id=study_id,
                         actor_user_id=ctx.user_id)
            except lifecycle.LifecycleError as exc:
                raise HTTPException(status_code=409, detail=exc.as_detail())
            if out is None:
                repo = repository.studies(conn)
                _deny_write_404(conn, request, ctx, repo, study_id, "study", action)
        finally:
            conn.close()
        return out

    @app.post(_PREFIX + "/studies/{study_id}/complete")
    def complete_study_ep(study_id: int, request: Request):
        """أنهِ دراسة — in_progress → completed؛ 409 ما دام في الطابور معلّق.

        «مكتملة» ورسائلها ستخرج بعد دقائق **ادعاءٌ كاذب** عن الواقع — والعامل لا
        يفحص حالة الدراسة، فلا شيء يوقفها. ينتظر العميل النفاد أو يؤرشف.
        """
        return _lifecycle(lifecycle.complete_study, study_id, request,
                          "cross_tenant_complete")

    @app.post(_PREFIX + "/studies/{study_id}/archive")
    def archive_study_ep(study_id: int, request: Request):
        """أرشِف دراسة — **سحبٌ حقيقي**: يُلغي البريد المعلّق ثم يُغلق الحالة.

        يرجّع `cancelled_queued_emails`. صفٌّ مُرسَل مِن قبل لا يُمَسّ (له قيد
        موافقة وقيد دفتر)، وصفٌّ في الطريق (`sending`) يرفع 409 عابراً.
        """
        return _lifecycle(lifecycle.archive_study, study_id, request,
                          "cross_tenant_archive")

    @app.post(_PREFIX + "/studies/{study_id}/cancel")
    def cancel_study_ep(study_id: int, request: Request):
        """ألغِ التشغيلة النشطة لدراسة (R2) — المنتظِرة تُرجَع فوراً، والجارية
        تُوقَف تعاونياً عند نقطة تفتيشها التالية (لا قتلَ خيوط؛ نداءٌ خارجيّ
        جارٍ يُكمِل مهلته أولاً). 409 معلَن حين لا تشغيلة نشطة؛ عبر المستأجر
        404 بلا تسريب وجود."""
        ctx = _require(request, Role.SILK_ADMIN, Role.FACTORY)
        conn = _open()
        try:
            repo = repository.studies(conn)
            study = repo.get(ctx.account_id, study_id)
            if study is None:
                _deny_write_404(conn, request, ctx, repo, study_id, "study",
                                "cross_tenant_cancel")
            if study["state"] != "in_progress":
                raise HTTPException(status_code=409, detail={
                    "error": "study_not_running",
                    "message": "لا تشغيلة جارية لهذه الدراسة"})
            try:
                out = study_runtime.request_cancel(
                    conn, study_id=study_id, account_id=ctx.account_id,
                    actor_user_id=ctx.user_id)
            except lifecycle.LifecycleError as exc:
                raise HTTPException(status_code=409, detail=exc.as_detail())
        finally:
            conn.close()
        return out

    # ══════════════════════════ IMAGES ══════════════════════════════════════
    @app.get(_PREFIX + "/images")
    def list_images(request: Request):
        """صور الحساب — كانت النقطة الوحيدة رفعاً بلا سرد، فرفعُ صورةٍ من
        الواجهة كان يختفي بلا أي سبيل لرؤيته أو استعماله لاحقاً."""
        ctx = _require(request, Role.FACTORY)
        conn = _open()
        try:
            rows = repository.images(conn).list(ctx.account_id)
        finally:
            conn.close()
        return {"images": rows}

    @app.post(_PREFIX + "/images")
    def create_image(request: Request, file: UploadFile = File(...),
                     alt_text_en: str = Form(default=""),
                     alt_text_ar: str = Form(default="")):
        """ارفع صورة حقيقية — real bytes to disk; size_bytes is measured, not trusted.

        قبل هذا الفرق كانت النقطة تسجّل `size_bytes`/`ext` كما يرسلهما العميل
        بلا أي بايت فعليّ — عيبٌ يخالف عقد عدم الاختلاق مباشرةً: فاتورة تخزينٍ
        (`jobs.run_storage_billing`) على رقمٍ لم يُقَس. الآن الحجم = طول
        المحتوى المرفوع فعلياً، والامتداد مُقيَّد بقائمة بيضاء (`storage.py`).
        Previously trusted client-supplied size_bytes/ext with zero real bytes
        — a direct violation of the no-fabrication contract for a number that
        feeds real billing. size_bytes is now measured from the actual upload.
        """
        ctx = _require(request, Role.FACTORY)
        # R4.2 (تدقيق 2026-09-01، API-2): الخانق **قبل** قراءة الجسم — الرفعُ
        # كان بلا أيّ حدٍّ معدَّليّ، فحلقةٌ تكتب على الوحدة المركَّبة بسرعة
        # القرص. عدّادٌ باسمه لا يستعير نافذة الدخول (الدرس ١٨٧).
        _uident = f"upload|{ctx.account_id}"
        _ulimits = throttle.named_limits("UPLOAD", 30)
        conn = _open()
        try:
            if throttle.is_throttled(conn, _uident, _ulimits):
                raise HTTPException(status_code=429, detail={
                    "error": "upload_throttled",
                    "message": "رفع الصور مقيّد المعدل — انتظر دقائق ثم أعد"})
            throttle.record_failure(conn, _uident, _ulimits)  # عدّاد نداء، لا «فشل»
        finally:
            conn.close()
        # اقرأ بحدّ أقصى +1 بايت فوق السقف — لا تحمّل رفعاً ضخماً كاملاً في
        # الذاكرة قبل أن تعرف أنه سيُرفَض. Bounded read: never buffer an
        # oversized upload fully before checking the cap.
        cap = storage.max_bytes()
        content = file.file.read(cap + 1)
        if len(content) > cap:
            raise _err(422, "upload_too_large", "الملف أكبر من الحدّ المسموح", max_bytes=cap)
        orig_name = file.filename or ""
        raw_ext = orig_name.rsplit(".", 1)[-1] if "." in orig_name else ""
        try:
            ext = storage.validate_extension(raw_ext)
        except ValueError as exc:
            raise _err(422, "bad_upload", str(exc))          # مراجعة R6 (FE-6)
        # R7 (AUTH-17/BIZ-9): المحتوى يحكم لا الامتداد — بايتاتُ JPEG (أو أيّ شيء)
        # باسم `.png` كانت تُخزَّن وتُقدَّم بنوع `image/png` وتُفوتَر.
        _kind = storage.sniff_image_kind(content[:16])
        if _kind is None or not storage.extension_matches_kind(ext, _kind):
            raise HTTPException(status_code=422, detail={
                "error": "image_content_mismatch",
                "message": "محتوى الملف لا يطابق امتداده — ارفع صورةً حقيقية "
                           "(PNG/JPEG/GIF/WebP) بامتدادها الصحيح",
                "declared": ext, "detected": _kind})
        # السقفُ التجميعيّ للطبقة — داخل **معاملة الإدراج نفسها** (`BEGIN
        # IMMEDIATE`): مراجعة §58 على R4 (٣ عالية) — قراءةُ المجموع على اتصالٍ
        # يُغلَق قبل قراءة الجسم كانت تدع رفعاتٍ متزامنة تمرّ كلُّها على المجموع
        # القديم. القفلُ يسبق أيّ بايتٍ على القرص، فرفضٌ بعد الكتابة لا يقع.
        key = f"{ctx.account_id}/{uuid.uuid4().hex}.{ext}"
        conn = _open()
        try:
            conn.execute("BEGIN IMMEDIATE")
            _tier = conn.execute("SELECT tier FROM accounts WHERE id = ?",
                                 (ctx.account_id,)).fetchone()
            _cap_bytes = quota.storage_cap_bytes(str(_tier["tier"]))
            _used_bytes = quota.storage_used_bytes(conn, ctx.account_id)
            if _used_bytes + len(content) > _cap_bytes:
                conn.rollback()
                _mb = _cap_bytes // (1024 * 1024)
                raise HTTPException(status_code=413, detail={
                    "error": "storage_quota_exceeded",
                    "message": f"بلغت مساحةَ التخزين المتاحة لباقتك ({_mb} ميغابايت)"
                               " — رقِّ الباقة أو احذف صوراً غير مستعملة",
                    "used_bytes": _used_bytes, "cap_bytes": _cap_bytes})
            storage.write(key, content)   # القرص أوّلاً — صفٌّ يشير لملفٍ غير مكتوب أسوأ من ملفٍ يتيم
            fields = {"filename": orig_name or None, "storage_key": key,
                      "mime_type": storage.mime_for_extension(ext),
                      "size_bytes": len(content),
                      "uploaded_by_user_id": ctx.user_id,
                      "alt_text_en": alt_text_en or None,
                      "alt_text_ar": alt_text_ar or None}
            row = repository.images(conn).create(ctx.account_id, fields)
            conn.commit()
        except HTTPException:
            raise
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return row

    @app.delete(_PREFIX + "/images/{image_id}")
    def delete_image(image_id: int, request: Request):
        """احذف صورةً غير مستعملة — مراجعة §58 على R4 (٥ متوسّطة): السقفُ التجميعيّ
        كان سقّاطةً باتجاهٍ واحد ورسالتُه تنصح بحذفٍ لا مسارَ له. صورةٌ مرتبطة
        بمنتجٍ أو دراسة ⇒ 409 (فكّ الربط أولاً)؛ الملفُ يُزال **بعد** الالتزام
        (صفٌّ بلا ملف أسوأ من ملفٍ بلا صفّ)."""
        ctx = _require(request, Role.FACTORY)
        conn = _open()
        try:
            repo = repository.images(conn)
            row = repo.get(ctx.account_id, image_id)
            if row is None:
                _deny_write_404(conn, request, ctx, repo, image_id, "image",
                                "cross_tenant_delete")
            in_use = conn.execute(
                "SELECT (SELECT COUNT(*) FROM products WHERE account_id = ? "
                "AND image_id = ?) + (SELECT COUNT(*) FROM studies "
                "WHERE owner_id = ? AND image_id = ?)",
                (ctx.account_id, image_id, ctx.account_id, image_id)).fetchone()[0]
            if in_use:
                raise HTTPException(status_code=409, detail={
                    "error": "image_in_use",
                    "message": "الصورة مرتبطة بمنتجٍ أو دراسة — فكّ الربط أولاً ثم احذفها"})
            repo.delete(ctx.account_id, image_id)
            audit.record(conn, action="image_deleted", user_id=ctx.user_id,
                         account_id=ctx.account_id, resource_type="image",
                         resource_id=image_id,
                         changes={"size_bytes": int(row["size_bytes"] or 0)})
            conn.commit()
        finally:
            conn.close()
        storage.delete(row["storage_key"])
        return {"ok": True, "freed_bytes": int(row["size_bytes"] or 0)}

    @app.get(_PREFIX + "/images/{image_id}/signed-url")
    def image_signed_url(image_id: int, request: Request):
        """رابط موقّع للصورة — verify owner_id BEFORE signing; foreign ⇒ 404/403."""
        row = _tenant_detail(request, repository.images, image_id, "image")
        # التوقيع يحدث فقط بعد إثبات الملكية · signed only after ownership proven.
        expiry = int(time.time()) + 900
        sig = tokens.sign(f"{row['storage_key']}:{expiry}")
        return {"signed_url": f"/files/{row['storage_key']}?expires={expiry}&sig={sig}",
                "expires": expiry, "storage_key": row["storage_key"],
                "serving_available": True}

    # ══════════════════════════ FILES (signed, public) ═══════════════════════
    # خارج _PREFIX عمداً (يطابق شكل signed_url أعلاه منذ PR-1) وبلا مصادقة —
    # التوقيع HMAC هو الحارس الوحيد. البحث عن
    # الصفّ بـstorage_key (عمودٌ UNIQUE عالمياً، لا لكل حساب) هو حدّ الثقة قبل
    # أي لمسٍ للقرص: مفتاحٌ لا يطابق صفّاً حقيقياً لا يصل نظام الملفات إطلاقاً.
    # Outside _PREFIX by design (matches signed_url's shape since PR-1), no
    # auth — the HMAC signature is the sole guard.
    @app.get("/files/{storage_key:path}")
    def serve_file(storage_key: str, expires: int, sig: str):
        if time.time() > expires or not tokens.verify_signature(
                f"{storage_key}:{expires}", sig):
            raise _err(404, "not_found", "غير موجود")
        conn = _open()
        try:
            row = conn.execute(
                "SELECT storage_key, mime_type FROM images WHERE storage_key = ?",
                (storage_key,)).fetchone()
        finally:
            conn.close()
        if row is None or not storage.exists(row["storage_key"]):
            raise _err(404, "not_found", "غير موجود")
        return FileResponse(storage.path_for(row["storage_key"]),
                            media_type=row["mime_type"] or "application/octet-stream")

    # ══════════════════════════ WALLET / LEDGER ═════════════════════════════
    @app.get(_PREFIX + "/wallet")
    def get_wallet_ep(request: Request):
        # analyst: لا بيانات حساب فردية · no individual account data.
        ctx = _ctx(request)
        if ctx.is_silk_analyst:
            raise _err(403, "analyst_aggregates_only", "المحلّل يرى المجاميع فقط")
        conn = _open()
        try:
            w = wallet.ensure_wallet(conn, ctx.account_id)  # own account only
            # المديونية وحدّها مرئيان للعميل صراحةً (لماذا تُحجَب الإطلاقات).
            w["delinquent"] = wallet.is_delinquent(conn, ctx.account_id)
            w["overdraft_floor_cents"] = wallet.overdraft_floor_cents()
        finally:
            conn.close()
        return w

    @app.get(_PREFIX + "/wallet/ledger")
    def get_ledger_ep(request: Request, limit: int = 20):
        ctx = _ctx(request)
        if ctx.is_silk_analyst:
            raise _err(403, "analyst_aggregates_only", "المحلّل يرى المجاميع فقط")
        # R4.4 (تدقيق 2026-09-01، API-4): `?limit=-1` كان يصل SQLite بمعنى
        # «بلا حدّ» فيُعيد الجدولَ كاملاً — نفس سقف قوائم الأدمِن (١..٥٠٠).
        limit = _as_int(limit, "limit", minimum=1, maximum=500, default=20)
        conn = _open()
        try:
            # النطاق دائماً حساب المنادي — أي account_id في الاستعلام يُتجاهَل.
            entries = wallet.list_ledger(conn, ctx.account_id, limit=limit)
        finally:
            conn.close()
        return {"account_id": ctx.account_id, "entries": entries}

    # ══════════════════════════ AUDIT (factory own) ═════════════════════════
    @app.get(_PREFIX + "/audit")
    def factory_audit(request: Request, limit: int = 50, action: str | None = None):
        """بحث تدقيق الحساب — same `action` filter admin_audit already has.

        النطاق يبقى account_id الجلسة دائماً (لا يُقبَل من الطلب) — البحث فقط
        على الفعل، لا توسيع النطاق. Search adds a filter, never widens scope.
        """
        ctx = _require(request, Role.FACTORY)
        limit = _as_int(limit, "limit", minimum=1, maximum=500, default=50)  # R4.4
        conn = _open()
        try:  # own account only — cannot see other accounts' logs
            rows = audit.search(conn, account_id=ctx.account_id, action=action,
                                limit=limit)
        finally:
            conn.close()
        return {"account_id": ctx.account_id, "audit": rows}

    # ═══════════════ الإشعارات · in-platform notifications (2026-08-18) ══════
    @app.get(_PREFIX + "/notifications")
    def list_notifications(request: Request):
        """إشعارات الحساب + عدد غير المقروء — تستطلعها الواجهة (جرس + متصفح).

        يكتبها جسر المحرّك عند إنهاء كل تشغيلة (نجاحاً/فشلاً معلَناً) في نفس
        معاملة الإنهاء. النطاق حساب الجلسة حصراً.
        """
        ctx = _require(request, Role.SILK_ADMIN, Role.FACTORY)
        conn = _open()
        try:
            out = notifications.list_for_account(conn, ctx.account_id)
        finally:
            conn.close()
        return out

    @app.post(_PREFIX + "/notifications/read")
    def read_notifications(request: Request, body: dict = Body(default=None)):
        """علّم إشعاراتٍ مقروءةً — `{ids:[...]}` أو الكل عند غياب القائمة."""
        ctx = _require(request, Role.SILK_ADMIN, Role.FACTORY)
        ids = (body or {}).get("ids")
        up_to = _as_int((body or {}).get("up_to_id"), "up_to_id", minimum=1,
                        default=0) or None      # BIZ-11: علامةٌ مائية اختيارية
        if ids is not None and not (isinstance(ids, list)
                                    and all(isinstance(i, int) for i in ids)):
            raise HTTPException(status_code=422, detail={
                "error": "bad_notification_ids",
                "message": "قائمة المعرّفات أعداد صحيحة أو تُحذف لتعليم الكل"})
        conn = _open()
        try:
            n = notifications.mark_read(conn, ctx.account_id, ids, up_to_id=up_to)
        finally:
            conn.close()
        return {"ok": True, "marked": n}

    # ═══════════════════ الاستحقاقات · entitlements ══════════════════════════
    # (حُذفت «المقاعد» والمستخدمون الفرعيون نهائياً — قرار المالك 2026-08-19:
    # حسابٌ واحد لكل مصنع. جدول `users` يبقى لأنه هويّة الدخول نفسها؛ ما ذهب
    # هو مسارُ إدارة مستخدمين فرعيين وبوّابةُ سقفهم. حارس الحذف:
    # tests/test_platform_seats_deletion_guard.py)
    def _tier_gate_403(exc: entitlements.TierGateError):
        """ترجم بوّابة الطبقة إلى 403 بدعوة ترقية — the ONE translation point.

        كل مسار يفرض طبقةً يرفع `TierGateError` ويمرّ من هنا، فتخرج دعوة الترقية
        بشكل واحد للواجهة بدل رسائل متناثرة. One shape for every tier denial.
        """
        return HTTPException(status_code=403, detail=exc.as_detail())

    @app.get(_PREFIX + "/entitlements")
    def get_entitlements(request: Request):
        """استحقاقات الحساب + استخدامه — what this tier grants and what's used.

        المصنع يقرأ حسابه؛ الأدمِن يقرأ حسابه هو (بيانات المصانع تمرّ من نقاط
        الأدمِن المخصّصة كي يبقى جدار PII واحداً).
        """
        ctx = _require(request, Role.FACTORY, Role.SILK_ADMIN)
        conn = _open()
        try:
            snap = entitlements.snapshot(conn, ctx.account_id,
                                         user_id=ctx.user_id)
        finally:
            conn.close()
        return snap.as_dict()

    # ══════════════════════════ ADMIN ═══════════════════════════════════════
    @app.get(_PREFIX + "/admin/metrics")
    def admin_metrics(request: Request):
        ctx = _require(request, Role.SILK_ADMIN)
        conn = _open()
        try:
            by_tier = {r["tier"]: r["c"] for r in conn.execute(
                "SELECT tier, COUNT(*) AS c FROM accounts WHERE is_vault = 0 "
                "GROUP BY tier").fetchall()}
            active_studies = conn.execute(
                "SELECT COUNT(*) AS c FROM studies WHERE state = 'in_progress'"
            ).fetchone()["c"]
            vault_id = seed_mod.vault_account_id(conn)
            vw = wallet.get_wallet(conn, vault_id) if vault_id else None
            out = {"accounts_by_tier": by_tier, "active_studies": active_studies,
                   "vault_balance_cents": int(vw["balance"]) if vw else 0}
            # ═══ نظرة عامة الأدمِن (قرار مالك 2026-08-17: «الخدمات في داشبورد
            # الأدمن سيئة ولا يستفاد منها») — مفاتيح إضافية فقط. الشهور من
            # سجلّ التدقيق لا من أختام الدراسة: ختم `launched_at` يُمسَح عمداً
            # عند الفشل (تعويض الحصّة)، والسجلّ append-only فلا يفقد إطلاقة.
            # نمط `substr(created_at,1,7)` نفسه المعتمد في quota.py.
            month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
            out["factory_accounts"] = conn.execute(
                "SELECT COUNT(*) AS c FROM accounts WHERE kind = 'factory'"
            ).fetchone()["c"]
            out["total_users"] = conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE is_active = 1"
            ).fetchone()["c"]

            def _audit_month_counts(action: str) -> dict:
                return {r["m"]: r["c"] for r in conn.execute(
                    "SELECT substr(created_at, 1, 7) AS m, COUNT(*) AS c "
                    "FROM audit_log WHERE action = ? GROUP BY m "
                    "ORDER BY m DESC LIMIT 12", (action,)).fetchall()}

            launched = _audit_month_counts("study_launched")
            completed = _audit_month_counts("study_run_completed")
            out["launched_this_month"] = int(launched.get(month, 0))
            out["completed_this_month"] = int(completed.get(month, 0))
            out["checkout_requests_this_month"] = conn.execute(
                "SELECT COUNT(*) AS c FROM audit_log "
                "WHERE action = 'checkout_requested' "
                "AND substr(created_at, 1, 7) = ?", (month,)).fetchone()["c"]
            # آخر ١٢ شهراً تقويمياً حتى الشهر الحالي — شهرٌ بلا صفوف يظهر
            # صفراً **مرصوداً** (عدُّ سجلٍّ كامل أعاد لا-شيء)، ليس اختلاقاً.
            months = []
            y, m = int(month[:4]), int(month[5:7])
            for _ in range(12):
                key = f"{y:04d}-{m:02d}"
                months.append({"month": key,
                               "launched": int(launched.get(key, 0)),
                               "completed": int(completed.get(key, 0))})
                m -= 1
                if m == 0:
                    y, m = y - 1, 12
            out["studies_by_month"] = list(reversed(months))
        finally:
            conn.close()
        # تكاليف البحث الداخلية — **سطح أدمِن حصراً** (قرار مالك 2026-08-17:
        # «إخفاء التكلفة من داشبورد العميل وتخليها في داشبورد الأدمِن»). تُقرأ
        # من قاعدة المحرّك باستيراد كسول وأفضل جهد: غيابها (منصّة مستقلّة في
        # الاختبارات) = فجوة معلنة لا انهيار ولا رقم مختلَق.
        # Internal research costs are ADMIN-ONLY; read lazily/best-effort from
        # the engine store — absent DB = a declared gap, never a fabricated 0.
        out["research_costs"] = _research_costs_summary()
        return out

    def _research_costs_summary() -> dict:
        """ملخّص تكاليف البحث من قاعدة المحرّك — أفضل جهد، فجوة معلنة عند التعذّر."""
        try:
            import silk_storage
            rows = silk_storage.list_analyses(limit=8)   # الأحدث أولاً، بلا مسح كامل
            total, priced = 0.0, 0
            recent = []
            for r in rows:
                cost = r.get("cost_usd")
                if isinstance(cost, (int, float)):
                    total += float(cost)
                    priced += 1
                recent.append({"id": r.get("id"), "product": r.get("product"),
                               "market": r.get("market_name"),
                               "cost_usd": cost, "created_at": r.get("created_at")})
            return {"available": True, "recent": recent, "window": 8,   # R6 (FE-22)
                    "recent_total_usd": round(total, 2),
                    "recent_priced_runs": priced}
        except Exception as exc:  # noqa: BLE001 — منصّة بلا محرّك = فجوة معلنة
            return {"available": False,
                    "note": "قاعدة تحليلات المحرّك غير متاحة من هذه الخدمة",
                    "error_type": type(exc).__name__}

    @app.post(_PREFIX + "/admin/fund")
    def admin_fund(request: Request, body: dict = Body(default=None)):
        ctx = _require(request, Role.SILK_ADMIN)
        body = _json_body(body)
        conn = _open()
        try:
            # صحيحان أو 422: `int("1,000")` كان 500، و250.75 كانت تُقتطَع صمتاً
            # إلى 250 فيُقيَّد مبلغ يخالف ما أرسله الأدمِن (المال سنتات صحيحة).
            factory_id = _as_int(body.get("account_id"), "account_id", minimum=1)
            amount = _as_int(body.get("amount_cents"), "amount_cents", minimum=1)
            acc = conn.execute("SELECT * FROM accounts WHERE id = ?",
                               (factory_id,)).fetchone()
            if not acc or acc["kind"] != "factory":
                raise _err(404, "not_found", "حساب المصنع غير موجود")
            vault_id = seed_mod.vault_account_id(conn)
            if vault_id is None:
                raise _err(500, "no_vault", "لا حسابَ خزنة — تهيئةُ المنصّة ناقصة")
            try:
                vault_eid, factory_eid = wallet.fund_wallet(
                    conn, admin_user_id=ctx.user_id, factory_account_id=factory_id,
                    amount_cents=amount, vault_account_id=vault_id,
                    description=body.get("description") or "admin funding")
            except wallet.InsufficientFunds:
                raise _err(402, "funding_rejected", "رصيدُ الخزنة لا يكفي")
            except wallet.WalletError as exc:
                raise _err(422, "funding_rejected", str(exc))    # مراجعة R6 (FE-6)
            out = {"ok": True, "vault_entry_id": vault_eid,
                   "factory_entry_id": factory_eid, "amount_cents": amount}
        finally:
            conn.close()
        return out

    @app.get(_PREFIX + "/admin/audit")
    def admin_audit(request: Request, limit: int = 50,
                    account_id: int | None = None, action: str | None = None):
        ctx = _require(request, Role.SILK_ADMIN)
        limit = _as_int(limit, "limit", minimum=1, maximum=500, default=50)  # R4.4
        conn = _open()
        try:  # global search (admin only)
            rows = audit.search(conn, account_id=account_id, action=action, limit=limit)
        finally:
            conn.close()
        return {"audit": rows}

    @app.patch(_PREFIX + "/admin/accounts/{account_id}")
    def admin_rename_account(account_id: int, request: Request,
                             body: dict = Body(default=None)):
        """أعِد تسمية حساب — P3 (BIZ-13، تدقيق 2026-09-01): الاسمُ يُكتَب مرّةً عند
        الإنشاء ولا مسارَ لتصحيحه، فخطأٌ إملائيّ يبقى على كل تقريرٍ وفاتورة. تغييرٌ
        مدقَّق (`account_renamed`) لا صامت."""
        ctx = _require(request, Role.SILK_ADMIN)
        body = _json_body(body)
        name = _str_or_none(body.get("name"))
        if not name or len(name.strip()) < 2:
            raise _err(422, "invalid_account_name", "الاسمُ حرفان على الأقلّ")
        conn = _open()
        try:
            row = conn.execute("SELECT name FROM accounts WHERE id = ?",
                               (account_id,)).fetchone()
            if row is None:
                raise _err(404, "not_found", "الحساب غير موجود")
            before = row["name"]
            conn.execute("UPDATE accounts SET name = ?, updated_at = ? WHERE id = ?",
                         (name.strip(), auth.now_iso(), account_id))
            audit.record(conn, action="account_renamed", user_id=ctx.user_id,
                         account_id=account_id, resource_type="account",
                         resource_id=account_id,
                         changes={"from": before, "to": name.strip()},
                         ip_address=_client_ip(request))
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "id": account_id, "name": name.strip()}

    @app.get(_PREFIX + "/admin/accounts")
    def admin_list_accounts(request: Request, limit: int = 100):
        """اسرد حسابات المصانع بطبقاتها ومقاعدها — tier management needs this view.

        مقاييس فقط (طبقة، مقاعد، حالة) بلا محتوى مصنع ولا PII — جدار الأدمِن
        القائم يمنع محتوى المصانع، وهذه النقطة لا تخرقه. No factory content/PII.
        """
        ctx = _require(request, Role.SILK_ADMIN)
        limit = _as_int(limit, "limit", minimum=1, maximum=500, default=100)
        conn = _open()
        try:
            rows = conn.execute(
                "SELECT id, name, tier, is_active, created_at, "
                "per_user_monthly_studies FROM accounts "
                "WHERE kind = 'factory' ORDER BY id LIMIT ?", (limit,)).fetchall()
            from .models import tier_limits as _tl
            out = []
            for r in rows:
                # الحدّ الفعلي من الصفّ المجلوب سلفاً — نداء `per_user_limit`
                # كان يعيد SELECT لكل حساب (N+1 — ملاحظة المراجعة §58).
                override = r["per_user_monthly_studies"]
                eff = (max(0, int(override)) if override is not None
                       else max(0, int(_tl(r["tier"]).per_user_monthly_studies)))
                out.append({**dict(r),
                            "per_user_quota_effective": eff})
        finally:
            conn.close()
        return {"accounts": out}

    @app.get(_PREFIX + "/admin/studies")
    def admin_all_studies(request: Request, limit: int = 100):
        """كل دراسات المصانع — إشراف الأدمِن (قرار مالك 2026-08-17: «من واجهة
        الأدمن يكون مطلعاً على الدراسات»).

        بيانات الطلب التشغيلية فقط (منتج/سوق/حالة/أختام/سبب فشل) — قرارُ
        المالك يُدخل **هذه** الحقول تحديداً في نطاق الإشراف؛ جدار PII القائم
        (بريد المستخدمين، محتوى الصور) يبقى كما هو — لا بريد في هذا الرد،
        و`launched_by_user_id` رقمٌ يقابل حصّة المستخدم التي يضبطها الأدمِن.
        """
        ctx = _require(request, Role.SILK_ADMIN)
        limit = _as_int(limit, "limit", minimum=1, maximum=500, default=100)
        conn = _open()
        try:
            rows = [dict(r) for r in conn.execute(
                "SELECT s.id, a.name AS account_name, a.tier, s.product, "
                "s.market_pref, s.hs_code, s.state, s.launched_at, "
                "s.launched_by_user_id, s.run_started_at, s.run_finished_at, "
                "s.run_error, s.analysis_id, s.created_at, s.run_stats "
                "FROM studies s JOIN accounts a ON a.id = s.owner_id "
                "WHERE a.kind = 'factory' ORDER BY s.id DESC LIMIT ?",
                (limit,)).fetchall()]
        finally:
            conn.close()
        # عدّادات التشغيل (ترحيل 007) — سطح أدمِن حصراً: JSON مخزَّن يُفكّ هنا؛
        # التالف/الغائب = None معلَنة (لا اختلاق عدّادات).
        for r in rows:
            raw = r.pop("run_stats", None)
            try:
                r["run_stats"] = json.loads(raw) if raw else None
            except (TypeError, ValueError):
                r["run_stats"] = None
        return {"studies": rows}

    @app.post(_PREFIX + "/admin/diagnostics")   # R7 (AUTH-8): الواجهةُ تنادي POST
    @app.get(_PREFIX + "/admin/diagnostics")
    def admin_diagnostics(request: Request):
        """فحص المصادر الحية بنقرة أدمِن — تشخيص «التقرير الفارغ» (2026-08-17).

        يعيد `silk_diagnostics.run_diagnostics()` نفسه الذي تخدمه نقطة
        `/diagnostics` الجذرية (المسابير تنقّح الأسرار عبر `_redact` قبل أن
        تغادر): حالة كل مصدر + تلميح علاجي. حوكمة النقطة نفس عائلتها:
        - دور أدمِن حصراً (المسابير تصرف نداءً مدفوعاً واحداً صغيراً لو كان
          مفتاح كلود مضبوطاً — نقرة الأدمِن الصريحة هي الموافقة، كما في النقطة
          الجذرية).
        - مقيَّدة بعدّاد `throttle` القائم (نافذة الفشل نفسها تُستعمل عدّادَ
          نداءات): تجاوزُ السقف = 429 معلَنة، فلا تُستنزف المصادر بالتحديث
          المتكرر.
        """
        ctx = _require(request, Role.SILK_ADMIN)
        conn = _open()
        try:
            ident = f"diag|{ctx.user_id}"
            # §58 L4: حدود مسماة — كانت مستعارة من متغيّري الدخول فرفعُ
            # تسامح الدخول يوسّع صامتاً ميزانية مسابير قد تكون مدفوعة.
            limits = throttle.named_limits("DIAG", 10)
            if throttle.is_throttled(conn, ident, limits):
                raise HTTPException(status_code=429, detail={
                    "error": "diagnostics_throttled",
                    "message": "فحص المصادر مقيّد المعدل — انتظر دقائق ثم أعد"})
            throttle.record_failure(conn, ident, limits)  # عدّاد نداء، لا «فشل»
            conn.commit()
        finally:
            conn.close()
        # درس 189 (F10 المقابل، قرار مالك 2026-08-27): حجزٌ من السقف المدفوع
        # اليومي — التشخيص يُطلق مسابير مدفوعة حيّة بمفاتيح الخادم، ونظيرتُه في
        # المحرّك (api.py:3429) تحجز؛ هذه لم تكن فتُنفَق خارج دفتر السقف
        # (2880/يوم عبر خانق DIAG وحده). نفس عقد المحرّك: إعفاءٌ صريح بـ
        # SILK_DIAG_EXEMPT، وبلا سقفٍ مضبوط لا حجب.
        # درس 193: الاستيراد **قبل** الحجز — فشلُه (منصّة بلا محرّك = 503) كان
        # يستهلك وحدةً من السقف بلا أي مسبار (طلبٌ فاشل يخصم). الاستيراد رخيص
        # بلا نداءٍ مدفوع، فيسبق الحجز.
        try:
            import silk_diagnostics
        except Exception:  # noqa: BLE001 — منصّة بلا محرّك = فجوة معلنة
            raise HTTPException(status_code=503, detail={
                "error": "engine_unavailable",
                "message": "وحدات التشخيص غير متاحة من هذه الخدمة"})
        _diag_exempt = os.environ.get("SILK_DIAG_EXEMPT", "").strip().lower() in (
            "1", "true", "yes", "on")
        import silk_usage
        if (not _diag_exempt and silk_usage.daily_cap() is not None
                and not silk_usage.try_reserve_paid_calls(1)):
            raise HTTPException(status_code=429, detail={
                "error": "daily_paid_cap_exhausted",
                "message": "السقف المدفوع اليومي مُستنفَد — التشخيص يحجز منه "
                           "وحدة. اضبط SILK_DIAG_EXEMPT=1 لإعفائه أو ارفع "
                           "SILK_PAID_DAILY_CAP."})
        # §58 L4: المسابير **قبل** قيد التدقيق — كان القيد يُلتزم عن فحصٍ قد
        # لا يجري (فشل الاستيراد = 500 + قيد كاذب)؛ الغياب الآن فجوة معلنة.
        try:
            out = silk_diagnostics.run_diagnostics()
        except Exception:  # noqa: BLE001 — منصّة بلا محرّك = فجوة معلنة
            raise HTTPException(status_code=503, detail={
                "error": "engine_unavailable",
                "message": "وحدات التشخيص غير متاحة من هذه الخدمة"})
        conn = _open()
        try:
            audit.record(conn, action="diagnostics_run", user_id=ctx.user_id,
                         account_id=ctx.account_id, resource_type="platform",
                         changes={"overall": out.get("overall")})
            conn.commit()
        finally:
            conn.close()
        return out

    @app.post(_PREFIX + "/admin/accounts/{account_id}/tier")
    def admin_set_tier(account_id: int, request: Request,
                       body: dict = Body(default=None)):
        """غيّر طبقة حساب مصنع — audited; quota counters are untouched.

        (سقط رفضُ «التخفيض الذي يترك مقاعد زائدة» مع حذف المقاعد نهائياً —
        قرار المالك 2026-08-19: حسابٌ واحد لكل مصنع.)
        """
        ctx = _require(request, Role.SILK_ADMIN)
        body = _json_body(body)
        _require_fields(body, "tier")
        conn = _open()
        try:
            try:
                out = entitlements.set_account_tier(
                    conn, account_id, body.get("tier"), admin_user_id=ctx.user_id)
            except entitlements.TierChangeError as exc:
                code = {"account_not_found": 404,
                        "not_a_factory_account": 422,
                        "unknown_tier": 422,
                        }.get(exc.code, 422)
                raise HTTPException(status_code=code, detail=exc.as_detail())
        finally:
            conn.close()
        return out

    @app.post(_PREFIX + "/admin/accounts/{account_id}/quota")
    def admin_set_per_user_quota(account_id: int, request: Request,
                                 body: dict = Body(default=None)):
        """اضبط حصّة الدراسات لكل مستخدم في حساب مصنع — قرار مالك 2026-08-17.

        الجسم `{"per_user_monthly_studies": N}` حيث `null` يمسح التجاوز (يعود
        افتراض الطبقة)، و`0` بلا حدّ صراحةً، و`>=1` السقف الشهري لكل مستخدم.
        """
        ctx = _require(request, Role.SILK_ADMIN)
        body = _json_body(body)
        if "per_user_monthly_studies" not in body:
            raise _err(422, "invalid_quota",
                       "per_user_monthly_studies مطلوب: عددٌ صحيح ≥ 0 أو null للمسح")
        raw = body.get("per_user_monthly_studies")
        value = None if raw is None else _as_int(raw, "per_user_monthly_studies",
                                                 minimum=0)
        conn = _open()
        try:
            try:
                out = entitlements.set_per_user_quota(
                    conn, account_id, value, admin_user_id=ctx.user_id)
            except entitlements.TierChangeError as exc:
                code = {"account_not_found": 404,
                        "not_a_factory_account": 422,
                        "invalid_quota": 422}.get(exc.code, 422)
                raise HTTPException(status_code=code, detail=exc.as_detail())
        finally:
            conn.close()
        return out

    @app.post(_PREFIX + "/admin/accounts/{account_id}/reset-quota")
    def admin_reset_quota(account_id: int, request: Request):
        """صفّر حصّة حسابٍ الآن (F17، درس 192) — إعادةُ تعيينٍ إدارية تصفّر
        العدّاد المخزَّن للحساب **والعدّاد المشتقّ لكل مستخدم معاً** عبر علامةٍ
        مائية واحدة (مصدر حقيقةٍ واحد لنقطة الصفر). العدّاد مدى-الحياة (Basic)
        لا يُمَسّ."""
        ctx = _require(request, Role.SILK_ADMIN)
        conn = _open()
        try:
            # الحساب موجود؟ (404 صريح لا تصفيرٌ صامت لحسابٍ وهمي.)
            row = conn.execute("SELECT id, is_vault FROM accounts WHERE id = ?",
                               (account_id,)).fetchone()
            if row is None:
                raise _err(404, "not_found", "الحساب غير موجود")
            if int(row["is_vault"] or 0) == 1:
                # R7 (AUTH-21): الخزنةُ ليست مصنعاً — «تصفيرُ حصّتها» عمليةٌ بلا معنى
                # كانت تكتب قيدَ تدقيقٍ وعلامةً مائية على حساب سِلك نفسه.
                raise HTTPException(status_code=422, detail={
                    "error": "vault_quota_reset_refused",
                    "message": "حساب الخزنة لا حصّةَ له — التصفير للمصانع فقط"})
            out = quota.reset_account_quota(conn, account_id)
            audit.record(conn, action="admin_quota_reset", user_id=ctx.user_id,
                         account_id=account_id, resource_type="account")
            conn.commit()
        finally:
            conn.close()
        return out

    @app.post(_PREFIX + "/admin/tiers/{tier}")
    def admin_set_tier_settings(tier: str, request: Request,
                                body: dict = Body(default=None)):
        """اضبط سعر باقة وحصّتها الشهرية — قرار المالك 2026-08-20.

        الجسم `{"price": N, "price_annual": N, "monthly_studies": N}` — الثلاثة
        معاً فلا يبقى صفٌّ نصفَ محدَّث. الأعداد بعملة `config/pricing.yaml`
        (ر.س) لا بالسنتات: وحدتان لرقمٍ واحد تُنتجان انحرافاً ×١٠٠.

        **الحصّة ليست عرضاً:** `quota.reserve_launch` تقرأ نفس القيمة عبر
        `tier_config.effective_limits`، فالتغيير يسري فوراً على كل حسابات
        الباقة والعدّاد المستهلك لا يُصفَّر (نفس عقد `POST .../tier`).
        الأساسية محكومةٌ بسقف مدى الحياة، فحصّتها الشهرية لا يقرؤها أحد.
        """
        ctx = _require(request, Role.SILK_ADMIN)
        body = _json_body(body)
        for field in ("price", "price_annual", "monthly_studies"):
            if field not in body:
                raise _err(422, "invalid_tier_settings",
                           f"{field} مطلوب: عددٌ صحيح غير سالب", field=field)
        conn = _open()
        try:
            try:
                out = tier_config.set_tier(
                    conn, tier, price=body.get("price"),
                    price_annual=body.get("price_annual"),
                    monthly_studies=body.get("monthly_studies"),
                    actor_user_id=ctx.user_id)
            except tier_config.TierSettingsError as exc:
                raise HTTPException(status_code=422,
                                    detail={"error": "invalid_tier_settings",
                                            "field": exc.field,
                                            "message": str(exc)})
        finally:
            conn.close()
        return {"tier": str(tier).strip().lower(), **out}

    @app.post(_PREFIX + "/admin/users/{user_id}/reset")
    def admin_issue_reset(user_id: int, request: Request):
        """إعادة تعيين مساعدة من الأدمِن — PR-5 stopgap until email delivery lands.

        يُصدر رمزاً أحادي الاستخدام (٣٠ دقيقة) لمستخدم، يوصله الأدمِن للمستخدم
        عبر قناة دعم؛ ثم يُستهلَك بنقطة confirm العادية. مدقَّق (من أعاد تعيين مَن).
        Admin-only, audit-logged; the raw token goes to the authenticated admin.
        """
        ctx = _require(request, Role.SILK_ADMIN)
        conn = _open()
        try:
            # ميّز «غيرُ موجود» عن «معطّل» للأدمِن المُصادَق: ٤٠٤ لمستخدمٍ لا
            # وجودَ له، ٤٠٩ لمستخدمٍ موجودٍ لكنّه (أو حسابُه) موقوف. دمجُهما في
            # ٤٠٤ واحدٍ يجعل التشخيصَ عن بُعد مستحيلاً بلا أن يحمي شيئاً —
            # المُنادي مخوَّلٌ أصلاً. Distinguish absent from suspended.
            state = auth.user_reset_state(conn, user_id)
            if state == auth.RESET_MISSING:
                raise _err(404, "not_found", "المستخدم غير موجود")
            if state == auth.RESET_INACTIVE:
                # خطأٌ مهيكل ثنائيّ اللغة كبقيّة نقاط المنصّة: `error` رمزٌ
                # تتفرّع عليه الواجهة، و`message` عربيٌّ احتياطاً. ولا تَعِد
                # الرسالةُ بإعادة تفعيلٍ لا وجودَ لنقطتها بعد.
                raise HTTPException(
                    status_code=409,
                    detail={"error": "user_deactivated",
                            "message": "المستخدم أو حسابه معطّل — لا يُصدَر له "
                                       "رمزُ إعادة تعيين",
                            "en": "user or account is deactivated"})
            raw = auth.issue_reset_token_for_user(conn, user_id)
            if raw is None:
                # الحالةُ قِيست قبل سطرين، فـ`None` هنا تعني تعطيلاً تزامن مع
                # الطلب — لا «مستخدماً غير موجود». قُل ما حدث فعلاً.
                raise HTTPException(
                    status_code=409,
                    detail={"error": "user_deactivated_concurrently",
                            "message": "تغيّرت حالةُ المستخدم أثناء الطلب — "
                                       "أعِد المحاولة",
                            "en": "user state changed during the request"})
            _target = conn.execute(
                "SELECT email, language_preference FROM users WHERE id = ?",
                (user_id,)).fetchone()
            audit.record(conn, action="admin_password_reset_issued",
                         user_id=ctx.user_id, account_id=ctx.account_id,
                         resource_type="user", resource_id=user_id,
                         ip_address=_client_ip(request))
            conn.commit()
        finally:
            conn.close()
        # R7 (AUTH-7): مع SMTP تشغيليّ يُرسَل الرمزُ إلى بريد المستخدم — لا يمرّ
        # بالأدمِن ولا بقناة دعمٍ خارجية؛ بلا SMTP يبقى المسارُ القديم معلَناً.
        if _target is not None and smtp_transport.operator_config_from_env() is not None:
            # متزامنٌ هنا (الأدمِن مُصادَق — لا قناةَ توقيت): فشلُ الإرسال يُعاد صدقاً مع
            # الرمز، لا `delivered: email` كاذبة ورمزٌ يضيع (مراجعة R7).
            err = _send_password_reset_email(str(_target["email"]),
                                             str(_target["language_preference"] or "ar"),
                                             raw, sync=True)
            if err is None:
                return {"ok": True, "user_id": user_id, "delivered": "email",
                        "note": "single-use, 30-min expiry; sent to the user's email"}
            return {"ok": True, "user_id": user_id, "delivered": "response",
                    "reset_token": raw, "email_error": err,
                    "note": "email delivery failed — convey the token via support"}
        return {"ok": True, "user_id": user_id, "delivered": "response",
                "reset_token": raw,
                "note": "single-use, 30-min expiry; convey to the user via support "
                        "(no operator SMTP configured)"}

    # ══════════════════════════ ANALYST ═════════════════════════════════════
    @app.post(_PREFIX + "/admin/users/{user_id}/unlock-login")
    def admin_unlock_login(user_id: int, request: Request):
        """فكُّ قفل عدّاد الدخول بالبريد (مراجعة R7): ٣٠ فشلاً من أيّ مكان تقفل الحسابَ
        ١٥ دقيقة — مقصودٌ ضدّ التخمين الموزَّع، لكنّ المهاجمَ يستطيع تجديدَه؛ الأدمِن يفكّه
        صراحةً (والمستخدمُ بإعادة تعيينٍ ناجحة). مدقَّق."""
        ctx = _require(request, Role.SILK_ADMIN)
        conn = _open()
        try:
            row = conn.execute("SELECT email FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise _err(404, "not_found", "المستخدم غير موجود")
            throttle.clear(conn, throttle.login_email_identity(str(row["email"])))
            audit.record(conn, action="admin_login_unlocked", user_id=ctx.user_id,
                         account_id=ctx.account_id, resource_type="user",
                         resource_id=user_id, ip_address=_client_ip(request))
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "user_id": user_id}

    @app.post(_PREFIX + "/admin/users/{user_id}/deactivate")
    def admin_deactivate_user(user_id: int, request: Request):
        """عطِّل مستخدم مصنع — السطحُ الوحيد الباقي بعد حذف المستخدمين الفرعيين.

        بلا هذه النقطة: حسابٌ أُنشئ له مستخدمٌ فرعيّ **قبل** الحذف يظلّ قادراً
        على الدخول وإطلاق الدراسات إلى الأبد، ولا للمصنع ولا للأدمِن مسارٌ
        لإيقافه (ملاحظة مراجعة ذاتية §58 على موجة الحذف). التعطيل لا الحذف:
        مراجعُ التدقيق والدفتر تبقى سليمة. جلساتُه تُنهى في المعاملة نفسها.
        Deactivation, not deletion — audit and ledger references stay intact.
        """
        ctx = _require(request, Role.SILK_ADMIN)
        conn = _open()
        try:
            row = conn.execute(
                "SELECT id, account_id, role, is_active FROM users WHERE id = ?",
                (user_id,)).fetchone()
            if row is None:
                raise _err(404, "not_found", "غير موجود")
            if row["role"] != Role.FACTORY.value:
                # حسابات سِلك تُدار خارج هذا المسار — لا يُعطِّل أدمِنٌ زميلَه
                # (ولا نفسَه) بنقطةٍ وُجدت لبقايا المستخدمين الفرعيين.
                raise HTTPException(status_code=422, detail={
                    "error": "not_a_factory_user",
                    "message": "هذه النقطة لمستخدمي المصانع فقط"})
            conn.execute("UPDATE users SET is_active = 0, updated_at = ? "
                         "WHERE id = ?", (auth.now_iso(), user_id))
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            audit.record(conn, action="admin_user_deactivated",
                         user_id=ctx.user_id, account_id=int(row["account_id"]),
                         resource_type="user", resource_id=user_id,
                         ip_address=_client_ip(request))
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "user_id": user_id, "is_active": False}

    # ══════════════════════════ ANALYST ═════════════════════════════════════
    @app.get(_PREFIX + "/analyst/aggregates")
    def analyst_aggregates(request: Request):
        # مجمّعات مجهّلة للقراءة فقط — no account-level data, no PII.
        ctx = _require(request, Role.SILK_ANALYST, Role.SILK_ADMIN)
        conn = _open()
        try:
            tiers = {r["tier"]: r["c"] for r in conn.execute(
                "SELECT tier, COUNT(*) AS c FROM accounts WHERE is_vault = 0 "
                "GROUP BY tier").fetchall()}
            studies_by_state = {r["state"]: r["c"] for r in conn.execute(
                "SELECT state, COUNT(*) AS c FROM studies GROUP BY state").fetchall()}
            # R7 (AUTH-22): أسماءُ منتجات المصانع بياناتُ أعمالٍ لمستأجرين — المحلّلُ
            # يرى **فصولَ HS** (رقمان) لا أسماء (كان `top_products` يسرّب المنتجَ
            # حرفياً). بلا معرّفات ولا PII.
            top_hs = [{"chapter": str(r["chapter"]), "studies": int(r["c"])}
                      for r in conn.execute(
                          "SELECT substr(hs_code, 1, 2) AS chapter, COUNT(*) AS c "
                          "FROM studies WHERE hs_code IS NOT NULL AND length(hs_code) >= 2 "
                          "GROUP BY chapter ORDER BY c DESC, chapter LIMIT 10").fetchall()]
            out = {"tier_adoption": tiers, "studies_by_state": studies_by_state,
                   "top_hs_chapters": top_hs}
        finally:
            conn.close()
        return out

    from . import export_opportunities
    export_opportunities.mount(app, _open, _require, _study_research_fields)

    # تأسيس الحسابات — opt-in بـSILK_SEED_ADMIN_PASSWORD. بلا هذا تُقلِع القاعدة
    # بجداولَ سليمة و**صفر مستخدمين**، فترفض شاشة الدخول كل شيء برسالة «بيانات
    # غير صحيحة» لا تُميَّز عن كلمة مرور خاطئة (بلاغ مالك حيّ: «ما يعمل»).
    # لا يُسقِط الإقلاع أبداً، ولا يطبع كلمة مرور.
    # Opt-in bootstrap: tables without users made login impossible to diagnose.
    try:
        _bconn = _open()
        try:
            bootstrap.maybe_seed(_bconn)
        finally:
            _bconn.close()
    except Exception:  # noqa: BLE001 — التأسيس أفضل جهد؛ الخدمة تُقلِع بلا شكّ
        log.warning("silk_platform: bootstrap step failed", exc_info=True)

    # كنس أيتام إعادة النشر — خيوط الجسر تموت مع العملية (نفس عائلة «التعافي
    # صريح لا ذاتي» في /research): دراسة `in_progress` بلا خيط حيّ تُحسَم عند
    # الإقلاع (اكتملت قبل الموت ⇒ completed؛ وإلا ⇒ draft بسبب معلن + إرجاع
    # الحصّة). لا يُسقِط التركيب أبداً.
    try:
        _sconn = _open()
        try:
            swept = engine_bridge.sweep_orphans(_sconn)
            if swept.get("completed") or swept.get("reverted"):
                log.info("silk_platform: orphan sweep %s", swept)
        finally:
            _sconn.close()
    except Exception:  # noqa: BLE001
        log.warning("silk_platform: orphan sweep failed", exc_info=True)

    # مجدول المهام — opt-in بـSILK_PLATFORM_SCHEDULER=1؛ بلا الضبط لا خيط أصلاً،
    # فتشغيلة اختبار أو تطوير لا تصفّر حصّة ولا تكتب فاتورة. يُبدأ بعد نجاح
    # التركيب كي لا يبقى خيطٌ يعمل لتطبيق لم يُركَّب.
    # Started only after a successful mount; no thread unless explicitly enabled.
    scheduler.start()
    # كنسُ الأيتام الدوري — مشغَّل افتراضياً (يُطفأ بـSILK_PLATFORM_ORPHAN_SWEEP=0):
    # لا يكتب فاتورة ولا يصفّر حصّة، فليس له سببٌ ليبقى خلف صمّامٍ مطفأ بينما
    # يتيمُ إعادة النشر يعلق «قيد الإعداد» للأبد.
    scheduler.start_orphan_sweeper()
    # R2 (RC-1): مُشرِف التشغيلات الدائمة — تعافٍ عند الإقلاع (قاطِع ما انقطعت
    # نبضتُه، ابدأ المنتظِر)، خيطُ نبضةٍ/كنسٍ/مطالبة، وختمُ إغلاقٍ يوسم تشغيلات
    # هذه العملية `interrupted` قبل أن تموت خيوطُها معها. حدثُ الإغلاق يُسجَّل
    # على التطبيق نفسه فيصل التطبيقَ الجذري (`api:app`) وتطبيقَ المنصّة المستقلّ.
    try:
        _rout = study_runtime.recover()
        if _rout.get("interrupted") or _rout.get("dispatched"):
            log.info("silk_platform: study runtime recovery %s", _rout)
    except Exception:  # noqa: BLE001 — التعافي تحسينُ إقلاع، لا يُسقِط التركيب
        log.warning("silk_platform: study runtime recovery failed", exc_info=True)
    study_runtime.start()
    # تدقيق الفرق النهائي (2026-09-02): Starlette ≥1.0 حذفت `add_event_handler`
    # من `Starlette`/`FastAPI` (أُبقيت على `APIRouter` وحدها) — والمكدّس الذي
    # يحلّه `pip install -r requirements.txt -r requirements-ci.txt` (CI
    # وDockerfile) يحمل Starlette 1.6.0 اليوم إذ `requirements.txt` لا يثبّت
    # Starlette. `app.router.add_event_handler` يعمل على الإصدارين معاً.
    app.router.add_event_handler("shutdown", study_runtime.shutdown)
    return True

