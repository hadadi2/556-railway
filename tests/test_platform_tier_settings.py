"""إعدادات الباقات من اللوحة — سعرٌ وحصّةٌ يُعدَّلان ويسريان فعلاً.

قرار المالك 2026-08-20 (٣): «السعر + حصّة الدراسات» يُعدَّلان من جدول الباقات
في لوحة الأدمِن. البند خطِر لأن حصّة الباقة ليست عرضاً — هي **البوّابة** التي
تمنع الإطلاق في `quota.reserve_launch`. لذلك هذه الأقفال تُكتب **قبل**
النقطة نفسها (test-first): جدولٌ يعرض رقماً لا يفرضه أسوأ من غياب الجدول.

وأين تُخزَّن: قاعدة المنصّة وحدها. `config/pricing.yaml` داخل صورة النشر
و`models.TIER_LIMITS` ثوابتُ كود — الكتابة على أيٍّ منهما تتبخّر عند إعادة
النشر (الدرس ٤: التخزين على وحدة مركَّبة، لا فقدان صامت). قاعدة المنصّة
تشتقّ مسارها من `SILK_DATA_DIR` (`silk_platform/db.py`) فهي الوحيدة المضمونة.
"""
from __future__ import annotations

from tests.platform_helpers import (client, hdr, login, make_factory,
                                    make_product_study, mock_engine, seed)


def _admin(cl, monkeypatch) -> str:
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    return login(cl, "admin@silk.local", "AdminPass1")


# ═══ ١) الحصّة الجديدة تمنع الإطلاق فعلاً ═══════════════════════════════════

def test_a_new_tier_quota_blocks_the_launch_it_should_block(monkeypatch):
    """رفعُ حصّة الفضية من ٢ إلى ٣ يسمح بالثالثة؛ وخفضُها يمنع فوراً.

    الاختبار يمرّ عبر **مسار الإطلاق الحقيقي** (`POST /studies/{id}/launch`)
    لا عبر قراءة الإعداد — رقمٌ يُعرَض ولا يُفرَض هو بالضبط ما نمنعه.
    """
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        mock_engine(monkeypatch)
        acc = make_factory("silver", "tiers@f.local")
        tok = login(cl, "tiers@f.local", "Factory1234")
        atok = login(cl, "admin@silk.local", "AdminPass1")

        # الافتراض: فضية = دراستان شهرياً (models.TIER_LIMITS).
        ent = cl.get("/platform/entitlements", headers=hdr(tok)).json()
        assert ent["studies_limit"] == 2

        # ارفع إلى ٣ — القيم الأخرى تُرسَل كما هي (النقطة تكتب الثلاثة معاً).
        r = cl.post("/platform/admin/tiers/silver",
                    headers=hdr(atok),
                    json={"price": 699, "price_annual": 6990,
                          "monthly_studies": 3})
        assert r.status_code == 200, r.text
        assert r.json()["monthly_studies"] == 3

        # الاستحقاق يعكس الحدّ الجديد فوراً — بلا إعادة تشغيل ولا ذاكرة مخبّأة.
        ent = cl.get("/platform/entitlements", headers=hdr(tok)).json()
        assert ent["studies_limit"] == 3, "الحصّة الجديدة لم تصل إلى الاستحقاق"

        # وثلاث إطلاقات تنجح فعلاً (البوّابة نفسها لا العرض).
        import silk_platform.engine_bridge as eb
        for i in range(3):
            sid = make_product_study(acc["account_id"], acc["user_id"], f"تمر{i}")
            got = cl.post(f"/platform/studies/{sid}/launch", headers=hdr(tok))
            assert got.status_code == 200, f"الإطلاق {i + 1}: {got.text}"
            assert eb.wait_idle()

        # الرابعة تُرفض بالحدّ الجديد — لا بالحدّ القديم.
        sid = make_product_study(acc["account_id"], acc["user_id"], "تمر4")
        blocked = cl.post(f"/platform/studies/{sid}/launch", headers=hdr(tok))
        assert blocked.status_code == 403, blocked.text
        detail = blocked.json()["detail"]
        assert detail.get("limit") == 3, f"الرفض بحدٍّ غير الجديد: {detail}"


def test_lowering_a_tier_quota_below_used_blocks_immediately(monkeypatch):
    """الخفض يسري فوراً على الحسابات القائمة، والعدّاد المستهلك لا يُصفَّر."""
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        mock_engine(monkeypatch)
        acc = make_factory("gold", "lower@f.local")
        tok = login(cl, "lower@f.local", "Factory1234")
        atok = login(cl, "admin@silk.local", "AdminPass1")

        import silk_platform.engine_bridge as eb
        sid = make_product_study(acc["account_id"], acc["user_id"], "زعفران")
        assert cl.post(f"/platform/studies/{sid}/launch",
                       headers=hdr(tok)).status_code == 200
        assert eb.wait_idle()

        assert cl.post("/platform/admin/tiers/gold", headers=hdr(atok),
                       json={"price": 1799, "price_annual": 17990,
                             "monthly_studies": 1}).status_code == 200

        ent = cl.get("/platform/entitlements", headers=hdr(tok)).json()
        assert ent["studies_limit"] == 1
        assert ent["studies_used"] == 1, "العدّاد المستهلك صُفِّر — لم يُطلَب ذلك"

        sid2 = make_product_study(acc["account_id"], acc["user_id"], "عود")
        blocked = cl.post(f"/platform/studies/{sid2}/launch", headers=hdr(tok))
        assert blocked.status_code == 403


# ═══ ٢) `/pricing` مصدرٌ واحد يصرّح بمصدره ═════════════════════════════════

def test_public_pricing_reflects_the_override_and_declares_it(monkeypatch):
    """صفحتا الهبوط والدفع تقرآن `/pricing` — فالتجاوز يظهر فيه أو انحرف السعر.

    وتصريحُ `overridden` شرطُ صدق: قيمةٌ من القاعدة تُعرَض بلا وسمٍ توهم أنها
    من ملف الأسعار المُقرّ.
    """
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        before = cl.get("/platform/pricing").json()
        gold_before = [t for t in before["tiers"] if t["key"] == "gold"][0]
        assert gold_before["overridden"] is False
        assert gold_before["price"] == 1799        # من config/pricing.yaml

        atok = _admin(cl, monkeypatch)
        assert cl.post("/platform/admin/tiers/gold", headers=hdr(atok),
                       json={"price": 1999, "price_annual": 19990,
                             "monthly_studies": 8}).status_code == 200

        after = cl.get("/platform/pricing").json()
        gold = [t for t in after["tiers"] if t["key"] == "gold"][0]
        assert gold["price"] == 1999 and gold["price_annual"] == 19990
        assert gold["monthly_studies"] == 8
        assert gold["overridden"] is True, "قيمةٌ من القاعدة بلا تصريح بمصدرها"
        # الباقات غير المعدَّلة تبقى على الملف وتصرّح بذلك.
        silver = [t for t in after["tiers"] if t["key"] == "silver"][0]
        assert silver["price"] == 699 and silver["overridden"] is False
        # نسبة الخصم السنوي تبقى مشتقّة من الأرقام نفسها — لا حقل يدوي.
        assert after["annual_discount_pct"] == min(
            round((1 - t["price_annual"] / (12 * t["price"])) * 100)
            for t in after["tiers"] if t["price"] > 0 and t["price_annual"] > 0)


def test_the_override_survives_a_fresh_process_reading_the_same_db(monkeypatch):
    """الدرس ٤: القيمة تعيش في قاعدة المنصّة، لا في ذاكرة العملية ولا في ملفٍ
    داخل صورة النشر — عميلٌ جديد على نفس القاعدة يراها."""
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        atok = _admin(cl, monkeypatch)
        assert cl.post("/platform/admin/tiers/platinum", headers=hdr(atok),
                       json={"price": 5999, "price_annual": 59990,
                             "monthly_studies": 20}).status_code == 200
    with client() as cl2:                      # تطبيق جديد، نفس القاعدة
        row = [t for t in cl2.get("/platform/pricing").json()["tiers"]
               if t["key"] == "platinum"][0]
        assert row["price"] == 5999 and row["monthly_studies"] == 20

    # ولا يُكتَب شيء في ملف الأسعار المُقرّ — هو بذرةٌ لا سجلٌّ حيّ.
    import pathlib
    cfg = (pathlib.Path(__file__).resolve().parent.parent /
           "config" / "pricing.yaml").read_text(encoding="utf-8")
    assert "5999" not in cfg, "النقطة كتبت في ملف الصورة — تتبخّر عند النشر"


# ═══ ٣) الحوكمة ═════════════════════════════════════════════════════════════

def test_checkout_records_the_price_the_visitor_actually_saw(monkeypatch):
    """مسار المال يقرأ نفس المصدر الذي يعرضه — لا سعرَين لصفقةٍ واحدة.

    السابقة (مراجعة ذاتية §58 على هذه الموجة): `/pricing` صار يخدم تجاوز
    المالك بينما ظلّت نقطة الاشتراك تقرأ `config/pricing.yaml` — فيرى الزائر
    السعر الجديد ويوافق عليه، ويُسجَّل في التدقيق السعر القديم. أخطر من فرقٍ
    في العرض: القيد المُدقَّق هو ما تُبنى عليه المطالبة.
    """
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        atok = _admin(cl, monkeypatch)
        assert cl.post("/platform/admin/tiers/silver", headers=hdr(atok),
                       json={"price": 899, "price_annual": 8990,
                             "monthly_studies": 2}).status_code == 200

        shown = [t for t in cl.get("/platform/pricing").json()["tiers"]
                 if t["key"] == "silver"][0]
        assert shown["price"] == 899

        r = cl.post("/platform/billing/checkout",
                    json={"plan": "silver", "billing_cycle": "monthly",
                          "name": "مصنع", "email": "buyer@f.local"})
        assert r.status_code == 200, r.text
        rows = cl.get("/platform/admin/audit", headers=hdr(atok)).json()["audit"]
        entry = [e for e in rows if e.get("action") == "checkout_requested"][0]
        import json as _json
        changes = entry["changes"]
        if isinstance(changes, str):
            changes = _json.loads(changes)
        assert changes["price_sar"] == 899, (
            f"سُجِّل سعرٌ غير المعروض: {changes['price_sar']} بدل 899")


def test_checkout_refuses_an_annual_cycle_the_owner_turned_off(monkeypatch):
    """إلغاء السعر السنوي من اللوحة يُخفيه من العرض **ويرفضه** في الاشتراك."""
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        atok = _admin(cl, monkeypatch)
        assert cl.post("/platform/admin/tiers/gold", headers=hdr(atok),
                       json={"price": 1799, "price_annual": 0,
                             "monthly_studies": 6}).status_code == 200
        r = cl.post("/platform/billing/checkout",
                    json={"plan": "gold", "billing_cycle": "annual",
                          "name": "مصنع", "email": "buyer2@f.local"})
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "annual_not_available"


def test_tier_settings_are_admin_only(monkeypatch):
    seed(monkeypatch)
    with client() as cl:
        make_factory("silver", "notadmin@f.local")
        tok = login(cl, "notadmin@f.local", "Factory1234")
        r = cl.post("/platform/admin/tiers/silver", headers=hdr(tok),
                    json={"price": 1, "price_annual": 1, "monthly_studies": 99})
        assert r.status_code == 403
        # ولا أثر للمحاولة على القيم العامة.
        silver = [t for t in cl.get("/platform/pricing").json()["tiers"]
                  if t["key"] == "silver"][0]
        assert silver["price"] == 699 and silver["overridden"] is False


def test_tier_settings_reject_invalid_input(monkeypatch):
    """أرقامٌ سالبة أو غير صحيحة أو باقةٌ مجهولة = رفضٌ معلَن لا كتابة."""
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        atok = _admin(cl, monkeypatch)
        base = {"price": 699, "price_annual": 6990, "monthly_studies": 2}
        assert cl.post("/platform/admin/tiers/vip", headers=hdr(atok),
                       json=base).status_code == 422
        for bad in ({"price": -1}, {"price_annual": -5}, {"monthly_studies": -2},
                    {"price": "كثير"}, {"monthly_studies": 1.5}):
            body = dict(base, **bad)
            r = cl.post("/platform/admin/tiers/silver", headers=hdr(atok),
                        json=body)
            assert r.status_code == 422, f"قُبِل إدخال فاسد {bad}: {r.text}"
        silver = [t for t in cl.get("/platform/pricing").json()["tiers"]
                  if t["key"] == "silver"][0]
        assert silver["overridden"] is False, "كتابةٌ نجحت رغم الرفض"


def test_tier_settings_change_is_audited(monkeypatch):
    """قيدُ تدقيقٍ بالقيمتين قبل/بعد — نفس نمط تغيير الطبقة والحصّة."""
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        atok = _admin(cl, monkeypatch)
        assert cl.post("/platform/admin/tiers/silver", headers=hdr(atok),
                       json={"price": 799, "price_annual": 7990,
                             "monthly_studies": 4}).status_code == 200
        rows = cl.get("/platform/admin/audit", headers=hdr(atok)).json()
        entries = [r for r in rows.get("entries", rows.get("audit", []))
                   if r.get("action") == "tier_settings_changed"]
        assert entries, "تغيير إعدادات باقة بلا قيد تدقيق"


def test_basic_tier_keeps_its_lifetime_rule(monkeypatch):
    """الأساسية محكومةٌ بسقف مدى الحياة لا بالشهري — تعديل الشهري لا يفتحها.

    بلا هذا القفل كان تعديلُ `monthly_studies` للأساسية يوهم بحدٍّ لا يُقرأ
    أصلاً (`quota` تفرّع على `Tier.BASIC` قبل السطر الشهري) — رقمٌ معروض
    بلا معنى، وهو اختلاقٌ بالعرض.
    """
    monkeypatch.setenv("SILK_SEED_ADMIN_PASSWORD", "AdminPass1")
    seed(monkeypatch)
    with client() as cl:
        mock_engine(monkeypatch)
        acc = make_factory("basic", "basic@f.local")
        tok = login(cl, "basic@f.local", "Factory1234")
        atok = _admin(cl, monkeypatch)
        assert cl.post("/platform/admin/tiers/basic", headers=hdr(atok),
                       json={"price": 0, "price_annual": 0,
                             "monthly_studies": 9}).status_code == 200
        ent = cl.get("/platform/entitlements", headers=hdr(tok)).json()
        assert ent["studies_period"] == "lifetime"
        assert ent["studies_limit"] == 1, "الأساسية تعرض حدّاً شهرياً لا يحكمها"

        import silk_platform.engine_bridge as eb
        sid = make_product_study(acc["account_id"], acc["user_id"], "تمر")
        assert cl.post(f"/platform/studies/{sid}/launch",
                       headers=hdr(tok)).status_code == 200
        assert eb.wait_idle()
        sid2 = make_product_study(acc["account_id"], acc["user_id"], "عسل")
        assert cl.post(f"/platform/studies/{sid2}/launch",
                       headers=hdr(tok)).status_code == 403
