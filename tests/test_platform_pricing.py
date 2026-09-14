"""أقفال مصدر الأسعار الواحد — `config/pricing.yaml` ← `GET /platform/pricing`.

قرار المالك (2026-08-17) ثم إعادة التسعير السوقية (2026-08-18: «اعد تصميم
الباقات بناء على تسعيرة السوق وخلي فيه خصم عن الاشتراك السنوي»): أسعار
ريال شهرية (0/699/1,799) وسنوية بخصم شهرين (0/6,990/17,990
مع annual_discount_pct)، يعدّلها من ملف إعدادات واحد بلا كود. الأقفال: الردّ يطابق الملف بايتاً ببايت،
تعذُّر الملف = افتراضات معلَنة (الأرقام المُقرّة نفسها) لا انهيار، والحصص
تأتي من `models.TIER_LIMITS` الحقيقية لا نسخة ثانية.
"""
from __future__ import annotations

import pathlib
import sqlite3

import pytest

from tests.platform_helpers import client, seed

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _file_prices() -> dict:
    out = {}
    for line in (_ROOT / "config" / "pricing.yaml").read_text(
            encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def test_endpoint_is_public_and_matches_the_file(monkeypatch):
    seed(monkeypatch)
    with client() as cl:
        r = cl.get("/platform/pricing")          # بلا توثيق عمداً — قراءة ملف
        assert r.status_code == 200
        body = r.json()
        f = _file_prices()
        assert body["currency"] == f["currency"] == "SAR"
        assert body["cycle"] == f["billing_cycle"] == "monthly"
        assert body["source"] == "file"
        assert body["cycles"] == ["monthly", "annual"]
        tiers = {t["key"]: t for t in body["tiers"]}
        assert list(tiers) == ["basic", "silver", "gold"]
        for key in tiers:
            assert tiers[key]["price"] == int(f[f"{key}_price"]), (
                f"سعر {key} في الردّ لا يطابق pricing.yaml")
            assert tiers[key]["price_annual"] == int(
                f[f"{key}_price_annual"]), (
                f"السعر السنوي لـ{key} لا يطابق pricing.yaml")
        # الأرقام المُقرّة حرفياً (توثيق قرار 2026-08-18 كقفل) —
        # السنوي = 10 أشهر (شهران مجاناً)، والنسبة **مشتقّة من الأسعار
        # نفسها** لا من حقل يدوي: round(1 − 6990⁄8388) = 17.
        assert body["annual_discount_pct"] == 17
        assert tiers["basic"]["price"] == 0
        assert tiers["silver"]["price"] == 699
        assert tiers["gold"]["price"] == 1799
        assert tiers["basic"]["price_annual"] == 0
        assert tiers["silver"]["price_annual"] == 6990
        assert tiers["gold"]["price_annual"] == 17990


def test_quotas_come_from_the_one_tier_limits_source(monkeypatch):
    seed(monkeypatch)
    with client() as cl:
        body = cl.get("/platform/pricing").json()
        from silk_platform.models import tier_limits
        for t in body["tiers"]:
            lim = tier_limits(t["key"])
            assert t["monthly_studies"] == lim.monthly_studies
            assert t["lifetime_studies"] == lim.lifetime_studies
            assert t["export"] == lim.export
            assert t["api_access"] == lim.api_access
            assert t["white_label"] == lim.white_label


def test_missing_file_falls_back_to_declared_defaults():
    from silk_platform.pricing import load_pricing
    out = load_pricing(path="/nonexistent/pricing.yaml")
    assert out["source"] == "defaults"
    assert out["silver_price"] == 699
    assert "platinum_price" not in out
    assert out["gold_price_annual"] == 17990


def test_platinum_is_removed_and_legacy_rows_are_migrated_to_gold():
    """قرار 2026-09-14: لا API ولا واجهة تقبل البلاتينية، والقديم لا يتعطل."""
    from silk_platform.models import Tier

    assert [tier.value for tier in Tier] == ["basic", "silver", "gold"]
    with pytest.raises(ValueError):
        Tier("platinum")
    assert "platinum" not in (_ROOT / "config" / "pricing.yaml").read_text(
        encoding="utf-8")
    for name in ("marketing.js", "checkout.html", "platform.html"):
        assert "platinum" not in (_ROOT / "web" / name).read_text(encoding="utf-8")

    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE accounts (tier TEXT, updated_at TEXT);
        CREATE TABLE tier_settings (tier TEXT);
        INSERT INTO accounts VALUES ('platinum', 'old');
        INSERT INTO tier_settings VALUES ('platinum');
    """)
    migration = (_ROOT / "migrations" / "platform" /
                 "023_remove_platinum_tier.sql").read_text(encoding="utf-8")
    conn.executescript(migration)
    assert conn.execute("SELECT tier FROM accounts").fetchone()[0] == "gold"
    assert conn.execute("SELECT COUNT(*) FROM tier_settings").fetchone()[0] == 0


def test_malformed_price_keeps_the_declared_default(tmp_path):
    p = tmp_path / "pricing.yaml"
    p.write_text("currency: SAR\nsilver_price: كثير\ngold_price: 100\n",
                 encoding="utf-8")
    from silk_platform.pricing import load_pricing
    out = load_pricing(path=str(p))
    assert out["source"] == "file"
    assert out["silver_price"] == 699      # التالف = الافتراض المعلَن
    assert out["gold_price"] == 100        # الصحيح يُقرأ


def test_payment_reports_unconfigured_without_a_provider(monkeypatch):
    monkeypatch.delenv("SILK_PAY_PROVIDER", raising=False)
    seed(monkeypatch)
    with client() as cl:
        body = cl.get("/platform/pricing").json()
        assert body["payment"]["configured"] is False
        assert body["payment"]["provider"] is None
