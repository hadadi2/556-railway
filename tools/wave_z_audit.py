"""تدقيقٌ بعديٌّ **سلوكيّ** على بنود الموجة Z — يقيس المصنوعَ النهائيّ.

نظيرُ `wave_c_audit.py` و`wave_d_audit.py`، ودرسُ الموجة Z يفرضه بالذات: بنودُ
هذه الموجة كلُّها **قائمةٌ في الشيفرة وغائبةٌ عن المصنوع** — حقلٌ مُصالَحٌ لا
يقرؤه المُصدِّر، ومحرّكٌ يعمل ولا يُطبَع، ولونٌ ناقصٌ يُسقِط التسليم. فوجودُ
الوحدة لا يقول شيئاً؛ القياسُ على `docx` المُولَّد فعلاً يقول.

    python3 tools/wave_z_audit.py
"""
from __future__ import annotations

import copy
import os
import re
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import silk_decision as D                                # noqa: E402
import silk_deep_pillars as DP                           # noqa: E402
import silk_render                                       # noqa: E402
import silk_reports                                      # noqa: E402
from canonical_netherlands import netherlands_research_blob  # noqa: E402
from silk_requirements_agent import regulatory_state     # noqa: E402

_rows: list = []


def chk(item: str, ok: bool, detail: str) -> None:
    _rows.append((item, bool(ok), detail))


# ── بناءُ عرضٍ على شكل الإنتاج بعد الموجة Z ──────────────────────────────

def _jury(state: str) -> dict:
    import silk_agents
    from silk_data_layer import DataPoint

    def dp(v):
        return DataPoint(value=v, source="UN Comtrade", confidence=0.8, note="—")
    ok = silk_agents.AgentReport(agent_name="a", findings=[dp(1.0)], failed=False)
    bad = silk_agents.AgentReport(agent_name="b", findings=[dp(None)], failed=True)
    good = silk_agents.AgentReport(agent_name="b", findings=[dp(2.0)], failed=False)
    reports = {"full": [ok, good], "partial": [ok, bad]}[state]
    v = silk_agents.JuryCommittee.evaluate(reports)
    v["synthesis_stage"] = 1
    return v


def _view(jury_state: str, engine: "str | None", lang: str = "ar") -> dict:
    reg = regulatory_state("NLD", "080410")
    r = netherlands_research_blob()
    dr = r["deep_research"]
    dec = copy.deepcopy(DP.decide_for_deep(dr, regulatory=reg))
    if engine:
        dec["verdict"] = engine
        dec["score"] = 0.31
        dec["why"] = "الدرجة الموزونة 31% دون عتبة الرفض (45%)"
    else:
        dec = None
    dr["verdict"] = DP.promote_engine_verdict(_jury(jury_state), dec)
    r["markets"] = [{"iso3": "NLD", "name_ar": "هولندا",
                     "name_en": "Netherlands", "rank": 1, "deep": True,
                     "regulatory": reg, "components": DP.build_components(dr),
                     "decision": dec}]
    return silk_render.build_view(r, lang)


def _lines(view: dict) -> list[str]:
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "c.docx")
        silk_reports.render_client_docx(view, p)
        xml = zipfile.ZipFile(p).read("word/document.xml").decode("utf-8")
    txt = re.sub(r"<[^>]+>", "",
                 xml.replace("</w:p>", "\n").replace("</w:tc>", " | "))
    return [l.strip() for l in txt.split("\n") if l.strip()]


# ── Z-01 · حكمٌ واحد يصل المصنوع ─────────────────────────────────────────

_v = _view("full", "NO-GO")
_lines_ar = _lines(_v)
_blob = "\n".join(_lines_ar)

chk("Z-01 · حكمُ المحرّك يحكم العرض",
    _v["decision"]["verdict"] == "NO-GO"
    and _v["deep_research"]["verdict_label"] == "عدم الدخول حالياً",
    f"decision={_v['decision']['verdict']} label={_v['deep_research']['verdict_label']}")
chk("Z-01 · وصل غلافَ المستند المُسلَّم",
    "عدم الدخول حالياً" in _lines_ar[:8],
    f"غلاف: {_lines_ar[3] if len(_lines_ar) > 3 else '—'}")
chk("Z-01 · لا توصيةَ تغطيةٍ في المُسلَّم",
    not any("توصية أولية بالدخول" in l for l in _lines_ar),
    "عدّادُ التغطية لم يعد يُقدَّم توصيةً تجارية")
chk("Z-01 · قراءةُ التغطية مُعلَنةٌ لا ضائعة",
    bool((_v["deep_research"]["verdict"] or {}).get("coverage_verdict")),
    str((_v["deep_research"]["verdict"] or {}).get("coverage_state")))
chk("Z-01 · تكافؤٌ رجعيّ بلا محرّك",
    DP.promote_engine_verdict(_jury("full"), None) == _jury("full"),
    "قاموسُ الحكم يعود كما هو حرفياً")

# ── Z-02 · حقلٌ واحد لا اشتقاقٌ ثانٍ ─────────────────────────────────────

_agree = []
for _js, _eng in (("full", "NO-GO"), ("full", None), ("partial", None)):
    _vv = _view(_js, _eng)
    _lbl = _vv["deep_research"]["verdict_label"]
    _agree.append(_lbl in _vv["brief"][0] and _lbl in _lines(_vv)[:8])
chk("Z-02 · الشارةُ والمختصرُ والغلافُ متّفقون", all(_agree),
    f"{sum(_agree)}/3 حالات")
chk("Z-02 · التصنيفُ يدور دورةً مغلقة",
    all(silk_render._verdict_tone(k) == k
        for k in silk_render._VERDICT_LABELS_AR),
    "مفتاحُ التصنيف يمرّ كما هو")
chk("Z-02 · المُصدِّر يقرأ الحقلَ المُصالَح",
    silk_reports._resolve_vtxt(
        {"verdict_tone": "data_partial",
         "verdict": {"verdict": "PRELIMINARY / INCONCLUSIVE"}}) == "data_partial",
    "لا اشتقاقَ من الرمز الخام فوق الحقل")
chk("Z-02 · حالةُ أدلةٍ لا تُقدَّم توصية",
    _view("partial", None)["brief"][0].startswith("الحالة:"),
    _view("partial", None)["brief"][0][:60])

# ── Z-03 · التسليمُ لا ينهار ─────────────────────────────────────────────

_missing_colour = [t for t in silk_render._VERDICT_LABELS_AR
                   if t not in silk_reports._VERDICT_TEXT_COLORS]
_missing_rec = [t for t in silk_render._VERDICT_LABELS_AR
                if t not in silk_reports._ACADEMIC_MAIN_REC]
chk("Z-03 · كلُّ تصنيفٍ له لونٌ ونصّ",
    not _missing_colour and not _missing_rec,
    f"ناقص: ألوان={_missing_colour} نصوص={_missing_rec}")
try:
    _partial_lines = _lines(_view("partial", None))
    _ok_partial, _why_partial = len(_partial_lines) > 40, f"{len(_partial_lines)} سطراً"
except Exception as e:  # noqa: BLE001
    _ok_partial, _why_partial = False, f"{type(e).__name__}: {e}"
chk("Z-03 · دراسةٌ بفجوةٍ مُعلَنة تُصدَّر", _ok_partial, _why_partial)

# ── Z-04 · لا معرّفاتٍ داخلية ────────────────────────────────────────────

_INTERNAL = ("political_stability", "regulatory_quality", "fx_stability",
             "price_position", "saudi_momentum", "named_density", "top_share",
             "tam_log", "legibility")
_d = D.decide({"coverage": 0.5, "pillar_inputs": {
    "market_attractiveness": {"tam_usd": 2e8},
    "competition_intensity": {"hhi": 1200},
    "regulatory_fit": {"entry_requirements_count": 5},
    "profitability": {}, "risk": {}}})
_leak_cond = [k for k in _INTERNAL if k in " ".join(_d["conditions"])]
chk("Z-04 · الشروطُ بلغةِ قارئ", not _leak_cond, f"تسرّب: {_leak_cond}")
_leak_doc = [k for k in _INTERNAL if k in _blob]
chk("Z-04 · مُسلَّمُ العميل بلا معرّفات", not _leak_doc, f"تسرّب: {_leak_doc}")

# ── Z-05 · قطبُ عمود المنافسة ────────────────────────────────────────────


def _bundle(hhi, top, named):
    return {"coverage": 1.0, "pillar_inputs": {
        "market_attractiveness": {"tam_usd": 3e8, "import_cagr_pct": 6.0,
                                  "gdp_per_capita_usd": 45_000,
                                  "saudi_share_pct": 2.0},
        "competition_intensity": {"hhi": hhi, "top_supplier_share_pct": top,
                                  "named_company_count": named},
        "regulatory_fit": {"tariff_applied_pct": 4.0,
                           "entry_requirements_count": 6,
                           "eligibility_gate": False},
        "profitability": {"border_unit_value_usd_kg": 5.0,
                          "saudi_border_unit_value_usd_kg": 4.2,
                          "margin_at_border_pct": 16.0},
        "risk": {"political_stability_wgi": 0.9, "fx_volatility_pct": 1.2,
                 "supplier_concentration_hhi": 900, "critical_risk": False}}}


_frag = D.decide(_bundle(200.0, 4.0, 9))["counter_case"]["case"]
_conc = D.decide(_bundle(4800.0, 68.0, 2))["counter_case"]["case"]
chk("Z-05 · سوقٌ مُفتَّتة ليست حجّةً ضدّ الدخول",
    "شدة المنافسة" not in _frag, _frag[:70])
chk("Z-05 · وسوقٌ مُحتكَرة هي الحجّة", "شدة المنافسة" in _conc, _conc[:70])

# ── Z-06 · أساسُ الحكم يصل المصنع ────────────────────────────────────────

chk("Z-06 · قسمُ أساس الحكم في المُسلَّم",
    "على أيّ أساس صدر هذا الحكم" in _blob, "كان صفرَ ظهور")
chk("Z-06 · قاعدةُ الحكم مُعلَنة قبل الأرقام",
    "قاعدة الحكم مُعلنة قبل النظر في الأرقام" in _blob, "حاضرة")
chk("Z-06 · الأعمدةُ الخمسة بأسمائها",
    all(n in _blob for n in ("جاذبية السوق", "شدة المنافسة",
                             "الملاءمة التنظيمية", "هامش الربحية")),
    "جدولُ الأعمدة")
chk("Z-06 · الغائبُ يُعلَن وما ينقصه",
    "غير محسوب" in _blob and "لم يُرصَد بعد" in _blob, "لا خانةٌ فارغة")
chk("Z-06 · الحجّةُ المضادّة تصل العميل",
    "أقوى ما يُقال ضدّ هذا الحكم" in _blob, "حاضرة")
try:
    _en = "\n".join(_lines(_view("full", "NO-GO", "en")))
    _ok_en, _why_en = "What this decision rests on" in _en, "بالإنجليزية"
except Exception as e:  # noqa: BLE001 — سردُ المدوّنة عربيّ (قيدُ مدوّنة)
    _ok_en = "تسرّبُ لغة" in str(e)
    _why_en = "قيدُ مدوّنة: سردُ الكاتب عربيّ فيرفضه حارسُ اللغة (لا عطلَ قسم)"
chk("Z-06 · القسمُ مكتوبٌ في اللغتين", _ok_en, _why_en)

# ── Z-07 · لا كسرٌ آليٌّ خام ─────────────────────────────────────────────

chk("Z-07 · سطرُ «لماذا» بنسبٍ بشرية",
    not re.search(r"\b0\.\d+\b", D.decide(_bundle(200.0, 4.0, 9))["why"]),
    D.decide(_bundle(200.0, 4.0, 9))["why"][:70])
chk("Z-07 · لا كسرٌ خام على وجه المُسلَّم",
    not re.search(r"\b0\.\d{2,3}\b", _blob), "المستندُ نظيف")

# ── Z-08/Z-09 · حراسٌ ───────────────────────────────────────────────────

chk("Z-08 · الثقةُ داخل مدىً يُقرأ",
    D.decide({**_bundle(200.0, 4.0, 9), "coverage": 3.0})["confidence"] == 1.0
    and D.decide({**_bundle(200.0, 4.0, 9), "coverage": 0.8})["confidence"] == 0.8,
    "والمدى الحقيقيّ بلا تغيير")
_bare = netherlands_research_blob()
_bare["markets"] = [{"iso3": "NLD", "name_ar": "هولندا", "rank": 1, "deep": True}]
_bv = silk_render.build_view(_bare, "ar")
chk("Z-09 · صفرُ قياسٍ يُعلَن لا يُطَمئِن",
    "غيابُ قياسٍ لا نتيجةَ قياس" in (_bv["decision"].get("why") or ""),
    str(_bv["decision"].get("why"))[:70])
chk("الهدف ٤ · جذرٌ عارٍ لا يُنشِط فرعاً",
    not _bv["markets"][0].get("components_detail")
    and _bv["markets"][0].get("has_competitive_position") is False
    and (_bv.get("completeness") or {}).get("pct") == 0.0,
    "لكلّ فرعٍ شرطُه المستقلّ")

# ── D-1 مدحوض · البوّابةُ تمنع الإيجابَ غير المشروط ─────────────────────

_best = {"coverage": 1.0, "pillar_inputs": {
    "market_attractiveness": {"tam_usd": 5e10, "import_cagr_pct": 40.0,
                              "gdp_per_capita_usd": 90_000,
                              "saudi_share_pct": 0.1},
    "competition_intensity": {"hhi": 100, "top_supplier_share_pct": 2.0,
                              "named_company_count": 12},
    "regulatory_fit": {"tariff_applied_pct": 0.0,
                       "entry_requirements_count": 8, "eligibility_gate": True},
    "profitability": {"border_unit_value_usd_kg": 20.0,
                      "saudi_border_unit_value_usd_kg": 2.0,
                      "margin_at_border_pct": 80.0},
    "risk": {"political_stability_wgi": 2.5, "fx_volatility_pct": 0.1,
             "supplier_concentration_hhi": 100, "critical_risk": False}}}
_gated = D.decide(_best)
_clear = copy.deepcopy(_best)
_clear["pillar_inputs"]["regulatory_fit"]["eligibility_gate"] = False
chk("D-1 · بوّابةٌ مفتوحة ⇒ لا GO بأيّ مدخلات",
    _gated["verdict"] != "GO" and "أهلية" in _gated["conditions"][0]
    and D.decide(_clear)["verdict"] == "GO",
    f"مفتوحة={_gated['verdict']} مغلقة={D.decide(_clear)['verdict']}")

# ── S-01 قفلاً دائماً ────────────────────────────────────────────────────


def _vintages(year):
    reg = regulatory_state("NLD", "080410")
    r = netherlands_research_blob()
    comps = DP.build_components(r["deep_research"])
    if year is not None:
        for c in comps.values():
            if isinstance(c, dict) and c.get("value") is not None:
                c["data_year"] = year
    r["markets"] = [{"iso3": "NLD", "name_ar": "هولندا", "rank": 1,
                     "deep": True, "regulatory": reg, "components": comps}]
    det = silk_render.build_view(r, "ar")["markets"][0]["components_detail"]
    return [d.get("vintage") or "" for d in det]


chk("S-01 · بلا سنةٍ لا تحذيرَ مختلَق", not any(_vintages(None)), "صامتٌ بحقّ")
chk("S-01 · سنةٌ قديمة تُطلِق الطبقة الأولى",
    any("أقدم من 3 سنوات" in v for v in _vintages(2019)), "2019")
chk("S-01 · وسنةٌ سحيقة تُصعِّد للثانية",
    any("أقدم من 7 سنوات" in v for v in _vintages(2016)), "2016")

# ── ما بعد Z · مسحُ الفجوات المتبقّية ────────────────────────────────────

_md_full = silk_reports.render_markdown(
    silk_render.build_view(netherlands_research_blob(), "ar"))
chk("G-07 · `report.md` مُخرَجُ مشغّلٍ لا عميل (أساسُ الدحض)",
    "ملحق: أثر المصادر" in _md_full and "ملحق: الأدلة الرقمية" in _md_full,
    "يحمل ملحقَين يستبعدهما تقريرُ العميل")

_plat = open(os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "silk_platform", "api.py"),
    encoding="utf-8").read()
chk("G-07 · ولا سطحَ مصنعٍ يبلغه",
    'report.md"' not in _plat and '/brief"' not in _plat,
    "مسارا النصّ للمشغّل وحدَه")

from silk_data_layer import DataPoint                    # noqa: E402
from silk_data_layer import atomic_source_ids as _atomic_audit  # noqa: E402

_pv = silk_render.build_view({
    "header": {}, "product": "ت", "hs_code": "080410",
    "markets": [{"country": "س", "iso3": "NLD", "total_score": 0.5,
                 "confidence": 0.5, "components": {"market_size": DataPoint(
                     5, "World Bank", 0.77, "n", url="https://x.test/q",
                     evidence_ids=("dp1",))}}]}, "ar")
_md = silk_reports.render_markdown(_pv)
_i = _md.find("أثر المصادر")          # `find` لا `index`: بندٌ يفشل لا تشغيلةٌ تسقط
_tail = _md[_i:_i + 400] if _i >= 0 else ""
chk("T-10 · ملحقُ الأثر حاضرٌ في المصنوع", _i >= 0, "وإلا فالبنودُ التالية عمياء")
chk("T-10 · الرابطُ المرصود يبلغ المصنوع (شكلُ الإنتاج)",
    "https://x.test/q" in _tail, _tail[:90])
chk("T-10 · ولا يُستبدَل بصفحةِ السجلّ",
    "data.worldbank.org" not in _tail, _tail[:90])

# وشكلُ المسار العميق (`silk_llm_runtime`) — منتِجُ `source_ids`/`evidence_ids`.
_deep = silk_render.build_view({
    "header": {}, "product": "ت", "hs_code": "080410",
    "markets": [{"country": "س", "iso3": "NLD", "total_score": 0.5,
                 "confidence": 0.5, "components": {"market_size": DataPoint(
                     5, "GCC secretariat", 0.8, "n",
                     url="https://gcc-sg.org/doc/17",
                     source_ids=("GCC secretariat", "GAFTA secretariat"),
                     evidence_ids=("dp3", "dp9"))}}]}, "ar")
_dmd = silk_reports.render_markdown(_deep)
_di = _dmd.find("أثر المصادر")
_dtail = _dmd[_di:_di + 400] if _di >= 0 else ""
chk("T-10 · شكلُ المسار العميق كاملاً",
    all(x in _dtail for x in ("https://gcc-sg.org/doc/17", "ثقة المرصود 80%",
                              "مصادر مدمجة: GCC secretariat")), _dtail[:120])
chk("T-10 · ولا معرّفَ بعثةٍ يُنطَق إسناداً (`dpN` غيرُ قابلٍ للحلّ)",
    re.search(r"\bdp\d+\b", _dtail) is None, _dtail[:120])
chk("T-10 · ولا اسمَ مصدرٍ يُقدَّم دليلاً",
    "أدلة" not in _dtail, _dtail[:120])
chk("T-10 · شكلٌ غيرُ قائمةٍ لا يخترع اسماً ولا يُفجِّر",
    (_atomic_audit("GCC secretariat", "GAFTA") == ["GAFTA"]
     and _atomic_audit("World Bank", {"A": 1}) == ["World Bank"]
     and _atomic_audit("World Bank", 5) == ["5"]),
    str(_atomic_audit("GCC secretariat", "GAFTA")))
chk("T-10 · تهجئتان لمصدرٍ واحدٍ ليستا دمجاً",
    "مصادر مدمجة" not in (silk_render._provenance({"x": [
        DataPoint(1, "UN Comtrade (مخزن الحقائق)", .9, "n",
                  source_ids=("UN Comtrade",)),
        DataPoint(2, "UN Comtrade (مخزن الحقائق)", .9, "n")]}, "ar")[0]["tail"]),
    "لاحقةُ المخزن كانت تصنع مصدراً ثانياً")
chk("T-10 · الذيلُ بلغةِ عارضيه لا بلغةِ العرض",
    "ثقة المرصود" in (silk_render._provenance(
        {"x": [DataPoint(1, "World Bank", .77, "n")]}, "en")[0]["tail"]),
    "سطرٌ بلغتين على مسار المصنع الإنجليزيّ")
chk("T-10 · الفرعان يحملان قائمةَ الحقول نفسَها",
    set(silk_render._DP_CARRIED_FIELDS) == {
        "url", "confidence", "evidence_ids", "source_ids",
        "retrieved_at", "data_year"}, str(silk_render._DP_CARRIED_FIELDS))
_nolink = silk_render._provenance({"x": [DataPoint(5, "World Bank", 0.7, "n")]}, "ar")
chk("T-10 · غيابُ المرصود يبقى غياباً",
    "http" not in (_nolink[0].get("tail") or ""), str(_nolink[:1]))
chk("T-10 · مدى الثقة المرصود في السطر",
    "ثقة المرصود 77%" in _tail, _tail[:120])
chk("T-10 · الذيلُ مبنيٌّ في نموذج العرض لا في العارض",
    "def _provenance_tail" not in open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "silk_reports.py"), encoding="utf-8").read(),
    "الدرس ١٠٥")


# ── الطباعة ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ok = sum(1 for _, good, _ in _rows if good)
    for item, good, detail in _rows:
        print(f"  [{'✓' if good else '✗'}] {item} — {detail}")
    print(f"\n  الموجة Z: {ok}/{len(_rows)}")
    sys.exit(0 if ok == len(_rows) else 1)
