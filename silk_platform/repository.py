"""طبقة العزل بين المستأجرين — the tenant-scoping data layer.

القلب الأمني: **كل** عملية على كيان مُستأجَر تمرّ من هنا وتُقيَّد بعمود المالك
(`owner_id`/`account_id`). قراءة بمعرّف لحساب آخر تُعيد None (فتترجمها النقطة
النهائية إلى 404 لا 403 — لا تُسرَّب معلومة الوجود)، والكتابة/الحذف عبر
المستأجر لا يمسّان صفّاً واحداً. لا استعلام مُستأجَر يُكتب خارج هذه الطبقة.

Every tenant-scoped read/write is filtered by the owner column here. A get for
another account's row returns None; a cross-tenant update/delete touches zero
rows. The DB is the enforcement point — never the UI.
"""
from __future__ import annotations

import sqlite3

import re

from .db import now_iso
from .engine_bridge import strip_cost_keys

# شكل `ORDER BY` المقبول: أعمدة معرّفة الشكل مع ASC/DESC اختياريتين، مفصولة
# بفواصل — ولا شيء غيرها (لا أقواس، لا استدعاء دالة، لا فاصلة منقوطة، لا
# تعليق). كل نداءات هذه الطبقة اليوم ثوابت حرفية، فالفحص لا يغيّر سلوكاً؛
# قيمته أنه يحوّل «آمنٌ لأن أحداً لم يمرّر مدخلاً بعد» إلى «آمنٌ بنيوياً».
# ORDER BY allowlist: identifier[.identifier] [ASC|DESC], comma-separated.
_ORDER_RE = re.compile(
    r"^\s*[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?"
    r"(\s+(ASC|DESC))?\s*(,\s*[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?"
    r"(\s+(ASC|DESC))?\s*)*$", re.I)


def _safe_order(order: str) -> str:
    """تحقّق من جملة الترتيب قبل إقحامها — raises on anything but plain columns."""
    o = str(order or "id DESC")
    if not _ORDER_RE.match(o):
        raise ValueError(
            f"unsafe ORDER BY clause rejected: {o!r} — only plain column names "
            "with optional ASC/DESC are allowed (never request-derived input)")
    return o

# الأعمدة المسموح الكتابة عليها لكل جدول (allowlist) — يمنع حقن owner_id أو
# أعمدة النظام عبر جسم الطلب. Per-table writable-column allowlist.
_WRITABLE: dict[str, set[str]] = {
    # حقول الدراسة كطلب دراسة سوق (التحوّل — قرار مالك 2026-08-17): المنتج
    # والسوق والرمز والصورة قابلة للكتابة عبر CRUD؛ أعمدة التشغيل
    # (analysis_id/run_*) **نظامية عمداً** — يكتبها جسر المحرّك حصراً، نفس
    # قاعدة `state` (آلة حالات لا تُكتَب بـCRUD عام).
    # جداول التنقيب (prospects/drafts/smtp_configs/comparison_funnels) حُذفت
    # قوائمُها مع شيفرتها نهائياً (قرار مالك 2026-08-17) — جداولها اليتيمة
    # باقية في المخطّط ببياناتها (قانون «لا حذف بيانات») بلا أي مسار كتابة.
    # R6 (FE-8): `title_en`/`description_en`/`target_count` حقولٌ ميتة — الأعمدةُ باقية
    # (لا حذف) لكنّ لا مسارَ كتابةٍ يبلغها.
    "studies": {"title_ar", "description_ar", "created_by_user_id",
                "product", "market_pref", "hs_code", "image_id", "hs_source",
                # ربط الدراسة بمنتج الكتالوج (ترحيل 010) — النقطة النهائية
                # تتحقق أن المنتج لحساب الجلسة قبل القبول.
                "product_id",
                # تكلفة إنتاج وحدة السوق (هدف الدراسة الاحترافية البند ٢،
                # ترحيل 015) — تتحقق منها النقطة النهائية (رقم موجب أو NULL).
                "production_cost"},
    "images": {"filename", "storage_key", "mime_type", "size_bytes",
               "uploaded_by_user_id", "alt_text_en", "alt_text_ar"},
    # كتالوج المنتجات (قرار المالك 2026-08-18، ترحيل 010).
    # الموجة C (E-04): الحقولُ الاقتصادية تملأ بطاقةَ المنتج للمحرّك.
    # `None` مسموحةٌ في `update` (محوٌ صريح) وتُسقَط في `create` (افتراضُ العمود).
    "products": {"name", "description", "hs_code", "image_id",
                 "cost_per_unit", "cost_unit", "tier", "monthly_capacity",
                 "shipping_per_unit", "certifications",
                 # تقرير ٧ §3.5 (الترحيل ٠٢٥): مدخلا الهامش والتعادل التشغيليّ.
                 "fixed_costs", "cost_currency",
                 # مصدرُ الرمز وتاريخُه (الترحيل ٠١٧) — بلا هذين كان `update`
                 # يُسقطهما صامتَين فيبقى الصفّ على `hs_source='unknown'`.
                 "hs_source", "hs_set_at"},
}

# جداول بلا عمود `updated_at` — الطابع الزمني عندها هو عمود الإنشاء وحده.
# Tables whose only timestamp is their creation column (no updated_at).
_NO_UPDATED_AT = {"images"}

# R5 (تدقيق 2026-09-01، DB-13): قيودُ CHECK لا تُضاف إضافياً على SQLite (لا
# `ALTER … ADD CONSTRAINT`) — فالأعمدةُ المسمّاة التي وصلت بعد 001 تُتحقَّق هنا في
# مسار الكتابة نفسه. قيمةٌ خارج المجموعة خطأُ شيفرةٍ يُرفَع بصوتٍ عالٍ لا صفٌّ
# يُكتَب بقيمةٍ لا يقرؤها أحد (الواجهةُ ترفض إدخالَ المستخدم بـ422 قبل الوصول هنا).
_ENUM_COLUMNS: dict[str, dict[str, frozenset[str]]] = {
    "products": {"hs_source": frozenset({"manual", "image", "unknown"}),
                 "tier": frozenset({"premium", "standard", "economy"})},
    "studies": {"hs_source": frozenset({"manual", "unknown"}),
                "report_language": frozenset({"ar", "en"}),
                "factory_language_at_generation": frozenset({"ar", "en"})},
}


def _validate_enums(table: str, fields: dict) -> None:
    for col, allowed in _ENUM_COLUMNS.get(table, {}).items():
        val = fields.get(col)
        if val is not None and str(val) not in allowed:
            raise ValueError(f"{table}.{col}: {val!r} not in {sorted(allowed)}")
_CREATED_COL = {"images": "uploaded_at"}


class TenantRepository:
    """مستودع مقيّد بالمالك — a repository bound to one owner column.

    يُنشأ لكل جدول مُستأجَر؛ توقيعات الدوال تُلزِم تمرير account_id دائماً
    فلا يمكن نسيان النطاق. The account_id argument is mandatory by construction.
    """

    def __init__(self, conn: sqlite3.Connection, table: str,
                 owner_col: str = "owner_id"):
        if table not in _WRITABLE:
            raise ValueError(f"unknown tenant table: {table}")
        self.conn = conn
        self.table = table
        self.owner_col = owner_col

    # ── قراءة · reads ────────────────────────────────────────────────────────
    def list(self, account_id: int, *, where: str = "",
             params: tuple = (), order: str = "id DESC",
             limit: int | None = None) -> list[dict]:
        """اسرد صفوف الحساب فقط — rows for this account only, never others.

        `order` و`where` يُقحمان نصّاً (SQLite لا يقبل معاملاً في ORDER BY).
        كل النداءات القائمة تمرّر ثوابت حرفية مكتوبة في الشيفرة — لا مدخلَ
        مستخدم — لكن لا شيء **بنيويّ** كان يمنع نداءً قادماً من تمرير قيمةٍ
        من الطلب. `_safe_order` أدناه (تدقيق 2026-08-27، البند ٢٨) يجعل
        الخطأ صاخباً وقتَ الكتابة بدل أن يكون ثغرةً صامتة.
        """
        sql = f"SELECT * FROM {self.table} WHERE {self.owner_col} = ?"
        args: list = [account_id]
        if where:
            sql += f" AND ({where})"
            args.extend(params)
        sql += f" ORDER BY {_safe_order(order)}"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(int(limit))
        # تجريد مفاتيح التكلفة/التشغيل بنيوياً (run_stats — ترحيل 007): القراءة
        # المستأجرة كلها تمرّ من هنا، فالسطح الأدمِني وحده (استعلامه المستقل في
        # api.py) يرى العدّادات. Cost/ops keys never reach tenant CRUD reads.
        return [strip_cost_keys(dict(r))
                for r in self.conn.execute(sql, args).fetchall()]

    def get(self, account_id: int, row_id: int) -> dict | None:
        """اقرأ صفّاً بمعرّفه ضمن الحساب — returns None if it belongs to another."""
        row = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE id = ? AND {self.owner_col} = ?",
            (row_id, account_id)).fetchone()
        return strip_cost_keys(dict(row)) if row else None

    def get_unscoped(self, row_id: int) -> dict | None:
        """اقرأ صفّاً **بلا نطاق حساب** — لإشراف الأدمِن حصراً، لا لمسار مستأجر.

        الاسمُ صارخٌ عمداً: كلُّ مسارٍ يستدعيه يجب أن يكون قد فحص الدور قبله.
        استعمالُه الوحيد اليوم `_tenant_detail` حين يكون المُنادي `silk_admin`
        وتكون المادّةُ **دراسة** — بقرار مالكٍ صريح (2026-08-19) بفتح تقارير
        المصانع للإشراف مع تقييد كل فتحٍ تدقيقاً. بريدُ المستخدمين والصور
        يبقيان خلف الجدار. Admin-only, role checked by the caller, audited.
        """
        row = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE id = ?", (row_id,)).fetchone()
        return strip_cost_keys(dict(row)) if row else None

    def exists_anywhere(self, row_id: int) -> bool:
        """هل المعرّف موجود لأي حساب؟ — internal: distinguishes missing vs foreign.

        تستعمله النقطة النهائية لتقرّر وسم محاولة عبور المستأجر في التدقيق؛
        الردّ للعميل يبقى 404 في الحالتين (لا تسريب وجود).
        """
        row = self.conn.execute(
            f"SELECT 1 FROM {self.table} WHERE id = ?", (row_id,)).fetchone()
        return row is not None

    # ── كتابة · writes (always stamped with the caller's account) ────────────
    def create(self, account_id: int, fields: dict, *, commit: bool = True) -> dict:
        """أنشئ صفّاً مملوكاً للحساب — insert; owner column is forced, never trusted.

        القيم None تُسقَط كي تُطبَّق افتراضيات الأعمدة (لا نكتب None فوق DEFAULT
        NOT NULL). Omitted (None) values are dropped so column defaults apply.
        commit=False joins a caller-owned transaction; existing callers still commit.
        """
        clean = {k: v for k, v in fields.items()
                 if k in _WRITABLE[self.table] and v is not None}
        _validate_enums(self.table, clean)
        clean[self.owner_col] = account_id
        now = now_iso()
        clean[_CREATED_COL.get(self.table, "created_at")] = now
        if self.table not in _NO_UPDATED_AT:
            clean["updated_at"] = now
        cols = list(clean.keys())
        placeholders = ", ".join("?" for _ in cols)
        cur = self.conn.execute(
            f"INSERT INTO {self.table} ({', '.join(cols)}) VALUES ({placeholders})",
            [clean[c] for c in cols])
        if commit:
            self.conn.commit()
        return self.get(account_id, int(cur.lastrowid))  # type: ignore[return-value]

    def update(self, account_id: int, row_id: int, fields: dict) -> dict | None:
        """حدّث صفّاً ضمن الحساب — no-op + None if the row is another tenant's.

        الشرط `AND owner_col = ?` يضمن أن تحديث عبر المستأجر يمسّ صفر صفوف؛
        القاعدة تبقى دون تغيير. Cross-tenant update changes zero rows.
        """
        clean = {k: v for k, v in fields.items() if k in _WRITABLE[self.table]}
        if not clean:
            return self.get(account_id, row_id)
        _validate_enums(self.table, clean)
        # لا تختم `updated_at` على جدول لا يملكه (images) — كان يفشل كل تحديث
        # لصورة بـ«no such column». Only stamp updated_at where the column exists.
        if self.table not in _NO_UPDATED_AT:
            clean["updated_at"] = now_iso()
        sets = ", ".join(f"{c} = ?" for c in clean)
        cur = self.conn.execute(
            f"UPDATE {self.table} SET {sets} WHERE id = ? AND {self.owner_col} = ?",
            [*clean.values(), row_id, account_id])
        self.conn.commit()
        if cur.rowcount == 0:
            return None
        return self.get(account_id, row_id)

    def delete(self, account_id: int, row_id: int) -> bool:
        """احذف صفّاً ضمن الحساب — returns False (no-op) for a foreign row."""
        cur = self.conn.execute(
            f"DELETE FROM {self.table} WHERE id = ? AND {self.owner_col} = ?",
            (row_id, account_id))
        self.conn.commit()
        return cur.rowcount > 0


# ── مصانع مريحة · convenience factories ──────────────────────────────────────
def studies(conn: sqlite3.Connection) -> TenantRepository:
    return TenantRepository(conn, "studies")


def images(conn: sqlite3.Connection) -> TenantRepository:
    return TenantRepository(conn, "images")


def products(conn: sqlite3.Connection) -> TenantRepository:
    return TenantRepository(conn, "products", owner_col="account_id")
