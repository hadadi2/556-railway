"""مسار المال — دلو اليوم عبر منتصف الليل/إعادة النشر (find all gaps مجموعة 2).

درس 188 (F7/F8/F9/F15، قرار مالك 2026-08-27):
- F7: التسوية تُطبَّق على **يوم الحجز** لا على «اليوم» المُعاد قراءته — تشغيلةٌ
  تعبر منتصف الليل كانت تُصفّر دفتر الغد وتمحو إنفاق تشغيلاتٍ متزامنة.
- F8: الحارس الأوسط يقيس على دلو الحجز (`usd_spent_on`) فلا يُعطَّل بعد منتصف
  الليل بطرح حجزِ يومٍ سابق من دلو اليوم التالي.
- F9: مصدرٌ واحد للتقدير (`expected_run_usd`) بدل أربع حرفيّات 3.0 تتباعد.
- F15: `_today()` بـUTC كبقية المنصّة لا بالتوقيت المحلي.

Hermetic؛ دفتر معزول لكل اختبار (path صريح).
"""
from __future__ import annotations

import datetime

import silk_usage as U


def test_today_is_utc():
    assert U._today() == datetime.datetime.now(
        datetime.timezone.utc).date().isoformat()


def test_expected_run_usd_is_one_guarded_source(monkeypatch):
    monkeypatch.setenv("SILK_RESEARCH_EXPECTED_USD", "5.5")
    assert U.expected_run_usd() == 5.5
    monkeypatch.setenv("SILK_RESEARCH_EXPECTED_USD", "not-a-number")
    assert U.expected_run_usd() == 3.0
    monkeypatch.delenv("SILK_RESEARCH_EXPECTED_USD", raising=False)
    assert U.expected_run_usd() == 3.0


def test_reconcile_applies_delta_to_the_reservation_day_not_today(tmp_path):
    """F7 الجوهري: حجزٌ على يوم سابق يُسوّى في دلوه، ودفتر اليوم لا يُمَسّ."""
    db = str(tmp_path / "usage.db")
    reserve_day = "2026-08-26"
    today = U._today()
    # ابذر الدلوين عبر الـAPI العام (delta موجب ينشئ الدلو).
    U.reconcile_usd(reserved=0.0, actual=5.0, path=db, day=reserve_day)
    U.reconcile_usd(reserved=0.0, actual=10.0, path=db, day=today)
    # تشغيلةُ يومِ الحجز اكتملت رخيصةً (actual 0.4 مقابل حجز 3.0).
    U.reconcile_usd(reserved=3.0, actual=0.4, path=db, day=reserve_day)
    assert abs(U.usd_spent_on(reserve_day, db) - (5.0 + 0.4 - 3.0)) < 1e-9
    # دفتر اليوم (تشغيلات متزامنة) سليمٌ لم يُصفَّر.
    assert abs(U.usd_spent_on(today, db) - 10.0) < 1e-9


def test_reconcile_default_day_is_today(tmp_path):
    """غيابُ day = اليوم (توافقٌ مع النداءات القديمة)."""
    db = str(tmp_path / "usage.db")
    U.reconcile_usd(reserved=0.0, actual=4.0, path=db)         # today += 4
    U.reconcile_usd(reserved=3.0, actual=0.5, path=db)         # today += (0.5-3)
    assert abs(U.usd_spent_on(U._today(), db) - (4.0 + 0.5 - 3.0)) < 1e-9


def test_usd_spent_on_reads_the_named_day_bucket(tmp_path):
    db = str(tmp_path / "usage.db")
    U.reconcile_usd(reserved=0.0, actual=7.0, path=db, day="2020-01-01")
    assert U.usd_spent_on("2020-01-01", db) == 7.0
    assert U.usd_spent_on("2019-12-31", db) == 0.0
