from silk_i18n import foreign_prose_spans
from silk_reports import _client_localize_observation


def test_google_trends_note_is_localized_without_changing_observations():
    raw = (
        "mean interest 0-100 for 'حلاوة طحينية' geo=BH "
        "tf='today 12-m' n=53; monthly mean search interest 0-100: "
        "2025-09=24.00; 2025-10=0.00; 2026-08=3.80; "
        "search interest is not sales or demand volume; "
        "a one-year peak does not establish recurring seasonality")

    localized = _client_localize_observation(raw, "ar")

    assert not foreign_prose_spans(localized, "ar", ("Google Trends",))
    assert "حلاوة طحينية" in localized
    assert "BH" in localized
    assert "today 12-m" in localized
    assert "53" in localized
    assert "2025-09=24.00" in localized
    assert "2026-08=3.80" in localized
    assert "ليس مبيعات أو حجم طلب" in localized


def test_english_trends_note_is_unchanged_for_english_report():
    raw = "mean interest 0-100 for 'tahini' geo=BH tf='today 12-m' n=53"
    assert _client_localize_observation(raw, "en") == raw

