from unittest.mock import patch
import silk_ai_judge as judge
from silk_render import _tag_stale_years


def test_reviewer_revision_receives_the_actual_draft():
    with patch.object(judge, "deep_report", side_effect=["Original complete draft.", "Edited draft."]) as writer, \
         patch.object(judge, "_writer_incomplete", return_value=[]), \
         patch.object(judge, "review_report", side_effect=[
             {"approved": False, "issues": ["Repeated figure"], "blocking": ["Repeated figure"]},
             {"approved": True}]), \
         patch("silk_context.agent_enabled", return_value=True):
        result = judge.write_reviewed_report({}, "", {}, "Honey", "Jordan", max_cycles=2)
    assert result["report"] == "Edited draft."
    assert writer.call_args_list[1].kwargs["revision_draft"] == "Original complete draft."


def test_existing_natural_year_disclosure_is_not_duplicated():
    text = "مؤشر الأداء اللوجستي 2.69 في بيانات 2018، وهي أحدث بيانات متاحة."
    assert _tag_stale_years(text, {2018}) == text


def test_stale_year_label_does_not_repeat_the_data_year():
    text = "مؤشر الأداء اللوجستي 2.69 في بيانات 2018."
    result = _tag_stale_years(text, {2018})
    assert result.count("بيانات 2018") == 1
    assert "الأحدث المتاح" in result
    assert _tag_stale_years(result, {2018}) == result
