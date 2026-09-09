"""Exercise the gosom web server contract, including its real CSV response."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import silk_gmaps as maps


def test_submit_uses_web_server_required_fields(monkeypatch):
    monkeypatch.setenv(maps.ENV_VAR, "http://scraper:8080")
    response = SimpleNamespace(raise_for_status=lambda: None,
                               json=lambda: {"id": "job"})
    with patch("requests.post", return_value=response) as post:
        assert maps.submit_scrape(["food distributor"]) == "job"
    body = post.call_args.kwargs["json"]
    assert isinstance(body["max_time"], int) and body["max_time"] > 0
    assert body['max_time'] < maps._HARD_TIMEOUT_S
    assert len(body["lang"]) == 2


def test_completed_web_job_downloads_csv_and_normalizes_numbers(monkeypatch):
    monkeypatch.setenv(maps.ENV_VAR, "http://scraper:8080")
    state = SimpleNamespace(raise_for_status=lambda: None,
                            json=lambda: {"Status": "completed", "Data": {"keywords": ["food"]}})
    csv = SimpleNamespace(ok=True, headers={"Content-Type": "text/csv; charset=utf-8"},
        content=('title,address,review_rating,review_count,emails,link\n'
                 'Example Distributor,"Street 1, Amman",4.6,120,office@example.test,https://maps.example.test/1\n'
                 'Second Distributor,Street 2,4.6,9,,\n').encode())
    with patch("requests.get", side_effect=[state, csv]):
        status, raw = maps._fetch_job("job")
    rows = maps.parse_and_rank(raw)
    assert status == "completed"
    assert rows[0]["name"] == "Example Distributor"
    assert rows[0]["address"] == "Street 1, Amman"
    assert rows[0]["rating"] == 4.6 and rows[0]["review_count"] == 120
    assert rows[1]["email"] == ""


@pytest.mark.parametrize("value", ["bad", "NaN", "inf", -1, True, None])
def test_invalid_numeric_fields_stay_missing(value):
    row = maps._parse_lead({"title": "Example", "review_rating": value, "review_count": value})
    assert row["rating"] is None and row["review_count"] is None


def test_completed_job_recovery_requires_same_queries_and_recent_date(monkeypatch):
    from datetime import datetime, timezone, timedelta
    monkeypatch.setenv(maps.ENV_VAR, 'http://scraper:8080')
    now = datetime.now(timezone.utc)
    def job(id, keywords, date):
        return {'ID': id, 'Status': 'ok', 'Data': {'keywords': keywords}, 'Date': date.isoformat()}
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: [
        job('wrong-market', ['food UAE'], now),
        job('old', ['food Jordan'], now - timedelta(days=8)),
        job('matching', ['food Jordan'], now - timedelta(minutes=5))])
    with patch('requests.get', return_value=response):
        assert maps._completed_job(['food Jordan']) == 'matching'


def test_scraper_activity_is_preserved():
    assert maps._parse_lead({'title': 'Business', 'category': 'Wholesaler'})['category'] == 'Wholesaler'
