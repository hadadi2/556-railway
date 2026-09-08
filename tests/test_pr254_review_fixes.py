"""أقفال سلوكية لإصلاحات مراجعة PR #254 — behavioral locks for the review fixes.

كل قفل هنا يقيس **الأثر** لا النصّ: يكتب عبر الطبقة الحقيقية ثم يقرأ الصفّ
بـSQL خام — فحوارس «السطر موجود في المصدر» وحدها سبق أن بقيت خضراء بينما
الكتابة نفسها تُرمى صامتةً (حادثة `_WRITABLE` أدناه).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import platform_helpers as H


def test_hs_provenance_columns_actually_persist(monkeypatch):
    """عمودا الترحيل ٠١٧ (`hs_source`/`hs_set_at`) يصلان القاعدة فعلاً.

    الحادثة: قائمة `_WRITABLE["products"]` لم تُوسَّع مع الترحيل ٠١٧، فكان
    `update()` يُسقط المفتاحين صامتَين ويبقى الصفّ على `hs_source='unknown'`
    (افتراض العمود) — بينما اختبارات النصّ في `test_platform_hs_two_paths.py`
    خضراء لأن سطر الكتابة موجود في `api.py` حرفياً. القفل هنا سلوكيّ:
    كتابة عبر المستودع ثم قراءة خام، لا نظرة على المصدر.
    """
    H.setup_env(monkeypatch)
    f = H.make_factory("gold", "hs-prov@f.local")
    from silk_platform import db as pdb, repository
    ts = "2026-08-31T00:00:00+00:00"
    conn = pdb.connect()
    try:
        row = repository.products(conn).create(
            f["account_id"], {"name": "حلاوة طحينية"})
        repository.products(conn).update(
            f["account_id"], row["id"],
            {"hs_code": "170490", "hs_source": "manual", "hs_set_at": ts})
        raw = conn.execute(
            "SELECT hs_code, hs_source, hs_set_at FROM products WHERE id = ?",
            (row["id"],)).fetchone()
    finally:
        conn.close()
    assert raw["hs_code"] == "170490"
    assert raw["hs_source"] == "manual", (
        "hs_source أُسقط صامتاً في _WRITABLE — بقي على افتراض العمود "
        f"{raw['hs_source']!r}")
    assert raw["hs_set_at"] == ts, (
        f"hs_set_at أُسقط صامتاً في _WRITABLE — قيمته {raw['hs_set_at']!r}")


def test_echoed_hs_code_patch_does_not_upgrade_source(monkeypatch):
    """ردُّ الرمز المخزون في PATCH ليس كتابةً يدوية — لا ترقية مصدر صامتة.

    الحادثة (كشفها إصلاح `_WRITABLE` أعلاه): نموذج تحرير المنتج يرسل
    `hs_code` المعبّأ مسبقاً **دائماً** (`web/platform.html`)، و`_product_fields`
    كان يعامل مجرّد حضور المفتاح ككتابة إنسان — فمصنعٌ يعدّل `certifications`
    وحدها يجد رمزَه الموسوم `image` قد صار `manual` بختمٍ جديد، خلافاً لقاعدة
    الترحيل ٠١٧ (لا ترقية ثقة صامتة لصفٍّ قديم). القفل سلوكيّ: PATCH حقيقي
    عبر TestClient ثم قراءة خام.
    """
    H.setup_env(monkeypatch)
    f = H.make_factory("gold", "hs-echo@f.local")
    cl = H.client()
    tok = H.login(cl, f["email"], f["password"])
    from silk_platform import db as pdb, repository
    ts = "2026-08-30T12:00:00+00:00"
    conn = pdb.connect()
    try:
        row = repository.products(conn).create(
            f["account_id"], {"name": "حلاوة طحينية", "hs_code": "170490"})
        # صفٌّ قديم مصدرُه الصورة — الآن قابلٌ للبذر فعلاً بفضل إصلاح _WRITABLE.
        repository.products(conn).update(
            f["account_id"], row["id"],
            {"hs_source": "image", "hs_set_at": ts})
    finally:
        conn.close()
    pid = row["id"]

    def _raw():
        c = pdb.connect()
        try:
            return c.execute(
                "SELECT hs_code, hs_source, hs_set_at, certifications "
                "FROM products WHERE id = ?", (pid,)).fetchone()
        finally:
            c.close()

    # (ب) ردّ الرمز نفسه + تعديل الشهادات وحدها ⇒ المصدر والختم يبقيان.
    r = cl.patch(f"/platform/products/{pid}",
                 json={"hs_code": "170490", "certifications": "ISO 22000"},
                 headers=H.hdr(tok))
    assert r.status_code == 200, r.text
    raw = _raw()
    assert raw["certifications"] == "ISO 22000"
    assert raw["hs_source"] == "image", (
        "ردُّ الرمز المخزون رقّى المصدر صامتاً إلى "
        f"{raw['hs_source']!r} — خلافاً لقاعدة الترحيل ٠١٧")
    assert raw["hs_set_at"] == ts, (
        f"ردُّ الرمز المخزون دفع الختم إلى {raw['hs_set_at']!r}")

    # (ج) رمزٌ مختلف فعلاً ⇒ كتابة يدوية حقيقية: manual + ختم جديد.
    r = cl.patch(f"/platform/products/{pid}",
                 json={"hs_code": "080410"}, headers=H.hdr(tok))
    assert r.status_code == 200, r.text
    raw = _raw()
    assert raw["hs_code"] == "080410"
    assert raw["hs_source"] == "manual"
    assert raw["hs_set_at"] and raw["hs_set_at"] != ts


def test_no_op_resave_never_buys_confirmation_nor_wipes_method(monkeypatch):
    """حفظٌ لا يغيّر شيئاً لا يشتري تأكيداً ولا يمسح «كيف حُسِم البند».

    الحادثتان (مراجعة PR #254 على فرع تعديل الدراسة): نموذج تحرير الدراسة
    يرسل `hs_code` المعبّأ مسبقاً **دائماً** (`_studyBody`)، فكان الفرع
    (١) يطابق الرمزَ المردود بمرشّح محفوظ ويرفعه «تأكيداً» بلا نقرة اختيار —
    تأكيد مجاني؛ و(٢) يكتب `hs_classification_method = NULL` فوق مصدرٍ
    مسجَّل (`deterministic_exact`/`llm_grounded`) في حفظٍ لم يلمس الرمز.
    الثابت المحفوظ (origin/main: «وتغييرُ المنتج يُسقِط التأكيد»): تغيير
    المنتج الحقيقي يبقى مُسقِطاً — رمزٌ أُقِرّ لمنتج «أ» لا يسري على «ب».
    """
    import json
    H.setup_env(monkeypatch)
    f = H.make_factory("gold", "hs-noop@f.local")
    cl = H.client()
    tok = H.login(cl, f["email"], f["password"])
    r = cl.post("/platform/studies",
                json={"product": "حلاوة طحينية", "hs_code": "170490"},
                headers=H.hdr(tok))
    assert r.status_code == 200, r.text
    sid = int(r.json()["id"])

    from silk_platform import db as pdb

    def _seed(method, confirmed):
        c = pdb.connect()
        try:
            c.execute(
                "UPDATE studies SET hs_classification_method = ?, "
                "hs_confirmed = ?, hs_candidates = ? WHERE id = ?",
                (method, confirmed,
                 json.dumps([{"hs6": "170490",
                              "band_ar": "حلويات سكرية أخرى"}],
                            ensure_ascii=False), sid))
            c.commit()
        finally:
            c.close()

    def _raw():
        c = pdb.connect()
        try:
            return c.execute(
                "SELECT product, hs_code, hs_confirmed, "
                "hs_classification_method FROM studies WHERE id = ?",
                (sid,)).fetchone()
        finally:
            c.close()

    # (١) حفظٌ يردّد الرمز والمنتج المخزونين (كما يرسلهما النموذج دائماً)
    #     ⇒ لا تأكيد مجاني، والمصدر المسجَّل يبقى.
    _seed("deterministic_exact", 0)
    r = cl.patch(f"/platform/studies/{sid}",
                 json={"product": "حلاوة طحينية", "hs_code": "170490",
                       "title_ar": "عنوان جديد"},
                 headers=H.hdr(tok))
    assert r.status_code == 200, r.text
    raw = _raw()
    assert raw["hs_confirmed"] == 0, (
        "ردُّ الرمز المعبّأ اشترى تأكيداً بلا نقرة اختيار — "
        f"hs_confirmed={raw['hs_confirmed']}")
    assert raw["hs_classification_method"] == "deterministic_exact", (
        "حفظٌ لا يغيّر شيئاً كتب فوق «كيف حُسِم البند» — "
        f"method={raw['hs_classification_method']!r}")

    # (١ب) تعديلٌ يذكر `product` وحده بقيمته المخزونة ⇒ لا مسح ولا إسقاط.
    _seed("llm_grounded", 1)
    r = cl.patch(f"/platform/studies/{sid}",
                 json={"product": "حلاوة طحينية"}, headers=H.hdr(tok))
    assert r.status_code == 200, r.text
    raw = _raw()
    assert raw["hs_confirmed"] == 1, (
        "ردُّ المنتج المخزون نفسِه أسقط تأكيداً قائماً")
    assert raw["hs_classification_method"] == "llm_grounded", (
        "ردُّ المنتج المخزون مسح المصدر إلى "
        f"{raw['hs_classification_method']!r}")

    # (٢) الثابت: تغيير المنتج الحقيقي يُسقِط التأكيد — ولو رُدِّد الرمز
    #     المعبّأ (النموذج يرسله دائماً، والردّ كان يُبقي التأكيد زوراً).
    _seed("user_confirmed", 1)
    r = cl.patch(f"/platform/studies/{sid}",
                 json={"product": "تمور سكري", "hs_code": "170490"},
                 headers=H.hdr(tok))
    assert r.status_code == 200, r.text
    raw = _raw()
    assert raw["product"] == "تمور سكري"
    assert raw["hs_confirmed"] == 0, (
        "رمزٌ مؤكَّد لمنتج «أ» سرى صامتاً على منتج «ب» — الثابت انتُقض")


# ═══════════ Task 4 — خريطة `_rows_by_code` بعمر كائن الصفوف لا بمفتاح المسار ═

_HS_CSV_HEADER = ("hs_code,chapter,chapter_desc_en,heading,heading_desc_en,"
                  "description_en,keywords_ar\n")


def _hs_row(code: str, desc: str) -> str:
    return (f"{code},{code[:2]},x,{code[:4]},x,\"{desc}\",\n")


def test_rows_by_code_rebuilds_after_reference_extension(tmp_path):
    """`load_hs_codes.cache_clear()` يجب أن يُعيد بناء خريطة التأكيد أيضاً.

    الحادثة (مراجعة #254، الملاحظة على `silk_hs_confirm.py:207`): الخريطة
    كانت `lru_cache` بمفتاح المسار وحده — ذاكرةٌ مستقلّة عن `load_hs_codes`.
    بعد `extend_from_comtrade_rows` (يوسّع الملف ويمسح ذاكرة المرجع) يعيد
    `load_hs_codes` صفوفاً **جديدة** بينما `_rows_by_code` يخدم الخريطةَ
    الميّتة، فيعيد `_find_row` لرمزٍ موجودٍ في المرجع `None` ⇒
    `confirmed=None` ⇒ درجة 0.0 ⇒ رفضُ رمزٍ صحيح على مسارٍ ينفق — بلا أيّ
    أثرٍ يُشخَّص. نفسُ عائلة `_INDEX_CACHE` («بذاكرتين مستقلّتين… أخطرُ
    أشكال العطل») على الجار الملاصق.
    """
    import silk_hs_confirm as C
    import silk_hs_resolver as R

    p = tmp_path / "ref.csv"
    p.write_text(_HS_CSV_HEADER + _hs_row("010101", "Horses; live"),
                 encoding="utf-8")
    P = str(p)
    try:
        assert C._find_row("010101", P) is not None
        assert C._find_row("020202", P) is None      # يُخزِّن الخريطة القديمة
        with open(P, "a", encoding="utf-8") as f:
            f.write(_hs_row("020202", "Meat of bovine animals; frozen"))
        # نفسُ ما تفعله extend_from_comtrade_rows بعد توسيع الملف.
        R.load_hs_codes.cache_clear()
        assert len(R.load_hs_codes(P)) == 2          # المرجعُ نفسُه يرى الصفّ
        row = C._find_row("020202", P)
        assert row is not None, (
            "خريطةُ _rows_by_code نجت من مسح ذاكرة المرجع — رمزٌ موجود في "
            "المرجع يُرفَض تصنيفُه بصمت (confirmed=None ⇒ score=0.0)")
        assert row.get("hs_code") == "020202"
    finally:
        R.load_hs_codes.cache_clear()


def test_rows_by_code_cache_is_bounded_to_four_paths(tmp_path):
    """سقفُ المسارات الأربعة (maxsize=4 القديم) محفوظ — حذفُ الأقدم إدراجياً."""
    import silk_hs_confirm as C

    maps = {}
    paths = []
    for i in range(6):
        p = tmp_path / f"ref{i}.csv"
        code = f"0101{i:02d}"
        p.write_text(_HS_CSV_HEADER + _hs_row(code, f"Row {i}"),
                     encoding="utf-8")
        paths.append(str(p))
        maps[str(p)] = C._rows_by_code(str(p))
    cache = C._ROWS_CACHE
    assert len(cache) <= 4, (
        f"خريطةٌ لكل مسار CSV بلا سقف — {len(cache)} مدخلاً")
    assert paths[0] not in cache and paths[1] not in cache, (
        "التجاوز لا يحذف الأقدم أولاً")
    # الأحدث ما زال مخدوماً من الذاكرة — **الكائن نفسه** لا نسخة مبنية من جديد.
    assert C._rows_by_code(paths[-1]) is maps[paths[-1]]


def test_axis_completion_survives_the_pipeline_path(monkeypatch):
    """علم `axis_completion` يعبر مسارَ الخط كاملاً — لا توسعة من الباب الخلفي.

    الحادثة: `_axis_candidates` يعيد بناء أشقّاء المحور من
    `silk_hs_dialog.build_candidates` لكنه كان **يُسقِط** مفتاح
    `axis_completion` من القاموس المُصدَر، فحارسُ `resolve_or_probe`
    (الذي يُسقِط صفوفَ الإكمال قبل المُحلِّل الرقمي — نهيُ المُشرِف الصريح عن
    توسيع التغطية) لا يجد ما يطابقه وتصل **كلُّ** الصفوف إلى
    `resolve_by_attribute`. القفلُ القائم في `test_hs_dialog_official_source`
    يفحص `build_candidates`+`resolve_or_probe` مباشرةً ولا يرى مسارَ الخط —
    فالقفل هنا يمرّ عبر `classify()` نفسِها.
    """
    import silk_hs_attributes as _attrs
    import silk_hs_dialog
    import silk_hs_pipeline
    from silk_hs_resolver import retrieve

    # ما قيّمه الخطُّ فعلاً (استرجاعٌ بدرجات حقيقية) وما أكمله الدليلُ عرضاً.
    hits = retrieve("حليب", top_n=5)
    evaluated = {h["hs_code"] for h in hits}
    top = hits[0]["hs_code"]
    rows = silk_hs_dialog.build_candidates("حليب", [top])
    completion = {r["hs6"] for r in rows
                  if r["axis_completion"] and r["hs6"] not in evaluated}
    assert completion, "لا صفوفَ إكمال لهذا المنتج — الاختبار فارغ"

    seen: list[list] = []

    def _spy(product, candidates, **kw):
        seen.append([c.get("hs6") for c in candidates])
        return {"hs6": None, "value": None, "resolved_from": None}

    monkeypatch.setattr(_attrs, "resolve_by_attribute", _spy)
    out = silk_hs_pipeline.classify("حليب", allow_web=False)

    # فرعُ المحور هو الذي جرى فعلاً — وإلا كان الفحص أدناه فارغاً.
    assert out["refusal_code"] == "hs_axis_disambiguation_needed", out
    assert seen, "المجسُّ لم يُستدعَ — الاختبار لم يبلغ _probe_axis"
    reached = {code for call in seen for code in call}
    leaked = completion & reached
    assert not leaked, (
        f"صفوفُ الإكمال بلغت المُحلِّلَ الرقمي من مسار الخط: {sorted(leaked)} "
        f"— علم axis_completion سقط في _axis_candidates")
    # الشقيقُ المُقيَّم فعلاً لا يُحرَم من المجسّ.
    assert top in reached, reached

    # نصفا الشرط معاً على _axis_candidates مباشرةً: شقيقٌ استُرجع وقُيِّم
    # (حاضر في by_code بدرجات حقيقية) ليس صفَّ إكمال — لأن مسار الخط يستدعي
    # build_candidates بـrequested=[top] وحده، بخلاف مسار confirm.
    sib = sorted(completion)[-1]
    fake_eval = [{"hs6": sib, "score": 0.55, "lexical_score": 0.55}]
    emitted = silk_hs_pipeline._axis_candidates("حليب", top, fake_eval)
    flags = {r["hs6"]: r.get("axis_completion") for r in emitted}
    assert flags.get(top) is False, flags
    assert flags.get(sib) is False, (
        f"{sib} قُيِّم فعلاً (في by_code) لكنه وُسِم إكمالاً فحُرِم المجسّ: {flags}")
    for code in completion - {sib}:
        assert flags.get(code) is True, (
            f"{code} صفُّ إكمالٍ بلا علم — سيبلغ المُحلِّل الرقمي: {flags}")


def test_english_plural_is_the_same_whole_unit():
    """الجمعُ الإنجليزيُّ ومفردُه وحدةُ قياسٍ واحدة — «cheeses» تعتمد كما «cheese».

    الحادثة: بعد تضييق `_covered` إلى تطابق الوحدة الكاملة (البند ٨ — قرارٌ
    نافذ لا يُنقَض) صارت «cheeses» وحدةً غريبة عن «cheese»: المفردُ يعتمد
    040690 بثقة 1.0 والجمعُ يُرفَض والمرشّحون كلُّهم @0.0. الإصلاحُ المُقرَّر:
    طيُّ الجمع في `tokens()` وحدها — فتبقى الوحدةُ الكاملة وحدةَ القياس،
    و«cheeses»/«cheese» وحدةٌ واحدة كما «حلاوة»/«حلاوه».
    """
    import silk_hs_pipeline

    singular = silk_hs_pipeline.classify("cheese", allow_web=False)
    plural = silk_hs_pipeline.classify("cheeses", allow_web=False)
    assert singular["final_hs_code"] == "040690", singular
    assert singular["classification_status"] == "approved", singular
    assert plural["final_hs_code"] == "040690", (
        plural["final_hs_code"], plural["refusal_code"], plural["reason"])
    assert plural["classification_status"] == "approved", plural


def test_plural_fold_touches_neither_arabic_nor_es_nor_normalize():
    """الأقفال السلبية الثلاثة لطيّ الجمع — عربيةٌ بلا تجذيع، لا حذفَ «es»،
    و`normalize()` حرفيةٌ كما كانت.

    (١) العربية لا تُمَسّ (حارس ASCII — عائلة «رقي»/«ورقية»، الدرس 211):
    وحداتُ «مناديل ورقية» تخرج كما هي بلا حذف لاحقة، والوحدتان تبقيان
    مختلفتين. (٢) تُحذَف الـ«s» الأخيرة **فقط** لا «es» كاملة — حذفُ «es»
    يحوّل cheeses إلى chees فيكسر الحالةَ الرئيسة نفسَها؛ والوحدةُ الأقصر من
    ٤ أحرف لا تُطوى («gas» تبقى «gas»). (٣) `normalize()` لا تطوي الجمع —
    هي تضمن المطابقةَ الحرفية للعبارة الكاملة وتغذّي مفاتيحَ difflib الضبابية
    (silk_hs_resolver.py:316)، فالطيُّ فيها يحرّك الدرجاتِ في الريبو كله.
    """
    import silk_hs_norm as _n

    # (١) لا تجذيعَ عربياً — القائمة الحرفية كاملةً، بلا أي حذف لاحقة.
    assert _n.tokens("مناديل ورقية") == ["مناديل", "ورقيه"]
    assert _n.tokens("رقي") == ["رقي"]
    assert _n.tokens("ورقية") == ["ورقيه"]
    assert _n.same_token("رقي", "ورقية") is False

    # (٢) «s» الأخيرة فقط — لا «es»، ولا طيَّ تحت ٤ أحرف.
    assert _n.tokens("cheeses") == ["cheese"], _n.tokens("cheeses")
    assert _n.tokens("dates") == ["date"], _n.tokens("dates")
    assert _n.tokens("gas") == ["gas"], _n.tokens("gas")

    # (٣) normalize لا تطوي الجمع — الحرفُ الأخير باقٍ بايتاً ببايت.
    assert _n.normalize("cheeses") == "cheeses"
    assert _n.normalize("cheeses").endswith("s")


def test_negation_needs_a_word_edge():
    """نفيُ العلامة يشترط حدَّ كلمة — «sun-dried» و«صغير» ليسا نفياً.

    الحادثة (كامنة — صفر حالات في CSV الحالي، لكنها فخّ حقيقي): نمط
    `_MARKER_NEGATION` كان بلا حدِّ كلمةٍ قبل التناوب، فأيُّ كلمةٍ تنتهي
    بـ«un»/«non»/«غير» قُبيل علامة الحالة تُقرأ نفياً: «s**un**-dried» تُسكِت
    «dried»، و«s**un** roasted» تُسكِت «roasted»، و«صـ**غير**» تُسكِت «مجفف»
    — فيُبلِغ `_process_state_conflict` تناقضاً كاذباً ⇒ hard ⇒ 0.0 ⇒
    الرمزُ الصحيح يسقط ويُحجَب عن الاختيار البشري. الإصلاح: أداةُ النفي
    نفسُها تبدأ عند بداية النصّ أو بعد فاصلٍ — و«unroasted» يبقى نفياً
    (سابقتُها «un» مسبوقةٌ بفراغ بداية الكلمة).
    """
    import silk_hs_confirm as HC
    from silk_hs_confirm import _marker_present, _norm

    # (١) الإيجابياتُ الكاذبة الثلاث المعاد إنتاجها — العلامةُ حاضرة، لا منفية.
    #     (`normalize` لا تحذف الترقيم — الشرطةُ والفاصلة تصلان النمطَ كما هما،
    #      فالصيغُ المُنمَّطة هنا تُصيب العلّةَ نفسَها التي أصابتها المراجعة.)
    assert _marker_present("dried", _norm("tomatoes, sun-dried")) is True
    assert _marker_present("roasted", _norm("nuts, sun roasted")) is True
    assert _marker_present("مجفف", _norm("تمور صغير مجفف")) is True

    # (٢) النفيُ الحقيقيّ يبقى نفياً — قفلُ 090111 «not roasted» وأخواته،
    #     ومعه سابقةٌ ملتصقة («unroasted») حيث «un» مسبوقةٌ بفراغ الكلمة.
    assert _marker_present("roasted", _norm("coffee; not roasted")) is False
    assert _marker_present("مجفف", _norm("تمور غير مجفف")) is False
    assert _marker_present("roasted", _norm("coffee unroasted")) is False

    # (٣) القفلُ النهائيّ عبر حارس حالة التصنيع والمسار العامّ (نمطُ أقفال
    #     `test_hs_gate_verdict_and_error_transparency.py`): لا تناقضَ كاذباً.
    assert HC._process_state_conflict(
        ["مجفف", "طماطم"], "Tomatoes, fresh; sun-dried") is None
    r = HC.confirm_against_description(
        "طماطم مجففة", "999999", "Tomatoes, fresh; sun-dried")
    assert not r.get("negation_conflict"), r["reason"]


def test_refusal_payload_does_not_claim_passing_confidence(monkeypatch):
    """الرفض يعلن سببه ودرجةَ مرشّحه — لا «ثقة فوق العتبة» كسبب رفض.

    الحادثة (مُعاد إنتاجها): `classify('olive oil')` يتعادل فيها 150910
    و150990 @1.0 فيُرفَض الحسم (تعادل، البند ١١) — لكن فروع الرفض كانت
    تحمل درجةَ القمة في حقل `confidence` وحده، فيبني `_classify_product_hs`
    حجبَ 422 يقرأ «hs_confidence: 1.0, min_confidence: 0.80» — قارئُ السجلّ
    يرى ثقةً **فوق** العتبة مدوَّنةً كأنها سببُ رفضٍ بالثقة، بينما السبب
    الحقيقي تعادلٌ/محورٌ/تعارض. الإصلاح: الدرجة تُعلَن باسمها الصريح
    (`top_candidate_score`) والزوج الموحي يُفَكّ — والثقة تبقى رقماً دائماً
    (البند ٤؛ حارسا `test_hs_golden_set.py:84` و`test_zz_phase2_final_gate.py`
    لا يُمسّان).
    """
    from unittest import mock

    import silk_hs_pipeline as P

    # ── (أ) العقد نفسه: الرفض يحمل درجة مرشّحه حقلاً صريحاً منفصلاً ──
    out = P.classify("olive oil", allow_web=False)
    assert out["final_hs_code"] is None
    assert out["refusal_code"] == P.REFUSAL_UNRESOLVED
    assert "بندان متقاربان" in out["reason"], out["reason"]  # السبب الحقيقي
    assert isinstance(out["confidence"], float)  # الثقة رقم — الحارس القائم
    assert "top_candidate_score" in out, (
        "الرفض لا يعلن درجة مرشّحه الأعلى باسمها — تتنكّر «ثقةً» فقط")
    assert isinstance(out["top_candidate_score"], float)
    assert out["top_candidate_score"] == 1.0, out["top_candidate_score"]

    # ── (ب) حمولة 422 من /analyze + سياق سجلّ العمليات ──
    monkeypatch.delenv("SILK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import silk_ops_log
    logged = []
    monkeypatch.setattr(
        silk_ops_log, "record_error",
        lambda kind, reason, context=None, path=None:
            logged.append((kind, reason, dict(context or {}))))

    import api
    from fastapi.testclient import TestClient
    with mock.patch("requests.get", side_effect=OSError("offline")), \
         mock.patch("requests.post", side_effect=OSError("offline")):
        resp = TestClient(api.create_app()).post(
            "/analyze", json={"product": "olive oil"})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "hs_requires_confirmation"
    # السبب الحقيقي معلَن في الرسالة — لا رفضٌ يُعزى للثقة.
    assert "بندان متقاربان" in detail["message"], detail["message"]
    # الثقة تبقى رقماً في الحمولة — لكن بلا زوجٍ يوحي بأنها السبب.
    assert isinstance(detail["hs_confidence"], float)
    assert "min_confidence" not in detail, (
        "زوج hs_confidence/min_confidence يعرض ثقةً فوق العتبة كأنها سبب "
        "الرفض — السبب الحقيقي تعادل/محور/تعارض")
    # درجة المرشّح الأعلى حاضرة باسمها، منفصلةً عن الثقة.
    assert isinstance(detail.get("top_candidate_score"), float), detail.keys()
    assert detail["top_candidate_score"] == 1.0

    # سياق سجلّ العمليات يحمل الدرجة باسمها والرسالة بسببها الحقيقي.
    kind, reason, ctx = next(
        (k, r, c) for k, r, c in logged if k == "hs_requires_confirmation")
    assert "بندان متقاربان" in reason
    assert ctx.get("top_candidate_score") == 1.0, ctx


# ══════════ متابعة المهمة ٥: قناتا المحور — الإكمالُ يُعلِم ولا يُحسَم به ══════════
#
# الحادثة (تشريح 2026-08-31): قفلُ التوصيل
# `test_the_label_settles_the_axis_before_any_dialog` انكسر بعد تمرير علم
# `axis_completion` عبر مسار الخط: الاسترجاع لـ«حليب» يعيد مرشّحَين فقط من
# ترويسة المحور، وحارسُ `resolve_or_probe` يُسقط أشقّاء الإكمال **قبل**
# المُحلِّل، فيبقى نطاقٌ واحد و`discriminator` يشترط اثنين — فمات القياسُ
# قبل أن يقرأ بطاقةَ العبوة أصلاً. عمارةُ المُشرِف: للنطاقات قناتان —
# نطاقاتُ الإكمال **تُعلِم المحور** (حدودُ المُميِّز)، ولا تدخل قناةَ
# **المرشّحين** التي وحدها تصلح نتيجةً. لا إضعافَ لأيّ حارسٍ قائم.


def _milk_axis_scene():
    """المشهد الحقيقي كاملاً: ما استُرجع، وما أُكمل عرضاً، ونطاقات المحور.

    كلُّ القيم تُحسَب من المرجع الرسميّ في مكانها — لا رمزَ ولا رقمَ مكتوباً
    صلباً، فلو تبدّل الدليل تبدّل المشهدُ معه.
    """
    import silk_hs_attributes as _attrs
    import silk_hs_dialog
    from silk_hs_resolver import retrieve

    hits = retrieve("حليب", top_n=5)
    evaluated = {h["hs_code"] for h in hits}
    top = hits[0]["hs_code"]
    rows = silk_hs_dialog.build_candidates("حليب", [top])
    completion = {r["hs6"] for r in rows
                  if r["axis_completion"] and r["hs6"] not in evaluated}
    disc = _attrs.discriminator(rows)     # المحورُ كاملاً — منه تُحسَب القيم
    assert disc and completion, "المشهد فارغ — لا محورَ أو لا صفوفَ إكمال"
    return evaluated, top, completion, disc


def test_completion_bands_inform_the_axis_but_never_resolve(monkeypatch):
    """قياسُ البطاقة يعود يعمل: نطاقاتُ الإكمال تبني المحور، والنتيجةُ من
    المُقيَّمين وحدهم — والحارسان القائمان بلا مساس.

    (أ) «حليب» + بطاقة بقيمةٍ في نطاق مرشّحٍ **مُقيَّم** ⇒ اعتمادٌ بلا حوار.
    (ج) بنيوياً: قناةُ المرشّحين الواصلة `resolve_by_attribute` بلا أيّ صفّ
        إكمال — يُقاس بغلافٍ مسجِّل يفوّض للدالة الحقيقية (سلوكٌ حقيقيّ).
    """
    monkeypatch.setenv("SILK_HS_ATTRIBUTE_RESOLVE", "1")
    import silk_hs_attributes as _attrs
    import silk_hs_pipeline as P

    evaluated, top, completion, disc = _milk_axis_scene()
    # قيمةٌ في وسط نطاقٍ مغلقِ الطرفين — نفسُ وصفة قفل التوصيل المكسور.
    target = next(b for b in disc["bands"]
                  if b["lo"] is not None and b["hi"] is not None)
    assert target["hs6"] in evaluated, (
        f"وصفةُ المشهد تغيّرت: النطاق المغلق {target['hs6']} لم يُسترجَع "
        f"أصلاً — الاختبار يفقد معناه ({sorted(evaluated)})")
    value = (target["lo"] + target["hi"]) / 2.0
    payload = [{"name": disc["label_ar"], "value": value,
                "unit": disc["unit"]}]

    reached: list[list] = []
    real = _attrs.resolve_by_attribute

    def _recorder(product, candidates, **kw):
        reached.append([c.get("hs6") for c in candidates])
        return real(product, candidates, **kw)   # تسجيلٌ ثم تفويض

    monkeypatch.setattr(_attrs, "resolve_by_attribute", _recorder)
    out = P.classify("حليب", None, label_attributes=payload, allow_web=False)

    # (ج) الحارسُ القائم كما هو: لا صفَّ إكمالٍ في قناة المرشّحين.
    assert reached, "المجسُّ لم يُستدعَ — لم يبلغ الخطُّ نقطةَ القياس"
    reached_codes = {c for call in reached for c in call}
    assert not (completion & reached_codes), (
        f"صفوفُ الإكمال بلغت قناةَ المرشّحين: "
        f"{sorted(completion & reached_codes)}")
    assert top in reached_codes, reached

    # (أ) القياسُ يحسم من جديد — البطاقةُ تُقرأ والبندُ المُقيَّم يُعتمَد.
    assert out["classification_status"] == P.APPROVED, out["reason"]
    assert out["final_hs_code"] == target["hs6"], out["final_hs_code"]
    assert out["final_hs_code"] in evaluated, "توسعةُ تغطيةٍ من الباب الخلفي"
    assert out["refusal_code"] is None
    assert any(p["step"] == "attribute_probe" for p in out["provenance"]), (
        out["provenance"])


def test_a_value_inside_a_completion_band_never_resolves_to_it(monkeypatch):
    """(ب) قيمةٌ تقع في نطاق صفِّ إكمالٍ **حصراً** ⇒ لا اعتمادَ لأيّ رمز:
    الحوارُ يُعرَض بسببٍ معلَنٍ يسمّي النطاق، ورمزُ الإكمال غائبٌ عن النتيجة
    — النطاقُ يُعلِم الحدود ولا يصلح نتيجةً أبداً."""
    monkeypatch.setenv("SILK_HS_ATTRIBUTE_RESOLVE", "1")
    import silk_hs_attributes as _attrs
    import silk_hs_pipeline as P

    evaluated, _top, completion, disc = _milk_axis_scene()
    comp_band = next(b for b in disc["bands"] if b["hs6"] in completion)
    # القيمةُ من النطاقات الحقيقية لا من رقمٍ صلب — داخل نطاق الإكمال وحده.
    if comp_band["lo"] is not None and comp_band["hi"] is not None:
        value = (comp_band["lo"] + comp_band["hi"]) / 2.0
    elif comp_band["hi"] is not None:
        value = comp_band["hi"] / 2.0
    else:
        value = comp_band["lo"] * 2.0
    # تحقُّقُ سلامة: على المحور الكامل هذه القيمة تصيب نطاقَ الإكمال وحده.
    assert _attrs.select_by_value(disc, value, disc["unit"]) == comp_band["hs6"]

    payload = [{"name": disc["label_ar"], "value": value,
                "unit": disc["unit"]}]
    out = P.classify("حليب", None, label_attributes=payload, allow_web=False)

    assert out["classification_status"] == P.REQUIRES_CONFIRMATION, out
    assert out["refusal_code"] == P.REFUSAL_AXIS, out["refusal_code"]
    assert out["final_hs_code"] is None, (
        f"رمزٌ اعتُمد على نطاق إكمال: {out['final_hs_code']}")
    probe = out.get("attribute_probe") or {}
    searched = probe.get("searched") or []
    assert any(comp_band["hs6"] in ln and "إكمال" in ln for ln in searched), (
        f"سببُ الامتناع لا يسمّي نطاقَ الإكمال الذي أصابته القيمة: {searched}")


# ═══════════ Task 9 — سجلّ أصل الترتيب يذكر الصيغة الفعلية ═══════════════════

def test_ranking_provenance_states_the_formula_in_the_code():
    """خطوةُ الترتيب في السجلّ تصف الحسابَ الحقيقيّ — لا نصّاً منفصلاً عنه.

    الحادثة: `prov.append({"step": "ranking", ...})` كان يكتب
    `"lexical*0.6 + semantic*0.4, contradiction ⇒ 0"` بينما `_evaluate`
    تحسب فعلياً `lexical * (1 - _SEMANTIC_DISCOUNT * (1 - semantic))`
    وتُسقط غيرَ المؤكَّد إلى صفر أيضاً — سجلّ الأصل، وهو المكانُ الوحيد الذي
    ينفّذ قاعدةَ الأصل لكل رقم على خط HS، كان يكذب من لحظة وصوله. القفلُ هنا
    عدديّ لا نصّي: يستخرج معامل الخصم **من نصّ السجلّ نفسه** (لا من الثابت
    مباشرةً) ويعيد حساب درجة مرشّحٍ حقيقيّ بصيغة السجلّ، فيطابق `score` —
    فلو انفصل نصّ السجلّ عن حساب `_evaluate` (حتى لو ظلّ الثابت صحيحاً في
    الكود) يفشل القفل.
    """
    import re

    import silk_hs_pipeline as P

    def _qualifies(c: dict) -> bool:
        return (c["confirmed"] is True and not c["contradictions"]
                and c["semantic_overlap"] is not None)

    out = P.classify("cheese", allow_web=False)
    cands = out["candidate_codes"]
    assert cands, "لا مرشّحين — الاختبار فارغ"
    top = cands[0] if _qualifies(cands[0]) else next(
        (c for c in cands if _qualifies(c)), None)
    assert top is not None, (
        "لا مرشّحَ مؤكَّداً بلا تناقضات في نتيجة classify('cheese') — "
        "غيّر المنتجَ المُختبَر لهذا القفل")

    ranking = next(p for p in out["provenance"] if p["step"] == "ranking")
    source = ranking["source"]

    # النصُّ القديم المهجور غائبٌ تماماً — لا بقايا منه في السجلّ الجديد.
    assert "lexical*0.6" not in source, (
        f"سجلّ الترتيب ما زال يذكر الصيغةَ القديمة المهجورة: {source!r}")

    # بنيةُ الصيغة الفعلية حاضرةٌ نصّاً — لا وصفٌ عام يتخطّى المعامل.
    m = re.search(r"lexical\*\(1-([0-9.]+)\*\(1-semantic\)\)", source)
    assert m is not None, (
        f"سجلّ الترتيب لا يذكر بنيةَ الصيغة التي يحسبها _evaluate فعلياً: "
        f"{source!r}")
    discount_in_text = float(m.group(1))
    assert discount_in_text == P._SEMANTIC_DISCOUNT, (
        f"معاملُ الخصم المكتوب في السجلّ ({discount_in_text}) لا يطابق "
        f"_SEMANTIC_DISCOUNT الحقيقي ({P._SEMANTIC_DISCOUNT}) — السجلّ "
        "انفصل عن الكود")

    # إعادةُ حساب درجة المرشّح بالصيغة **كما استُخرجت من نصّ السجلّ** —
    # لا بنسخةٍ يدوية موازية مكتوبة في الاختبار.
    expected = round(
        top["lexical_score"]
        * (1.0 - discount_in_text * (1.0 - top["semantic_overlap"])), 4)
    assert expected == top["score"], (
        f"الصيغةُ المُستخرَجة من سجلّ الأصل تعطي {expected} بينما درجةُ "
        f"المرشّح الفعلية {top['score']} — السجلّ لا يصف الحساب الحقيقي")


# ═══════════ Task 10 — مقياسٌ واحد للمرشّح الكتالوجي والمرشّحين ═══════════════

def test_score_and_retrieve_use_one_scale(tmp_path):
    """`_score` والمسارُ الفهرسي (`retrieve`) يقيسان الصفَّ نفسَه بالرقم نفسِه.

    الحادثة (مراجعة #254 على `silk_hs_resolver.py`): `_score` كان يقيس
    الرتبةَ الضبابية على **كلّ** مفاتيح الصفّ، بينما `_index` يبني
    `keys[:2] + description_en` و`retrieve` لا يقيس إلا عليها. وبما أنّ
    `_catalog_lexical` (خطّ التصنيف) يستعمل `_score`، فرمزُ كتالوجٍ لم
    يرشّحه الاسترجاعُ يُقاس على مقياسٍ أوسع من كلّ منافسيه في `cands.sort`
    واختبارِ `min_separation` — ترتيبٌ يخلط مقياسين غير قابلين للمقارنة.

    الصفُّ الصناعي: مفاتيحُ كثيرة لا يقارب الاستعلامَ ضبابياً إلا **رابعُها**
    (خارج `keys[:2]`) — فيراه `_score` القديم (0.69 مسقوفاً) ولا يراه
    المسارُ الفهرسي (≈0.31 من تشابه حروفٍ عرَضي).
    """
    import silk_hs_resolver as R

    p = tmp_path / "ref.csv"
    p.write_text(
        _HS_CSV_HEADER
        + ('010101,01,x,0101,x,"Widgets; industrial, other",'
           '"apple;orange;banana;zanjabeel"\n'),
        encoding="utf-8")
    P = str(p)
    q = "zanjabil"  # لا وحدةَ كاملة مشتركة مع أيّ مفتاح — الضبابية وحدها تقيس
    try:
        row = R.load_hs_codes(P)[0]
        direct = R._score(q, row)
        hit = next((h for h in R.retrieve(q, path=P)
                    if h["hs_code"] == "010101"), None)
        indexed = hit["score"] if hit else 0.0
        assert direct == indexed, (
            f"مقياسان لصفٍّ واحد على استعلامٍ واحد: _score={direct} بينما "
            f"المسارُ الفهرسي (retrieve) يعطي {indexed} — رمزُ الكتالوج "
            "يُقاس على مفاتيحَ أوسع من منافسيه في الترتيب نفسه")
    finally:
        R.load_hs_codes.cache_clear()


# ═══════════ Task 11 — سقفٌ لـ`_INDEX_CACHE` ══════════════════════════════════

def test_index_cache_is_bounded(tmp_path):
    """سقفُ أربعة مسارات (كسقف الجارة `_ROWS_CACHE`) — حذفُ الأقدم إدراجياً.

    الحادثة: `_INDEX_CACHE` قاموسُ وحدةٍ بلا سقف — كلُّ مسارٍ CSV جديد
    (مسارات `tmp_path` في السويت وأداة المجموعة الذهبية) يضيف مدخلاً يبقى
    حتى نهاية العملية: صفوفٌ + فهرسٌ مقلوبٌ كامل (٥٬٦١٣ صفاً للمرجع الحقيقي).
    فحصُ الهويّة (`cached[0] is rows`) يستبدل مدخلَ **المسار نفسه** فقط —
    مسارٌ جديد يُضاف دائماً فلا يتقلّص شيء.
    """
    import silk_hs_resolver as R

    paths: list[str] = []
    built: dict[str, tuple] = {}
    try:
        for i in range(6):
            p = tmp_path / f"idx{i}.csv"
            code = f"0102{i:02d}"
            p.write_text(_HS_CSV_HEADER + _hs_row(code, f"Row {i}"),
                         encoding="utf-8")
            P = str(p)
            paths.append(P)
            R.retrieve(code, path=P)          # يبني الفهرس عبر _index
            built[P] = R._INDEX_CACHE[P][1]

        cache = R._INDEX_CACHE
        assert len(cache) <= 4, (
            f"فهرسٌ مقلوبٌ لكل مسار CSV بلا سقف — {len(cache)} مدخلاً")
        assert paths[0] not in cache and paths[1] not in cache, (
            "التجاوز لا يحذف الأقدم أولاً")
        # الأحدث ما زال مخدوماً من الذاكرة — الفهرسُ نفسُه لا مُعاد بناؤه.
        R.retrieve(f"0102{5:02d}", path=paths[-1])
        assert R._INDEX_CACHE[paths[-1]][1] is built[paths[-1]], (
            "المسارُ الأحدث أُعيد فهرسُه رغم بقائه في الذاكرة — هويّةٌ مفقودة")
    finally:
        R.load_hs_codes.cache_clear()


# ═══════════ Task 12 — عطل الخادم ليس «اختر البند» ════════════════════════════

def test_server_fault_never_becomes_a_pick_dialog(monkeypatch):
    """`hs_classification_error` عطلُ خادمٍ (`empty_product`/`retrieval_failed`)
    — ليس رفضَ بوّابةِ بندٍ يكون «اختر البند» جواباً له.

    الحادثة (silk_platform/engine_bridge.py:228): `_HS_GATE_CODES` ضمّ
    `hs_classification_error` رغم أن توثيق المجموعة نفسها يقصرها على ما
    يكون الاختيارُ جواباً صالحاً له. `REFUSAL_ERROR` (نفسُ الرمز) يصدر عن
    `empty_product`/`retrieval_failed: <ExcType>` في `silk_hs_pipeline.classify`
    — اسمُ منتجٍ فارغ أو تعذّرُ قراءة data/hscodes_full.csv، لا التباسَ بندٍ.
    ومع ذلك كان `_thread_body` يستدعي `_catalog_candidates` لهذا الرمز، وإن
    عادت مرشّحين يستبدل ذيلَ الرسالة `NO_CANDIDATES_TAIL` بـ`PICK_TAIL`:
    عطلُ خادمٍ يُعرَض كسؤال اختيارٍ لا مخرج منه فعلياً — طريقٌ مسدود بزيّ
    حوار. القفلُ سلوكيّ: إطلاقٌ حقيقي عبر التشغيلة الحقيقية للجسر (لا نداءُ
    دالةٍ داخلية مباشر)، ثم قراءةُ صفّ الدراسة.
    """
    import json

    from silk_hs_confirm import NO_CANDIDATES_TAIL, PICK_TAIL

    H.setup_env(monkeypatch)
    f = H.make_factory("gold", "hs-serverfault@f.local")
    cl = H.client()
    tok = H.login(cl, f["email"], f["password"])
    r = cl.post("/platform/studies", json={"product": "حلاوة طحينية سادة"},
                headers=H.hdr(tok))
    assert r.status_code == 200, r.text
    sid = int(r.json()["id"])

    import silk_platform.engine_bridge as eb

    fault_message = (
        "تعذّر قراءةُ مرجع الرموز الجمركية — راجع سلامة "
        "data/hscodes_full.csv ثم أعد المحاولة. " + NO_CANDIDATES_TAIL)

    def _boom(*_a, **_k):
        raise eb.DeepRunRefused(fault_message, code="hs_classification_error")

    monkeypatch.setattr(eb, "_run_engine", _boom)

    # جاسوسٌ مُسجِّل: لو نودي فعلياً سيعيد مرشّحين حقيقيّين (وصفُ الكتالوج
    # كان سيصنّف إلى بندٍ ما) — كي يفشل القفلُ فشلاً حقيقياً قبل الإصلاح لا
    # لأن المرشّحين فارغون صدفةً.
    calls = []

    def _spy_catalog_candidates(study_id, account_id, product):
        calls.append((study_id, account_id, product))
        return [{"hs6": "170490", "band_ar": "حلويات سكرية أخرى"}]

    monkeypatch.setattr(eb, "_catalog_candidates", _spy_catalog_candidates)

    r = cl.post(f"/platform/studies/{sid}/launch", headers=H.hdr(tok))
    assert r.status_code == 200, r.text
    assert eb.wait_idle(15)

    from silk_platform import db as pdb
    conn = pdb.connect()
    try:
        row = conn.execute(
            "SELECT state, run_error, hs_candidates FROM studies "
            "WHERE id = ?", (sid,)).fetchone()
    finally:
        conn.close()

    assert row["state"] == "draft"
    assert calls == [], (
        "عطلُ خادمٍ (hs_classification_error) استدعى _catalog_candidates — "
        "خارج بوّابات البند فلا مرشّحين له إطلاقاً")
    run_error = row["run_error"] or ""
    assert NO_CANDIDATES_TAIL in run_error, (
        f"ذيلُ عطل الخادم اختفى من الرسالة المخزَّنة: {run_error!r}")
    assert PICK_TAIL not in run_error, (
        f"عطلُ خادمٍ تحوّل إلى سؤال اختيارٍ («{PICK_TAIL}») في: {run_error!r}")
    assert row["hs_candidates"] in (None, "", "[]", "null"), (
        f"عطلُ خادمٍ أرفق قائمةَ مرشّحين ({row['hs_candidates']!r}) — "
        "شاشةُ المصنع ستعرض زرَّ «اختر البند» بلا أيّ بندٍ ملتبس فعلاً")
    if row["hs_candidates"] not in (None, ""):
        assert json.loads(row["hs_candidates"]) in ([], None)

# ══════════ المهمة ١٣: رمز صريح + منتج فارغ — فحصُ المرجع لا empty_product ══════════
#
# الحادثة (مُعاد إنتاجها على HEAD): `AnalyzeRequest.product` نصٌّ إلزاميّ،
# و`POST /analyze {"product": "", "hs_code": "170490"}` يصل `classify("", ...)`
# فيسقط في فرع `if not normalized` (silk_hs_pipeline.py) ويعود
# `error="empty_product"` ⇒ 422 — بينما قبل الموجة كان التحليل يمضي على الرمز
# المكتوب. والسببُ المعلَن نفسُه كاذب: الطلبُ ليس فارغاً — رمزٌ صريحٌ فيه.
#
# القرار (افتراضٌ معلَن أقرّه المالك، خطة 2026-08-31): رمزٌ صريحٌ باسمٍ فارغ
# يُفحَص حتمياً على المرجع الرسمي (`silk_hs_confirm._find_row`): موجودٌ ⇒
# يمضي التحليل عليه بوسم `explicit_unverified` وأصلٍ يعلن أن الاتفاق **غير
# مقيس** (لا اسمَ يُقاس عليه)؛ غائبٌ ⇒ 422 بسببه الحقيقي («ليس في المرجع»)؛
# فارغٌ بلا رمزٍ أصلاً ⇒ `empty_product` الصادق كما كان.


def test_explicit_code_with_empty_product_is_served(monkeypatch):
    """رمزٌ صريح + اسمٌ فارغ: مرجعٌ يحويه ⇒ يُخدَم؛ لا يحويه ⇒ سببٌ صادق.

    القفل سلوكيّ عبر `POST /analyze` الحقيقي (نفس عتاد
    `test_refusal_payload_does_not_claim_passing_confidence`)، مضافاً إليه
    فحصُ عقد المسار الجديد مباشرةً — الطريقةُ والثقةُ والأصل.
    """
    import json as _json
    from unittest import mock

    monkeypatch.delenv("SILK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import silk_ops_log
    logged = []
    monkeypatch.setattr(
        silk_ops_log, "record_error",
        lambda kind, reason, context=None, path=None:
            logged.append((kind, reason, dict(context or {}))))

    import api
    import silk_hs_pipeline as P

    # ── (أ) عقدُ المسار الجديد مباشرةً: موجودٌ في المرجع ⇒ explicit_unverified ──
    contract = api._explicit_code_only_contract("170490")
    assert contract["final_hs_code"] == "170490"
    assert contract["classification_status"] == P.APPROVED
    assert contract["classification_method"] == "explicit_unverified"
    assert contract["error"] is None, contract["error"]        # ليس empty_product
    # الثقة رقمٌ دائماً (البند ٤) — ولا تُختلَق: لا اسمَ قيسَ عليه شيء.
    assert isinstance(contract["confidence"], float)
    # الأصلُ يعلن أن الاتفاق غير مقيس — وسمُ القرار لا إخفاؤه.
    trail = _json.dumps(contract["provenance"], ensure_ascii=False) \
        + contract["reason"]
    assert "غير مقيس" in trail or "لا اسمَ يُقاس عليه" in trail, trail

    # ── (ب) السلوك عبر HTTP: يمضي على الرمز الصريح — لا empty_product ──
    from fastapi.testclient import TestClient
    cl = TestClient(api.create_app())
    offline = mock.patch("requests.sessions.Session.request",
                         side_effect=OSError("offline"))
    with offline:
        ok = cl.post("/analyze", json={"product": "", "hs_code": "170490",
                                       "markets": ["NLD"], "persist": False})
    assert ok.status_code == 200, ok.text
    assert ok.json().get("hs_code") == "170490"

    # ── (ج) رمزٌ غائب عن المرجع ⇒ 422 بسببه الحقيقي لا empty_product ──
    #   («999999» نفسُه موجود في المرجع — Commodities not specified — فيُخدَم؛
    #    الغائبُ فعلاً مثل 123456 هو ما يُرفَض.)
    with offline:
        absent = cl.post("/analyze", json={"product": "", "hs_code": "123456",
                                           "markets": ["NLD"]})
    assert absent.status_code == 422, absent.text
    detail = absent.json()["detail"]
    assert detail["error"] == P.REFUSAL_CATALOG_REJECTED, detail["error"]
    assert "المرجع" in detail["message"], detail["message"]
    # بصمةُ رفض `empty_product` («لا يمكن التصنيف بلا اسم») لا تظهر —
    # ذكرُ فراغِ الاسم سياقاً مشروع، أما عزوُ الرفض إليه فسببٌ كاذب.
    assert "لا يمكن التصنيف بلا اسم" not in detail["message"], (
        "رفضُ رمزٍ غائبٍ عن المرجع ما زال يُعزى لاسمٍ فارغ — سببٌ كاذب")
    assert detail["error"] != "hs_classification_error"

    # ── (د) اسمٌ فارغ **بلا** رمزٍ إطلاقاً ⇒ empty_product الصادق كما كان ──
    with offline:
        bare = cl.post("/analyze", json={"product": "", "markets": ["NLD"]})
    assert bare.status_code == 422
    assert "فارغ" in bare.json()["detail"]["message"]
    assert P.classify("")["error"] == "empty_product"   # عقدُ الخطّ لم يُمسّ


def test_classification_machinery_runs_once_per_request(monkeypatch):
    """الآلة التصنيفية مرّةً واحدة لكل طلب — لا إعادة تشغيلٍ كاملة في preflight.

    الحادثة (قياسٌ مباشر): كل مسار إنفاقٍ كان يشغّل الآلة مرّتين —
    `_classify_product_hs` يحسم العقد كاملاً (استرجاع + تأكيد لكل مرشّح +
    مجسّ المحور + fallback النموذج)، ثم `preflight_resolve` يعيد تشغيل
    `preflight_block`/`resolve_or_probe`/`classify_general` على المنتج نفسه.
    والأدهى: التشغيلة الثانية كانت **تنقض** الأولى — بطاقةٌ حسمت المحور في
    الخطّ (approved 040120) فيعيد preflight بناء المرشّحين بـ
    `deterministic_candidates` (تلوّث عابر للترويسة: 040221 بين أشقّاء 0401)
    فيفشل المُميِّز ويرُدّ 422 لطلبٍ حُسم للتوّ.

    عدّادان بسيناريو مسمّى لكلٍّ منهما (بدون سيناريوهه يكون العدّاد فارغاً):
    (أ) عدّاد `silk_hs_resolver.retrieve` على منتج محورٍ تحسمه البطاقة —
        يتضاعف عبر `deterministic_candidates→resolve_all` في إعادة التشغيل؛
    (ب) عدّاد `silk_hs_classifier.classify_general` على إخفاقٍ لفظيّ يوقظ
        fallback النموذج (المسارات المعتمَدة معجمياً لا تناديه أصلاً) —
        النداء الثاني من فرع `is_flagged` في preflight_block.
    """
    from unittest import mock

    monkeypatch.delenv("SILK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("SILK_HS_ATTRIBUTE_RESOLVE", "1")

    import api
    import silk_engine
    import silk_hs_attributes as A
    import silk_hs_pipeline as P
    import silk_hs_resolver as R
    from fastapi.testclient import TestClient
    from silk_hs_resolver import load_hs_reference

    offline = mock.patch("requests.sessions.Session.request",
                         side_effect=OSError("offline"))
    # المحرّك خارج السؤال: العدّ يخصّ طبقة التصنيف/البوّابة وحدها، والمحرّك
    # الحقيقي يملك مُحلِّله الخاص (يعمل فقط حين لا يصله رمز) فيلوّث العدّ.
    monkeypatch.setattr(silk_engine, "analyze", lambda product, **k: {
        "product": product, "hs_code": k.get("hs_code"),
        "year": k.get("year") or 2023, "markets": []})

    # ── (أ) منتجُ محورٍ تحسمه البطاقة — نفس عتاد test_hs_attribute_gate_wiring ──
    codes = [c for c in sorted(load_hs_reference())
             if c.startswith("0401") and A.band_of(c)]
    disc = A.discriminator([{"hs6": c} for c in codes])
    band = next(b for b in disc["bands"]
                if b["lo"] is not None and b["hi"] is not None)
    attrs_payload = [{"name": disc["label_ar"],
                      "value": (band["lo"] + band["hi"]) / 2.0,
                      "unit": disc["unit"]}]

    calls = {"n": 0}
    real_retrieve = R.retrieve

    def counting_retrieve(*a, **k):
        calls["n"] += 1
        return real_retrieve(*a, **k)

    monkeypatch.setattr(R, "retrieve", counting_retrieve)

    # عدُّ الخطّ وحده أولاً — التوقّعُ يُقاس لا يُكتب صلباً.
    with offline:
        settled = P.classify("حليب", None, label_attributes=attrs_payload)
    assert settled["classification_status"] == P.APPROVED, settled["reason"]
    assert settled["final_hs_code"] == band["hs6"]
    pipeline_retrieve = calls["n"]
    assert pipeline_retrieve >= 1

    calls["n"] = 0
    with offline:
        resp_axis = TestClient(api.create_app()).post(
            "/analyze", json={"product": "حليب", "markets": ["NLD"],
                              "label_attributes": attrs_payload,
                              "persist": False})
    axis_retrieve = calls["n"]

    # ── (ب) إخفاقٌ لفظيّ يوقظ fallback النموذج — النموذج نفسه مقلَّد ──
    import silk_hs_classifier as K
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("SILK_API_KEY", "s3cret")
    monkeypatch.setattr(K, "_claude_classify_general",
                        lambda product, ingredients, category, instruction="":
                        [{"hs6": "040900",
                          "description_ar": "زبزبوب النجوم منتج نحلي طبيعي",
                          "reason_ar": "زبزبوب النجوم يعبأ كعسل نحل طبيعي",
                          "confidence": 0.95}])
    monkeypatch.setattr(K, "_reserve_llm_call", lambda: True)
    monkeypatch.setattr(K, "_cached_general", lambda key: None)
    monkeypatch.setattr(K, "_store_general_cache", lambda key, cands: None)

    gen = {"n": 0}
    real_general = K.classify_general

    def counting_general(*a, **k):
        gen["n"] += 1
        return real_general(*a, **k)

    monkeypatch.setattr(K, "classify_general", counting_general)

    with offline:
        resp_llm = TestClient(api.create_app()).post(
            "/analyze", json={"product": "زبزبوب النجوم", "markets": ["NLD"],
                              "persist": False},
            headers={"X-API-Key": "s3cret"})
    llm_general = gen["n"]

    # العدّادان معاً — الأحمر يسجّل التضاعف في كليهما بأرقامه.
    assert (axis_retrieve, llm_general) == (pipeline_retrieve, 1), (
        f"الآلة أعيد تشغيلها بعد العقد: retrieve={axis_retrieve} "
        f"(عدّ الخطّ وحده {pipeline_retrieve})، "
        f"classify_general={llm_general} (المتوقّع 1)")

    # والعقدُ المحسوم يقف — التشغيلة الثانية كانت تنقضه بـ422:
    # (أ) بطاقةٌ حسمت المحور => الرمز المقيس يمضي موسوماً بمصدره.
    assert resp_axis.status_code == 200, resp_axis.text
    body = resp_axis.json()
    assert body.get("hs_code") == band["hs6"]
    prov = body.get("hs_provenance") or {}
    assert prov.get("hs6") == band["hs6"]
    assert prov.get("resolved_from") == "image"
    # (ب) عقدُ llm_grounded المعتمَد لا يُقلَب hs_confirmation_needed.
    assert resp_llm.status_code == 200, resp_llm.text
