"""جسم تشغيلة `/research` — the deep-research pipeline body (البند ٧).

**لماذا وُجد هذا الملف (تدقيق 2026-08-27، البند ٧).** `api.create_app` كان
إغلاقاً واحداً بطول ~٤٬٠٦٠ سطراً يضمّ ٣٦ مساراً وعشرات الدوالّ المتداخلة —
وأثقلها `_run_research_pipeline` (٧٠٧ أسطر، ثمانية كوميتات داخله) ومعه سبع
دوالّ لا يستعملها غيره. منطقُ محرّكٍ بهذا الحجم داخل ملف المسارات **لا
يُختبَر معزولاً**، وهو في آنٍ أكثرُ ملفّات الريبو تغيّراً (٢٤ تغييراً).

**ما جرى بالضبط: نقلٌ حرفيّ.** الدوالّ الثماني + الثابت `_TRANSIENT_HTTP_
STATUSES` انتقلت **بنصّها ومسافتها البادئة كما هي**، من إغلاق `create_app`
إلى إغلاق `build` أدناه — نفس عمق التعشيش، فلا سطر منطق تغيّر ولا توقيع
تبدّل. لا سلوك جديد، ولا عقد استجابة تحرّك، ولا نصّ عربي مرئي مسّه هذا النقل.

**لماذا `build()` مصنعٌ لا وحدة دوالّ مسطّحة:** العنقود كان **إغلاقاً** يقرأ
خمسة مساعِدين من نطاق `api` — ثلاثةٌ منها يستعملها باقي المسارات أيضاً
(`_view`، `_attach_quality_gate`، `_attach_watchdog`) واثنان على مستوى وحدة
`api` (`_to_jsonable`، `_early_halt_enabled`). حقنُها وسائطَ صريحة في `build`
يحفظ دلالة الإغلاق حرفياً **ويمنع دورة الاستيراد**: هذه الوحدة لا تستورد
`api` إطلاقاً (يقفله اختبار AST) — الاتجاه أحاديّ: `api` ← هذه.

A literal extraction: the eight functions moved with their exact text and
indentation from one closure into another. `build()` injects the five helpers
the cluster read from `api`'s scope, so the module never imports `api` back.
"""
from __future__ import annotations

import logging
import os

import silk_usage

# **اسم المُسجِّل يبقى "api" حرفياً** لا اسم هذه الوحدة: الشيفرة المنقولة كانت
# تُسجّل تحته، ومستهلكوها يرشّحون به (سطور `stage_transition` تُلتقَط في
# `tests/test_wave_p6_pipeline_resilience.py` عبر `caplog.at_level(logger="api")`،
# وأي ترشيح تشغيليّ في النشر يفعل المثل). تغييرُه كان سيُسقِط السطور من كل
# مرشِّحٍ قائم بصمت — نقلُ الشيفرة لا ينقل هويّة سجلّها.
# The logger name stays "api": the moved code logged under it and consumers
# filter on it; renaming would silently drop those lines from every filter.
log = logging.getLogger("api")


def build(*, view_fn, attach_quality_gate, attach_watchdog,
          to_jsonable, early_halt_enabled):
    """اربط العنقود بمساعِدي `api` المشتركة وأعِد جسم التشغيلة.

    الوسائط الخمسة هي **بالضبط** ما كان العنقود يقرؤه من نطاق `create_app`:

    - `view_fn` → `_view`: بناء القالب الموحّد (يستعمله أيضاً `analyze`/
      `deepen`/`analysis`/`regenerate_report`/`enrich_leads` فيبقى في `api`).
    - `attach_quality_gate` → `_attach_quality_gate` (يستعمله أيضاً
      `regenerate_report`).
    - `attach_watchdog` → `_attach_watchdog` (يستعمله أيضاً `analyze`).
    - `to_jsonable` / `early_halt_enabled` → دالّتان على مستوى وحدة `api`.

    يعيد `_run_research_pipeline` — وهو الاسم الوحيد من العنقود الذي يناديه
    شيءٌ خارجه (`_research_background` و`_research_impl`).
    """
    _view = view_fn
    _attach_quality_gate = attach_quality_gate
    _attach_watchdog = attach_watchdog
    _to_jsonable = to_jsonable
    _early_halt_enabled = early_halt_enabled

    def _default_report_style() -> str:
        """نمط الكتابة الافتراضي للتوليد — `SILK_REPORT_STYLE` (طلب المالك:
        الافتراضي "decision"). يبقى الأسلوب الأكاديمي خياراً صريحاً فقط."""
        return (os.environ.get("SILK_REPORT_STYLE", "decision") or "decision").strip().lower()

    def _research_budget_status(economics: dict) -> dict:
        """حالة الميزانية على مستوى التشغيلة كاملة — P1، حادثة نفاد
        الاعتمادات: يسمّي **أي** سقف بلغ حدّه صراحة، لا يكتفي بملاحظة
        مدفونة داخل فجوات بعثة واحدة (كانت موجودة أصلاً — هذا تجميع
        علوي إضافي يجعلها مرئية فوراً للوحة/المستهلك)."""
        llm_cap = int(os.environ.get("SILK_RESEARCH_MAX_LLM_CALLS", "40"))
        tool_cap = int(os.environ.get("SILK_RESEARCH_MAX_TOOL_CALLS", "100"))
        llm_calls = economics.get("llm_calls", 0)
        tool_calls = economics.get("tool_calls", 0)
        hit = []
        if llm_calls >= llm_cap:
            hit.append(f"SILK_RESEARCH_MAX_LLM_CALLS={llm_cap}")
        if tool_calls >= tool_cap:
            hit.append(f"SILK_RESEARCH_MAX_TOOL_CALLS={tool_cap}")
        return {"exhausted": bool(hit), "caps_hit": hit,
               "llm_calls": llm_calls, "llm_cap": llm_cap,
               "tool_calls": tool_calls, "tool_cap": tool_cap,
               # H5: هل تدهور الذيل (تخطّى حَكَم التوليف + مراجعة الكاتب) لأن
               # البعثات استنفدت السقف؟ مُعلَن صراحةً، لا مدفون.
               "tail_degraded": bool(economics.get("tail_degraded"))}

    def _collect_importer_leads(scrape_future, product: str, market_ref,
                                mission_reports: dict, scrape_t0: float,
                                mono) -> dict:
        """اجمع جهات اتصال المستوردين بسقف زمني كلّي — نفس مسار الروابط الوحيد
        (مكشطة → احتياط Places → فجوة معلنة). بلا نداء كلود. أمر المالك
        المُحدَّث ITEM 1: يُنادى تلقائياً في التشغيلة قبل الكاتب.

        السقف الكلّي `SILK_ENRICH_TIMEOUT_S` (٦٠ث افتراضياً) يحدّ زمن الجمع —
        الكشط راكَب البعثات أصلاً فيكون عادةً جاهزاً. مهلة/فشل = فجوة معلنة
        `{leads:[], path:"gap"}`، لا تشغيلة عالقة ولا رقم مخترَع."""
        import silk_gmaps
        try:
            _cap = float(os.environ.get("SILK_ENRICH_TIMEOUT_S", "60"))
            _web_cands = silk_gmaps.extract_web_candidates(mission_reports)
            leads = silk_gmaps.finalize_leads(
                scrape_future, product, market_ref, _web_cands, timeout_s=_cap)
            log.info("gmaps leads path=%s count=%d (%.1fs after submit)",
                     leads.get("path"), len(leads.get("leads") or []),
                     mono.monotonic() - scrape_t0)
            # §6 من أمر سد الفجوات: الحد الأدنى للمخرج 5 كيانات؛ عند التعذر
            # يُذكر العدد المتاح وطريقة البحث والنقص المتبقي صراحةً — خلف
            # صمّام الطبقة (الإطفاء = ناتج اليوم حرفياً).
            try:
                import silk_gap_recovery
                n = len(leads.get("leads") or [])
                if silk_gap_recovery.enabled() and n < 5:
                    path_ar = {"cache": "المخزن", "scraper": "مكشطة الخرائط",
                               "places": "Google Places",
                               "gap": "فجوة"}.get(leads.get("path"),
                                                  str(leads.get("path")))
                    shortfall = (
                        f"عدد الموزّعين المتاح {n} من حدّ أدنى 5؛ طريقة البحث: "
                        f"{path_ar}؛ النقص المتبقي {5 - n} كيانات — الإدراج في "
                        "دليل يثبت الوجود وجهة الاتصال فقط، لا نشاط الاستيراد.")
                    leads["note"] = (f"{leads.get('note', '')} | {shortfall}"
                                     .strip(" |"))
            except Exception:
                pass
            return leads
        except Exception as e:  # noqa: BLE001 — الروابط تحسين لا شرط؛ لا تُسقط التشغيلة
            log.warning("gmaps enrich failed: %s", e)
            return {"leads": [], "path": "gap",
                    "note": f"تعذّر جمع الروابط: {type(e).__name__}"}

    def _run_research_pipeline(market_ref, product: str, hs_code: str | None,
                               hs_note: str | None, product_card_dict: dict | None,
                               ai_ok: bool, ai_note: str, prefs: dict | None,
                               ready: bool, ready_reason: str,
                               analysis_id: int | None,
                               resume_reports: dict | None,
                               report_style: str | None = None,
                               hs_confidence: float | None = None,
                               hs_provenance: dict | None = None,
                               hs_classification: dict | None = None,
                               lang: str = "ar",
                               resume_stages: dict | None = None) -> dict:
        """جسم التشغيلة الثقيل — بعثات + محلل + توليف + كاتب/مراجع + بوابة
        جودة. مستخرَج من مسار /research المتزامن السابق **بلا تغيير سلوكي**
        كي يُستدعى إما مباشرة (وضع متزامن) أو من خيط خلفي (async_run=true)
        بلا ازدواج منطق. لا حفظ هنا — المستدعي يقرّر متى/كيف يُخزَّن."""
        import contextlib
        import silk_context
        ctx = (contextlib.nullcontext() if ai_ok
               else silk_context.block_ai_extras())
        with ctx, silk_context.agent_prefs_context(prefs):
            silk_context.begin_data_counter()
            # R2: إلغاءٌ وصل قبل أوّل إنفاق (دراسة منصّة أُلغيت وهي تُخصَّص) —
            # لا بعثة تُطلَق. خارج سياق إلغاءٍ هذا لا-شيء (السلوك القائم).
            silk_context.check_cancelled("start")
            # درس 188 (F7/F8/F9): يوم الحجز والمبلغ المحجوز يُلتقطان **مرّة**
            # عند بدء التشغيلة ويُثبَّتان طوال ذيلها — فحارسُ الميزانية الأوسط
            # والتسويةُ النهائية يقيسان على دلو الحجز نفسه لا على «اليوم»
            # المتحرّك، فلا يُعطَّل الحارس ولا يُصفَّر دفتر الغد عبر منتصف الليل.
            _reserve_day = silk_usage._today()
            _reserved_usd = silk_usage.expected_run_usd()
            from silk_missions import deep_research
            from silk_market_analyst import analyze_market, to_synthesis_input
            from silk_synthesis import synthesize
            from silk_ai_judge import write_reviewed_report

            # تقدّم حيّ (GET /research/{id}/status): لقطة أولى تضبط started_at
            # مرّة واحدة — كل لقطة لاحقة (لكل بعثة، ولكل مرحلة كاتب/مراجع)
            # تعيد استعمال نفس القناة (silk_context.snapshot_research_progress)
            # بلا عدّاد جديد، تُقرأ من نفس data_counter المستعمَل للتقرير النهائي.
            import datetime as _dt
            _started_at = _dt.datetime.now().isoformat(timespec="seconds")
            silk_context.snapshot_research_progress(
                analysis_id, "missions", started_at=_started_at)

            # C2/D-02 (Command #5b): قدّم مهمة كشط الخرائط **مبكراً** (قبل
            # البعثات) على خيط منفصل — مهلتها (٨ دقائق) تتراكب مع زمن البعثات
            # والذيل فلا تزيد زمن التشغيلة الكلي، والتشغيلة لا تنتظرها (تُجمَع
            # بمهلة قصيرة قبل بناء النتيجة، وإلا السلسلة الاحتياطية/فجوة).
            # تعطيل نظيف: إن كانت المكشطة غير مُهيَّأة يعود None بلا أي أثر.
            import time as _mono
            import silk_gmaps
            _scrape_future = silk_gmaps.submit_scrape_async(product, market_ref)
            _scrape_t0 = _mono.monotonic()
            # E3 (SPEC-v2): علامات زمن الجدار لكل مرحلة — تُحسَب منها المصارف
            # الثلاثة الكبرى (stage_top_sinks) وتُطبَع في data_economics.
            _stage_marks = {"missions": _scrape_t0}

            # ── p6/T9 · سجلّ انتقال مهيكل + حارس ميزانية عند حدود المراحل ──
            from silk_pricing import estimate_cost_usd as _cost_fn
            _stage_seconds_acc: dict = {}
            _stage_budget: dict = {"halted_before": None, "caps_hit": []}
            _last_mark = {"name": "missions", "t": _scrape_t0,
                          "in": 0, "out": 0, "cost": 0.0}

            def _usage_totals() -> tuple[int, int, float]:
                c = silk_context.data_counter() or {}
                usage = c.get("llm_usage") or {}
                tin = sum(int((u or {}).get("input_tokens", 0))
                          for u in usage.values())
                tout = sum(int((u or {}).get("output_tokens", 0))
                           for u in usage.values())
                return tin, tout, float(_cost_fn(usage)["total_usd"])

            def _stage_mark(name: str) -> None:
                """نهاية المرحلة السابقة/بداية `name`: يحفظ علامة الزمن (نفس
                القاموس الذي يغذّي data_economics.stage_seconds كما كان)، ويُصدر
                سطر سجلّ مهيكلاً + حدث تتبّع kind=stage + يراكم stage_seconds في
                لقطة التقدّم — فتنجو القياسات من تشغيلةٍ لا تكتمل."""
                # R2: حدودُ المراحل هي نقاط التفتيش الآمنة للإلغاء التعاونيّ —
                # قبل النداء المدفوع التالي، بعد أن حُفظت نقاطُ المرحلة السابقة.
                # العلامة الختامية «end» ليست نقطة تفتيش (§58 #2): لا نداء مدفوع
                # بعدها، وإلغاءٌ وصل أثناء الكاتب كان سيُتلف تقريراً اكتمل ودُفع ثمنه.
                if name != "end":
                    silk_context.check_cancelled(name)
                now = _mono.monotonic()
                tin, tout, cost = _usage_totals()
                prev = _last_mark["name"]
                dur = round(now - _last_mark["t"], 1)
                d_in, d_out = tin - _last_mark["in"], tout - _last_mark["out"]
                d_cost = round(cost - _last_mark["cost"], 4)
                _stage_marks[name] = now
                _stage_seconds_acc[prev] = dur
                log.info("stage_transition analysis_id=%s stage=%s duration_s=%.1f "
                         "tokens_in=%d tokens_out=%d cost_usd=%.4f next=%s",
                         analysis_id, prev, dur, d_in, d_out, d_cost, name)
                try:
                    import silk_trace as _st
                    if trace_id:
                        _st.append_event(
                            trace_id, kind="stage", stage=prev, duration_s=dur,
                            tokens_in=d_in, tokens_out=d_out, cost_usd=d_cost,
                            next_stage=name)
                except Exception as _te:  # noqa: BLE001 — تتبّع تحسيني
                    log.warning("stage trace event skipped: %s", _te)
                if analysis_id is not None:
                    try:
                        from silk_storage import update_research_progress
                        update_research_progress(
                            analysis_id, stage_seconds=dict(_stage_seconds_acc))
                    except Exception as _pe:  # noqa: BLE001 — لقطة تحسينية
                        log.warning("stage_seconds snapshot skipped: %s", _pe)
                _last_mark.update(name=name, t=now, **{"in": tin, "out": tout,
                                                       "cost": cost})

            def _budget_ok(before_stage: str) -> bool:
                """حارس الإنفاق قبل نداءٍ مدفوع: سقف التشغيلة SILK_RESEARCH_MAX_USD
                (غير مضبوط = معطّل) + السقف اليومي (المُنفَق اليوم − المحجوز لهذه
                التشغيلة + الفعلي حتى الآن). الخرق = تخطّي المراحل المدفوعة
                الباقية برسالة معلَنة — لا إجهاض نداءٍ جارٍ، لا خطأ صلب."""
                if _stage_budget["halted_before"]:
                    return False
                _, _, actual = _usage_totals()
                hit: list[str] = []
                raw = os.environ.get("SILK_RESEARCH_MAX_USD", "").strip()
                if raw:
                    try:
                        cap = float(raw)
                        if cap > 0 and actual > cap:
                            hit.append(f"SILK_RESEARCH_MAX_USD={raw}")
                    except ValueError:
                        log.warning("SILK_RESEARCH_MAX_USD=%r ignored (not a number)",
                                    raw)
                daily = silk_usage.daily_usd_cap()
                if daily is not None:
                    projected = (silk_usage.usd_spent_on(_reserve_day)
                                 - _reserved_usd + actual)
                    if projected > daily:
                        hit.append(f"SILK_PAID_DAILY_USD_CAP={daily:g}")
                if hit:
                    _stage_budget["halted_before"] = before_stage
                    _stage_budget["caps_hit"] = hit
                    log.warning("budget guard halted analysis %s before %s: %s "
                                "(actual so far %.4f$)", analysis_id, before_stage,
                                hit, actual)
                    return False
                return True

            # deep_research() (لا run_all_missions مباشرة) — يفعّل التتبّع
            # الكامل دوماً (data/traces/{trace_id}.jsonl، الموجة ٦) فيبقى كل
            # تشغيل /research إنتاجي قابلاً للتدقيق، لا التشغيلات التجريبية فقط.
            from silk_request_identity import fingerprint
            resume_fingerprint = fingerprint(resume_reports or {})
            research_run = deep_research(market_ref, product=product,
                                         hs_code=hs_code,
                                         product_card=product_card_dict,
                                         analysis_id=analysis_id,
                                         resume_reports=resume_reports)
            mission_reports = research_run["reports"]
            # تغيير أي مدخل يلغي الذيل المحفوظ؛ البعثات السليمة تبقى قابلة للاستعمال.
            from silk_missions import MISSION_ORDER, _report_is_failed
            if resume_stages and (any(
                    key not in (resume_reports or {}) or _report_is_failed(resume_reports[key])
                    for key in MISSION_ORDER)
                    or fingerprint(mission_reports) != resume_fingerprint):
                resume_stages = {}
            trace_id = research_run.get("trace_id")
            # المرحلة 0 (توجيه المنصّة): طبقة سد الفجوات — تعمل مرة واحدة بعد
            # كل البعثات وقبل المحلل، خلف صمّام مُطفأ افتراضياً (LESSONS 70).
            # فشلها الكلي لا يمسّ المسار (لا حجب — قيد الأمر التنفيذي).
            gap_recovery_log = None
            try:
                import silk_gap_recovery
                if silk_gap_recovery.enabled():
                    silk_context.snapshot_research_progress(
                        analysis_id, "gap_recovery")
                    gap_recovery_log = silk_gap_recovery.recover(
                        mission_reports, market_ref=market_ref,
                        product=product, hs_code=hs_code,
                        year=_dt.date.today().year - 1)
            except Exception as _gap_e:
                try:
                    import silk_gap_recovery as _gr_mod
                    _gr_enabled = _gr_mod.enabled()
                except Exception:
                    _gr_enabled = "unknown"
                gap_recovery_log = {"enabled": _gr_enabled,
                                    "error": str(_gap_e)[:300]}
            _stage_mark("analyst")  # E3: نهاية البعثات (p6/T9: سجلّ + تتبّع + لقطة)
            silk_context.snapshot_research_progress(analysis_id, "analyst")
            # ── الموجة ٨ (هدف الدراسة الاحترافية، البند ٨): الإيقاف المبكر ──
            # قرار المحرك الحتمي يُحسب هنا مرة واحدة (صفر نداء مدفوع — كان
            # يُحسب بعد التوليف بنفس المدخلات تماماً، Z-01) فيخدم غرضين: إن
            # كانت الأعمدة المحسوبة دون الحد الأدنى فالنتيجة محسومة سلفاً
            # (فرع insufficient_pillars) ولا يغيّرها المحلل ولا الكاتب —
            # أغلى نداءين يُتخطّيان معلَنَين والبعثات محفوظة تُستأنف بعد
            # إكمال المصادر. القاعدة الصلبة: لا قطع لأي بعثة تغذي ركيزة —
            # البعثات كلها جرت أعلاه والتوفير في الذيل المدفوع حصراً.
            _deep_reg, _deep_decision = _deep_engine_decision(
                {"missions": mission_reports}, market_ref, hs_code,
                product_card_dict)
            early_halted = (_early_halt_enabled()
                            and bool((_deep_decision or {})
                                     .get("insufficient_pillars")))
            if early_halted:
                log.info(
                    "analysis %s: early halt — computed pillars %s below "
                    "minimum %s; paid analyst+writer skipped", analysis_id,
                    (_deep_decision or {}).get("computed_pillars"),
                    (_deep_decision or {}).get("min_scored_pillars"))
            # H5 (تدقيق): حارس إنفاق على مستوى التشغيلة للذيل. السقف الكلي
            # (SILK_RESEARCH_MAX_LLM_CALLS) كان يُستشار داخل حلقة البعثات
            # فقط؛ الذيل (محلل+توليف+كاتب+مراجع) يجري بلا حكم حتى لو استُنفد.
            # الآن: إن بلغت البعثاتُ السقف، يُنتِج الذيل التقرير الأساسي
            # (المحلل + مسوّدة الكاتب — لا يُلغى الكاتب فلا فقدان) لكن يتخطّى
            # المكلّف الاختياري: حَكَم التوليف مرحلة-٢ (تبقى جورية المرحلة ١)
            # ودورة مراجعة الكاتب (مسوّدة بلا تنقيح). تدهور رشيق مُعلَن.
            _llm_cap = int(os.environ.get("SILK_RESEARCH_MAX_LLM_CALLS", "40"))
            _ctr = silk_context.data_counter() or {}
            tail_over_budget = ai_ok and _ctr.get("llm_calls", 0) >= _llm_cap
            # الموجة ٨: الإيقاف المبكر يطفئ أيضاً حَكَم التوليف مرحلة-٢
            # المدفوع (تبقى جورية المرحلة ١ الحتمية) — نفس عائلة تدهور
            # tail_over_budget الرشيق المعلن.
            tail_with_ai = ai_ok and not tail_over_budget and not early_halted
            # PART C1: تجاوز الميزانية يفرض دورة واحدة؛ وإلا None = افتراض
            # البيئة (SILK_MAX_REVIEW_CYCLES، افتراضياً ١ — التنقيح الثاني
            # للمشاكل الحاجبة فقط حتى حين يُرفَع السقف إلى ٢).
            tail_max_cycles = 1 if tail_over_budget else None
            # بلاغ حي (تمور/هولندا، تشغيلة ثانية): trace_context البعثات
            # الاثنتي عشرة يُغلَق فور عودة deep_research() أعلاه — نداءا
            # المحلل الشامل والكاتب/المراجع كانا يجريان **بلا أي تتبّع**،
            # فحين فشل الكاتب لم يكن هناك أثر يوضّح هل بلغ مهلته الموسّعة
            # فعلاً أم فشل أسرع بخطأ آخر. إعادة فتح نفس ملف التتبّع (معرّف
            # واحد، إلحاق فقط — لا تصادم) للمحلل صراحة؛ الكاتب يُمرَّر
            # trace_id مباشرة (راجع silk_ai_judge._traced_call).
            import silk_trace
            # الموجة p6 (T4): محللٌ محفوظٌ **ناجحاً** من تشغيلة سابقة يُعاد
            # استعماله بلا نداء — «الاستئناف بالقروش لا بالدولارات» يشمل
            # المحلل لا البعثات فقط. محفوظٌ فاشلاً/غائب ⇒ يُعاد نداؤه وحده.
            analyst_skipped_budget = False
            analyst_skipped_early = False
            _saved_analyst = (resume_stages or {}).get("analyst") or {}
            _saved_payload = _saved_analyst.get("payload") or {}
            if (_saved_analyst.get("status") == "succeeded"
                    and isinstance(_saved_payload.get("analyst_out"), dict)
                    and isinstance(_saved_payload.get("analyst_input"), dict)):
                analyst_out = dict(_saved_payload["analyst_out"])
                analyst_out["resumed_from_checkpoint"] = True
                analyst_input = dict(_saved_payload["analyst_input"])
                analyst_reused = True
                log.info("analysis %s: analyst stage reused from checkpoint "
                         "(no Claude call)", analysis_id)
            elif ai_ok and early_halted:
                # الموجة ٨: الأعمدة دون الحد الأدنى — النتيجة محسومة
                # «بيانات غير كافية» قبل المحلل فلا يُدفع نداؤه (نفس بنية
                # فرع بلوغ السقف أدناه؛ البعثات محفوظة تُستأنف).
                from silk_agents import AgentReport as _AR
                from silk_market_analyst import REQUIRED_CATEGORIES as _RC
                analyst_reused = False
                analyst_skipped_early = True
                analyst_out = {
                    "report": _AR("LLMAgent:market_analyst", [], True,
                                  "أُوقف التحليل الشامل قبل تشغيله — ما جمعته "
                                  "البعثات دون الحد الأدنى لجوانب التقييم "
                                  "فالنتيجة محسومة سلفاً «بيانات غير كافية»؛ "
                                  "لا نتائج مختلَقة"),
                    "by_category": {c: [] for c in _RC},
                    "missing_categories": list(_RC),
                    "diagnostics": {"raw_findings": 0, "binned": 0,
                                    "uncategorized": 0, "synonym_rescued": 0,
                                    "analyst_failed": True,
                                    "all_missing_cause": "early_halt"}}
                analyst_input = to_synthesis_input(analyst_out)
            elif ai_ok and not _budget_ok("analyst"):
                # مراجعة §58 #5: أغلى نداءٍ في التشغيلة كان بلا حارس إنفاق
                # (الحارس كان يُقيَّم قبله فيقرّر بميزانيةٍ لا تشمله، ومدخلةُ
                # «التحليل الشامل» في خريطة الرسائل ميتة). الآن: بلوغُ السقف
                # قبل التحليل يوقفه ويوقف الكاتب معه — البعثاتُ محفوظة تُستأنَف.
                from silk_agents import AgentReport as _AR
                from silk_market_analyst import REQUIRED_CATEGORIES as _RC
                analyst_reused = False
                analyst_skipped_budget = True
                analyst_out = {
                    "report": _AR("LLMAgent:market_analyst", [], True,
                                  "أُوقف التحليل الشامل قبل تشغيله لبلوغ سقف "
                                  "الإنفاق المحدَّد — لا نتائج مختلَقة"),
                    "by_category": {c: [] for c in _RC},
                    "missing_categories": list(_RC),
                    "diagnostics": {"raw_findings": 0, "binned": 0,
                                    "uncategorized": 0, "synonym_rescued": 0,
                                    "analyst_failed": True,
                                    "all_missing_cause": "budget_halt"}}
                analyst_input = to_synthesis_input(analyst_out)
            else:
                analyst_reused = False
                # T3 fix-up: الحارس أدناه يقرأ last_error() — يُعاد ضبطه **قبل**
                # نداء المحلل كي يرى خطأ هذه التشغيلة حصراً، لا بقايا نداءٍ
                # سابق في السياق نفسه (محللٌ لم يمرّ بالمزوّد لا يعيد ضبطه).
                import silk_llm_provider as _prov_reset
                _prov_reset._last_error.set(None)
                with silk_trace.trace_context(trace_id):
                    analyst_out = analyze_market(
                        market_ref, product, mission_reports, hs_code=hs_code,
                        product_card=product_card_dict)
                analyst_input = to_synthesis_input(analyst_out)
            # الموجة p6 (T3): اقرأ تفصيل فشل **نداء** المحلل فوراً (قبل أيّ نداء
            # كلود آخر يعيد ضبط contextvar آخر الأخطاء) — الفرع ب الحيّ: مهلة
            # القراءة ابتُلعت في المزوّد فصار «ملخّص المحلل» نصَّ الخطأ نفسه،
            # وشُغِّل الكاتب عليه بثمن كامل. فشل النداء يوقف الكاتب أدناه.
            import silk_llm_provider as _prov
            _analyst_err = ({} if (analyst_reused or analyst_skipped_budget
                                   or analyst_skipped_early)
                            else dict(_prov.last_error() or {}))
            # مراجعة §58 #1: يُلتقَط **نصّ** التشخيص هنا أيضاً لا عند بناء الرد —
            # نداءُ التوليف (المرحلة ٢) بينهما يُصفّر `_last_error` بنجاحه،
            # فكان «ReadTimeout» يضيع ويحلّ محلّه نصٌّ عامّ في الرد وسجلّ المشغّل.
            from silk_ai_judge import failure_reason as _fr
            _analyst_failure_text = ("" if (analyst_reused
                                            or analyst_skipped_budget
                                            or analyst_skipped_early)
                                     else _fr())
            # «فشل النداء» يتطلّب **دليل المزوّد** (last_error مضبوط: مهلة/شبكة/
            # رفض HTTP) لا مجرّد صفر نتائج — نداءٌ نجح وأعاد قائمةً فارغة
            # (diagnostics تسمّيه analyst_call_failed أيضاً) ليس فشل نداء،
            # والكاتب يعمل فيه كما كان. لا تخمين من شكل النتيجة.
            analyst_call_failed = (not analyst_reused) and bool(_analyst_err) and (
                (analyst_input.get("diagnostics") or {}).get("all_missing_cause")
                == "analyst_call_failed")
            # الموجة p6 (T2): احفظ المحلل **فور عودته** — أغلى نداء في التشغيلة
            # كان يعيش في الذاكرة حتى الحفظ النهائي (الفرع ب الحيّ) فيُعاد دفعه
            # عند أيّ فشل لاحق. نفس آلية نقطة تفتيش البعثة (silk_missions.py:586).
            if not analyst_reused:
                # الحمولة بالشكل المخزَّن نفسه (`_to_jsonable`) كي يُعاد
                # استعمالها حرفياً عند الاستئناف: `analyst_out` كما يقرؤه
                # العرض والبوّابة، و`analyst_input` كما يقرؤه التوليف والكاتب.
                _stage_checkpoint(
                    analysis_id, "analyst",
                    {"analyst_out": _to_jsonable(analyst_out),
                     "analyst_input": analyst_input},
                    status=("failed" if (analyst_input.get("diagnostics") or {})
                            .get("analyst_failed") else "succeeded"),
                    market_iso3=market_ref.iso3)
            _stage_mark("synthesis")  # E3: نهاية المحلل
            # p6/T9 + مراجعة #5: حارس الدولار قبل حكم المرحلة ٢ مباشرةً —
            # بعد إنفاق المحلل لا قبله.
            if tail_with_ai and not _budget_ok("synthesis"):
                tail_with_ai = False
            verdict = synthesize(
                list(mission_reports.values()), product=product,
                market=market_ref.name_en, with_ai=tail_with_ai,
                analyst_assessment=analyst_input)
            # وكيل الامتناع (محرك دراسة السوق، القاعدة ٥؛ الموجة ٣ — SHADOW
            # بحت): يُحسَب ويُسجَّل فقط (`judge_abstain_shadow` أدناه) — صفر
            # أثر على `verdict`/الكاتب. فشلُ الحساب نفسه لا يوقف التشغيلة
            # (نفس منطق الميثاق/المُطعِّم، PR #238).
            judge_abstain_shadow = None
            try:
                import silk_judge_abstain
                judge_abstain_shadow = silk_judge_abstain.would_abstain(
                    charter=research_run.get("charter"),
                    by_category=analyst_out.get("by_category"))
            except Exception:
                log.exception("judge_abstain_shadow: تعذّر الحساب — يُتابَع بلا إشارة")
            # ── الموجة Z · البند Z-01 — الحكمُ الواحد يسبق الكاتب ─────────
            # كان محرّكُ القرار الحتميّ يُشغَّل **بعد** الكاتب وبعد التخزين
            # (`_attach_deep_market_row`)، فيعيش حكمُه في `view["decision"]`
            # وحدَه بينما غلافُ الـdocx والـPDF و`view["brief"]` وسردُ الكاتب
            # تُشتَقّ كلُّها من عدّاد تغطيةِ البعثات. مُثبَتٌ بإعادة إنتاج:
            # محرّكٌ يقول `NO-GO` («الدرجة 0.31 دون عتبة الرفض») وغلافُ تقرير
            # العميل المُسلَّم يقول «توصية أولية بالدخول» — وحكمُ المحرّك صفرُ
            # ظهورٍ في المستند. حكمان في مصنوعٍ واحد.
            #
            # العلاجُ عند المنشأ: يُحسَب القرارُ **هنا** مرّةً واحدة ويُقدَّم
            # داخل نفس قاموس الحكم الذي يقرؤه الكاتبُ (`authoritative_verdict`)
            # وكلُّ سطحِ عرض. فلا سطحَ يشتقّ حكماً بنفسه، وحالةُ تغطيةِ الأدلة
            # تبقى **مُعلَنةً** بجواره لا مُستبدَلةً به.
            import silk_deep_pillars
            # الموجة ٨: القرار حُسب مرة واحدة قبل الذيل (فحص الإيقاف المبكر
            # أعلاه — نفس المدخلات حرفياً) ويُعاد استعماله هنا: نسختان من
            # نفس الحساب قد تتباعدان.
            verdict = silk_deep_pillars.promote_engine_verdict(
                verdict, _deep_decision)
            _stage_mark("enrich")  # E3: نهاية التوليف
            # إكمال بيانات المستوردين تلقائياً (أمر المالك المُحدَّث ITEM 1):
            # حين تكون المكشطة مُهيَّأة، تُجمَع جهات الاتصال (هاتف/إيميل/موقع)
            # **قبل الكاتب** فيشحن التقرير كاملاً من التشغيلة الأولى. الكشط
            # قُدِّم مبكراً (submit_scrape_async قبل البعثات) فتراكب زمنه مع
            # البعثات/المحلل؛ هنا يُجمَع بسقف زمني كلّي (SILK_ENRICH_TIMEOUT_S،
            # ٦٠ث افتراضياً). فشل/مهلة = فجوة معلنة «—»، لا تشغيلة عالقة، لا
            # نداء كلود. صندوق التقدّم يعرض المرحلة «إكمال بيانات المستوردين».
            silk_context.snapshot_research_progress(analysis_id, "enrich_leads")
            importer_leads = _collect_importer_leads(
                _scrape_future, product, market_ref, mission_reports,
                _scrape_t0, _mono)
            _stage_checkpoint(analysis_id, "leads", importer_leads,
                              market_iso3=market_ref.iso3)  # p6/T2
            _stage_mark("writer")  # E3: نهاية الإكمال
            # Wave 1.2/1.3 (تدقيق زبدة الفول السوداني/اليمن): عقد تأكيد رمز HS
            # — يُقاس تداخل صفات المنتج المميّزة مع وصف الرمز؛ رمز غير مؤكَّد
            # يُمرَّر للكاتب فيؤطّر أرقام كومتريد «مؤشر سياقي»، ويُخزَّن في
            # النتيجة فتعيد طبقة العرض تأطيرها + تسقف الثقة (silk_render).
            try:
                from silk_hs_confirm import (confirm_hs,
                                             cap_confidence_for_flagged_hs)
                hs_conf = confirm_hs(product, hs_code) if hs_code else None
            except Exception:
                hs_conf = None
            # PR A §A1: سقفُ ثقةِ الحكم عند تعليم الرمز يُطبَّق **قبل** الكاتب من
            # المصدر الواحد، فيرى الكاتب القيمة المسقوفة نفسها التي سيعرضها
            # الغلاف — لا §4 «73%» مقابل غلاف «50%». طبقة العرض تُبقيها idempotent.
            try:
                verdict = cap_confidence_for_flagged_hs(verdict, hs_conf)
            except Exception:  # noqa: BLE001 — تسقيفٌ تحسينيّ لا يُسقِط تشغيلة
                pass
            # p6/T2: الحكم النهائي (بعد الترقية والتسقيف) كما سيراه الكاتب.
            _stage_checkpoint(analysis_id, "verdict", _to_jsonable(verdict),
                              market_iso3=market_ref.iso3)
            # نمط الكتابة (طلب المالك): يُمرَّر للكاتب فيبدّل عقد السجل اللغوي
            # وحده (الأكاديمي مقابل التجاري) — نفس الأقسام/الحكم/قواعد الصدق.
            eff_report_style = (report_style or _default_report_style())
            if ai_ok and early_halted:
                # الموجة ٨: لا كاتب فوق نتيجة محسومة «بيانات غير كافية» —
                # الرسالة بلغة الزائر وأرقامها من قرار المحرك نفسه، وسبيل
                # الإكمال معلن (استئناف بالقروش لا تشغيلة جديدة).
                _cp = (_deep_decision or {}).get("computed_pillars")
                _mp = (_deep_decision or {}).get("min_scored_pillars")
                _np = len((_deep_decision or {}).get("pillars") or {}) or 4
                # بلاغ التحليل ٢٧: «أكمل المصادر الغائبة» بلا اسمِ غائبٍ طلبٌ
                # غير قابل للتنفيذ — والأسماء محسوبةٌ أصلاً في القرار
                # (`silk_decision`: missing_pillars + `_AR`). تُنقَل كما هي من
                # المصدر الواحد، لا قاموسَ تعريبٍ ثانٍ يتباعد عنه.
                # وموجةُ «الشامل بدل الترقيع» (بلاغ المالك، التحليلان ٢٧/٢٨):
                # اسمُ العمود وحده لا يقول **أيّ قياسٍ** سقط، فبقي المالك
                # يسأل والمُنفِّذُ يطلب بلوبَ التشغيلة في كل مرة — حلقةٌ
                # تُغلَق هنا لا في كل حادثة. المكوّناتُ الناقصة محسوبةٌ أصلاً
                # (`pillars[k]["missing"]`) ومُعرَّبةٌ بـ`_parts_ar` — تُنقَل
                # كما هي، فيقرأ المصنعُ «جاذبية السوق (الناقص: حجم واردات
                # السوق، معدّل نموّ الواردات…)» ويعرف فوراً أهي فجوةُ مصدرٍ
                # عندنا أم فجوةُ إدخالٍ عنده.
                try:
                    from silk_decision import _AR as _PILLAR_AR, _parts_ar
                    _pillars = (_deep_decision or {}).get("pillars") or {}
                    _missing_ar = []
                    for k in ((_deep_decision or {}).get("missing_pillars")
                              or []):
                        _parts = (_pillars.get(k) or {}).get("missing") or []
                        _txt = _parts_ar(_parts) if _parts else ""
                        _missing_ar.append(
                            f"{_PILLAR_AR.get(k, k)}"
                            + (f" (الناقص: {_txt})" if _txt else ""))
                except Exception:  # noqa: BLE001 — تسميةٌ تحسينية لا تُسقِط تشغيلة
                    _missing_ar = []
                report_out = {
                    "report": None, "review_cycles": 0, "unresolved_notes": [],
                    "skipped": "writer", "skip_reason": "early_halt",
                    "failure_reason": (
                        "أوقفنا الدراسة مبكراً قبل مرحلتي التحليل والكتابة: "
                        f"ما جمعناه يغطي {_cp} من {_np} جوانب يحتاجها القرار "
                        f"والحد الأدنى {_mp} — لا نكتب توصية فوق بيانات لا "
                        "تكفي للحكم."
                        + (" الجوانب الغائبة: " + "؛ ".join(_missing_ar) + "."
                           if _missing_ar else "")
                        + " ما جُمع محفوظ؛ أكمل مصادر هذه الجوانب ثم أعد "
                        "التشغيل وسيُستأنف من حيث توقف.")}
            elif ai_ok and (analyst_skipped_budget
                            or (not analyst_call_failed
                                and not _budget_ok("writer"))):
                # p6/T9: سقف الإنفاق بلغ حدّه قبل الكاتب — يُتخطّى معلَناً؛ ما
                # اكتمل (بعثات + محلل + حكم) محفوظ ويُسلَّم جزئياً.
                report_out = {
                    "report": None, "review_cycles": 0, "unresolved_notes": [],
                    "skipped": "writer", "skip_reason": "budget",
                    "failure_reason": "أُوقف التقرير قبل الكتابة لبلوغ سقف الإنفاق "
                                      "المحدَّد — البعثات والتحليل محفوظة، ويمكن "
                                      "توليد التقرير لاحقاً بعد رفع السقف"}
            elif ai_ok and analyst_call_failed:
                # p6/T3: فشل نداء المحلل (مهلة/شبكة/رفض HTTP) — **لا كاتب**.
                # ما اكتمل (البعثات + الحكم الحتميّ) محفوظ ويُسلَّم جزئياً
                # معلَناً؛ نوع الخطأ وقابلية إعادة المحاولة يصلان النتيجة كي
                # تُوجَّه إعادةُ التوليد (POST /analyses/{id}/report) لا تشغيلة
                # كاملة. عقد عدم الاختلاق: report=None، لا نصّ بديل.
                report_out = {
                    "report": None, "review_cycles": 0, "unresolved_notes": [],
                    "failure_reason": _analyst_failure_text,
                    "skipped": "writer", "skip_reason": "analyst_call_failed",
                    "error_type": _analyst_err.get("type"),
                    "retryable": _llm_error_retryable(_analyst_err)}
                if _analyst_err.get("status_code"):
                    report_out["status_code"] = _analyst_err["status_code"]
                try:
                    from silk_render import _strip_internal_plumbing
                    import silk_ops_log
                    silk_ops_log.record_error(
                        "analyst_failure",
                        _strip_internal_plumbing(report_out["failure_reason"])
                        or "فشل نداء المحلل بلا سبب مسجَّل",
                        context={"analysis_id": analysis_id,
                                 "trace_id": trace_id,
                                 "error_type": report_out["error_type"],
                                 "retryable": report_out["retryable"]})
                except Exception as _oe:  # noqa: BLE001 — سجلّ المشغّل قناة جانبية
                    log.warning("ops log analyst_failure skipped: %s", _oe)
            else:
                # الاستئناف من الجزء (بلاغ تحليل 20): مسوّدةٌ محفوظة
                # (`writer_partial`) تُمرَّر بذرةً فيُكمِل الكاتبُ الأقسامَ
                # الباقية بدل إعادة توليد المسوّدة من الصفر (نداءٌ غالٍ).
                # حصراً على الاستئناف (resume_stages) — التشغيلة الطازجة None.
                _wp = (resume_stages or {}).get("writer_partial") or {}
                _seed_draft = ((_wp.get("payload") or {}).get("text")
                               if _wp.get("status") == "partial" else None)
                # R2b (API-5): تقريرٌ مكتمل محفوظ نقطةَ تفتيش (فشلَ الحفظُ النهائي
                # بعده) يُعاد كما هو — لا كاتبَ ثانياً مدفوعاً على تقريرٍ كُتب.
                _rp = (resume_stages or {}).get("report") or {}
                _saved_report = (dict(_rp.get("payload") or {})
                                 if (_rp.get("status") == "succeeded"
                                     and (_rp.get("payload") or {}).get("report"))
                                 else None)
                report_out = _saved_report if _saved_report is not None else (
                    write_reviewed_report(
                    mission_reports, analyst_input.get("summary", ""), verdict,
                    product, market_ref.name_en, max_cycles=tail_max_cycles,
                    trace_id=trace_id, hs_code=hs_code,
                    hs_confirmation=hs_conf,
                    style=eff_report_style, lang=lang,
                    # الموجة C (E-07): نفسُ بطاقة المنتج التي يقرؤها العرض —
                    # وإلا حسب الكاتبُ اقتصاداً وحسب العارضُ اقتصاداً آخر.
                    product_card=product_card_dict,
                    importer_leads=importer_leads,
                    seed_draft=_seed_draft,
                    # الدرس ٢٥٤: قرارُ المحرّك المحسوبُ سلفاً (الموجة Z) —
                    # الكاتبُ يستلم منه سقفَ تسمية الثقة نفسَه الذي تفرضه
                    # بوّابةُ الجودة، فلا يُحجَب التقريرُ على طاعةِ الموجّه.
                    entry_decision=_deep_decision,
                    on_stage=lambda s: silk_context.snapshot_research_progress(
                        analysis_id, s)) if ai_ok else
                    {"report": None, "review_cycles": 0, "unresolved_notes": []})
            _stage_mark("end")  # E3: نهاية الكاتب/المراجع
            economics = dict(silk_context.data_counter() or {})
            economics["tail_degraded"] = tail_over_budget
            # الموجة ٨: الإيقاف المبكر معلن في اقتصاد التشغيلة (قياس المالك).
            economics["early_halt"] = early_halted
            # E3 (SPEC-v2): زمن الجدار لكل مرحلة + أكبر ثلاثة مصارف — يُطبَع في
            # data_economics كي يقيس المالك أين تذهب الدقائق (البعثات متوازية،
            # الذيل متسلسل)، وهدف < ١٠ دقائق يُقاس عليه.
            _order = ["missions", "analyst", "synthesis", "enrich", "writer",
                      "end"]
            _labels = {"missions": "البعثات (متوازية)", "analyst": "المحلل الشامل",
                       "synthesis": "التوليف/الحكم",
                       "enrich": "إكمال بيانات المستوردين",
                       "writer": "الكاتب+المراجع"}
            _ss = {}
            for _i in range(len(_order) - 1):
                a, b = _order[_i], _order[_i + 1]
                if a in _stage_marks and b in _stage_marks:
                    _ss[a] = round(_stage_marks[b] - _stage_marks[a], 1)
            economics["stage_seconds"] = _ss
            economics["stage_total_seconds"] = round(sum(_ss.values()), 1)
            economics["stage_top_sinks"] = [
                {"stage": _labels.get(k, k), "seconds": v}
                for k, v in sorted(_ss.items(), key=lambda kv: -kv[1])[:3]]
            if report_out.get("partial_text"):
                # المسوّدة الجزئية تُحفَظ نقطةَ تفتيش — يُكمِل منها الاستئناف/
                # إعادة التوليد الأقسامَ الباقية بدل الصفر (بلاغ تحليل 20)؛ لا
                # نصّ مدفوع يُهدَر من القرص.
                _stage_checkpoint(analysis_id, "writer_partial",
                                  {"text": report_out["partial_text"]},
                                  status="partial", market_iso3=market_ref.iso3)
            if report_out.get("report"):
                # R2b (API-5): التقريرُ الكامل نقطةُ تفتيش **قبل** الحفظ النهائي —
                # فشلُ `save_analysis` بعده كان يُضيع النصَّ المدفوع كلَّه.
                _stage_checkpoint(analysis_id, "report", dict(report_out),
                                  market_iso3=market_ref.iso3)
            if not report_out.get("report"):
                # ITEM 5ب: فشل الكاتب في التشغيلة الرئيسية (لا مسار regen) —
                # السبب مُطهَّر قبل التخزين (نفس مُطهِّر H1/H4 القائم).
                from silk_render import _strip_internal_plumbing
                import silk_ops_log
                silk_ops_log.record_error(
                    "writer_failure",
                    _strip_internal_plumbing(report_out.get("failure_reason") or "")
                    or "فشل الكاتب بلا سبب مسجَّل",
                    context={"analysis_id": analysis_id, "trace_id": trace_id})
            elif report_out.get("incomplete"):
                # بلاغ تحليل 20 (تجاوز §5-الإتلاف): تقريرٌ ناقصٌ سُلِّم موسوماً —
                # يُرصَد للمشغّل (لا فشلٌ صلب: قرارٌ وأقسامٌ مكتوبة سليمة) كي
                # يُوجَّه الاستئمالُ لإكمال الأقسام الباقية.
                try:
                    import silk_ops_log
                    from silk_render import _strip_internal_plumbing
                    _miss = "، ".join(report_out.get("missing_sections") or [])
                    silk_ops_log.record_error(
                        "writer_incomplete",
                        f"تقرير غير مكتمل سُلِّم موسوماً — أقسام غائبة: {_miss}",
                        context={"analysis_id": analysis_id, "trace_id": trace_id,
                                 "missing": report_out.get("missing_sections"),
                                 # الدرس ٢٦١: شكلُ أسطرِ العناوين الفعليّ —
                                 # النقصُ البنيويُّ يُشخَّص بأثرٍ لا بحدس.
                                 "heading_sample": _strip_internal_plumbing(
                                     report_out.get("heading_sample") or ""),
                                 "reasons": report_out.get("incomplete_reasons")})
                except Exception as _ie:  # noqa: BLE001 — سجلّ المشغّل قناة جانبية
                    log.warning("ops log writer_incomplete skipped: %s", _ie)

        served = economics.get("store_hits", 0) + economics.get("cache_hits", 0)
        economics["note"] = (
            f"{economics.get('llm_calls', 0)} نداء كلود، "
            f"{economics.get('tool_calls', 0)} نداء أداة، {served} قراءة "
            "خُدمت من المخزن/ذاكرة الطلبات")
        from silk_pricing import estimate_cost_usd
        cost = estimate_cost_usd(economics.get("llm_usage"))
        economics["cost_usd_estimate"] = cost["total_usd"]
        economics["cost_usd_by_model"] = cost["by_model"]
        economics["cost_unpriced_models"] = cost["unpriced_models"]
        # إسناد التكلفة لكل بعثة (Part C، تحضير قياس حقيقي لتخفيض الكلفة):
        # mission_usage يُملأ فقط داخل silk_context.mission_context (وسم كل
        # نداء بمفتاح بعثته) — يُعاد استعمال estimate_cost_usd نفسه لكل بعثة
        # لا حساب تسعير موازٍ. تشغيلات سابقة لهذه الإضافة تعرض {} — فجوة
        # معلنة صريحة (تشغيلة قديمة بلا هذا الوسم)، لا اختلاق رقم.
        economics["cost_usd_by_mission"] = {
            mkey: estimate_cost_usd(mu)["total_usd"]
            for mkey, mu in (economics.get("mission_usage") or {}).items()}
        silk_context.snapshot_research_progress(analysis_id, "done")
        # H6: صالِح الحجز المسبق بالتكلفة الفعلية المُقدَّرة — المعالج حجز
        # التقدير (_expected) ذرّيًا قبل البدء؛ هنا نبدّله بالمُنفَق الحقيقي
        # المحسوب من رموز *كل* نداءات كلود في التشغيلة: بعثات + محلل + توليف +
        # كاتب بما فيه **كل محاولات تصعيد السقف** + **دورات المراجع** — العدّاد
        # يُقرأ بعد اكتمال الذيل كله (economics أعلاه)، وكل ردّ HTTP يسجّل رموزه
        # حتى المقتطع (silk_llm_provider._record_usage قبل فحص الاقتطاع). لكل
        # تشغيلة (متزامنة أو خلفية، كلاهما يمرّ من هنا).
        # درس 188: التسوية على دلو **يوم الحجز** بالمبلغ الملتقَط عند البدء
        # (لا إعادة قراءةٍ للتقدير هنا — قد يكون النشر تغيّر بينهما، F9).
        # الموجة p6 (T2): وسم الإعدام — `reconcile_failed_run_usd` (مسار
        # الاستثناء بعد هذه النقطة: فشل الحفظ النهائي مثلاً) يقرأ هذا الوسم
        # ولم يكن يُضبَط هنا، فكان الحجز يُصالَح **مرّتين** (الاختبار المطلوب د).
        # R2b (API-2): وإن سبقنا حاصدٌ فصالَح مبكّراً، تنطلق المصالحةُ النهائية من
        # مبلغه لا من التقدير — `silk_storage.reconcile_run_usd_final`.
        if analysis_id is not None:
            try:
                from silk_storage import reconcile_run_usd_final
                reconcile_run_usd_final(analysis_id, reserved=_reserved_usd,
                                        actual=cost["total_usd"], day=_reserve_day)
            except Exception as _e:  # noqa: BLE001 — قناة جانبية لا تُسقِط التشغيلة
                log.warning("final usd reconcile failed for %s: %s", analysis_id, _e)
                silk_usage.reconcile_usd(reserved=_reserved_usd,
                                         actual=cost["total_usd"], day=_reserve_day)
        else:
            silk_usage.reconcile_usd(reserved=_reserved_usd,
                                     actual=cost["total_usd"], day=_reserve_day)
        budget_status = _research_budget_status(economics)
        if _stage_budget["halted_before"]:
            # p6/T9: الخرق الدولاري يُسمّى صراحةً — السقف والمرحلة التي أُوقف
            # قبلها، ورسالة بلغة الزائر (لا أسماء متغيّرات بيئة).
            budget_status["exhausted"] = True
            budget_status["caps_hit"] = list(budget_status.get("caps_hit") or []) \
                + _stage_budget["caps_hit"]
            budget_status["halted_before"] = _stage_budget["halted_before"]
            budget_status["message"] = (
                "أُوقفت التشغيلة قبل مرحلة "
                + {"synthesis": "حكم الذكاء الاصطناعي", "writer": "كتابة التقرير",
                   "analyst": "التحليل الشامل"}.get(
                    _stage_budget["halted_before"], _stage_budget["halted_before"])
                + " لبلوغ سقف الإنفاق المحدَّد. ما اكتمل محفوظ ولا يُعاد دفعه؛ "
                "يمكن استكمال التشغيلة بعد رفع السقف.")

        # روابط المستوردين جُمِعت تلقائياً **قبل الكاتب** (أمر المالك المُحدَّث
        # ITEM 1) في مرحلة «إكمال بيانات المستوردين» أعلاه — تُشحن مع التقرير
        # من التشغيلة الأولى. `importer_leads` جاهز هنا لبناء النتيجة.
        result: dict = {
            "product": product, "hs_code": hs_code,
            # ثقةُ التصنيف تصل النتيجةَ فالعرض (كانت تُهدَر => «ثقة التصنيف —»).
            "hs_confidence": hs_confidence,
            "year": None,
            "preliminary": True,
            "market": {"iso3": market_ref.iso3, "m49": market_ref.m49,
                      "iso2": market_ref.iso2, "name_en": market_ref.name_en,
                      "name_ar": market_ref.name_ar},
            # **الموجة D (الجذر ١ + D-01).** كان هنا `[]` بتعليل «لا ترتيب
            # أسواق هنا». والتعليلُ صحيح — لا **ترتيب** — لكنّ النتيجة كانت
            # أوسعَ بكثير: `build_view` يبني كلَّ ما يتعلّق بالسوق من
            # `top = markets[0] if markets else None`، فسقط معاً **محرّكُ
            # القرار** وقسمُ «موقعك التنافسي» وتحذيرُ القِدَم ذو الطبقتين
            # (S-01) وبوّابةُ الأهلية (R-03) وحرّاسُ الدرس ٨٨ (X-03)
            # و`_completeness` — على كلّ دراسة مصنع.
            #
            # الآن صفٌّ **واحد** للسوق المُحلَّل: ليس ترتيباً، بل حاملُ نتائجِ
            # تحليله. يُملأ أدناه بعد بناء النتيجة (يحتاج البعثاتِ نفسَها).
            "markets": [],
            "deep_research": {
                "missions": mission_reports, "analyst": analyst_out,
                "verdict": verdict, "report": report_out,
                # نمط الكتابة المستعمَل فعلاً — يُخزَّن كي تتّسق طبقة العرض
                # وإعادة التوليد/التصدير مع ما كُتب به التقرير أول مرّة.
                "report_style": eff_report_style,
                # C5 (Command #5b): قائمة مستوردين/موزعين قابلين للتواصل
                # (خرائط قوقل/Places + مرشّحو ويب) — تُعرَض في قسم الدخول.
                "importer_leads": importer_leads,
                "trace_id": research_run.get("trace_id"),
                # P1 (حادثة نفاد الاعتمادات): سقف بلغ حدّه = إنهاء رشيق
                # بفجوات معلنة، لا خطأ صلب — لكن يُذكَر صراحةً أيّ سقف.
                "budget_status": budget_status,
                # محرك دراسة السوق (PR #238/#242، الموجتان ١-٣ — SHADOW بحت):
                # ثغرةٌ اكتُشفت أثناء ربط الموجة ٣ — `research_run["charter"]`/
                # `["fact_records"]` كانا يُحسَبان فعلياً داخل `silk_missions.
                # deep_research()` لكن لا يصلان أبداً `result["deep_research"]`
                # هنا (خط أنابيب api.py منفصلٌ يبني قاموسه الخاص من الصفر) —
                # فكانا `{}` دوماً في كل عرض/تخزين إنتاجي حقيقي رغم حسابهما.
                # يُصلَح هنا بتمريرهما صراحةً؛ إضافيٌّ بحت، صفر أثر على البقية.
                "charter": research_run.get("charter") or {},
                "fact_records": research_run.get("fact_records") or {},
                "judge_abstain_shadow": judge_abstain_shadow or {},
            },
            "data_economics": economics,
        }
        # المرحلة 0: سجل المشغّل لطبقة سد الفجوات — قبل/بعد، الأصناف، مسارات
        # الإغلاق، وقائمة OPS (إصلاحات المنصّة). لا يقرأه build_view — لا يصل
        # لأي سطح عميل (نمط عزل ops_errors/watchdog).
        if gap_recovery_log is not None:
            result["gap_recovery"] = gap_recovery_log
        if hs_note:
            result["hs_resolution_note"] = hs_note
        # مصدرُ الرمز حين حُسِم آلياً بالسمة الرقمية (بلاغ المُشرِف) — يعرضه
        # التقريرُ صراحةً («الرمز محدَّد من صورة العبوة» / «من مصدر ويب: …»)
        # فلا يظهر رمزٌ حُسِم آلياً بلا إفصاحٍ عن دليله.
        if isinstance(hs_provenance, dict) and hs_provenance.get("hs6"):
            result["hs_provenance"] = hs_provenance
        # ملخّصُ خطّ التصنيف الواحد (`silk_hs_pipeline`) — **حاملُ الإفصاح**.
        # بدونه كان رمزٌ أكّده المصنعُ رغم تعارضه يبني تقريراً لا يذكر التعارض
        # إطلاقاً: العقدُ يحسبه، ولا أحدَ يحمله إلى وجه التقرير.
        if isinstance(hs_classification, dict) and hs_classification:
            result["hs_classification"] = hs_classification
        # Wave 1.3: عقد تأكيد الرمز يُخزَّن في النتيجة — تعيد طبقة العرض تأطير
        # أرقام كومتريد وتسقف الثقة عند التعليم (silk_render._deep_research_view).
        if isinstance(hs_conf, dict):
            result["hs_confirmation"] = hs_conf
        # إعادةُ تحقّقٍ للرمز المُعاد من سجلّ (بلاغ «حليب نادك»، الثغرة الثانية):
        # `resume` يتخطّى بوّابةَ ما قبل التشغيل عمداً (البعثاتُ المخزَّنة تُعاد
        # بلا نداءٍ جديد، فحجبُها يُفقِد عملاً مدفوعاً اكتمل) — لكنّ المرورَ
        # الصامت يُعيد إنتاج تقريرٍ على رمزٍ ربّما صار خاطئاً. العقد: **يمرّ
        # ويُوسَم**، فتعرضه طبقةُ العرض في «حدود هذا التقرير».
        # **لا تُعاد المصالحة على رمزٍ حُسِم بقياس** (اللائحة ٦٥، منعاً لعائلة
        # اللائحة ١٢ «الحدود تناقض المتن»): `revalidate` يقارن الرمزَ بمُحلِّلٍ
        # **لفظيّ** — وهو بالضبط ما عجز عن التمييز بين بنود الترويسة فاستُدعي
        # القياسُ أصلاً. تركُه يعمل يُخرِج سطرَ حدٍّ يقول «المُحلِّل اليوم يعيد
        # رمزاً آخر» بجوار سطرِ إفصاحٍ يقول «الرمز محدَّد من صورة العبوة» —
        # تناقضٌ صريح، ومقارنةُ دليلٍ مقيسٍ بتطابقٍ حرفيّ. سطرُ الإفصاح وحده
        # يبقى، وهو يذكر القياسَ ومصدرَه وحدودَ الثقة.
        if not (isinstance(hs_provenance, dict) and hs_provenance.get("hs6")):
            try:
                from silk_hs_confirm import revalidate
                _reval = revalidate(product, hs_code, hs_confidence)
                if _reval:
                    result["hs_revalidation"] = _reval
            except Exception as e:  # noqa: BLE001 — وسمٌ تحسينيّ لا يُسقِط تشغيلة
                log.warning("hs revalidation skipped: %s", e)
        if not ai_ok:
            result["ai_extras_note"] = ai_note
        # التدهور الفعلي = عدم الجهوزية (ready=False، بلاغ حي: _free_ai_
        # extras_allowed تعيد (True, "") حين لا مفتاح إطلاقاً — "لا قيد على
        # إضافات كلود" لأن /analyze لا يحتاجها أصلاً؛ ذلك المنطق يُخفي هنا
        # حقيقة أن /research **لا يعمل بلا مفتاح** رغم ai_ok=True ظاهرياً)
        # أو فشل الحجز الذرّي المتأخر رغم اجتياز البوابة (سباق نادر).
        if not ready or not ai_ok:
            result["degraded"] = True
            result["degraded_reason"] = (ai_note if not ai_ok else "") or ready_reason
        # **الموجة D.** صفُّ السوق المُحلَّل + قرارُ المحرّك الحتميّ — قبل
        # بناء العرض حصراً (العرضُ يقرأ `markets[0]`).
        _attach_deep_market_row(result, market_ref, product_card_dict,
                                regulatory=_deep_reg,
                                decision=_deep_decision)
        # البند 7 (أمر إصلاح المحرّك): فحص اتجاه الحكم مقابل الدليل عبر
        # التشغيلات لنفس (المنتج × السوق) — يُحسَب قبل بناء العرض فيمرّ
        # عبر `build_view` إلى بوابة الجودة (`verdict_evidence_direction`
        # المُفشِل). قناة جانبية: أي عطل لا يمسّ التشغيلة.
        try:
            import silk_consistency
            result["deep_research"]["verdict_consistency"] = (
                silk_consistency.check_against_history(
                    result, analysis_id=analysis_id))
        except Exception as e:  # noqa: BLE001 — فحص إضافي لا شرط تشغيل
            log.warning("verdict consistency check failed: %s", e)
        result["view"] = _view(result)

        # بوابة الجودة قبل التسليم (الموجة ١٠) — تعمل على القالب الموحّد
        # النهائي **قبل** أي عرض docx، فتلحَق نتيجتها بالتتبّع وبقسم
        # "منهجية البحث ونطاقه" داخل التقرير (طبقة العرض، silk_reports.py).
        _attach_quality_gate(result, research_run.get("trace_id"))
        _attach_watchdog(result, analysis_id, "research")
        return result

    def _deep_engine_decision(dr: dict, market_ref, hs_code: str | None,
                              card: dict | None):
        """(حالةُ الحواجز، قرارُ المحرّك) — تُحسَبان **مرّةً واحدة** للتشغيلة.

        الموجة Z (Z-01): كانا يُحسَبان بعد الكاتب، فيصل الكاتبَ وغلافَ التقرير
        حكمٌ غيرُ حكمِ المحرّك. الحسابُ هنا مبكّرٌ ووحيد، ونتيجتُه تُمرَّر
        للصفّ بدل إعادة حسابها — نسختان من نفس الحساب قد تتباعدان.

        أيُّ عطلٍ يعيد `None` فيبقى السلوكُ كما كان قبل الموجة D بالضبط.
        """
        reg = None
        try:
            from silk_requirements_agent import regulatory_state
            reg = regulatory_state(market_ref.iso3, hs_code)
        except Exception as e:  # noqa: BLE001 — الحالةُ إضافةٌ لا شرط
            log.warning("deep regulatory state failed: %s", e)
        dec = None
        try:
            import silk_deep_pillars
            dec = silk_deep_pillars.decide_for_deep(
                dr, product_card=card, regulatory=reg)
        except Exception as e:  # noqa: BLE001 — القرارُ لا يُسقِط تشغيلة
            log.warning("deep decision failed: %s", e)
        return reg, dec

    def _attach_deep_market_row(result: dict, market_ref, card: dict | None,
                                *, regulatory: dict | None = None,
                                decision: "dict | None" = None):
        """ابنِ صفَّ السوق المُحلَّل وشغّل **محرّك القرار الواحد** عليه.

        الجذر ١ في `docs/ENGINE_AUDIT.md`: `markets: []` أسقط ستَّ طبقاتٍ دفعةً
        واحدة على مسار المصنع. الصفُّ هنا ليس ترتيبَ أسواق — هو حاملُ نتائج
        السوق الوحيدة المُحلَّلة، وهو ما يتوقّعه `build_view`.

        القرارُ من `silk_decision.decide` نفسِه الذي يخدم `/analyze` — لا منطقَ
        ثانٍ (D-01). وأيُّ عطلٍ يترك الصفَّ بلا قرارٍ فيبقى السلوكُ كما كان.
        """
        dr = result.get("deep_research") or {}
        row = {
            "iso3": market_ref.iso3, "name_ar": market_ref.name_ar,
            "name_en": market_ref.name_en, "m49": market_ref.m49,
            # `build_view` و`silk_reports`/`silk_render` يقرؤون `country` مفتاحاً
            # للاسم المعروض؛ غيابُه كان يُخرِج عنوانَ «٩.1 None» في docx المشغّل
            # ويُفشِل `render_text` بـTypeError عند `{m['country']:<22}`. اسمُ
            # السوق المُحلَّلة عربيّاً (احتياطُه الإنجليزيّ) — لا اسمَ مُرتِّب.
            "country": market_ref.name_ar or market_ref.name_en,
            # لا درجةَ **ترتيبٍ** هنا: سوقٌ واحدةٌ مُحلَّلة، والدرجةُ المعروضة
            # تأتي من محرّك القرار (تُملأ أدناه من `decision` لا من المُرتِّب).
            "rank": 1, "deep": True,
        }
        try:
            import silk_deep_pillars
            # **الجذرُ لم يكن `markets: []` وحدَه.** `build_view` يبني
            # `components_detail` من `row["components"]`؛ فصفٌّ بلا مكوّنات
            # يُبقي حارسَي الدرس ٨٨ (X-03) وتحذيرَ القِدَم (S-01) خامدَين
            # بشكلٍ آخر. مقيسٌ: `components_detail` صفر قبل هذه الإضافة.
            row["components"] = silk_deep_pillars.build_components(dr)
        except Exception as e:  # noqa: BLE001 — المكوّناتُ إضافةٌ لا شرط
            log.warning("deep components failed: %s", e)
        # الموجة Z (Z-01): الحالةُ والقرارُ مُحسوبان سلفاً قبل الكاتب —
        # يُستهلكان هنا ولا يُعاد حسابُهما (نسختان قد تتباعدان). المسارُ
        # الاحتياطيّ يبقى لمُنادٍ لا يملكهما (استئنافُ تشغيلةٍ مخزَّنة).
        if regulatory is None or decision is None:
            _reg, _dec = _deep_engine_decision(
                dr, market_ref, result.get("hs_code"), card)
            regulatory = regulatory if regulatory is not None else _reg
            decision = decision if decision is not None else _dec
        if regulatory is not None:
            row["regulatory"] = regulatory
        if decision:
            row["decision"] = decision
            # `build_view` يقرأ `total_score`/`confidence` من الصفّ لقائمة
            # `view["markets"]`؛ غيابُهما كان يُمرِّر None فيَنكسر `render_text`
            # على `{m['score']:.3f}`. الدرجةُ من محرّك القرار الواحد نفسِه —
            # لا من مُرتِّب الأسواق (D-01: حكمٌ واحد، لا مصدرَ درجةٍ ثانٍ).
            if decision.get("score") is not None:
                row["total_score"] = decision.get("score")
            if decision.get("confidence") is not None:
                row["confidence"] = decision.get("confidence")
        result["markets"] = [row]

    _TRANSIENT_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 529})

    def _llm_error_retryable(err: dict | None) -> bool:
        """هل يستحق فشلُ نداء كلود إعادةَ محاولة (عابر) أم هو دائم؟ (p6/T3)
        عابر: مهلة/شبكة/5xx/429/529 ⇒ إعادة التوليد مُجدية. دائم: رفض النموذج
        أو 4xx آخر (حمولة مرفوضة) ⇒ إعادة المحاولة عبث حتى تُصلَح الحمولة.
        بلا تفصيل (None) ⇒ True تحفّظاً (لا نمنع إعادة توليد رخيصة بلا دليل)."""
        if not err:
            return True
        if err.get("type") in ("refusal", "empty_response"):
            return False
        status = err.get("status_code")
        if status:
            return int(status) in _TRANSIENT_HTTP_STATUSES
        # نوع غير معروف بلا رمز حالة (خطأ شبكة/مكتبة) ⇒ عابر تحفّظاً.
        return True

    def _stage_checkpoint(analysis_id: int | None, stage: str, payload,
                          status: str = "succeeded",
                          market_iso3: str | None = None) -> None:
        """نقطة تفتيش مرحلة (الموجة p6، T2) — نظير `silk_missions._checkpoint`
        للمحلل/الحكم/الروابط: تُكتب فور عودة المرحلة لا في الحفظ النهائي.
        تحسين لا شرط تشغيل: بلا `analysis_id` (persist=False) لا شيء، وفشل
        الكتابة تحذير لا استثناء (نفس عقد نقطة تفتيش البعثة)."""
        if analysis_id is None:
            return
        try:
            from silk_storage import save_stage_checkpoint
            save_stage_checkpoint(analysis_id, stage, payload, status=status,
                                  market_iso3=market_iso3)
        except Exception as e:  # noqa: BLE001 — نقطة التفتيش تحسين لا شرط تشغيل
            log.warning("stage checkpoint %s/%s failed: %s", analysis_id,
                        stage, e)

    return _run_research_pipeline
