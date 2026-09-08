"""البرهانُ البنيويّ: لا تصنيفٌ خاطئ يُعتمَد تلقائياً — never auto-approve wrong.

عيّنةٌ من الحالات تُثبِت أن العيوبَ المعروفة أُغلِقت؛ **هذا الملفّ يُثبِت
الخاصيّة نفسها** على فضاءٍ مولَّدٍ من المرجع كلّه، فلا يبقى الأمانُ رهنَ قائمةٍ
كتبها إنسانٌ يتذكّر ما فكّر فيه.

الخاصيّةُ المحروسة — **كلُّ** اعتمادٍ تلقائيّ (`approved` بلا تأكيدٍ بشريّ)
يجب أن يستوفي الأربعة معاً:

  ١) تأكيدٌ دلاليّ إيجابيّ  (`confirmed is True`)
  ٢) صفرُ تناقضات          (نفي / حالةُ تصنيع / صفرُ تداخل / خارج النطاق)
  ٣) ثقةٌ **رقمية** فوق العتبة
  ٤) فارقٌ كافٍ عن المرشّح الثاني (لا اعتمادَ على تعادل)

وأيُّ اعتمادٍ يخرق واحدةً منها عيبٌ يُحمِّر السويت — بمعزلٍ عن أيّ منتجٍ بعينه.
"""
import random

import pytest

import silk_hs_norm as N
import silk_hs_pipeline as P
from silk_hs_resolver import load_hs_codes

_SEED = 20260830          # حتميّةٌ تامّة: نفسُ العيّنة في كل تشغيل (البند ١٠)
_SAMPLE = 220             # صفوفٌ من المرجع تُولَّد منها الاستعلامات


def _invariants(out: dict, probe: str) -> None:
    """افحص الأربعةَ على مخرجٍ واحد — تُستدعى من كل اختبارٍ أدناه."""
    if out["classification_status"] != P.APPROVED:
        return
    if out["classification_method"] == P.METHOD_USER_CONFIRMED:
        return                       # قرارُ إنسانٍ، لا اعتمادٌ تلقائيّ
    code = out["final_hs_code"]
    assert code, (probe, out)
    top = next((c for c in out["candidate_codes"] if c["hs6"] == code), None)
    assert top is not None, (probe, "الرمزُ المُعتمَد ليس من المرشّحين", out)
    assert top["confirmed"] is True, (probe, code, top)
    assert not top["contradictions"], (probe, code, top["contradictions"])
    assert isinstance(out["confidence"], float), (probe, out["confidence"])
    assert out["confidence"] >= P.min_confidence(), (probe, out["confidence"])
    rivals = [c for c in out["candidate_codes"]
              if c["hs6"] != code and c["offer"]
              and c["score"] >= P.min_confidence()]
    for r in rivals:
        assert top["score"] - r["score"] >= P.min_separation(), (
            probe, code, r["hs6"], top["score"], r["score"])


@pytest.fixture(scope="module")
def rows():
    return load_hs_codes()


def _arabic_keys(row) -> list[str]:
    return [k.strip() for k in (row.get("keywords_ar") or "").split(";")
            if k.strip() and N.is_arabic(k)]


# ═══════════ ١ — كلُّ اعتمادٍ يستوفي الأربعة، على فضاءٍ من المرجع ════════════
def test_every_auto_approval_over_the_reference_satisfies_the_invariants(rows):
    """استعلاماتٌ مولَّدةٌ من مفاتيح المرجع نفسه — الفضاءُ الذي يعيش فيه العيب."""
    rng = random.Random(_SEED)
    keyed = [r for r in rows if _arabic_keys(r)]
    assert len(keyed) > 100, len(keyed)
    checked = 0
    for row in rng.sample(keyed, min(_SAMPLE, len(keyed))):
        for key in _arabic_keys(row)[:2]:
            for probe in (key, key + " فاخر", "ال" + key, key.replace("ة", "ه")):
                _invariants(P.classify(probe), probe)
                checked += 1
    assert checked > 400, checked


def test_adversarial_containment_probes_never_auto_approve(rows):
    """استعلاماتٌ مصنوعةٌ لتصطاد العيب: مفتاحٌ قصير مدفونٌ داخل كلمةٍ أطول.

    هذا هو مولّدُ الحادثة: «رقي» ⇒ «سرقية»/«ورقية». لو عاد فرعُ الاحتواء
    الحرفيّ يوماً، هذا الاختبارُ يحمرّ على **كلّ** صفٍّ قصيرِ المفتاح دفعةً
    واحدة — لا على الصفّ الذي اشتكى منه أحدٌ.
    """
    rng = random.Random(_SEED + 1)
    short = [(r, k) for r in rows for k in _arabic_keys(r)
             if 3 <= len(N.normalize(k)) <= 5 and " " not in N.normalize(k)]
    assert len(short) > 20, len(short)
    for row, key in rng.sample(short, min(120, len(short))):
        k = N.normalize(key)
        for probe in (f"س{k}ية", f"م{k}ات", f"{k}ونية"):
            out = P.classify(probe)
            _invariants(out, probe)
            # وتحديداً: لا يُعتمَد صفُّ المفتاح المدفون لهذا الاستعلام.
            if out["classification_status"] == P.APPROVED:
                assert out["final_hs_code"] != row["hs_code"], (
                    probe, key, row["hs_code"])


def test_nonsense_input_never_auto_approves():
    """محارفُ بلا معنى ⇒ لا اعتمادَ أبداً (ولا انهيار)."""
    for probe in ("qwxzptvbmzzz", "زخثصضطظ", "١٢٣٤٥", "!!!???", "ااااااا",
                  "x", "منتج", "شيء ما", "abcdefgh ijklmnop"):
        out = P.classify(probe)
        _invariants(out, probe)
        assert out["classification_status"] != P.APPROVED, (probe, out)


# ═══════════ ٢ — رمزُ الكتالوج لا يشتري اعتماداً ═════════════════════════════
def test_no_catalog_code_is_auto_approved_without_its_own_evidence(rows):
    """رمزٌ مخزَّنٌ عشوائيٌّ مع اسمٍ لا يخصّه ⇒ لا اعتمادَ تلقائيّ أبداً.

    هذه هي العائلةُ التي أنتجت حادثةَ الدراسة #10 (رمزُ حليبٍ قديم بنى دراسةً
    كاملة): الاعتمادُ يجب أن يُشترى بالدليل لا بالتخزين.
    """
    rng = random.Random(_SEED + 2)
    codes = [str(r["hs_code"]) for r in rows if len(str(r["hs_code"])) == 6]
    names = ["حلاوة طحينية", "مناديل ورقية", "عسل سدر", "دجاج مجمد", "معكرونة"]
    for name in names:
        settled = P.classify(name)["final_hs_code"]
        for code in rng.sample(codes, 40):
            if code == settled:
                continue          # الاتفاقُ حالةٌ مشروعة تُقاس في مكانها
            out = P.classify(name, code)
            _invariants(out, f"{name}|{code}")
            assert out["final_hs_code"] != code, (
                name, code, out["classification_status"],
                "رمزُ كتالوجٍ لا يخصّ المنتج اعتُمِد")


# ═══════════ ٣ — الحوادث المرصودة، صراحةً ════════════════════════════════════
@pytest.mark.parametrize("product,never", [
    ("مناديل ورقية", "080711"),      # بطيخ — الحادثة المُبلَّغة
    ("منديل ورقي", "080711"),
    ("حلاوة طحينية", "110100"),      # دقيق قمح — الدرس ٢٠٥
    ("طحينة", "110100"),
    ("زبدة الفول السوداني", "040510"),  # زبدة ألبان — حادثة التأسيس
    ("عصير برتقال", "080510"),       # برتقال طازج — حارسُ حالة التصنيع
    ("سمسم", "200819"),              # بذورٌ محضّرة لبذرةٍ خام
])
def test_the_recorded_incidents_can_never_auto_approve_again(product, never):
    out = P.classify(product)
    assert out["final_hs_code"] != never, (product, out)
    _invariants(out, product)
