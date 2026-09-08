"""أدوات اختبار المنصّة — shared helpers for silk_platform tests (not collected).

كل اختبار يحصل على قاعدة منصّة معزولة (SILK_PLATFORM_DB في مجلّد مؤقّت) +
بيانات مبذورة + TestClient. لا شبكة، لا مفاتيح. Hermetic; no network, no keys.
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile


# ── تنظيفُ المجلّدات المؤقّتة · temp-dir cleanup ────────────────────────────
#
# تدقيق 2026-08-30: كل اختبار منصّة كان يخلّف مجلّداً مؤقّتاً إلى الأبد — بلغت
# التركةُ ٢٠٩٬٦٤٨ مجلّداً على آلة التطوير. وعند ذلك الحجم يتباطأ إنشاءُ الملفات
# على ويندوز حتى تتعثّر اختباراتٌ لا علاقة لها بما تقيسه: رُصِد تعليقٌ داخل
# `apply_migrations` على قاعدةٍ **جديدة تماماً**، بخيطٍ واحد وبلا مالكِ قفل،
# ثم نجحت الشيفرةُ نفسُها في الإعادة. عطلُ بيئةٍ يقرأ كأنه انحدارُ شيفرة.
#
# التنظيفُ عند **خروج العملية** لا في تفكيك كل اختبار: أثناء الاختبار قد تبقى
# اتصالاتُ SQLite مفتوحةً فيرفض ويندوز حذفَ الملفّ، فيتحوّل التنظيفُ إلى فشلٍ
# كاذب. عند الخروج تكون كلُّها مغلقة، و`ignore_errors` يبتلع أيَّ شاردة.
# النموّ يبقى محدوداً بتشغيلةٍ واحدة بدل أن يتراكم عبر الشهور.
_TMPDIRS: list[str] = []


def _tmpdir() -> str:
    """مجلّدٌ مؤقّت يُنظَّف عند خروج العملية — بديلُ `mkdtemp` المتسرّب."""
    d = tempfile.mkdtemp(prefix="silk-plat-")
    _TMPDIRS.append(d)
    return d


@atexit.register
def _sweep_tmpdirs() -> None:
    for d in _TMPDIRS:
        shutil.rmtree(d, ignore_errors=True)


def setup_env(monkeypatch) -> str:
    """قاعدة منصّة معزولة لكل اختبار — isolated platform DB; returns its path.

    يعزل أيضاً جذر تخزين الملفات (PR-8) في نفس المجلّد المؤقّت — بلا هذا كان
    رفع صورة في الاختبارات يكتب فعلياً داخل `data/` الحقيقي للريبو.
    Also isolates the file-storage root in the same temp dir — otherwise an
    uploaded-image test would write real files into the repo's actual data/.
    """
    # **التنظيف** (تدقيق 2026-08-30): كل اختبار منصّة كان يخلّف مجلّداً مؤقّتاً
    # إلى الأبد — بلغت التركةُ ١٧٨٬٣٤٧ مجلّداً على آلة التطوير، وعند ذلك الحجم
    # يتباطأ إنشاءُ الملفات على ويندوز حتى تتعثّر اختباراتٌ لا علاقة لها بما
    # تقيسه (رُصِد: تعليقٌ داخل `apply_migrations` على قاعدةٍ **جديدة تماماً**،
    # ثم نجاحُ نفسِ الشيفرة في الإعادة). التنظيف يُسجَّل على `monkeypatch` فيقع
    # في التفكيك بعد آخر إغلاقِ اتصال، و`ignore_errors` يمنعه من تحويل قفلِ
    # ملفٍّ عابر إلى فشلِ اختبار.
    d = _tmpdir()
    path = os.path.join(d, "platform.db")
    monkeypatch.setenv("SILK_PLATFORM_DB", path)
    monkeypatch.setenv("SILK_PLATFORM_SECRET", "fixed-test-secret-do-not-use-in-prod")
    monkeypatch.setenv("SILK_PLATFORM_STORAGE_DIR", os.path.join(d, "files"))
    # التحوّل (جسر المحرّك): إطلاق دراسةٍ في اختبارٍ نسي محاكاة `_run_engine`
    # يصل `silk_engine.analyze(persist=True)` — فيكتب `data/silk.db` الحقيقية
    # في شجرة الريبو. عزل قاعدة المحرّك هنا حزامُ أمانٍ بنيوي لكل اختبار منصّة.
    # Belt-and-braces: an unmocked bridge run persists to tmp, never the repo.
    monkeypatch.setenv("SILK_DB", os.path.join(d, "engine.db"))
    # الوضع السريع افتراضُ العُدّة المشتركة (قرار 2026-08-18): هذه الاختبارات
    # تُثبت آليات الجسر/الحصص/الدورة — وهي واحدة في الوضعين — بينما إنتاجياً
    # الافتراضي `deep` (بوابة جهوزية تتطلب تسجيل `silk_research_gateway` الذي
    # لا يحدث في تطبيق منصّةٍ معزول). اختبارات العمق الصريحة تضبط `deep`
    # وتسجّل مغلقة وهمية بنفسها (`tests/test_platform_deep_mode.py`).
    monkeypatch.setenv("SILK_PLATFORM_STUDY_MODE", "quick")
    from silk_platform import db as pdb
    pdb.init_db(path, force=True)
    return path


def seed(monkeypatch) -> dict:
    """هيّئ + ابذر — set up an isolated DB and seed the standard fixture."""
    setup_env(monkeypatch)
    from silk_platform import db as pdb, seed as pseed
    conn = pdb.connect()
    try:
        info = pseed.seed(conn)
    finally:
        conn.close()
    return info


def client():
    """TestClient على تطبيق منصّة جديد — a TestClient over a fresh platform app."""
    from fastapi.testclient import TestClient
    from silk_platform.api import create_platform_app
    return TestClient(create_platform_app())


def login(cl, email: str, password: str) -> str:
    """سجّل الدخول وأعِد الرمز — POST /platform/auth/login → raw token."""
    r = cl.post("/platform/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def hdr(token: str) -> dict:
    """ترويسة المصادقة — Authorization: Bearer header."""
    return {"Authorization": f"Bearer {token}"}


def make_factory(tier: str, email: str, password: str = "Factory1234",
                 *, fund_cents: int = 0):
    """أنشئ حساب مصنع + مستخدم (+ تمويل) — a factory account/user with a wallet.

    مباشرةً في القاعدة (أسرع وأدقّ من مسار الأدمِن للحالات الحديّة). يرجّع dict.
    """
    from silk_platform import db as pdb, passwords, wallet
    from silk_platform.db import now_iso
    from silk_platform.models import Operation
    conn = pdb.connect()
    try:
        now = now_iso()
        cur = conn.execute(
            "INSERT INTO accounts (name, kind, is_vault, tier, created_at, "
            "updated_at) VALUES (?, 'factory', 0, ?, ?, ?)",
            (f"Factory-{tier}", tier, now, now))
        aid = int(cur.lastrowid)
        cur = conn.execute(
            "INSERT INTO users (account_id, email, password_hash, role, "
            "first_name, last_name, language_preference, created_at, updated_at) "
            "VALUES (?,?,?, 'factory', 'F', 'Owner', 'ar', ?, ?)",
            (aid, email.lower(), passwords.hash_password(password), now, now))
        uid = int(cur.lastrowid)
        wallet.ensure_wallet(conn, aid)
        conn.commit()
        if fund_cents:
            # التمويل يمرّ بالدفتر لا بكتابة رصيد خام: التثبيت نفسه يجب أن يُنمذج
            # المسار المسموح، وإلا نُطبِّع الانحراف الذي وُجد الدفتر غير القابل
            # للتعديل لمنعه (رصيد بلا قيد = لا مُكتشِف له).
            # Fund through the ledger — never raw-UPDATE a balance, even in tests.
            wallet.post_entry(conn, account_id=aid, actor_user_id=uid,
                              operation=Operation.WALLET_FUNDED, amount=fund_cents,
                              description="test fixture funding")
    finally:
        conn.close()
    return {"account_id": aid, "user_id": uid, "email": email, "password": password,
            "tier": tier}


def make_product_study(account_id: int, user_id: int,
                       product: str = "تمور سكري",
                       state: str = "draft") -> int:
    """دراسة سوق مسودّة بمنتج — a draft market-study row; returns its id.

    بديل `make_draft_study` المحذوف مع التنقيب (قرار مالك 2026-08-17): الدراسة
    طلبُ دراسة سوق (منتج) لا حملة بريدية — بلا SMTP ولا مسودّة رسالة.
    """
    from silk_platform import db as pdb
    from silk_platform.db import now_iso
    conn = pdb.connect()
    try:
        now = now_iso()
        cur = conn.execute(
            "INSERT INTO studies (owner_id, product, title_ar, state, "
            "created_by_user_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (account_id, product, product, state, user_id, now, now))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def mock_engine(monkeypatch, analysis_id: int = 777, classified: bool = True):
    """حاكِ محرّك الجسر — أي إطلاق عبر API يكتمل فوراً بلا شبكة ولا محرّك حقيقي.

    يرجّع وحدة الجسر كي ينتظر الاختبار خمود خيوطها بـ`wait_idle`.
    """
    import silk_platform.engine_bridge as eb
    monkeypatch.setattr(
        eb, "_run_engine",
        lambda product, hs_code, market_pref, *_a, **_k: {
            "product": product, "hs_code": hs_code, "classified": classified,
            # سوق جوهري واحد (واقعية المحاكاة — §58): حارس «المكتملة الفارغة»
            # في الجسر يعيد نتيجة بلا أي نقطة بيانات إلى مسودّة، فمحاكاة
            # بأسواق فارغة كانت ستناقض مسار الإنتاج الذي تدّعي تمثيله.
            "markets": [{"country": "الإمارات", "iso3": "ARE",
                         "total_score": 0.5, "confidence": 0.4,
                         "components": {}}],
            "analysis_id": analysis_id, "note": "mocked"})
    return eb
