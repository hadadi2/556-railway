"""رُتبة ٣ — متصفّح حقيقي (rung 3 — the real-browser lane).

> **القاعدة الجديدة (تأكيد المالك آخِراً لا أوّلاً).** الرُتبة ٢ تُثبِت أن
> الخادم يخدم الـHTTP الصحيح؛ هذه الرُتبة تُثبِت أن **الواجهة الفعلية تعمل**:
> chromium (headless) ينقر الأزرار الحقيقية ضدّ خادم رُتبة ٢. التدفّق: افتح
> اللوحة ← انقر عنصر الشريط الجانبي ← يُعرَض التقرير ← تصدير Word (‏.docx غير
> فارغ) ← تصدير Markdown (محتوى حقيقي لا القالب الفارغ) ← صندوق التقدّم. هذا
> بالضبط كان سيلتقط **خطأَي التصدير** و**الشريط الجانبي الميت** قبل المالك.

يُقلِع الخادم الحقيقي (`tools/live_shape_server.LiveShapeServer`) ثم يشغّل
تدفّق Playwright (`tests/e2e/live_shape_flow.mjs`) عبر Node مع NODE_PATH يحلّ
حزمة playwright العمومية والمتصفّح من `/opt/pw-browsers`.

بيئة بلا Node/playwright: يُخطَّى بسبب صريح (أفضل جهد — نفس تساهل اختبارات
الواجهة عبر Node)، لكن في وظيفة `e2e-live-shape` كلاهما مثبّت فيعمل فعلياً.
يُتخطّى في `pytest tests/ -q` الافتراضية (SILK_RUN_E2E غير مضبوط).

Run locally:
    SILK_RUN_E2E=1 python3 -m pytest tests/test_rung3_playwright_e2e.py -q -s
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "tools"))

pytestmark = pytest.mark.e2e

_FLOW = os.path.join(_ROOT, "tests", "e2e", "live_shape_flow.cjs")
_PRERUN_FLOW = os.path.join(_ROOT, "tests", "e2e", "prerun_flow.cjs")
_READINESS_FLOW = os.path.join(_ROOT, "tests", "e2e", "readiness_flow.cjs")
_HS_CANDIDATES_FLOW = os.path.join(_ROOT, "tests", "e2e", "hs_candidates_flow.cjs")
_HS_TIER_FAMILY_FLOW = os.path.join(_ROOT, "tests", "e2e", "hs_tier_family_flow.cjs")
_HS_DIALOG_FLOW = os.path.join(_ROOT, "tests", "e2e",
                               "hs_dialog_official_flow.cjs")

# حالتا رُتبة ٣ لحوار المرشّحين — **فصلان مختلفان وبُعدا قياسٍ مختلفان** (شرط
# المُشرِف: لا على 0401 وحدها). المكتوب هنا صلباً هو **اسم المنتج والتوقّع**
# فقط؛ كلُّ ما يُؤكَّد في المتصفّح (الأشقّاء، حدود النطاق، مجموعة المرجع)
# يُشتَقّ لحظةَ التشغيل من `data/hs_reference.csv`.
_DIALOG_CASES = (
    {"product": "حليب طازج مبستر", "heading": "0401", "dimension": "fat",
     "anchor": "040110"},
    {"product": "شاي أخضر معبأ", "heading": "0902", "dimension": "weight",
     "anchor": "090210"},
)

# رموزٌ تُمنَع من نصّ الحوار: اسمُ المنتج المكتوب وعلامةٌ تجاريةٌ وبلدٌ — نثرُ
# الحوار وصفٌ رسميٌّ للبند، لا صدىً لِما كتبه التاجر (البند ٧٤).
_DIALOG_BANNED = ("نادك", "المراعي", "هولندا", "طازج", "معبأ")


def _dialog_cases_payload() -> tuple[str, str]:
    """يبني حمولةَ الحالات ومجموعةَ المرجع الرسميّ **من المرجع نفسه**."""
    import json

    import silk_hs_attributes as attrs
    import silk_hs_dialog as dialog
    import silk_hs_resolver as resolver

    cases = []
    for case in _DIALOG_CASES:
        anchor = case["anchor"]
        siblings = dialog.axis_siblings(anchor)
        assert len(siblings) >= 2, f"{anchor}: axis has no sibling to complete"
        edges: dict[str, list[str]] = {}
        for hs6 in siblings:
            band = attrs.band_of(hs6, resolver.official_description(hs6))
            assert band, f"{hs6}: no band parsed from the official description"
            unit = band.get("unit") or ""
            vals = [v for v in (band.get("lo"), band.get("hi")) if v is not None]
            # الحدُّ المتوقَّع مشتقٌّ من **المُحلِّل** (`band_of`) لا من المُصيِّر
            # المُختبَر (`range_ar`) — فالتأكيد ليس دائرياً.
            edges[hs6] = [
                f"{int(v) if float(v).is_integer() else v}{unit}" for v in vals]
        cases.append({
            "product": case["product"], "heading": case["heading"],
            "dimension": case["dimension"], "siblings": siblings,
            "edges": edges, "banned_tokens": list(_DIALOG_BANNED),
        })
    official = sorted(resolver.load_hs_reference())
    assert len(official) > 5000, f"reference looks truncated: {len(official)}"
    return json.dumps(cases, ensure_ascii=False), json.dumps(official)


def _node() -> str | None:
    return shutil.which("node")


# ── محرّكُ تحويل PDF: شرطُ بيئةٍ صريحٌ لا حُمرةٌ صامتة (PART 3) ───────────────
#
# التدفّقُ الكامل ينقر زرّ **PDF** (المُسلَّم النهائي، اللائحة ١٩) فيحتاج
# فلاتر Writer لقراءة .docx. صورةُ النشر (`Dockerfile`) ووظيفةُ
# `e2e-live-shape` تُثبّتان `libreoffice-writer`؛ بيئةُ تطويرٍ بلا الحزمة
# تُفشِل الخطوةَ بمهلةِ تنزيلٍ غامضة لا علاقة لها بالشيفرة — وهو بالضبط ما
# يجعل رُتبةً حمراءَ تُقرأ «ورقَ حائط» فتُتجاهَل. الحلُّ: **تخطٍّ مُسمّىً
# بسببه** بعد إثباتِ العطل على مستندٍ أدنى (لا على مستنداتنا)، فيبقى الفشلُ
# الحقيقيُّ أحمرَ ويبقى عطلُ البيئة معلَناً.
_MIN_DOCX_PROBE = "silk_rung3_pdf_probe"


def _docx_to_pdf_engine_works() -> bool:
    """هل تستطيع البيئةُ تحويل **أبسط** .docx إلى PDF؟ — مِجَسٌّ لا يمسّ
    شيفرتنا إطلاقاً: يفشل => العطلُ في الحزم لا في المستند."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return False
    import tempfile
    try:
        from docx import Document
    except Exception:  # noqa: BLE001
        return False
    d = tempfile.mkdtemp(prefix=_MIN_DOCX_PROBE)
    src = os.path.join(d, "probe.docx")
    doc = Document()
    doc.add_paragraph("probe")
    doc.save(src)
    profile = tempfile.mkdtemp(prefix=_MIN_DOCX_PROBE + "_lo")
    try:
        subprocess.run(
            [soffice, "--headless", "--norestore",
             f"-env:UserInstallation=file://{profile}",
             "--convert-to", "pdf", "--outdir", d, src],
            capture_output=True, timeout=120,
            env={**os.environ, "HOME": profile})
    except Exception:  # noqa: BLE001
        return False
    return os.path.exists(os.path.join(d, "probe.pdf"))


def _node_path() -> str | None:
    """جذر حزم npm العمومية — حيث تُثبَّت playwright في هذه البيئة/CI."""
    # البيئة المُدارة قد تثبّت Playwright في مسار معلَن لا في npm root -g.
    # Honour the caller's module path; availability is checked separately.
    configured = os.environ.get("NODE_PATH", "").strip()
    if configured:
        return configured
    node = _node()
    if not node:
        return None
    # على ويندوز `npm` هو `npm.cmd`، و`CreateProcess` لا يحلّ اللاحقة بلا
    # `shell=True`؛ فكان `subprocess.run(["npm", ...])` يرمي `FileNotFoundError`
    # ⇒ `None` ⇒ بوّابةُ البيئة تُفشِل الرُتبةَ كلَّها برسالة «playwright غير
    # محلولة» بينما الحزمةُ مثبَّتةٌ فعلاً. `shutil.which` يحلّ اللاحقة على
    # ويندوز ويعيد المسارَ نفسَه على لينكس (CI) — عطلٌ في أداة القياس لا في
    # المقيس، وكان يجعل رُتبةً إلزامية غيرَ قابلةٍ للتشغيل محلياً.
    npm = shutil.which("npm")
    if not npm:
        return None
    try:
        out = subprocess.run([npm, "root", "-g"], capture_output=True,
                             timeout=30)
        root = out.stdout.decode().strip()
        return root or None
    except Exception:  # noqa: BLE001
        return None


def _rung_gate(reason: str) -> None:
    """تخطٍّ برفق محلياً، وفشلٌ عالٍ داخل وظيفة الرُتبة — skip locally, FAIL in CI.

    **تدقيق 2026-08-27 (البند ٤).** كل شروط البيئة هنا (node، حزمة playwright،
    محرّك docx→PDF) كانت `pytest.skip` **حتى داخل وظيفة `e2e-live-shape`
    نفسها**، فانكسارُ تثبيت Node أو Playwright كان يُنتِج وظيفةً **خضراء بصفر
    خطوة متصفّح فعلية**: البوّابة المطلوبة على `main` تمرّ وهي لم تنقر شيئاً.
    وهذا بالضبط ما تمنعه القاعدة القائمة في `SILK_PDF_ACCEPTANCE` — وُجد النمط
    ولم يُطبَّق هنا.

    القاعدة الآن: `SILK_RUN_E2E=1` (الذي تضبطه الوظيفة حصراً) ⇒ الشرط الغائب
    **فشل** لا تخطٍّ. خارجها (مطوّر محلي/sandbox) يبقى تخطّياً برفق كما كان.
    """
    if os.environ.get("SILK_RUN_E2E") == "1":
        pytest.fail(f"رُتبة ٣ مُلزَمة (SILK_RUN_E2E=1) وفشل شرط بيئتها: {reason}")
    pytest.skip(reason)


def _playwright_available(node_path: str | None) -> bool:
    node = _node()
    if not node or not node_path:
        return False
    env = dict(os.environ, NODE_PATH=node_path)
    r = subprocess.run(
        [node, "-e", "require('playwright');console.log('ok')"],
        capture_output=True, env=env, timeout=30)
    return r.returncode == 0


def test_rung3_full_browser_flow_word_and_md_export_and_sidebar():
    """التدفّق الكامل عبر متصفّح حقيقي — يجب أن يخرج سكربت Playwright بـ0 ويطبع
    RUNG3 PASS بعد اجتياز كل خطوة (لوحة/تقدّم/نقر جانبي/Word/Markdown)."""
    node = _node()
    if not node:
        _rung_gate("node غير متاح في هذه البيئة (أفضل جهد؛ وظيفة CI تثبّته)")
    node_path = _node_path()
    if not _playwright_available(node_path):
        _rung_gate("حزمة playwright غير محلولة عبر NODE_PATH "
                    "(أفضل جهد؛ وظيفة e2e-live-shape تثبّتها)")

    # PART 3: التدفّقُ ينقر زرّ PDF — بلا فلاتر Writer يفشل التنزيل لسببٍ
    # بيئيٍّ بحت. أثبِتْه على مستندٍ أدنى ثم تخطَّ **بسببٍ مُسمّى** بدل
    # ترك رُتبةٍ حمراءَ صامتة. وظيفةُ `e2e-live-shape` تُثبّت الحزمة فتعمل.
    if not _docx_to_pdf_engine_works():
        _rung_gate("PDF_ENGINE_MISSING: محرّكُ docx→PDF غير مكتمل في هذه "
                    "البيئة (فشل تحويلُ مستندٍ أدنى لا يمسّ شيفرتنا — حزمةُ "
                    "libreoffice-writer غائبة). الخطوةُ تعمل على وظيفة "
                    "e2e-live-shape وعلى صورة النشر (اللائحة ١٩).")

    from live_shape_server import LiveShapeServer
    with LiveShapeServer() as srv:
        env = dict(
            os.environ,
            NODE_PATH=node_path or "",
            BASE_URL=srv.base_url,
            COMPLETED_ID=str(srv.completed_id),
            RUNNING_ID=str(srv.running_id),
        )
        # المتصفّح يُورَّث من البيئة كما هي: هذه البيئة تصدّر
        # PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers مسبقاً؛ وعلى CI يضعه
        # `playwright install chromium` في مخبأه الافتراضي. لا نفرض مساراً
        # هنا كي لا نُخطئ الموضع في أيّ من البيئتين.
        r = subprocess.run([node, _FLOW], capture_output=True, env=env,
                           timeout=180)
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0, (
            f"Playwright flow failed (rc={r.returncode}).\n"
            f"STDOUT:\n{out}\nSTDERR:\n{err}")
        assert "RUNG3 PASS" in out, f"missing PASS marker.\nSTDOUT:\n{out}"


def test_rung3_prerun_modals_flow_classify_confirm_advisory_consent():
    """الشرط المُلزِم (Wave 1): متصفّح حقيقي ينقر نوافذ ما قبل التشغيل الجديدة —
    اختيار منتج/سوق ← «بحث عميق» ← نافذة تصنيف HS ← تأكيد ← نافذة استشارة بلد
    المنشأ ← موافقة صريحة ← إعادة إرسال بالموافقة. الأعلام مُفعَّلة في الخادم
    فقط (prerun_flags)، والاستشارة تُطلق من مخبأ تصدير مبذور (بلا شبكة/مفتاح/
    soffice). يخرج السكربت بـ0 ويطبع PRERUN PASS بعد كل خطوة."""
    node = _node()
    if not node:
        _rung_gate("node غير متاح في هذه البيئة (أفضل جهد؛ وظيفة CI تثبّته)")
    node_path = _node_path()
    if not _playwright_available(node_path):
        _rung_gate("حزمة playwright غير محلولة عبر NODE_PATH "
                    "(أفضل جهد؛ وظيفة e2e-live-shape تثبّتها)")

    from live_shape_server import LiveShapeServer
    with LiveShapeServer(prerun_flags=True) as srv:
        env = dict(
            os.environ,
            NODE_PATH=node_path or "",
            BASE_URL=srv.base_url,
            PRERUN_PRODUCT=srv.PRERUN_PRODUCT,
            PRERUN_HS=srv.PRERUN_HS,
            PRERUN_MARKET_ISO3=srv.PRERUN_MARKET_ISO3,
        )
        r = subprocess.run([node, _PRERUN_FLOW], capture_output=True, env=env,
                           timeout=180)
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0, (
            f"Prerun Playwright flow failed (rc={r.returncode}).\n"
            f"STDOUT:\n{out}\nSTDERR:\n{err}")
        assert "PRERUN PASS" in out, f"missing PASS marker.\nSTDOUT:\n{out}"


def test_rung3_readiness_panel_flow_checklist_before_confirm():
    """عائلة D (Wave 1.5): متصفّح حقيقي يرى لوحة «جاهزية الدراسة» — كلُّ تدهورٍ
    كسطر ✓/⚠/✗ قبل زرّ التأكيد — ثم «أكمل الدراسة» يرسل الموافقات الموحّدة.
    الخادم في وضع readiness_panel (SILK_PRERUN_ADVISORIES + مخبأ مبذور)."""
    node = _node()
    if not node:
        _rung_gate("node غير متاح (أفضل جهد؛ وظيفة CI تثبّته)")
    node_path = _node_path()
    if not _playwright_available(node_path):
        _rung_gate("حزمة playwright غير محلولة عبر NODE_PATH (أفضل جهد)")

    from live_shape_server import LiveShapeServer
    with LiveShapeServer(readiness_panel=True) as srv:
        env = dict(
            os.environ,
            NODE_PATH=node_path or "",
            BASE_URL=srv.base_url,
            PRERUN_PRODUCT=srv.PRERUN_PRODUCT,
            PRERUN_HS=srv.PRERUN_HS,
            PRERUN_MARKET_ISO3=srv.PRERUN_MARKET_ISO3,
        )
        r = subprocess.run([node, _READINESS_FLOW], capture_output=True,
                           env=env, timeout=180)
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0, (
            f"Readiness Playwright flow failed (rc={r.returncode}).\n"
            f"STDOUT:\n{out}\nSTDERR:\n{err}")
        assert "READINESS PASS" in out, f"missing PASS marker.\nSTDOUT:\n{out}"


def test_rung3_hs_candidates_dialog_blocks_on_flagged_product_and_never_auto_badges():
    """الموجة ٣ (المصنّف العام، systemic fix): متصفّح حقيقي ينقر صندوق حوار
    مرشّحي HS لمنتجٍ غير معتادٍ مُعلَّمٍ فعلاً («عود معطر»، عائلة حادثة
    الكويت LESSONS ٣٩) — صندوقٌ حاجبٌ بمرشّحين فعليّين، صفر «✓ صُنّف
    تلقائياً» على منتجٍ غير محسوم، واختيار مرشّحٍ يُتابع التدفّق فعلياً.

    (بطل الحادثة الأصلية «زبدة الفول السوداني» عاد يُحسَم تلقائياً للرمز
    الصحيح 200811 بعد إصلاح البذرة — طلب المالك 2026-07-23؛ قفلُه صار حالةَ
    auto في `hs_tier_family_flow.cjs`.)

    **بلا مفتاح كلود** (يُنزَع عمداً في كل e2e) — المرشّحون هنا حتميّون
    (بذرة CSV) لا عامّون بمساعدة نموذج؛ إثبات المسار العام الحيّ هو بوّابة
    المالك المدفوعة (LAW §2)، لا هذا الاختبار."""
    node = _node()
    if not node:
        _rung_gate("node غير متاح في هذه البيئة (أفضل جهد؛ وظيفة CI تثبّته)")
    node_path = _node_path()
    if not _playwright_available(node_path):
        _rung_gate("حزمة playwright غير محلولة عبر NODE_PATH "
                    "(أفضل جهد؛ وظيفة e2e-live-shape تثبّتها)")

    from live_shape_server import LiveShapeServer
    with LiveShapeServer(prerun_flags=True) as srv:
        env = dict(
            os.environ,
            NODE_PATH=node_path or "",
            BASE_URL=srv.base_url,
            PRERUN_MARKET_ISO3=srv.PRERUN_MARKET_ISO3,
        )
        r = subprocess.run([node, _HS_CANDIDATES_FLOW], capture_output=True,
                           env=env, timeout=180)
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0, (
            f"HS-candidates Playwright flow failed (rc={r.returncode}).\n"
            f"STDOUT:\n{out}\nSTDERR:\n{err}")
        assert "HSCAND PASS" in out, f"missing PASS marker.\nSTDOUT:\n{out}"


def test_rung3_hs_dialog_renders_only_official_codes_complete_siblings_and_bands():
    """البند ٧٢–٧٤ في متصفّحٍ حقيقي: حوارُ المرشّحين على **فصلين مختلفين**
    وببُعدَي قياسٍ مختلفين — «حليب طازج مبستر» (الفصل ٠٤، بُعد `fat`) و«شاي
    أخضر معبأ» (الفصل ٠٩، بُعد `weight`) — يُصيَّر عبر مسار المستخدم الحقيقي
    (خطّاف المنتج ← سوق ← «بحث عميق» ← `/classify_hs` ← `showHsCandidates`)،
    ثم يُقرأ الـDOM ويُؤكَّد أربعُ خصائصٍ مشتقّةٍ من `data/hs_reference.csv`:
    لا رمزَ خارج المرجع، أشقّاءُ المحور كاملون، حدودُ النطاق الرسميّة حاضرةٌ
    نصّاً، ولا صدىً لاسم منتجٍ/علامةٍ/بلدٍ في نثر الحوار.

    الحادثة التي يقفلها: الحوارُ كان يعرض نثرَ نموذجٍ (حدوداً تناقض المرجع)
    ورمزاً لا وجود له في المرجع ولا في البذرة، ومجموعةً مقتطعةً إلى ثلاثة —
    فيخرج التاجرُ برمزٍ جمركيٍّ **خاطئ بلا أيّ إشارة**."""
    node = _node()
    if not node:
        _rung_gate("node غير متاح في هذه البيئة (أفضل جهد؛ وظيفة CI تثبّته)")
    node_path = _node_path()
    if not _playwright_available(node_path):
        _rung_gate("حزمة playwright غير محلولة عبر NODE_PATH "
                    "(أفضل جهد؛ وظيفة e2e-live-shape تثبّتها)")

    cases_json, official_json = _dialog_cases_payload()
    from live_shape_server import LiveShapeServer
    with LiveShapeServer(prerun_flags=True) as srv:
        env = dict(
            os.environ,
            NODE_PATH=node_path or "",
            BASE_URL=srv.base_url,
            PRERUN_MARKET_ISO3=srv.PRERUN_MARKET_ISO3,
            DIALOG_CASES=cases_json,
            OFFICIAL_CODES=official_json,
        )
        r = subprocess.run([node, _HS_DIALOG_FLOW], capture_output=True,
                           env=env, timeout=240)
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0, (
            f"HS-dialog Playwright flow failed (rc={r.returncode}).\n"
            f"STDOUT:\n{out}\nSTDERR:\n{err}")
        assert "HSDIALOG PASS" in out, f"missing PASS marker.\nSTDOUT:\n{out}"


def test_rung3_ui_tier_consumption_locked_across_product_families():
    """قفلٌ صريحٌ طلبه المُشرِف («UI-ONLY FIX»، الموجة ٤): عبر ست عائلات
    منتجاتٍ حقيقية دفعةً واحدة — «مياه ورد»/«عود معطر»/«زيت زيتون» تُظهِر
    صندوق حوار المرشّحين ولا تُظهِر «✓ صُنّف تلقائياً» إطلاقاً؛ «زبدة الفول
    السوداني» (بعد إصلاح البذرة 2026-07-23 تُحسَم للرمز الصحيح 200811)
    و«تمر سكري»/«عسل سدر» تُظهِر الشارة مباشرةً بلا صندوق حوار. يغطّي نفس
    نقطة الاختناق (`ensureHs`) من مسار الاختيار عبر خطّاف
    الاختبار — الفارق عن `hs_candidates_flow.cjs` أنّ هذا يُثبِت **التعميم**
    (عائلات متعددة متتالية على نفس الجلسة) لا مثالاً واحداً.

    **بلا مفتاح كلود** (يُنزَع عمداً في كل e2e، LAW §2 — الدلو الثاني فقط):
    الحسم التلقائي الفعلي (اقتراح كلود يعبر عتبة الثقة) بوّابة المالك
    المدفوعة الحيّة — مُثبَتٌ هرمتياً بمحاكاة LLM في
    tests/test_hs_general_classifier.py، لا هذا القفل المتصفّحي."""
    node = _node()
    if not node:
        _rung_gate("node غير متاح في هذه البيئة (أفضل جهد؛ وظيفة CI تثبّته)")
    node_path = _node_path()
    if not _playwright_available(node_path):
        _rung_gate("حزمة playwright غير محلولة عبر NODE_PATH "
                    "(أفضل جهد؛ وظيفة e2e-live-shape تثبّتها)")

    from live_shape_server import LiveShapeServer
    with LiveShapeServer(prerun_flags=True) as srv:
        env = dict(
            os.environ,
            NODE_PATH=node_path or "",
            BASE_URL=srv.base_url,
            PRERUN_MARKET_ISO3=srv.PRERUN_MARKET_ISO3,
        )
        r = subprocess.run([node, _HS_TIER_FAMILY_FLOW], capture_output=True,
                           env=env, timeout=240)
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0, (
            f"HS tier-family Playwright flow failed (rc={r.returncode}).\n"
            f"STDOUT:\n{out}\nSTDERR:\n{err}")
        assert "HSTIERFAMILY PASS" in out, f"missing PASS marker.\nSTDOUT:\n{out}"


_PLATFORM_FLOW = os.path.join(_ROOT, "tests", "e2e", "platform_flow.cjs")
_PLATFORM_LANG_FLOW = os.path.join(_ROOT, "tests", "e2e",
                                   "platform_language_flow.cjs")


def test_rung3_platform_console_full_flow_admin_and_factory(monkeypatch):
    """رُتبة ٣ للمنصّة (2026-08-17): متصفّح حقيقي ينقر منصّة المصانع كاملةً.

    الدرسان ٧٦–٧٧ وحادثة «الدخول مستحيل» اكتشفها المالك لا الاختبارات — لأن
    رُتبة المتصفّح كانت تغطي `web/index.html` وحدها بينما وُلدت رقعة
    `platform.html` كاملة بلا رُتبة مكافئة. التدفّق: `/platform` ← دخول أدمِن ←
    قسم «تكاليف البحث» ← تمويل مصنع ← ضبط حصّة المستخدم (قرار المالك) ← خروج ←
    دخول مصنع ← الرصيد والحصّة ظاهران، **ولا أثر لأي تكلفة داخلية** (قرار
    المالك) ← الأقسام الجديدة (قمع/صور/تدقيق) تُفتَح ← صفحة إعادة التعيين
    الحقيقية تُحمَّل. يخرج السكربت بـ0 ويطبع PLATFORM RUNG3 PASS.
    """
    node = _node()
    if not node:
        _rung_gate("node غير متاح في هذه البيئة (أفضل جهد؛ وظيفة CI تثبّته)")
    node_path = _node_path()
    if not _playwright_available(node_path):
        _rung_gate("حزمة playwright غير محلولة عبر NODE_PATH "
                    "(أفضل جهد؛ وظيفة e2e-live-shape تثبّتها)")

    from live_shape_server import LiveShapeServer
    # R3: ابذر دراسةً آخرُ محاولتها **انقطعت** — الشريحةُ الوحيدة التي لا
    # يبلغها نقرٌ (انقطاعُ إعادة النشر يحتاج قتلَ خادمٍ في منتصف تشغيلة).
    # البذرُ خلف العلَم فلا تراه بقيةُ التدفّقات، والسكربتُ يعلن التخطّي بدونه.
    # `monkeypatch` يستردّ البيئة حتماً — لا تسرّبَ لبقية العملية (الدرس ٥٥).
    monkeypatch.setenv("SILK_LIVE_SHAPE_SEED_INTERRUPTED", "1")
    with LiveShapeServer(platform=True) as srv:
        env = dict(
            os.environ,
            NODE_PATH=node_path or "",
            BASE_URL=srv.base_url,
            ADMIN_EMAIL=srv.PLATFORM_ADMIN_EMAIL,
            FACTORY_EMAIL=srv.PLATFORM_FACTORY_EMAIL,
            PLATFORM_PASSWORD=srv.PLATFORM_PASSWORD,
            SEED_INTERRUPTED="1",
        )
        r = subprocess.run([node, _PLATFORM_FLOW], capture_output=True,
                           env=env, timeout=240)
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0, (
            f"Platform Playwright flow failed (rc={r.returncode}).\n"
            f"STDOUT:\n{out}\nSTDERR:\n{err}")
        assert "PLATFORM RUNG3 PASS" in out, f"missing PASS marker.\nSTDOUT:\n{out}"


def test_rung3_factory_report_language_full_browser_flow(tmp_path):
    """رُتبة ٣ — لغة تقارير المصنع بالنقر، **باللغتين**، حتى الـPDF النهائي.

    التدفّق الذي طلبه المالك حرفياً: إعدادات المصنع ← تغيير لغة التقارير ←
    حفظ ← إنشاء دراسة ← لقطة اللغة ← توليد التقرير ← DOCX/PDF نهائي. ويؤكّد
    السكربتُ في المتصفّح ثلاثة قيودٍ لا يراها أيّ اختبارٍ آخر: أنّ تدفّق
    إنشاء الدراسة **يعرض** اللغة ولا **يسأل** عنها (§15)، وأنّ قلب لغة
    **الواجهة** لا يغيّر لغة **التقارير** (إعدادان مستقلّان)، وأنّ تقريراً
    مكتملاً لا تنقلب لغتُه بتبديلٍ لاحق.

    ثمّ يُفحَص هنا **نصُّ الـPDF المُنزَّل من المتصفّح فعلاً** — الترويسة
    والتذييل ضمنه (لا يقرؤهما فحصُ متن الـdocx إطلاقاً).
    """
    node = _node()
    if not node:
        _rung_gate("node غير متاح في هذه البيئة (أفضل جهد؛ وظيفة CI تثبّته)")
    node_path = _node_path()
    if not _playwright_available(node_path):
        _rung_gate("حزمة playwright غير محلولة عبر NODE_PATH "
                    "(أفضل جهد؛ وظيفة e2e-live-shape تثبّتها)")

    from live_shape_server import LiveShapeServer
    with LiveShapeServer(platform=True) as srv:
        # المصنعُ المبذور «فضّي» (سقفٌ شهريّ حقيقيّ = دراستان) وهذا التدفّق
        # يُطلق ثلاثاً — تُرفَع الطبقة عبر **نقطة الأدمِن الحقيقية** فتبقى
        # بوّابة الحصّة فاعلةً كما في الإنتاج بدل تعطيل الحارس.
        _raise_tier_to_gold(srv)
        env = dict(
            os.environ,
            NODE_PATH=node_path or "",
            BASE_URL=srv.base_url,
            FACTORY_EMAIL=srv.PLATFORM_FACTORY_EMAIL,
            PLATFORM_PASSWORD=srv.PLATFORM_PASSWORD,
        )
        r = subprocess.run([node, _PLATFORM_LANG_FLOW], capture_output=True,
                           env=env, timeout=300)
        out = r.stdout.decode("utf-8", "replace")
        err = r.stderr.decode("utf-8", "replace")
        assert r.returncode == 0, (
            f"Factory-language Playwright flow failed (rc={r.returncode}).\n"
            f"STDOUT:\n{out}\nSTDERR:\n{err}")
        assert "PLATFORM LANGUAGE RUNG3 PASS" in out, (
            f"missing PASS marker.\nSTDOUT:\n{out}")

        # ── الدليلُ على المصنوع النهائي: نصُّ الـPDF المُنزَّل من المتصفّح ──
        import silk_i18n
        arts = dict(ln.split("=", 1) for ln in out.splitlines()
                    if ln.startswith("ARTIFACT_PDF_"))
        for key, lang in (("ARTIFACT_PDF_AR", "ar"), ("ARTIFACT_PDF_EN", "en")):
            path = arts.get(key)
            assert path and os.path.exists(path), f"مصنوع مفقود: {key}"
            assert os.path.getsize(path) > 5000, f"{key} صغير جداً"
            body = _pdf_text_or_fail(path)
            spans = silk_i18n.foreign_prose_spans(body, lang)
            assert spans == [], (
                f"PDF المُنزَّل بلغة «{lang}» فيه نثرٌ بلغةٍ أخرى: {spans[:2]}")
            if lang == "en":
                # التذييلُ يُطبَع على كل صفحة ولا يظهر في متن الـdocx إطلاقاً.
                assert "Export Market Study" in body, "غلافٌ ليس بلغة التقرير"
                assert "Silk Market Intelligence" in body, (
                    "تذييلُ الصفحة ليس بلغة التقرير")
                assert "منصة تحليل أسواق التصدير" not in body, (
                    "تذييلٌ عربيٌّ على تقريرٍ إنجليزيّ")
            else:
                assert "دراسة سوق" in body, "غلافٌ ليس بلغة التقرير"


def _raise_tier_to_gold(srv) -> None:
    """ارفع طبقةَ المصنع المبذور عبر نقطة الأدمِن — لا كتابةَ مباشرةً بالقاعدة."""
    import json
    import urllib.request

    def _post(path, token, body):
        req = urllib.request.Request(
            srv.base_url + path, data=json.dumps(body).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")

    def _get(path, token):
        req = urllib.request.Request(srv.base_url + path)
        req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")

    admin = _post("/platform/auth/login", "",
                  {"email": srv.PLATFORM_ADMIN_EMAIL,
                   "password": srv.PLATFORM_PASSWORD})["token"]
    fac = _post("/platform/auth/login", "",
                {"email": srv.PLATFORM_FACTORY_EMAIL,
                 "password": srv.PLATFORM_PASSWORD})["token"]
    aid = _get("/platform/me", fac)["account_id"]
    _post(f"/platform/admin/accounts/{aid}/tier", admin, {"tier": "gold"})


def _pdf_text_or_fail(pdf_path: str) -> str:
    """نصُّ الـPDF — غيابُ `pdftotext` فشلٌ لا تخطٍّ إلا ببيئةٍ موسومة."""
    import shutil
    if not shutil.which("pdftotext"):
        if os.environ.get("SILK_PDF_LOCAL_SKIP", "").strip() in ("1", "true"):
            pytest.skip("SILK_PDF_LOCAL_SKIP=1 — نصّ الـPDF لم يُستخرَج")
        pytest.fail("pdftotext غائب — لا يُتحقَّق من لغة الـPDF النهائي")
    out = pdf_path + ".txt"
    subprocess.run(["pdftotext", "-enc", "UTF-8", pdf_path, out],
                   check=True, timeout=120)
    with open(out, encoding="utf-8", errors="replace") as fh:
        return fh.read()
