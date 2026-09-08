"""نصُّ الإيقاف المبكر يقول ما وقع فعلاً ويسمّي الغائب — بلاغ التحليل ٢٧.

الحادثة (بلاغ المالك 2026-08-29): صفُّ الدراسة عرض جملةً تناقض نفسها:

    «اكتملت البعثات **والتحليل** وحُفظا (رقم التحليل 27)؛ لم يُنتَج نصّ
     التقرير — الطبقة الفاشلة: **كاتب التقرير** — السبب: أوقفنا الدراسة
     مبكراً **قبل مرحلتي التحليل والكتابة**: … 2 من 5 … أكمل المصادر
     الغائبة …»

ثلاث مخالفات في جملةٍ واحدة:

١) «اكتمل التحليل» كذبة — عند الإيقاف المبكر لا يُنادى المحلل إطلاقاً
   (`silk_research_pipeline`: `analyst_skipped_early`)، والنصُّ كان ثابتاً
   مكتوباً صلباً بلا فرعٍ على `skip_reason`.
٢) «الطبقة الفاشلة: كاتب التقرير» تشخيصٌ خاطئ — `_empty_reason` عرف ثلاث
   حالاتٍ فقط وأسقط كلَّ ما عداها على الكاتب، بينما الإيقاف المبكر **ليس
   عطلَ طبقة**: هو رفضُ كفايةٍ مقصود قبل أيّ نداءٍ مدفوع.
٣) «أكمل المصادر الغائبة» بلا اسمِ غائب — والأسماء محسوبةٌ أصلاً في
   `silk_decision` (`missing_pillars` + `_AR`) ثمّ تُرمى عند بناء النصّ.

القاعدة العامّة المشتقّة: **لا نصَّ حالةٍ ثابتاً فوق فروعٍ متعدّدة — النصُّ
يُشتقّ من الحالة التي وقعت فعلاً**؛ وطلبُ فعلٍ من المستخدم يسمّي موضوعه.
"""
import silk_platform.engine_bridge as eb


def _result(skip_reason: str, *, failure_reason: str = "سبب معلن") -> dict:
    """نتيجةُ تشغيلةٍ بحثٍ عميقٍ بلا تقرير — الشكل الذي يقرؤه `_empty_reason`."""
    return {"analysis_id": 27,
            "data_economics": {"cost_usd_estimate": 0.22},
            "deep_research": {"report": {
                "report": None, "skipped": "writer",
                "skip_reason": skip_reason,
                "failure_reason": failure_reason}}}


# ═══════════ ١ — الإيقاف المبكر: لا ادّعاءَ تحليلٍ ولا اتّهامَ كاتب ══════════
def test_early_halt_text_never_claims_the_analyst_ran():
    """المحلل لم يُنادَ — فلا «اكتملت البعثات والتحليل» في نصٍّ يقرؤه المصنع."""
    txt = eb._empty_reason(_result("early_halt"))
    assert "والتحليل وحُفظا" not in txt, txt
    assert "اكتملت البعثات وحُفظت" in txt, txt
    assert "رقم التحليل 27" in txt, txt


def test_early_halt_is_not_reported_as_a_failed_layer():
    """رفضُ الكفاية ليس عطلاً — لا «الطبقة الفاشلة» ولا اتّهامَ الكاتب."""
    txt = eb._empty_reason(_result("early_halt"))
    assert "الطبقة الفاشلة" not in txt, txt
    assert "كاتب التقرير" not in txt, txt
    assert "لا لعطلٍ تقني" in txt, txt


def test_the_other_failure_branches_keep_naming_their_layer():
    """الفروعُ الحقيقية (عطلٌ فعليّ) تبقى كما هي — الإصلاح لا يعمّم صمتاً."""
    assert "الطبقة الفاشلة: طبقة التحليل الشامل" in eb._empty_reason(
        _result("analyst_call_failed"))
    assert "الطبقة الفاشلة: سقف الإنفاق" in eb._empty_reason(_result("budget"))
    # سببٌ غير معروف يبقى على الكاتب (السلوك القائم، لا تغيير).
    assert "الطبقة الفاشلة: كاتب التقرير" in eb._empty_reason(_result(""))


def test_seat_cost_and_resume_promise_survive_the_rewrite():
    """ما كان صادقاً يبقى حرفياً: المقعد والتكلفة ووعدُ الاستئناف."""
    txt = eb._empty_reason(_result("early_halt"))
    assert "أُرجع مقعد الإطلاق إلى باقتك" in txt
    assert "0.22$" in txt and "لا تُستردّ" in txt
    assert "تستأنف من المحفوظ" in txt


# ═══════════ ٢ — «أكمل المصادر الغائبة» تسمّي الغائب ═════════════════════════
def test_early_halt_failure_reason_names_the_missing_pillars():
    """نصُّ خطِّ الأنابيب يحمل أسماء الأعمدة الغائبة من قرار المحرّك نفسه."""
    import silk_decision
    src = open(__file__.replace(
        "tests/test_early_halt_reason_text.py",
        "silk_research_pipeline.py"), encoding="utf-8").read()
    # المصدرُ الواحد: التعريبُ يُستورَد من `silk_decision` لا يُنسَخ.
    assert "from silk_decision import _AR as _PILLAR_AR" in src
    assert "الجوانب الغائبة: " in src
    assert 'get("missing_pillars")' in src
    # وأسماءُ الأعمدة الخمسة موجودةٌ فعلاً في المصدر المُستورَد.
    assert set(silk_decision._AR) == {"market", "competition", "regulatory",
                                      "profit", "risk"}


def test_insufficient_pillars_decision_still_names_them_for_the_message():
    """القرارُ نفسه يُخرِج `missing_pillars` — مصدرُ الأسماء ليس تخميناً."""
    import silk_decision
    dec = silk_decision.decide({"coverage": 0.0, "pillar_inputs": {}})
    assert dec.get("insufficient_pillars") is True, dec.get("verdict")
    assert dec["missing_pillars"], dec
    assert all(k in silk_decision._AR for k in dec["missing_pillars"])


# ═══════════ ٣ — ما التقطته المراجعة الذاتية (§58) على هذه الموجة ════════════
def test_the_message_tail_survives_the_run_error_truncation():
    """القصُّ لا يبتلع المقعدَ المُرجَع ولا التكلفة ولا وعدَ الاستئناف.

    ملاحظةُ مراجعةٍ ذاتية: تسميةُ الجوانب الغائبة أطالت النصّ إلى ٥٦٩ حرفاً
    بينما `_finish_failure` يقصّ عند ٤٠٠ — فيسقط **ذيل** الرسالة، وهو أهمُّ
    ما يقرؤه المصنع (حصّته عادت، وكم دفع، وأن إعادة الإطلاق تستأنف).
    """
    detail = (
        "أوقفنا الدراسة مبكراً قبل مرحلتي التحليل والكتابة: ما جمعناه يغطي 2 "
        "من 5 جوانب يحتاجها القرار والحد الأدنى 3 — لا نكتب توصية فوق بيانات "
        "لا تكفي للحكم. الجوانب الغائبة: الملاءمة التنظيمية، هامش الربحية، "
        "أمان السوق (المخاطر). ما جُمع محفوظ؛ أكمل مصادر هذه الجوانب ثم أعد "
        "التشغيل وسيُستأنف من حيث توقف.")
    txt = eb._empty_reason(_result("early_halt", failure_reason=detail))
    assert len(txt) <= eb._REASON_MAX, len(txt)
    cut = txt[:eb._REASON_MAX]
    assert "أُرجع مقعد الإطلاق إلى باقتك" in cut
    assert "0.22$" in cut and "تستأنف من المحفوظ" in cut


def test_no_double_period_between_the_reason_and_its_tail():
    """سببٌ ينتهي بنقطةٍ لا يُنتِج «توقف.. أُرجع» على وجهٍ يقرؤه المصنع."""
    txt = eb._empty_reason(_result("early_halt", failure_reason="سببٌ منتهٍ."))
    assert ".." not in txt, txt


# ═══════════ ٤ — مرشّحو الكتالوج لا يُملأون إلا لرفضِ بوّابةِ بند ════════════
def test_catalog_candidates_are_only_offered_for_hs_gate_refusals():
    """الواجهة تقرأ `hs_candidates` كإشارةِ «الرفض الأخير بوّابةُ بند».

    ملاحظةُ مراجعةٍ ذاتية: ملؤها لرفضِ جهوزيةٍ أو سقفِ ميزانية يُنبِت زرَّ
    «اختر البند الجمركي» على صفٍّ لا علاقة له بالبند، فيعيد الإطلاقَ إلى
    الرفض نفسِه — طريقٌ مسدود جديد مكان القديم.
    """
    assert "hs_confidence_too_low" in eb._HS_GATE_CODES
    assert "hs_confirmation_needed" in eb._HS_GATE_CODES
    assert "unresolved_hs" in eb._HS_GATE_CODES
    for code in ("research_not_ready", "daily_usd_budget_exhausted",
                 "quota_exceeded", None):
        assert code not in eb._HS_GATE_CODES, code
    src = open(eb.__file__, encoding="utf-8").read()
    assert 'getattr(exc, "code", None) in _HS_GATE_CODES' in src


# ═══════════ ٥ — «الشامل بدل الترقيع»: أيُّ قياسٍ سقط، لا أيُّ عمود فقط ══════
def test_missing_pillars_name_their_missing_components():
    """اسمُ العمود وحده لا يقول ماذا يُصلِح المصنع — المكوّناتُ تُسمَّى معه.

    بلاغ المالك (التحليلان ٢٧/٢٨، مرّتين): «أكمل مصادر هذه الجوانب» تركته
    يسأل ويسألني عن بلوب التشغيلة في كل حادثة. المكوّناتُ الناقصة محسوبةٌ
    أصلاً (`silk_decision`: `pillars[k]["missing"]`) ومُعرَّبةٌ (`_parts_ar`)
    — نقلُها يُغلق الحلقة **مرّةً واحدة** بدل تشخيصٍ يدويّ كلَّ مرّة.
    """
    src = open(__file__.replace(
        "tests/test_early_halt_reason_text.py",
        "silk_research_pipeline.py"), encoding="utf-8").read()
    assert "from silk_decision import _AR as _PILLAR_AR, _parts_ar" in src
    assert '(_pillars.get(k) or {}).get("missing")' in src
    assert "الناقص: " in src


def test_the_component_names_are_readable_not_internal_keys():
    """ما يُطبَع أسماءُ قياساتٍ بلغةِ مصنع، لا مفاتيحُ كود."""
    import silk_decision
    dec = silk_decision.decide({"coverage": 0.4, "pillar_inputs": {
        "regulatory": {"tariff_applied_pct": 5.0,
                       "entry_requirements_count": 4},
        "risk": {"political_stability_wgi": 0.6, "regulatory_quality_wgi": 0.5,
                 "logistics_lpi": 3.2, "fx_volatility_pct": 4.0}}})
    assert dec.get("insufficient_pillars") is True
    parts = (dec["pillars"]["market"] or {}).get("missing") or []
    assert parts, dec["pillars"]["market"]
    txt = silk_decision._parts_ar(parts)
    assert "حجم واردات السوق" in txt, txt
    assert "tam_log" not in txt and "cagr" not in txt, txt


def test_truncation_eats_the_detail_not_the_tail():
    """كلُّ إثراءٍ لاحقٍ للسبب لا يبتلع المقعدَ والتكلفةَ ووعدَ الاستئناف.

    رفعُ السقف كلّما طال السببُ مطاردةٌ لا حلّ: الذيلُ يُحجَز أوّلاً والباقي
    للتفصيل. سببٌ مُفرِطُ الطول يُقصّ بـ«…» ويبقى الذيلُ كاملاً.
    """
    txt = eb._empty_reason(_result("early_halt", failure_reason="س" * 5000))
    assert len(txt) <= eb._REASON_MAX, len(txt)
    assert txt.endswith("لا إعادة للبعثات ولا دفع مضاعف.")
    assert "أُرجع مقعد الإطلاق إلى باقتك" in txt
    assert "0.22$" in txt


def test_a_short_reason_is_not_clipped_at_all():
    """القصُّ لا يعمل إلا عند الحاجة — السببُ القصير يمرّ حرفياً."""
    txt = eb._empty_reason(_result("early_halt", failure_reason="سببٌ قصير"))
    assert "…" not in txt
    assert "السبب: سببٌ قصير." in txt


# ═══════════ ٦ — القفل الطرفيّ الذي غاب (ملاحظة مراجعةٍ ذاتية) ══════════════
def _realistic_early_halt_detail() -> str:
    """نصُّ السبب كما يبنيه خطُّ الأنابيب فعلاً من قرارٍ حقيقيّ — لا سلسلةٌ
    مصطنعة. الملاحظة التي أنتجت هذا القفل: اختبارٌ بـ٥٠٠٠ حرفٍ يمرّ بينما
    الحالةُ **العاديّة** (٥٦٣ حرفاً) كانت تُقصّ وسط الكلمة."""
    import silk_decision as D
    dec = D.decide({"coverage": 0.4, "pillar_inputs": {
        "regulatory": {"tariff_applied_pct": 5.0,
                       "entry_requirements_count": 4},
        "risk": {"political_stability_wgi": 0.6,
                 "regulatory_quality_wgi": 0.5,
                 "logistics_lpi": 3.2, "fx_volatility_pct": 4.0}}})
    p = dec["pillars"]
    miss = "؛ ".join(
        f"{D._AR[k]}" + (f" (الناقص: {D._parts_ar(p[k]['missing'])})"
                         if p[k].get("missing") else "")
        for k in dec["missing_pillars"])
    return ("أوقفنا الدراسة مبكراً قبل مرحلتي التحليل والكتابة: ما جمعناه "
            f"يغطي {dec['computed_pillars']} من 5 جوانب يحتاجها القرار والحد "
            f"الأدنى {dec['min_scored_pillars']} — لا نكتب توصية فوق بيانات "
            f"لا تكفي للحكم. الجوانب الغائبة: {miss}. ما جُمع محفوظ؛ أكمل "
            "مصادر هذه الجوانب ثم أعد التشغيل وسيُستأنف من حيث توقف.")


def test_the_realistic_message_is_never_clipped_at_all():
    """الحالةُ العاديّة تمرّ كاملةً: كلُّ عمودٍ غائبٍ بقياساته، والذيلُ سليم."""
    txt = eb._empty_reason(
        _result("early_halt", failure_reason=_realistic_early_halt_detail()))
    assert "…" not in txt, txt
    assert len(txt) <= eb._REASON_MAX, len(txt)
    for pillar in ("جاذبية السوق", "شدة المنافسة", "هامش الربحية"):
        assert pillar in txt, pillar
    assert "حجم واردات السوق" in txt and "موقع سعرك مقابل السوق" in txt
    assert txt.count("(") == txt.count(")"), txt          # لا قوسَ مفتوح
    assert "أكمل مصادر هذه الجوانب" in txt
    assert txt.endswith("لا إعادة للبعثات ولا دفع مضاعف.")


def test_an_over_long_reason_is_cut_at_a_sentence_boundary():
    """الحالةُ الشاذّة تُقصّ عند حدّ جملة لا وسطَ كلمة (قاعدة نصّ العميل)."""
    long_detail = _realistic_early_halt_detail() + " " + ("جملةٌ زائدة. " * 60)
    txt = eb._empty_reason(_result("early_halt", failure_reason=long_detail))
    assert len(txt) <= eb._REASON_MAX
    body = txt.split(" — السبب: ", 1)[1].split(". أُرجع مقعد", 1)[0]
    assert not body.endswith("…"), body          # المقصّ بلا نقاط حذف
    assert body.rstrip()[-1] not in "ـ", body
    assert txt.endswith("لا إعادة للبعثات ولا دفع مضاعف.")


def test_the_failure_class_sits_in_the_head_so_clipping_never_eats_it():
    """نوعُ العطل ورمزُ HTTP أوّلُ ما يحتاجه المشخِّص — فلا يُقصّان."""
    res = _result("analyst_call_failed", failure_reason="س" * 4000)
    res["deep_research"]["report"]["error_type"] = "timeout"
    res["deep_research"]["report"]["status_code"] = 529
    txt = eb._empty_reason(res)
    assert "(timeout)" in txt and "[HTTP 529]" in txt
    assert txt.index("(timeout)") < txt.index("السبب:")


def test_no_clipped_message_ever_leaves_an_open_bracket():
    """ملاحظةُ مراجعةٍ ذاتية: المقصُّ يكسر عند الفاصلة العربية — وهذه الموجة
    وضعت فواصلَ عربية **داخل** قوس «(الناقص: أ، ب، ج)»، فكان القصُّ ينتج
    القوسَ المفتوح الذي يقول تعليقُه إنه يمنعه. كلُّ طولٍ ممكن يُفحَص."""
    base = _realistic_early_halt_detail()
    padded = base + " ذيلٌ إضافيّ. " * 20
    for n in range(40, len(base) + 200, 7):
        txt = eb._empty_reason(_result("early_halt", failure_reason=padded[:n]))
        assert txt.count("(") == txt.count(")"), (n, txt)
        assert len(txt) <= eb._REASON_MAX, (n, len(txt))
        assert txt.endswith("لا إعادة للبعثات ولا دفع مضاعف.")
