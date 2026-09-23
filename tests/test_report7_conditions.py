"""تقرير سِلك ٧ — الشروط والقناة (§4.1–4.2، الدرس ٢٧٧).

one conditions list: the engine emits structured `condition_items` (id, kind,
closing step); the decision basis and the writer both read the same list, the
displayed number is the id's number («الشرط 3»), so every 90-day step the
writer ties to a condition points at a visible one. One entry-channel record
from the analyst's ranked entry doors, marked as a candidate, handed to the
writer as well.

كلُّ الحالات مصطنعةٌ لاختبارٍ هرمتيّ.
"""
import silk_ai_judge as AJ
import silk_render as R


def _ed():
    return {"schema": "silk.decision/v1",
            "conditions": ["بوابة", "جانب السوق غائب", "جانب الربحية ضعيف"],
            "condition_items": [
                {"id": "C1", "kind": "eligibility_gate", "pillar": "regulatory",
                 "status": "open"},
                {"id": "C2", "kind": "pillar_missing", "pillar": "market",
                 "missing": ["tam_usd"], "status": "open"},
                {"id": "C3", "kind": "pillar_weak", "pillar": "profit",
                 "pct": 31, "status": "open"}],
            "pillars": {
                "market": {"value": None, "missing": ["tam_usd"]},
                "profit": {"value": 0.31, "missing": []},
                "regulatory": {"value": 0.8, "missing": [],
                               "eligibility_gate": True}}}


def test_condition_rows_are_numbered_by_their_id_in_the_reader_language():
    rows = R.condition_texts(_ed(), "ar")
    assert [r["id"] for r in rows] == ["C1", "C2", "C3"]
    assert [r["label"][:8] for r in rows] == ["الشرط 1:", "الشرط 2:", "الشرط 3:"]
    assert "جاذبية السوق" in rows[1]["text"] and "31%" in rows[2]["text"]
    assert "market" not in rows[1]["text"], "لا مفتاحَ داخليّ على سطح العميل"
    en = R.condition_texts(_ed(), "en")
    assert en[0]["label"].startswith("Condition 1:")


def test_the_basis_shows_the_engine_list_with_its_numbers():
    basis = R.decision_basis(_ed())
    assert basis["conditions_count"] == basis["engine_conditions_count"] == 3
    assert basis["conditions"][2].startswith("الشرط 3:")


def test_a_stored_result_without_items_takes_the_same_wording_path():
    legacy = {k: v for k, v in _ed().items() if k != "condition_items"}
    basis = R.decision_basis(legacy)
    assert all(c.startswith("الشرط ") for c in basis["conditions"])


def test_the_writer_receives_the_numbered_list_in_the_report_language():
    block = AJ._conditions_block(_ed(), "ar")
    assert "الشروط المفتوحة المحسوبة (3)" in block
    assert "الشرط 3:" in block and "لا تضف شرطاً ولا تحذفه" in block
    assert "استكمال: " not in block, "لا تكرار «الإجراء: استكمال:»"
    en = AJ._conditions_block(_ed(), "en")
    assert "Condition 1:" in en and "الشرط" not in en
    assert AJ._conditions_block({"conditions": ["x"]}, "ar") == ""


def test_the_real_engine_emits_one_item_per_condition_string():
    """على مدوّنةٍ حقيقية الشكل — لا على نصّ المصدر."""
    import silk_deep_pillars as DP
    from tools.canonical_netherlands import netherlands_research_blob
    blob = netherlands_research_blob()
    ed = DP.decide_for_deep(blob["deep_research"])
    items = ed.get("condition_items") or []
    assert len(items) == len(ed.get("conditions") or [])
    assert [it["id"] for it in items] == [f"C{n}" for n in
                                          range(1, len(items) + 1)]


def test_one_entry_channel_record_skips_weak_and_duplicate_doors():
    ch = R.entry_channel({"entry_door": [
        {"value": "بابٌ ضعيف الدليل", "confidence": 0.2},
        {"value": "متاجر القهوة المتخصصة", "source": "تحليل", "confidence": 0.7},
        {"value": "متاجر القهوة المتخصصة", "confidence": 0.7},
        {"claim": "الضيافة", "confidence": 0.6}]})
    assert ch == {"primary": "متاجر القهوة المتخصصة", "alternative": "الضيافة",
                  "source": "تحليل", "status": "candidate"}
    assert R.entry_channel({}) is None
    block = AJ._entry_channel_block({"entry_door": [
        {"claim": "متاجر القهوة المتخصصة", "confidence": 0.7}]}, "ar")
    assert "القناة الأولى المرشّحة" in block
