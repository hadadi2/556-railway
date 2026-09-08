"""الموجة C · §٦ — تفعيلٌ **جزئيٌّ** لسدّ الفجوات، بصمّامٍ لكلّ صنف.

> أمرُ المالك حرفياً: «لا تُفعِّلها عمياء». فالتصنيف في §٦ من
> `docs/ENGINE_AUDIT.md` مبنيٌّ على **المصدر الفعليّ** لكلّ مُستَرِدّ لا على
> اسمه:
>
> - **يجوز آلياً:** استعلامٌ حتميٌّ من **نفس** المصدر الرسميّ الذي كان
>   سيستعمله الوكيل — لا استنتاج، لا مصدرَ جديد.
> - **يحتاج دليلاً خارجياً:** الموسميةُ إشارةُ اهتمامٍ **بديلٌ عن** الطلب لا
>   الطلبُ نفسه؛ والموزّعون كياناتٌ مسمّاةٌ أعلى خطرِ اختلاق.
> - **يبقى UNKNOWN:** بحثُ ويبٍ حرّ — مصدريّةٌ غير محدودة، وملءُ فجوةٍ معلنة
>   من نصٍّ عشوائيّ هو بالضبط ما يحظره عقدُ التأسيس.

**والقيمةُ لا تتغيّر أبداً** — يتغيّر ما يُقال عنها: «مُستَردّ» يظهر في سطر
المصدر. عرضُها بلا وسمٍ كان سيجعلها تبدو رصداً مباشراً، وهو ادّعاءُ منشأٍ لم
يحدث.
"""
from __future__ import annotations

import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_gap_recovery as G                           # noqa: E402
from silk_data_layer import DataPoint                   # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALL = ("wgi", "per_capita", "partner_shares", "tariff",
        "seasonality", "distributors", "web_search")


@pytest.fixture
def valve_on(monkeypatch):
    monkeypatch.setenv(G.FLAG, "1")
    for name in _ALL:
        monkeypatch.delenv(f"SILK_GAP_RECOVER_{name.upper()}", raising=False)


# ── الصمّام العامّ يبقى سيّداً ───────────────────────────────────────────

def test_nothing_runs_while_the_master_valve_is_off(monkeypatch):
    """البند ٧٠ كما هو: التفعيلُ قرارُ مالكٍ منفصل."""
    monkeypatch.setenv(G.FLAG, "0")
    monkeypatch.setenv("SILK_GAP_RECOVER_WGI", "1")
    assert all(G.recoverer_enabled(n) is False for n in _ALL)


# ── التصنيفُ الثلاثيّ ───────────────────────────────────────────────────

def test_deterministic_recoverers_are_on_under_the_valve(valve_on):
    for name in ("wgi", "per_capita", "partner_shares", "tariff"):
        assert G.recoverer_enabled(name) is True, name


def test_evidence_needing_recoverers_stay_off_by_default(valve_on):
    """لا يُفتَحان قبل شحن وسمَيهما الصريحَين — «مؤشّر بديل»/«مرشّح غيرُ مؤكَّد»."""
    for name in ("seasonality", "distributors"):
        assert G.recoverer_enabled(name) is False, name


def test_an_evidence_recoverer_opens_only_by_its_own_key(valve_on, monkeypatch):
    """لا مفتاحَ واحدٌ يفتحها جميعاً: فتحُ الحتميّ لا يجرّ فتحَ غيره."""
    monkeypatch.setenv("SILK_GAP_RECOVER_SEASONALITY", "1")
    assert G.recoverer_enabled("seasonality") is True
    assert G.recoverer_enabled("distributors") is False


def test_web_search_is_structurally_off_and_has_no_key(valve_on, monkeypatch):
    """**مفتاحٌ يفتحه خطأٌ في التصميم لا خيارُ تشغيل.**"""
    assert G.recoverer_enabled("web_search") is False
    monkeypatch.setenv("SILK_GAP_RECOVER_WEB_SEARCH", "1")
    assert G.recoverer_enabled("web_search") is False, (
        "بحثُ الويب الحرّ صار قابلاً للفتح — مصدريّةٌ غير محدودة تملأ فجوةً "
        "معلنة، وهو ما يحظره عقد التأسيس")


def test_an_unclassified_recoverer_never_runs(valve_on):
    """مُستَرِدٌّ جديدٌ بلا تصنيفٍ لا يعمل — لا افتراضَ متساهل."""
    assert G.recoverer_enabled("mystery_source") is False


# ── كلُّ نقطة إرسالٍ محكومةٌ بصمّامها ────────────────────────────────────

def test_every_dispatch_site_is_gated():
    src = io.open(os.path.join(_ROOT, "silk_gap_recovery.py"),
                  encoding="utf-8").read()
    for name in _ALL:
        assert f'recoverer_enabled("{name}")' in src, (
            f"مُستَرِدٌّ بلا صمّامٍ عند نقطة إرساله: {name}")


def test_every_valve_is_documented():
    env = io.open(os.path.join(_ROOT, ".env.example"), encoding="utf-8").read()
    for name in ("wgi", "per_capita", "partner_shares", "tariff",
                 "seasonality", "distributors"):
        assert f"SILK_GAP_RECOVER_{name.upper()}=" in env, (
            f"صمّامٌ لا يعرفه المشغّل ليس مخرجاً: {name}")
    assert "SILK_GAP_RECOVER_WEB_SEARCH=" not in env, (
        "وُثِّق مفتاحٌ لبحث الويب — وهو مطفأٌ بنيوياً بلا مفتاح")


# ── الوسمُ يظهر، والقيمةُ لا تتغيّر ─────────────────────────────────────

def test_marking_preserves_the_value_and_declares_the_origin():
    dp = DataPoint(42.0, "World Bank", 0.8, "ملاحظة", "2026-01-01")
    G.mark_recovered(dp, "الواردات ÷ السكان")
    assert dp.value == 42.0, "القيمةُ تغيّرت — خرقُ عقد عدم الاختلاق"
    assert dp.retrieval_method == G.RECOVERED_METHOD
    assert "مُستَردّ" in dp.note and "الواردات ÷ السكان" in dp.note


def test_marking_twice_does_not_duplicate_the_tag():
    dp = DataPoint(1.0, "s", 0.5, "n", "")
    G.mark_recovered(dp, "م")
    G.mark_recovered(dp, "م")
    assert dp.note.count("مُستَردّ") == 1


def test_a_recovered_point_is_capped_like_agent_gathered_evidence():
    """«مُستَردّ» ليس رصداً مباشراً — فلا يُعرَض «✓ موثّق» كأنّه كذلك."""
    from silk_narrative import evidence_badge_for
    dp = DataPoint(42.0, "World Bank", 0.9, "n", "")
    G.mark_recovered(dp, "م")
    badge = evidence_badge_for(dp)
    assert not badge.startswith("✓"), (
        f"نقطةٌ مُستَردّةٌ تُعرَض رصداً مباشراً: {badge}")
