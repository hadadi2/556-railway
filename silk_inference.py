"""الاستدلال العابر للمهمات — deterministic cross-mission inference (البند ٦).

> **الغرض.** كل بعثة تكتب قسمها ولا شيء يقرأ الاثنتي عشرة معاً — وقائع
> دراسة #14 كلها كانت مجموعة ولم يظهر أي استنتاج يجمعها. هذه الوحدة تطبّق
> **أنماطاً عامة** (لا قواعد حليب) على اكتشافات البعثات المخزَّنة وتُخرج
> **فرضيات لا نتائج**: كل إطلاق يحمل الوقائع التي جُمعت، وتفسيرين مرشحين
> على الأقل، وأيهما أرجح ولماذا، والفحص الواحد الذي يحسم.
>
> **الحاكمية:** حتمي بالكامل — stdlib فقط، صفر شبكة، صفر نماذج (قفل AST)،
> ولا يمسّ الحكم ولا الدرجة (لا يدخل `synthesize` ولا `decide` — عرضٌ
> إضافي حصراً). النمط الذي لا يطلق أبداً ميت والذي يطلق على كل شيء عديم
> القيمة — أداة `tools/inference_audit.py` تعدّ الإطلاق على المدونات العشر.
>
> **المناطق العمياء المعلنة (الدرس 172):** المدخلات نصوص ملاحظات البعثات
> المخزنة — إشارةٌ لم تُذكر في ملاحظة (استحواذ لم يرصده أي مصدر، حصة فئةٍ
> بلا نسبة مكتوبة) لا تُرى؛ واستخراج الأرقام regex على الصيغ الشائعة
> («نمو 168%», «حصة 84%») — صياغة بعيدة عنها تفلت. كل نمط يعلن مشغّله
> الدقيق في docstring دالته.
"""
from __future__ import annotations

import re

_PCT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_GROWTH_RE = re.compile(
    r"(?:نمو|ارتفاع|ارتفع|قفز|زيادة|\bgrowth\b|\bup\b|\+)\D{0,15}"
    r"(\d{1,3}(?:\.\d+)?)\s*%")
_DROP_RE = re.compile(
    r"(?:انخفاض|انخفض|تراجع|هبوط|\bdown\b|\bdecline\b|-)\D{0,15}"
    r"(\d{1,3}(?:\.\d+)?)\s*%")
_ACQ_RE = re.compile(r"استحوذ|استحواذ|acquisition|acquired", re.I)
_SHARE_RE = re.compile(r"(?:حصة|حصته|تستحوذ|يستحوذ|share)\D{0,15}"
                       r"(\d{1,3}(?:\.\d+)?)\s*%", re.I)
_FX_STABLE_RE = re.compile(r"سعر الصرف[^.\n]{0,60}(?:مستقر|ثابت|مربوط)"
                           r"|peg|stable exchange", re.I)
_SEASON_TOKENS = ("رمضان", "الموسم", "موسمي", "seasonal", "ramadan")


def _field(f: object, name: str):
    """حقل اكتشافٍ بالشكلين: dict مخزَّن أو AgentReport/DataPoint حي."""
    if isinstance(f, dict):
        return f.get(name)
    return getattr(f, name, None)


def _findings(dr: dict, key: str) -> list:
    rep = ((dr or {}).get("missions") or {}).get(key) or {}
    return list(_field(rep, "findings") or [])


def _texts(dr: dict, *mission_keys: str) -> list[tuple[str, str]]:
    """أزواج (نص، مصدر معلَن) من اكتشافات بعثات مسماة — بالشكلين."""
    out: list[tuple[str, str]] = []
    missions = (dr or {}).get("missions") or {}
    for key in mission_keys:
        rep = missions.get(key) or {}
        for f in (_field(rep, "findings") or []):
            note = str(_field(f, "note") or "")
            val = _field(f, "value")
            blob = (note + " " + val) if isinstance(val, str) else note
            src = str(_field(f, "source") or key)
            if blob.strip():
                out.append((blob, f"{key}: {src}"))
        summary = str(_field(rep, "summary") or "")
        if summary.strip():
            out.append((summary, f"{key}: الملخص"))
    return out


_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _yearly_series(dr: dict, key: str) -> dict:
    """سلاسل سنوية {مقياس: [(سنة، قيمة)]} من اكتشافات بعثة — **بنفس
    المقياس حصراً**: التجميع على نص الملاحظة بعد نزع السنة، فلا تُخلَط
    مرآةُ صادراتٍ بوارداتٍ مباشرة في سلسلة واحدة (قاعدة الدرس 178: لا
    نسبة بسطُها من عالم ومقامها من آخر)."""
    series: dict[str, list[tuple[int, float]]] = {}
    for f in _findings(dr, key):
        note = str(_field(f, "note") or "")
        val = _field(f, "value")
        m = _YEAR_RE.search(note)
        if not m or not isinstance(val, (int, float)) \
                or isinstance(val, bool):
            continue
        metric = _YEAR_RE.sub("سنة", note).strip()
        series.setdefault(metric, []).append((int(m.group(1)), float(val)))
    return {k: sorted(v) for k, v in series.items() if len(v) >= 2}


def _yoy_moves(dr: dict, key: str) -> list[tuple[float, str, str]]:
    """حركات سنوية (نسبة%، وصف، مصدر) من السلاسل أحادية المقياس —
    موجبة صعوداً وسالبة هبوطاً؛ قسمة على صفر تُسقط الحركة لا تُصفّرها."""
    out = []
    for metric, rows in _yearly_series(dr, key).items():
        for (y1, v1), (y2, v2) in zip(rows, rows[1:]):
            gap = y2 - y1
            if v1 <= 0 or v2 <= 0 or gap < 1:
                continue
            # فجوة سنوات تُسنوَّى (نمو مركّب) — «-63% عبر أربع سنوات» ليست
            # حركة سنوية فوق 40%، وعدُّها كذلك إطلاق زور (قاعدة CAGR
            # بطرفيها المعلنين: الوصف يحمل السنتين الفعليتين دائماً).
            pct = ((v2 / v1) ** (1.0 / gap) - 1.0) * 100.0
            out.append((pct,
                        f"{metric}: {y1}→{y2} ({v1:,.0f}→{v2:,.0f}، "
                        f"{pct:+.0f}%" + ("/سنة مركّباً" if gap > 1 else "")
                        + ")",
                        f"{key}"))
    return out


def _hyp(pattern: str, title: str, facts: list[str],
         explanations: list[str], likelier: str, why: str,
         settling_check: str) -> dict:
    """فرضية مكتملة الحقول — العقد البنيوي: تفسيران على الأقل وفحص حاسم."""
    assert len(explanations) >= 2, "فرضية بتفسير واحد ليست فرضية"
    return {"pattern": pattern, "title": title, "facts": facts,
            "explanations": explanations, "likelier": likelier,
            "why": why, "settling_check": settling_check,
            "status": "فرضية للتحقق — ليست نتيجة"}


def _p_channel_redirection(dr: dict) -> "dict | None":
    """نمط ١: مهيمنٌ يستحوذ على موزّع + قفزة استيراد ⇒ قد تكون إعادة توجيه
    قناة لا نمو طلب. المشغّل: لفظ استحواذ في اكتشافات المنافسين/المخاطر/
    القنوات + نمو ≥40% في ملاحظات تدفقات التجارة."""
    acq = [(t, s) for t, s in _texts(dr, "competitors", "risk_news",
                                     "channels_importers")
           if _ACQ_RE.search(t)]
    if not acq:
        return None
    spikes = [(p_, d, src) for p_, d, src in _yoy_moves(dr, "trade_flow")
              if p_ >= 40]
    for t, s in _texts(dr, "trade_flow", "pricing_scout"):
        m = _GROWTH_RE.search(t)
        if m and float(m.group(1)) >= 40:
            spikes.append((float(m.group(1)), t, s))
    if not spikes:
        return None
    g, spike_t, spike_s = max(spikes)
    facts = [f"استحواذ مرصود: {acq[0][0][:110]} ({acq[0][1]})",
             f"قفزة استيراد {g:g}%: {spike_t[:110]} ({spike_s})"]
    share = None
    for t, s in _texts(dr, "competitors", "trade_flow"):
        m = _SHARE_RE.search(t)
        if m and float(m.group(1)) >= 60:
            share = (float(m.group(1)), s)
            facts.append(f"حصة مهيمن {share[0]:g}% ({s})")
            break
    return _hyp(
        "channel_redirection",
        "قفزة الاستيراد قد تكون إعادة توجيه قناة لا نمواً في الطلب",
        facts,
        ["نما الطلب الفعلي في السوق بهذا المقدار",
         "أعاد المستحوِذ توجيه مشترياته عبر قناة الاستيراد بعد الاستحواذ "
         "فارتفع الرقم دون أن يكبر السوق نفسه"],
        "إعادة توجيه القناة",
        "اجتماع الاستحواذ مع القفزة في نافذة واحدة"
        + (f" مع حصة مهيمن {share[0]:g}%" if share else "")
        + " يجعل تفسير القناة أرجح من نموّ استهلاكي بهذا الحجم المفاجئ",
        "قارن مبيعات التجزئة (أو استهلاك الفرد) قبل القفزة وبعدها — نموّ "
        "الطلب الحقيقي يظهر هناك، وإعادة التوجيه لا تظهر")


def _p_wrong_heading(dr: dict) -> "dict | None":
    """نمط ٢: البند المدروس صغير وفئة مجاورة كبيرة ⇒ قد تكون الدراسة على
    البند الخطأ — يُقال باسمه. المشغّل: اكتشاف مستهلك يحمل نسبتي حصة
    لفئتين وأكبرهما ≥ ٣× حصة فئة المنتج المدروس."""
    product = str((dr or {}).get("product") or "")
    if not product:
        return None
    # §58 (find all gaps): `product='ال'`/فراغ صرف (صادقٌ لكن split()==[]) كان
    # يرفع IndexError يبتلعه حارس derive_hypotheses العام — يُعالَج هنا مباشرة.
    _root_parts = product.replace("ال", "", 1).split() if product else []
    root = _root_parts[0] if _root_parts else ""
    rows: list[tuple[str, float, str, str]] = []   # (فئة، %، نص، مصدر)
    for t, s in _texts(dr, "consumer_culture", "demand_trends"):
        for m in _PCT_RE.finditer(t):
            # نافذة سياق قبل النسبة — «حليب سائل 16%» يُنسب لحليب وإن كانت
            # الكلمة الملاصقة «سائل».
            ctx = t[max(0, m.start() - 30):m.start()]
            words = re.findall(r"[\w؀-ۿ]{3,}", ctx)
            if not words:
                continue
            label = words[-1]
            rows.append((label if root not in ctx else product,
                         float(m.group(1)), t, s))
    if len(rows) < 2:
        return None
    prod_rows = [r for r in rows if r[0] == product
                 or (root and root in r[0])]
    other_rows = [r for r in rows if r not in prod_rows]
    if not prod_rows or not other_rows:
        return None
    big = max(other_rows, key=lambda r: r[1])
    small = min(prod_rows, key=lambda r: r[1])
    if big[1] < 3 * small[1]:
        return None
    return _hyp(
        "wrong_heading",
        f"قد تكون الدراسة على البند الخطأ — «{big[0]}» أكبر بكثير من "
        f"«{product}» في هذا السوق",
        [f"حصة {small[0]} نحو {small[1]:g}% ({small[3]})",
         f"حصة {big[0]} نحو {big[1]:g}% ({big[3]})"],
        [f"سوق {product} صغير فعلاً وهذه حدود الفرصة",
         f"الفرصة الحقيقية في فئة «{big[0]}» المجاورة والدراسة وُجّهت "
         "لبند أضيق منها"],
        f"الفرصة في «{big[0]}»",
        f"فارق ×{big[1] / max(small[1], 0.1):.0f} بين الفئتين في سوق واحد "
        "أكبر من أن يُقرأ هامشاً إحصائياً",
        f"شغّل دراسة على بند «{big[0]}» (رمزه الجمركي) وقارن حجمي "
        "الواردات تحت الرمزين")


def _p_unserved_niche(dr: dict) -> "dict | None":
    """نمط ٣: نموّ بحث مرتفع لصيغة منتج + غيابها من قائمة الموردين ⇒ نيش
    غير مخدوم. المشغّل: نمو ≥100% في اكتشافات الاتجاهات لمصطلحٍ، والمصطلح
    غائب من نصوص المنافسين/الموردين."""
    supplier_blob = " ".join(t for t, _ in _texts(
        dr, "competitors", "channels_importers"))
    _STOP = ("بنسبة", "بحث", "نمو", "عمليات", "خلال", "سنتين", "سنوات",
             "مؤشر", "الفئة", "search", "growth")
    for t, s in _texts(dr, "demand_trends", "consumer_culture"):
        m = _GROWTH_RE.search(t)
        if not m or float(m.group(1)) < 100:
            continue
        # المصطلح قد يسبق رمز النمو أو يليه («نمو 200% في بحث حليب بروتين»)
        words = [w for w in re.findall(r"[\w؀-ۿ]{4,}", t[:m.start()])
                 if w not in _STOP]
        words += [w for w in re.findall(r"[\w؀-ۿ]{4,}", t[m.end():])[:5]
                  if w not in _STOP]
        term = words[-1] if words else ""
        if not term:
            continue
        if supplier_blob and term not in supplier_blob:
            g = float(m.group(1))
            return _hyp(
                "unserved_niche",
                f"طلب متصاعد على «{term}» بلا مورد يلبيه — نيش غير مخدوم "
                "محتمل",
                [f"نمو بحث {g:g}%: {t[:110]} ({s})",
                 f"«{term}» غائبة من قوائم الموردين والمنافسين المرصودة"],
                ["اهتمام بحثي عابر لا يترجم إلى شراء",
                 "طلب حقيقي متكوّن لم يصله العرض بعد — فرصة دخول مبكر"],
                "طلب متكوّن لم يصله العرض",
                "نموٌّ بهذا الحجم مع غياب كامل من العرض المرصود عادةً "
                "يسبق دخول أول مورد لا يليه",
                f"افحص مبيعات منصة تجزئة إلكترونية واحدة لصنف «{term}» "
                "شهرين متتاليين — الشراء الفعلي يحسم بين التفسيرين")
    return None


def _p_volatility(dr: dict) -> "dict | None":
    """نمط ٤: تقلب استيراد سنوي فوق 40% صعوداً وهبوطاً ⇒ نصيحة بنية العقود
    (عقود قصيرة، لا التزام إنتاجي). المشغّل: نمو ≥40% وهبوط ≥40% معاً في
    ملاحظات تدفقات التجارة."""
    ups, downs = [], []
    for p_, d, src in _yoy_moves(dr, "trade_flow"):
        if p_ >= 40:
            ups.append((p_, d, src))
        elif p_ <= -40:
            downs.append((abs(p_), d, src))
    for t, s in _texts(dr, "trade_flow"):
        mu = _GROWTH_RE.search(t)
        md = _DROP_RE.search(t)
        if mu and float(mu.group(1)) >= 40:
            ups.append((float(mu.group(1)), t, s))
        if md and float(md.group(1)) >= 40:
            downs.append((float(md.group(1)), t, s))
    if not ups or not downs:
        return None
    u, ut, us = max(ups)
    d, dt, ds = max(downs)
    return _hyp(
        "import_volatility",
        "تقلب الاستيراد فوق 40% سنوياً — سوق عقود قصيرة لا التزامات",
        [f"ارتفاع {u:g}%: {ut[:110]} ({us})",
         f"انخفاض {d:g}%: {dt[:110]} ({ds})"],
        ["صدمة عرض/سعر عالمية عابرة انعكست في سنة واحدة",
         "سوق يشتري بعقود قصيرة ويبدّل الموردين مع السعر — لا ولاء "
         "توريد"],
        "سوق عقود قصيرة",
        "التأرجح في الاتجاهين خلال سلسلة قصيرة سمة هيكل شراء لا صدمة "
        "واحدة",
        "اطلب من مستوردَين اثنين مدة عقود توريدهما الحالية — سنة فأقل "
        "تؤكد الفرضية")


def _p_no_seasonal(dr: dict) -> "dict | None":
    """نمط ٥: مصطلح موسمي أدنى بكثير من المصطلح العام ⇒ لا تخزين موسمياً —
    خطط للتوريد المنتظم. المشغّل: رقم بجوار لفظ موسمي ≤ خُمس رقم عام في
    اكتشافات الاتجاهات."""
    seasonal, general = None, None
    for key in ("demand_trends", "consumer_culture"):
        for f in _findings(dr, key):
            note = str(_field(f, "note") or "")
            val = _field(f, "value")
            nums = [float(x) for x in
                    re.findall(r"\b(\d{1,3}(?:\.\d+)?)\b", note)]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                nums.append(float(val))
            if not nums:
                continue
            src = f"{key}: {_field(f, 'source') or key}"
            if any(tok in note for tok in _SEASON_TOKENS):
                v = min(nums)
                if seasonal is None or v < seasonal[0]:
                    seasonal = (v, note, src)
            else:
                v = max(nums)
                if v <= 100 and (general is None or v > general[0]):
                    general = (v, note, src)
    if not seasonal or not general or general[0] <= 0:
        return None
    if seasonal[0] > 0.2 * general[0]:
        return None
    return _hyp(
        "no_seasonal_stockpiling",
        "لا موسمية شراء تُذكر — لا تخطط لمخزون موسمي",
        [f"المؤشر الموسمي {seasonal[0]:g}: {seasonal[1][:110]} "
         f"({seasonal[2]})",
         f"المؤشر العام {general[0]:g}: {general[1][:110]} ({general[2]})"],
        ["الاهتمام الموسمي موجود لكنه يمرّ بقنوات لا يراها مؤشر البحث",
         "الاستهلاك مستقر على مدار السنة فعلاً — لا ذروة تخزين"],
        "استهلاك مستقر بلا ذروة",
        f"نسبة {seasonal[0]:g} إلى {general[0]:g} أدنى من خُمس — فارق "
        "أكبر من أثر قياس",
        "اسأل مستورداً واحداً عن جدول طلبياته في الشهرين قبل الموسم — "
        "غياب الذروة هناك يحسم")


def _p_currency_stable(dr: dict) -> "dict | None":
    """نمط ٦: عملة مستقرة/مربوطة ⇒ سعّر بالدولار بلا كلفة تحوّط. المشغّل:
    لفظ استقرار/ربط بجوار سعر الصرف في اكتشافات المخاطر."""
    for t, s in _texts(dr, "risk_news", "demographics_economy"):
        if _FX_STABLE_RE.search(t):
            return _hyp(
                "currency_stable",
                "العملة مستقرة — التسعير بالدولار بلا كلفة تحوّط",
                [f"استقرار الصرف: {t[:110]} ({s})"],
                ["استقرار مدعوم بربطٍ رسمي يستمر ما استمر الربط",
                 "استقرار ظرفي قابل للانكسار مع صدمة احتياطات"],
                "استقرار قابل للاعتماد في أفق التعاقد",
                "الربط الرسمي المعلن أثبت من متوسط تقلب عائم، والكسر "
                "حدث سيادي يُرى قادماً",
                "تحقق من نظام الصرف المعلن لدى البنك المركزي وتاريخ آخر "
                "تعديل له")
    return None


_PATTERNS = (_p_channel_redirection, _p_wrong_heading, _p_unserved_niche,
             _p_volatility, _p_no_seasonal, _p_currency_stable)


def derive_hypotheses(dr: dict) -> list[dict]:
    """طبّق الأنماط الستة على تشغيلة مخزَّنة — قائمة فرضيات (قد تكون فارغة).

    كل عطل نمطٍ يُعزَل: نمطٌ يخفق لا يُسقط البقية ولا التشغيلة (العرض
    إثراء لا شرط)."""
    out: list[dict] = []
    for pattern in _PATTERNS:
        try:
            h = pattern(dr or {})
        except Exception:  # noqa: BLE001 — إثراء لا يُسقط عرضاً
            h = None
        if h:
            out.append(h)
    return out
