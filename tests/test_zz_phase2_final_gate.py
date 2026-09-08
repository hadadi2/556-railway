"""بوّابةُ الإغلاق — Phase 2 final gate. Verification only, no logic touched.

يُعيد تشغيل التدفّق المطلوب حرفياً على **تطبيق `api` الحقيقي** (نفس عُدّة
`test_platform_deep_real_path`: كل البوّابات حيّة، والمُحاكى طبقةُ مزوّد كلود
والشبكة وحدهما) ويطبع كلَّ قيمةٍ مطلوبة بدل أن يؤكّدها صامتاً.

يُشغَّل: `pytest tests/test_zz_phase2_final_gate.py -q -s`
"""
import json

import pytest

from tests.test_platform_deep_real_path import (  # noqa: F401
    _launch_and_settle, _mk, _row, deep_env)

import silk_hs_pipeline as P


def _show(title: str, pairs: list[tuple[str, object]]) -> None:
    print(f"\n===== {title} =====")
    for k, v in pairs:
        print(f"  {k:26} {v}")


# ═══════════ ٥ — التدفّق المطلوب حرفياً ══════════════════════════════════════
def test_gate_5_halva_with_catalog_170490_end_to_end(deep_env):
    """حلاوة طحينية + رمز كتالوج 170490 ⇒ تنطلق وتكتمل بكل الشروط المسمّاة."""
    cls = P.classify("حلاوة طحينية", "170490")
    _show("STEP 5a — classification contract", [
        ("product", cls["product_name"]),
        ("normalized_product", cls["normalized_product"]),
        ("catalog_hs_code", cls["catalog_hs_code"]),
        ("catalog_hs_status", cls["catalog_hs_status"]),
        ("classification_status", cls["classification_status"]),
        ("classification_method", cls["classification_method"]),
        ("confidence", f'{cls["confidence"]} ({type(cls["confidence"]).__name__})'),
        ("final_hs_code", cls["final_hs_code"]),
        ("requires_user_confirmation", cls["requires_user_confirmation"]),
        ("contradictions", cls["contradictions"]),
    ])
    assert cls["classification_status"] == "approved"
    assert isinstance(cls["confidence"], float)
    assert cls["confidence"] >= P.min_confidence()
    assert cls["final_hs_code"] == "170490"

    r = deep_env["cl"].post("/platform/products", headers=deep_env["hdr"],
                            json={"name": "حلاوة طحينية",
                                  "description": "حلاوة طحينية سادة",
                                  "hs_code": "170490"})
    assert r.status_code == 200, r.text
    pid = int(r.json()["id"])
    sid = _mk(deep_env, product="حلاوة طحينية", market_pref="OMN",
              product_id=pid, hs_code="170490")

    before = _row(deep_env["db"], sid)
    # «تصل running» تُثبَت من ردّ نقطة الإطلاق نفسها: المطالبةُ الذرّية تكتب
    # `in_progress` وتختم `run_started_at` في الجملة نفسها **قبل** إقلاع خيط
    # المحرّك — فالتقاطُ الحالة من الردّ دليلٌ لا سباق.
    import silk_platform.engine_bridge as _eb
    launched = deep_env["cl"].post(f"/platform/studies/{sid}/launch",
                                   headers=deep_env["hdr"])
    assert launched.status_code == 200, launched.text
    running_state = launched.json().get("state")
    assert _eb.wait_idle(180), "خيط الجسر لم يخمد"
    row = _row(deep_env["db"], sid)
    _show("STEP 5b — study lifecycle", [
        ("study_id", sid),
        ("state at creation", before["state"]),
        ("state from the launch response", running_state),
        ("state after launch", row["state"]),
        ("analysis_id", row["analysis_id"]),
        ("run_error", repr(row["run_error"])),
        ("run_stats.mode", json.loads(row["run_stats"] or "{}").get("mode")),
        ("hs_code on the study", row["hs_code"]),
        ("hs_confirmed", row["hs_confirmed"]),
        ("hs_candidates", repr(row["hs_candidates"])),
    ])
    assert before["state"] == "draft"
    assert running_state == "in_progress", running_state
    assert row["state"] == "completed", row["run_error"]
    assert row["analysis_id"], "لا معرّف تحليل — النتيجة غير مرتبطة"
    assert row["run_error"] is None
    assert json.loads(row["run_stats"])["mode"] == "deep"
    # ولم يُطلَب تأكيدٌ بشريّ: الدليلُ حسم وحده.
    assert not row["hs_confirmed"]

    # وأختامُ الدورة الثلاثة حاضرة — تأكيدٌ ثانٍ مستقلٌّ عن ردّ الإطلاق.
    _show("STEP 5c — lifecycle stamps", [
        ("run_started_at", row["run_started_at"]),
        ("run_finished_at", row["run_finished_at"]),
        ("launched_at", row["launched_at"]),
    ])
    assert row["launched_at"] and row["run_started_at"] and row["run_finished_at"]


# ═══════════ ٦ — الحالة العدائية ═════════════════════════════════════════════
def test_gate_6_paper_tissues_never_auto_approve_watermelons():
    """مناديل ورقية: 080711 ممنوعٌ اعتمادُه تلقائياً — بأيّ مسار."""
    out = P.classify("مناديل ورقية")
    offered = [(c["hs6"], c["score"], c["offer"]) for c in out["candidate_codes"]]
    _show("STEP 6 — adversarial case", [
        ("classification_status", out["classification_status"]),
        ("final_hs_code", out["final_hs_code"]),
        ("confidence", out["confidence"]),
        ("candidates (hs6, score, offer)", offered),
        ("reason", out["reason"][:120]),
    ])
    assert out["final_hs_code"] != "080711"
    assert out["classification_status"] != "approved"
    eligible = [c["hs6"] for c in out["candidate_codes"]
                if c.get("offer") and c["score"] >= P.min_confidence()]
    assert "080711" not in eligible, eligible
    # ونفسُ المنع حين يصل الرمزُ من الكتالوج بدل المُحلِّل.
    with_catalog = P.classify("مناديل ورقية", "080711")
    _show("STEP 6b — same code arriving from the catalog", [
        ("classification_status", with_catalog["classification_status"]),
        ("catalog_hs_status", with_catalog["catalog_hs_status"]),
        ("final_hs_code", with_catalog["final_hs_code"]),
        ("contradictions", with_catalog["contradictions"][:1]),
    ])
    assert with_catalog["final_hs_code"] != "080711"
    assert with_catalog["classification_status"] != "approved"


# ═══════════ ٧ — الكتالوج ≠ المُحلِّل ════════════════════════════════════════
@pytest.mark.parametrize("product,catalog,classifier", [
    ("حلاوة طحينية", "110100", "170490"),   # دقيق قمح مقابل حلويات سكرية
    ("طحينة", "170490", "200819"),          # حلويات مقابل بذور محضّرة
    ("زبدة الفول السوداني", "040510", "200811"),  # ألبان مقابل فول سوداني
])
def test_gate_7_catalog_conflict_never_silently_approves(product, catalog,
                                                         classifier):
    """اختلافُ الكتالوج عن المُحلِّل ⇒ تعارضٌ يُسأل عنه، لا اعتمادٌ صامت."""
    out = P.classify(product, catalog)
    _show(f"STEP 7 — {product} | catalog {catalog}", [
        ("classification_status", out["classification_status"]),
        ("catalog_hs_status", out["catalog_hs_status"]),
        ("refusal_code", out["refusal_code"]),
        ("final_hs_code", out["final_hs_code"]),
        ("confidence", out["confidence"]),
        ("reason", out["reason"][:130]),
    ])
    assert out["classification_status"] == P.REQUIRES_CONFIRMATION
    assert out["catalog_hs_status"] == P.CATALOG_CONFLICT
    assert out["refusal_code"] == P.REFUSAL_CONFLICT
    assert out["final_hs_code"] is None, "اعتُمِد أحدُهما صامتاً"
    assert catalog in out["reason"] and classifier in out["reason"]
    assert isinstance(out["confidence"], float)
