"""بيانات البذر — seed data: 1 vault/Silk account, 1 admin, 1 analyst, 2 factories.

قابلة لإعادة النداء (idempotent): إن وُجد الأدمِن لا تُعاد الكتابة. كلمات المرور
تُضبَط بالبيئة (SILK_SEED_*_PASSWORD)، وإلا تُولَّد عشوائياً لكل تشغيل وتُعاد في
نتيجة البذر — لا كلمة مرور افتراضية ثابتة في الشيفرة.
Passwords come from env, else are randomly generated per run and returned once.
"""
from __future__ import annotations

import os
import secrets
import sqlite3

from . import passwords, wallet
from .db import connect, init_db, now_iso
from .models import Operation

# رأس مال الخزنة الافتتاحي · vault opening capitalization ($1,000,000).
VAULT_OPENING_CENTS = 100_000_000

_EMAILS = {
    "admin": "admin@silk.local",
    "analyst": "analyst@silk.local",
    "factory_a": "owner@factory-a.local",
    "factory_b": "owner@factory-b.local",
}

# كلمات المرور المولَّدة لهذا التشغيل — تُولَّد مرّة وتُعاد في نتيجة البذر.
_GENERATED: dict[str, str] = {}


def _pw(kind: str) -> str:
    """كلمة مرور البذر — env override, else a per-run RANDOM password.

    لا كلمات مرور افتراضية ثابتة بعد الآن: نصّ مثل «Admin1234» في ريبو عام كان
    يعني أن أي نشر يُبذَر بلا ضبط البيئة يمنح `silk_admin` لأوّل من يجرّبها،
    وتسجيل الدخول غير محدود المحاولات. المولَّدة تُطبَع في نتيجة البذر مرّة
    واحدة (لا تُخزَّن نصّاً في القاعدة). No shipped default passwords.
    """
    explicit = os.environ.get(f"SILK_SEED_{kind.upper()}_PASSWORD", "").strip()
    if explicit:
        return explicit
    if kind not in _GENERATED:
        # مطابقة للسياسة حتماً (حالتان + رقم) مع إنتروبيا كافية.
        _GENERATED[kind] = "Aa1" + secrets.token_urlsafe(18)
    return _GENERATED[kind]


def _account(conn: sqlite3.Connection, *, name: str, kind: str,
             is_vault: int, tier: str) -> int:
    now = now_iso()
    cur = conn.execute(
        "INSERT INTO accounts (name, kind, is_vault, tier, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)", (name, kind, is_vault, tier, now, now))
    aid = int(cur.lastrowid)
    wallet.ensure_wallet(conn, aid)
    return aid


def _user(conn: sqlite3.Connection, *, account_id: int, email: str, pw_hash: str,
          role: str, first: str, last: str, lang: str = "ar") -> int:
    """أدخل مستخدماً بهاش مُحضَّر سلفاً — insert with an ALREADY-hashed password.

    التجزئة (وفرض السياسة) تحدث قبل أي كتابة في `seed()`، فلا يبقى صفٌّ ملتزَم
    خلف استثناء سياسة. Hashing happens before any write — see seed().
    """
    now = now_iso()
    cur = conn.execute(
        "INSERT INTO users (account_id, email, password_hash, role, first_name, "
        "last_name, language_preference, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (account_id, email.lower(), pw_hash, role, first, last, lang, now, now))
    return int(cur.lastrowid)


def _prod_signal() -> bool:
    """إشارةُ إنتاج — نفسُ تعريف `silk_platform.api.boot_config_guard`."""
    return (os.environ.get("SILK_PLATFORM_REQUIRE_SECRET") == "1"
            or os.environ.get("SILK_PLATFORM_SECURE_COOKIES") == "1")


def _demo_wanted(demo_factories: "bool | None") -> bool:
    """هل نزرع مصنعَي العرض ورأسَ المال الافتتاحيّ؟ — P3 (BIZ-12، تدقيق 2026-09-01):
    كان البذرُ يزرع «Factory A/B» و**مليونَ دولارٍ خيالياً** في دفتر الخزنة على أيّ
    قاعدة تُبذَر، فيقرأ المالكُ رصيداً لا وجودَ له ويرى مستأجرَين ليسا عملاءه. تحت أيّ
    إشارةِ إنتاج لا يُزرَع شيءٌ من ذلك إلا بطلبٍ صريح (`SILK_SEED_DEMO_FACTORIES=1`)."""
    if demo_factories is not None:
        return bool(demo_factories)
    if os.environ.get("SILK_SEED_DEMO_FACTORIES", "").strip() in ("1", "true", "yes", "on"):
        return True
    return not _prod_signal()


def seed(conn: sqlite3.Connection, *, reset: bool = False,
         demo_factories: "bool | None" = None) -> dict:
    """ابذر البيانات — create the standard fixture; returns created identities.

    idempotent: يتخطّى إن وُجد أدمِن (ما لم يُطلب reset). يرجّع القواميس مع
    كلمات المرور المستخدَمة كي يطبعها سكربت البذر (لا تُخزَّن نصّاً في القاعدة).
    """
    existing = conn.execute(
        "SELECT id FROM users WHERE role = 'silk_admin' LIMIT 1").fetchone()
    if existing and not reset:
        return {"seeded": False, "reason": "already seeded"}

    # جزّئ **كل** كلمات المرور أولاً (تفرض السياسة وقد ترفع PasswordError) قبل
    # أيّ كتابة. بلا هذا كان استثناءُ سياسةٍ يترك حساب الخزنة ملتزَماً بلا
    # `silk_admin`، فيفشل كل بذر تالٍ أبداً على فهرس `ux_accounts_vault` الفريد
    # — قاعدة لا تُبذَر إلا بجراحة يدوية. Hash (and validate) before any write.
    pw_hashes = {kind: passwords.hash_password(_pw(kind))
                 for kind in ("admin", "analyst", "factory_a", "factory_b")}

    # 1) حساب سِلك = الخزنة · Silk operator account is the vault.
    vault_id = _account(conn, name="Silk (operator/vault)", kind="silk",
                        is_vault=1, tier="platinum")
    admin_id = _user(conn, account_id=vault_id, email=_EMAILS["admin"],
                     pw_hash=pw_hashes["admin"], role="silk_admin",
                     first="Silk", last="Admin", lang="ar")
    analyst_id = _user(conn, account_id=vault_id, email=_EMAILS["analyst"],
                       pw_hash=pw_hashes["analyst"], role="silk_analyst",
                       first="Silk", last="Analyst")
    _demo = _demo_wanted(demo_factories)
    fa_id = fa_user = fb_id = fb_user = None
    if _demo:
        # رأس المال الافتتاحي للخزنة · vault opening capitalization (consistent ledger).
        # BIZ-12: رقمٌ **افتراضيّ** — لا يُقيَّد على نشرٍ حقيقيّ (رصيدٌ لا وجود له).
        wallet.post_entry(conn, account_id=vault_id, actor_user_id=admin_id,
                          operation=Operation.WALLET_FUNDED,
                          amount=VAULT_OPENING_CENTS, description="vault opening balance",
                          metadata={"opening": True})
        # 2) حسابا مصنع · two factory accounts (Silver + Gold) with owners.
        fa_id = _account(conn, name="Factory A", kind="factory", is_vault=0, tier="silver")
        fa_user = _user(conn, account_id=fa_id, email=_EMAILS["factory_a"],
                        pw_hash=pw_hashes["factory_a"], role="factory",
                        first="Factory", last="A-Owner")
        fb_id = _account(conn, name="Factory B", kind="factory", is_vault=0, tier="gold")
        fb_user = _user(conn, account_id=fb_id, email=_EMAILS["factory_b"],
                        pw_hash=pw_hashes["factory_b"], role="factory",
                        first="Factory", last="B-Owner", lang="ar")
    conn.commit()

    out = {
        "seeded": True,
        "vault_account_id": vault_id,
        "demo_factories": _demo,
        "admin": {"id": admin_id, "email": _EMAILS["admin"],
                  "password": _pw("admin")},
        "analyst": {"id": analyst_id, "email": _EMAILS["analyst"],
                    "password": _pw("analyst")},
    }
    if _demo:
        # BIZ-12: المفتاحان يظهران **حين يُنشآن فقط**. مفتاحٌ يحمل بريداً وكلمةَ مرور
        # لحسابٍ غير موجود هويّةٌ مختلَقة: من يقرؤه يظنّه صالحاً ويكتشف الكذبةَ عند
        # محاولةِ دخولٍ تفشل بلا سبب. الغيابُ يُسقِط القارئَ فوراً وبوضوح.
        out["factory_a"] = {"account_id": fa_id, "user_id": fa_user,
                            "email": _EMAILS["factory_a"], "password": _pw("factory_a"),
                            "tier": "silver"}
        out["factory_b"] = {"account_id": fb_id, "user_id": fb_user,
                            "email": _EMAILS["factory_b"], "password": _pw("factory_b"),
                            "tier": "gold"}
    return out


def vault_account_id(conn: sqlite3.Connection) -> int | None:
    """معرّف حساب الخزنة — the single vault account id (or None if unseeded)."""
    row = conn.execute("SELECT id FROM accounts WHERE is_vault = 1 LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def main() -> None:  # pragma: no cover — سكربت CLI للبذر
    """python3 -m silk_platform.seed — initialize + seed the platform DB."""
    init_db()
    conn = connect()
    try:
        result = seed(conn)
    finally:
        conn.close()
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
