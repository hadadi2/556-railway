"""حُرّاس صفحة لوحة المنصّة — `web/platform.html`.

**العائلة التي تُغلقها:** الصفحة تقرأ حقولاً من ردود `/platform/*`. اسمُ حقلٍ
خاطئ **لا يرفع خطأً** — يعرض قسماً فارغاً صمتاً. وقع هذا فعلاً أثناء البناء:
كُتِب `.ledger` والنقطة تُرجع `entries`، فكان الدفتر يظهر فارغاً دائماً بلا أي
إشارة. مراجعةُ عينٍ لا تلتقط هذا؛ هذه الاختبارات تلتقطه.

لذلك الحارس الأهمّ هنا **يقارن مفاتيح الردّ الحقيقية** بما تقرؤه الصفحة، لا
يتفحّص النصّ فقط. A wrong field name renders an empty section silently — these
tests compare the page's reads against real response keys.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.platform_helpers import client, hdr, login, make_factory, seed

_PAGE = pathlib.Path(__file__).resolve().parent.parent / "web" / "platform.html"


def _without_comments(src: str) -> str:
    """الصفحة بلا شروح — ما يراه المستخدم فعلاً، لا ما يشرحه المطوّر.

    يلزم للفحوص التي تمنع **نصّاً معروضاً**: ذكرُ العبارة الممنوعة في تعليقٍ
    يشرح سببَ إزالتها كان يُحمِّر الحارسَ على شيفرةٍ سليمة، وحارسٌ يُنذِر كاذباً
    يُدرَّب المرءُ على تجاهله.
    """
    src = re.sub(r"<!--.*?-->", " ", src, flags=re.S)      # شروح HTML
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)       # شروح CSS/JS الكتلية
    return re.sub(r"(?m)^\s*//.*$", " ", src)              # شروح JS السطرية


@pytest.fixture(scope="module")
def html() -> str:
    assert _PAGE.exists(), "web/platform.html مفقودة — صفحة اللوحة"
    return _PAGE.read_text(encoding="utf-8")


# ═════════════════ الاكتفاء الذاتي · self-contained (CSP-safe) ════════════════
def test_page_has_no_external_references(html):
    """لا CDN ولا خطّ خارجي — الخدمة تُقدّم CSP صارمة، والخارجي يُحجَب حيّاً.

    الخطوط مستضافة ذاتياً في `web/fonts/` (نفس اتفاق `index.html`).
    """
    external = re.findall(r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)', html)
    assert not external, f"مراجع خارجية ستُحجَب بـCSP: {external}"


def test_page_uses_no_eval_so_it_survives_the_csp(html):
    """لا `eval`/`new Function` — سياسة `script-src` تمنعهما (وقد أثبتَه المتصفّح).

    اكتُشف عملياً: انتظارُ Playwright بنصٍّ يُقيَّم كان يُرفَض بـ`unsafe-eval`،
    فالسياسة فعّالة حقاً — والصفحة يجب أن تبقى نظيفة منهما.
    """
    for bad in ("eval(", "new Function(", "setTimeout(\"", "setInterval(\""):
        assert bad not in html, f"استعمالٌ يمنعه CSP: {bad}"


def test_page_is_rtl_arabic_first(html):
    assert 'dir="rtl"' in html and 'lang="ar"' in html


# ══════ الحارس الذي كان غائباً فمرّت صفحةٌ ميّتة تماماً ═══════════════════════
# **الحادثة:** كتبتُ سلسلةً تفتح بـ`"` وتُغلق بـ`'`، فالتقط المُحلِّلُ بقيّةَ
# النصّ داخل سلسلةٍ لا تنتهي ⇒ **خطأ صياغة يقتل كل السكربت**: لا زرّ يعمل، ولا
# حتى الدخول. ومع ذلك **مرّت كل حُرّاس هذا الملف** — لأنها تُطابِق نصوصاً، وكلُّ
# النصوص المطلوبة كانت حاضرة في ملفٍ لا يعمل. التقطه المتصفّح في رُتبة ٣ فقط.
# القاعدة: حارسُ نصٍّ لا يُثبِت أن الصفحة **تعمل**؛ يلزم فحصُ تحليلٍ فعليّ.
def _script_body(html: str) -> str:
    m = re.search(r"<script>(.*)</script>", html, re.S)
    assert m, "لا كتلة سكربت في الصفحة"
    return m.group(1)


def test_the_page_script_parses_with_a_real_js_engine(html):
    """تحليلٌ فعليّ بـnode — لا مطابقةُ نصّ.

    **لماذا مُحلِّلٌ حقيقيّ ولا شيء أقلّ:** كتبتُ أوّلاً ماسحَ سلاسل هرمتيّاً
    (يتعقّب الاقتباسات بلا أدوات خارجية) فأنذر **كاذباً** على شيفرةٍ سليمة:
    السلسلةُ الحرفية `/[&<>"']/g` في `esc()` تحمل اقتباسات داخل **تعبيرٍ نمطيّ**،
    ولا يُميّزها عن السلسلة إلا محلّلٌ كامل (تمييزُ القسمة من النمط يحتاج تحليلاً
    نحويّاً لا مسحاً). وحارسٌ يُنذِر كاذباً يُدرَّب المرءُ على تجاهله، فحُذِف.

    **الحدّ المُعلَن بصراحة:** يُتخطّى إن غاب node، فالحزمة الهرمتية وحدها **لا
    تُثبِت** أن الصفحة تُحلَّل في تلك البيئة. المُعوِّض أن عُقدة CI تحمل node،
    وأن رُتبة ٣ (متصفّح حقيقي) تُسقِط أيّ سكربت ميّت فوراً — وهي من التقطت
    الحادثة أصلاً.
    """
    import shutil
    import subprocess
    import tempfile
    node = shutil.which("node") or next(
        (p for p in ("/opt/node22/bin/node", "/usr/bin/node",
                     "/usr/local/bin/node") if pathlib.Path(p).exists()), None)
    if not node:
        pytest.skip("node غير متوفّر — الماسح الهرمتيّ يبقى هو الحارس")
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "page.js"
        f.write_text(_script_body(html), encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, f"سكربت الصفحة لا يُحلَّل:\n{r.stderr[:1200]}"


# ═══════════ كل مسار تطلبه الصفحة موجود فعلاً · every fetched path exists ════
def _paths_fetched(html: str) -> set[str]:
    """مسارات `/platform/...` التي تطلبها الصفحة — الحرفيّة منها.

    تُطبَّع القوالب (`"/studies/" + id + "/" + action`) إلى شكلٍ قابل للمقارنة.
    """
    out = set()
    for m in re.finditer(r'api\(\s*"([^"]+)"', html):
        out.add(m.group(1).split("?")[0])
    # النداءات المركّبة: "/studies/" + id + "/" + action
    for m in re.finditer(r'api\(\s*"(/[a-z-]+/)"\s*\+', html):
        out.add(m.group(1))
    return out


def test_every_path_the_page_calls_is_a_registered_route(html):
    """مسارٌ تطلبه الصفحة ولا وجود له = قسمٌ ميت — يُلتقَط هنا لا في الإنتاج."""
    import silk_platform.api as papi
    registered = set(re.findall(r'@app\.\w+\(_PREFIX \+ "([^"]+)"',
                                pathlib.Path(papi.__file__).read_text(encoding="utf-8")))
    # الأشكال المُعامَلة: حوِّل `/studies/{study_id}/archive` إلى بادئة قابلة للمطابقة.
    prefixes = {re.sub(r"\{[^}]+\}.*$", "", r) for r in registered}
    missing = []
    for p in _paths_fetched(html):
        if p in registered:
            continue
        if any(p == pre or p.rstrip("/") == pre.rstrip("/") for pre in prefixes):
            continue
        missing.append(p)
    assert not missing, (
        f"الصفحة تطلب مسارات غير مُسجَّلة: {missing}\nالمُسجَّل: {sorted(registered)}")


# ══════ الحارس الأهمّ: مفاتيح الردّ الحقيقية مقابل ما تقرؤه الصفحة ═══════════
def _root_key_the_page_reads(html: str, path: str) -> str | None:
    """المفتاح الجذري الذي تقرؤه الصفحة من ردّ هذا المسار — أو None.

    شكلان في الصفحة: قراءةٌ مباشرة `(await api("/x")).key`، أو عبر متغيّر
    (`out = await api("/users")` ثم `out.users`). نتعامل مع الاثنين كي لا يمرّ
    خللُ اسمٍ في أيٍّ منهما.
    """
    # طابِق على المسار الأساس بلا سلسلة الاستعلام: الاختبار قد يستعمل `?limit=5`
    # والصفحة `?limit=12` — والمقارنة الحرفية كانت تُرجع None فتُشخِّص خللاً
    # وهميّاً (وقع فعلاً في أوّل تشغيل لهذا الحارس).
    esc = re.escape(path.split("?")[0])
    m = re.search(rf'api\(\s*"{esc}(?:\?[^"]*)?"[^)]*\)\s*\)\s*\.\s*(\w+)', html)
    if m:
        return m.group(1)
    # عبر متغيّر: احصر النافذة على ما بعد النداء ثم خُذ أوّل `<var>.<key>`.
    m = re.search(rf'(\w+)\s*=\s*await\s+api\(\s*"{esc}(?:\?[^"]*)?"', html)
    if m:
        var = m.group(1)
        after = html[m.end():m.end() + 900]
        m2 = re.search(rf'\b{re.escape(var)}\s*\.\s*(\w+)\s*\|\|', after)
        if m2:
            return m2.group(1)
    # التفكيك من `Promise.all` — `const [a, b] = await Promise.all([api("/x"), …])`
    # ثم `a.key`. بلا هذا الشكل كان المُساعِد يرجع `None` على شيفرةٍ **سليمة**،
    # وهي نقطةٌ عمياء أخطر من الفشل: مفتاحٌ خاطئ في نداءٍ مُفكَّك يمرّ بلا حارس.
    for m in re.finditer(r"\[([^\]]+)\]\s*=\s*await\s+Promise\.all\(\s*\[(.*?)\]\s*\)",
                         html, re.S):
        names = [n.strip() for n in m.group(1).split(",")]
        calls = re.findall(r'api\(\s*"([^"]+)"', m.group(2))
        for idx, call in enumerate(calls):
            if call.split("?")[0] != path.split("?")[0] or idx >= len(names):
                continue
            var = names[idx]
            after = html[m.end():m.end() + 900]
            m2 = re.search(rf'\b{re.escape(var)}\s*\.\s*(\w+)\b', after)
            if m2:
                return m2.group(1)
    return None


def test_page_reads_the_real_response_keys(monkeypatch, html):
    """كل حقلٍ تقرؤه الصفحة موجود في الردّ الفعلي — يقفل خلل `.ledger`/`entries`.

    اسمُ حقلٍ خاطئ يعرض قسماً فارغاً **بلا خطأ**، فلا اختبارُ نصٍّ يكفي ولا
    مراجعةُ عين. هنا نضرب النقاط فعلاً ونقارن.
    """
    seed(monkeypatch)
    f = make_factory("silver", "ui-keys@example.com", fund_cents=500)
    cl = client()
    tok = login(cl, f["email"], f["password"])

    # املأ صفّاً واحداً في كل مجموعة كي تُفحَص **حقول العنصر** لا القائمة الفارغة:
    # قائمةٌ فارغة تجعل فحص الحقول لا-عمليّاً فيبدو أخضر بلا أن يقيس شيئاً.
    cl.post("/platform/studies", headers=hdr(tok),
            json={"product": "تمور", "market_pref": "ARE"})

    cl.post("/platform/products", headers=hdr(tok),
            json={"name": "تمور", "hs_code": "080410"})

    # (المسار, مفتاح القائمة الجذري, الحقول التي تقرؤها الصفحة من كل عنصر)
    # (واجهات users/ledger/audit حُذفت — قرار المالك 2026-08-18؛ حلّ محلّها
    #  products/overview/notifications، وكلٌّ يُفحَص بنفس الصرامة.)
    checks = [
        ("/studies", "studies",
         ("id", "product", "market_pref", "state", "run_started_at",
          "run_error", "analysis_id")),
        ("/products", "products",
         ("id", "name", "description", "hs_code", "studies_count")),
        ("/notifications", "notifications",
         ("id", "kind", "title", "body", "created_at", "read_at")),
        # قسم «الصور» حُذف (قرار المالك 2026-08-17) — الرفع صار داخل نافذة
        # الدراسة (POST /images فقط)، فلا قارئ قائمةٍ للصور في الصفحة بعد.
    ]
    for path, root, item_fields in checks:
        body = cl.get(f"/platform{path}", headers=hdr(tok)).json()
        # (أ) الردّ يحمل المفتاح المتوقّع.
        assert root in body, (
            f"{path}: المتوقّع مفتاح `{root}` والردّ يحمل {list(body)}")
        assert isinstance(body[root], list)
        # (ب) **والصفحة تقرأ هذا المفتاح بعينه** — هذا هو الحارس الفعلي.
        page_key = _root_key_the_page_reads(html, path)
        assert page_key == root, (
            f"{path}: الصفحة تقرأ `{page_key}` والردّ يحمل `{root}` — "
            "قسمٌ سيظهر فارغاً صمتاً بلا أي خطأ")
        if body[root]:
            missing = [k for k in item_fields if k not in body[root][0]]
            assert not missing, f"{path}: حقول تقرؤها الصفحة وغائبة: {missing}"

    # حقول الاستحقاقات المسطّحة (بطاقة الرصيد حُذفت — «الباقة فقط»).
    ent = cl.get("/platform/entitlements", headers=hdr(tok)).json()
    for k in ("tier", "studies_limit", "studies_used", "studies_period", "dashboard", "export",
              "api_access", "white_label"):
        assert k in ent, f"/entitlements: حقل تقرؤه الصفحة وغائب: {k}"
    me = cl.get("/platform/me", headers=hdr(tok)).json()
    for k in ("email", "role", "first_name", "last_name"):
        assert k in me, f"/me: حقل تقرؤه الصفحة وغائب: {k}"

    # نظرة عامة المصنع (2026-08-18) — ليست قائمةً جذرية واحدة، تُفحَص حقولها.
    ov = cl.get("/platform/overview", headers=hdr(tok)).json()
    for k in ("studies", "markets", "best_market", "recent", "markets_note"):
        assert k in ov, f"/overview: حقل تقرؤه الصفحة وغائب: {k}"
    for k in ("completed", "in_progress", "draft"):
        assert k in ov["studies"], f"/overview.studies: حقل غائب: {k}"


def test_admin_panel_reads_the_real_admin_response_keys(monkeypatch, html):
    """مفاتيح لوحة الأدمِن حقيقية أيضاً — `accounts` و`on` لا اسمٌ مُخترَع."""
    info = seed(monkeypatch)
    make_factory("gold", "ui-admin-keys@example.com")
    cl = client()
    tok = login(cl, info["admin"]["email"], info["admin"]["password"])
    accts = cl.get("/platform/admin/accounts", headers=hdr(tok)).json()
    assert _root_key_the_page_reads(html, "/admin/accounts") == "accounts"
    assert "accounts" in accts and accts["accounts"]
    for k in ("id", "name", "tier", "is_active"):
        assert k in accts["accounts"][0], f"/admin/accounts: حقل غائب: {k}"
    allst = cl.get("/platform/admin/studies", headers=hdr(tok)).json()
    assert "studies" in allst, (
        f"/admin/studies: المتوقّع `studies`، وُجد {list(allst)}")
    assert "renderAdminStudies" in html, "الصفحة لا تعرض إشراف كل الدراسات"


# ══════ الحارس الذي يحمل بلاغ المالك: «كيف أستعمل؟ لا يوجد أيّ خيار» ══════════
# الشاشة الأولى كانت قارئةً فقط: ٢٩ نقطةَ كتابة في الـAPI مقابل **زرَّي** دخول
# وخروج. فبدت مستنداً لا أداة. هذا الحارس يمنع الانحدار إلى تلك الحالة: كلُّ فعلٍ
# يقوم عليه المنتَج يجب أن يبقى **قابلاً للنقر** من الصفحة.
_REQUIRED_WRITES = [
    ('"/studies"', "إنشاء دراسة سوق"),
    # قرار 2026-08-18: واجهة المستخدمين حُذفت (مستخدم واحد فعلياً) وحلّ محلّها
    # كتالوج المنتجات + البروفايل — الفعلان الجديدان مقفولان بنفس الصرامة.
    ('"/products"', "إضافة منتج"),
    ('"/me/password"', "تغيير كلمة المرور ذاتياً"),
    ('"/overview"', "نظرة عامة الأسواق المدروسة"),
    ('/launch', "إطلاق دراسة"),
    ('/report"', "عرض تقرير الدراسة"),
    # طلب المالك 2026-08-17: «اريده pdf» — المُسلَّم النهائي PDF غير قابل
    # للتحرير؛ نقطة docx باقية خادمياً بلا زر.
    ('/report.pdf', "تنزيل تقرير PDF"),
    ('"/classify-image"', "قراءة المنتج والرمز من الصورة"),
    # الأرشفة تُبنى كـ`"/studies/" + id + "/" + action` — يُفحَص الوسيط نفسه.
    # (الموجة الثنائية: التسمية صارت زوج tr(عربي، إنجليزي) — الفعل كما هو.)
    ('actBtn(ar_en("أرشفة", "Archive"), s.id, "archive"', "أرشفة"),
    # «تمويل محفظة مصنع» خرج من الواجهة (قرار المالك 2026-08-20: «حساب
    # التمويل ما له أي فائدة» — بعد «الباقة فقط» لا يُخصَم من المحفظة شيء عند
    # الإطلاق). النقطة والدفتر باقيان خادمياً؛ الحارس أدناه يقفل غياب الواجهة.
    ('"/admin/tiers/"', "تعديل سعر الباقة وحصّتها"),
    ('/tier', "تغيير الطبقة"),
    ('/quota', "حصّة المستخدم"),
]


@pytest.mark.parametrize("needle,label", _REQUIRED_WRITES,
                         ids=[l for _n, l in _REQUIRED_WRITES])
def test_the_page_still_exposes_this_action(html, needle, label):
    """كل فعلٍ من هذه القائمة له نداءٌ في الصفحة — وإلا عادت لوحةَ عرضٍ صامتة."""
    assert needle in html, (
        f"لا سبيل إلى «{label}» من الصفحة — الفعل موجود في الـAPI وغائب عن "
        "الواجهة، وهو بعينه بلاغ «لا يوجد أيّ خيار»")


def test_a_write_call_uses_a_writing_http_method(html):
    """الأفعال تُنادى بـPOST فعلاً — لا نداءُ قراءةٍ يبدو زرّ فعل.

    بلا هذا الفحص كان يكفي أن يُذكَر المسار نصّاً ليمرّ الحارسُ أعلاه، فيبدو
    الزرُّ موجوداً وهو لا يكتب شيئاً.
    """
    for needle in ('"/studies"', '"/products"', '"/me/password"',
                   '"/admin/tiers/"', '"/classify-image"'):
        # نافذةٌ بعد النداء تكفي لظهور method: "POST" في نفس الاستدعاء.
        idx = 0
        found = False
        while True:
            idx = html.find("api(" + needle, idx + 1)
            if idx < 0:
                break
            if 'method: "POST"' in html[idx:idx + 260]:
                found = True
                break
        assert found, f"{needle}: لا نداء POST — الزرّ لا يكتب شيئاً"


def test_launch_is_a_plain_confirm_with_no_prospecting_payload(html):
    """الإطلاق تأكيدٌ واحد بلا حمولة تنقيب — قرار المالك (2026-08-17).

    (عكسُ الحارس القديم `launch_sends_both_a_draft_and_prospects` عمداً:
    الإطلاق يشغّل محرّك سِلك، ولا وجود لنصوص رسائل أو عملاء محتملين أصلاً.)
    """
    assert 'api("/studies/" + s.id + "/launch", {method: "POST"})' in html, (
        "نداء الإطلاق البسيط غائب")
    for banned in ("draft_id", "prospect_ids"):
        assert banned not in html, (
            f"أثر تنقيب `{banned}` ما يزال في الصفحة بعد الحذف النهائي")


def test_the_page_never_calls_a_missing_feature_unavailable(html):
    """«غير متاح» اختفت لصالح «في الباقة …» — بلاغُ مالك: تُقرأ «مكسور».

    الطبقة silver كانت تُظهِر أربعة صفوف «غير متاح» والمصفوفة صحيحة
    (`models.TIER_LIMITS`: الثلاثة في platinum فقط) — فالعيب عرضيٌّ: النصّ يجب
    أن يسمّي الباقة التي تفتح الميزة لا أن يبدو عطلاً.
    """
    # يُفحَص **ما يُعرَض** لا الشروح: الفحص الأوّل كان يُحمِّر على ذكرِ العبارة
    # داخل تعليقٍ يشرح سببَ إزالتها — إنذارٌ كاذب على شيفرةٍ سليمة.
    visible = _without_comments(html)
    assert "غير متاح" not in visible, (
        "«غير متاح» تُقرأ «مكسور» بدل «ليست في خطّتك» — سمِّ الباقة التي تفتحها")
    assert "في الباقة " in visible, "لا نصّ ترقية يسمّي الباقة"


# ══════ القائمة الجانبية · the sidebar (بلاغ مالك: «المفروض قائمة جانبية») ════
def test_every_sidebar_section_points_at_a_panel_that_exists(html):
    """كل مدخلٍ في `SECTIONS` يشير إلى لوحٍ موجود — لا مدخلَ يفتح فراغاً.

    القائمة تُبنى من جدولٍ واحد، فمِعرَّفٌ مكتوبٌ خطأً يُنتِج زرّاً يُبدِّل إلى
    **لا شيء** بلا أيّ خطأ في وحدة التحكّم: القسم لا يظهر والسابق يختفي. وهذا
    عيبٌ لا تلتقطه مراجعةُ عين.
    """
    m = re.search(r"const SECTIONS = \[(.*?)\n\];", html, re.S)
    assert m, "لم يُوجد جدول الأقسام `SECTIONS`"
    panels = re.findall(r'panel:\s*"(\w+)"', m.group(1))
    assert len(panels) >= 7, f"عدد الأقسام أقلّ من المتوقّع: {panels}"
    # شريط المقاييس سياقٌ دائم لا قسماً — فلا يجوز أن يعود إلى الجدول.
    assert "factoryStats" not in panels, (
        "شريط المقاييس عاد قسماً يُبدَّل؛ وهو سياقٌ دائم (والقسم كان يُفكِّك شبكته)")
    for pid in panels:
        assert f'id="{pid}"' in html, f"القسم يشير إلى لوحٍ غير موجود: {pid}"


def test_every_panel_in_the_page_is_reachable_from_the_sidebar(html):
    """والعكس: لوحٌ في الصفحة بلا مدخلٍ في القائمة = محتوىً لا سبيل إليه.

    هذا الاتجاه هو الذي يُنتِج بلاغ «لا يوجد أيّ خيار» من جديد: القسم موجود
    ومحمَّل ولا زرَّ يُظهِره.
    """
    m = re.search(r"const SECTIONS = \[(.*?)\n\];", html, re.S)
    listed = set(re.findall(r'panel:\s*"(\w+)"', m.group(1)))
    in_page = set(re.findall(r'<section class="panel sect" id="(\w+)"', html))
    orphans = in_page - listed
    assert not orphans, f"ألواحٌ لا يفتحها أيّ مدخل في القائمة: {sorted(orphans)}"


def test_the_sidebar_hides_admin_sections_from_a_factory(html):
    """أقسام كل دور لا تُبنى لغيره — التصفية بالدور لا بإخفاءٍ بصريّ.

    زرٌّ مخفيٌّ بـCSS يبقى في الشجرة ويُنقَر برمجياً؛ التصفية عند البناء تمنع
    وجوده أصلاً. **حُدِّث للنموذج الثلاثي** (إصلاح دور المحلّل 2026-08-17):
    التصفية الثنائية القديمة `(x.role === "silk_admin") === !!admin` كانت تُظهِر
    للمحلّل أقسامَ المصنع كلّها فترتدّ نداءاتها 403 — كل دورٍ يطابق أقسامه
    بالاسم الحرفيّ الآن.
    """
    assert "function visibleSections" in html, "لا تصفية للأقسام بالدور"
    assert "x.role === role" in html, "لا مطابقة دورٍ حرفية عند البناء"
    # «any» (البروفايل 2026-08-18) — قسمٌ مشترك للأدوار الثلاثة، بشرطٍ حرفيّ
    # صريح لا بتوسيع مطابقة الدور نفسها.
    assert 'x.role === "any"' in html, "لا شرط قسمٍ مشترك (البروفايل)"
    # الأدوار الثلاثة كلها ممثَّلة في جدول الأقسام — قسمٌ واحد على الأقل لكلٍّ.
    m = re.search(r"const SECTIONS = \[(.*?)\n\];", html, re.S)
    roles = set(re.findall(r'role:\s*"(\w+)"', m.group(1)))
    assert roles == {"factory", "silk_admin", "silk_analyst", "any"}, (
        f"أدوار جدول الأقسام ناقصة/زائدة: {roles}")
    # والتصفية الثنائية القديمة (عيب المحلّل) لم تعُد:
    assert '(x.role === "silk_admin") === !!admin' not in html


def test_the_page_is_usable_at_a_phone_width(html):
    """استجابةٌ عند ٣٧٥px: القائمة تنطوي، والبطاقات تتراصف، ولا تمريرَ أفقيّ.

    (معيارُ قبولٍ صريح في الأمر المُعدَّل §8.1(1). التحقّق البصريّ الفعليّ يجري
    في رُتبة ٣ بلقطة عند ٣٧٥px؛ هذا يقفل وجودَ القواعد نفسها.)
    """
    assert "@media(max-width:820px)" in html, "لا استعلامَ وسائط للجوّال"
    mobile = html[html.index("@media(max-width:820px)"):][:600]
    assert "translateX(100%)" in mobile, "القائمة لا تنطوي على الجوّال"
    assert "grid-template-columns:1fr" in mobile, "البطاقات لا تتراصف"
    # الجداول تُمرَّر داخل حاوٍ لا تُمرِّر الصفحة أفقياً.
    assert ".tbl{width:100%;overflow-x:auto}" in html


def test_the_admin_and_factory_toolbars_are_separated(html):
    """شريطُ الأدمِن لا يظهر لمصنع ولا العكس — نقاط الأدمِن ترفض 403 أصلاً.

    زرٌّ يظهر ثم يُرفَض 403 تجربةٌ سيّئة، والأسوأ أنه يُلبِس المستأجرَ حدودَ دوره.
    """
    assert 'id="adminBar"' in html and 'id="factoryBar"' in html
    assert 'ME.role === "silk_admin"' in html, "لا تفريقَ بالدور في الصفحة"


def test_page_renders_every_state_label_the_api_can_return(html):
    """كل حالة دراسة في مخطّط القاعدة لها ترجمة في الصفحة — لا حالة تظهر خاماً."""
    migration = (pathlib.Path(__file__).resolve().parent.parent /
                 "migrations" / "platform" / "001_platform_core.sql"
                 ).read_text(encoding="utf-8")
    m = re.search(r"state\s+TEXT NOT NULL DEFAULT 'draft'\s*CHECK \(state IN \(([^)]+)\)",
                  migration)
    assert m, "لم يُقرأ قيد حالات الدراسة من الترحيل"
    states = [s.strip().strip("'") for s in m.group(1).split(",")]
    for st in states:
        assert st in html, f"حالة `{st}` بلا ترجمة/تعامل في الصفحة"


def test_error_codes_the_gates_raise_have_arabic_messages(html):
    """أكواد بوّابات الحالة والمال لها رسائل عربية — المنتَج عربيّ أولاً.

    الترجمة على **الكود** لا على نصّ الخادم، فتبقى صحيحة لو أُعيدت صياغة النصّ.
    """
    for code in ("already_archived", "invalid_transition",
                 "insufficient_funds", "tier_gate",
                 # أكواد التحوّل لدراسات السوق (2026-08-17).
                 "study_no_product", "no_report_yet", "user_quota_exceeded"):
        # حدُّ الكلمة ضروري: بلا `(?<![\w])` كان `XX_pending_emails:` يُشبِع
        # فحصَ `pending_emails:` (أُثبِت عملياً) — أي حارسٌ يُخدَع بإعادة تسمية.
        assert re.search(rf"(?<![\w]){code}\s*:", html), (
            f"كود بلا رسالة عربية: {code}")


# ══════ الموجة ٣ (التحوّل): الاتجاه الصحيح + صفحة الهبوط + الرسالة العالقة ════
def test_sidebar_is_pinned_to_the_inline_start_right_in_rtl(html):
    """الشريط الجانبي يمين الشاشة — بلاغ مالك حيّ: «المفروض عربي على اليمين».

    الخلل كان `inset-inline-end:0` (= يسار في RTL) فظهر الشريط يساراً كواجهة
    أجنبية. `inset-inline-start` في RTL = اليمين الفيزيائي، وهامش المحتوى
    يقابله. `translateX(100%)` للدرج **صحيح بعد القلب** (transform فيزيائي:
    ينزلق يميناً خارج الشاشة) — فيُثبَّت بقاؤه لا تغييره.
    """
    assert "inset-inline-start:0" in html, "الشريط ليس مثبتاً على بداية السطر (يمين RTL)"
    assert "inset-inline-end:0" not in html, "تثبيت نهاية السطر (يسار RTL) عاد"
    assert "margin-inline-start:var(--sidew)" in html
    assert "translateX(100%)" in html


def test_sticky_error_banner_is_cleared_on_navigation(html):
    """الرسالة الحمراء لا تعلق للأبد — تُمسح عند تبديل القسم وإعادة التحميل.

    بلاغ مالك حيّ: «طبقتك لا تمنح هذه الميزة» بقيت معلّقة أعلى كل الأقسام
    (say() كان يمسح "good" فقط).
    """
    show = html[html.index("function showSection"):]
    show = show[:show.index("function buildNav")]
    assert 'if (!$("appMsg").className.includes("good")) $("appMsg").className = "msg"' in show, \
        "تبديل القسم لا يطوي الرسالة العالقة"
    load = html[html.index("async function loadAll"):]
    load = load[:load.index("async function loadFactory")]
    assert 'if (!$("appMsg").className.includes("good")) $("appMsg").className = "msg"' in load, \
        "إعادة التحميل لا تطوي الرسالة العالقة"


def test_landing_page_is_served_at_the_platform_prefix(monkeypatch):
    """`/platform` يخدم صفحة الهبوط وفيها زرّ الدخول إلى البوابة (طلب المالك)."""
    seed(monkeypatch)
    cl = client()
    r = cl.get("/platform")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    assert "تسجيل الدخول" in body, "رابط الدخول غائب عن صفحة الهبوط"
    assert 'href="/platform.html"' in body, "الزرّ لا يقود إلى البوابة"
    assert 'dir="rtl"' in body


def test_latin_content_is_bidi_isolated(html):
    """البريد والأدوار والأكواد اللاتينية معزولة اتجاهياً — «الإنجليزي على اليسار».

    العزل إمّا صنف `.num` (direction:ltr + unicode-bidi) أو مساعد `ltr()`
    (LRI…PDI عبر textContent) — النص الخام في خلية RTL كان يتقلّب.
    """
    assert "const ltr = (s)" in html
    # شارة الدور صارت معرّبة عبر dd(ROLE_AR, ROLE_EN, …) (موجة الملف التعريفي
    # 2026-08-19: الرمز الخام "factory" رطانة — نفس عقد الباقات) فخرجت من فحص
    # العزل اللاتيني؛ المساعد ltr() باقٍ حيّاً لمعرّف التقرير في عنوان النافذة.
    assert 'ltr("#" + s.id)' in html                    # معرّف التقرير معزول
    assert "dd(ROLE_AR, ROLE_EN, ME.role)" in html      # شارة الدور المعرّبة
    # (خلايا المستخدمين/التدقيق حُذفت مع واجهاتها 2026-08-18 — العزل يُفحَص
    #  على الخلايا اللاتينية الحيّة اليوم: رموز HS والأسواق وبريد البروفايل.)
    assert 'cell(tr, p.hs_code || "—", "num")' in html  # رموز HS في المنتجات
    assert 'id="pfEmail" dir="ltr"' in html             # بريد البروفايل


# ═══ جولة المالك 2026-08-17 («جرّب كل الأزرار») — أقفال التنظيف ═══════════════
def test_images_panel_is_gone_and_upload_is_inline(html):
    """قسم «الصور» حُذف نهائياً (قرار المالك: «ايش فائدة الصور في داشبورد
    المستخدم احذفها») — الرفع صار حقل ملف داخل نافذة الدراسة نفسها."""
    assert 'id="imagesPanel"' not in html
    assert '"images"' not in html.split("const SECTIONS")[1].split("];")[0], \
        "صف الصور ما زال في جدول الأقسام"
    assert 'id="uploadImgBtn"' not in html
    assert "loadImages" not in html
    # الرفع داخل النافذة: حقل ملف + معرّف خفي + رفع فوري عند الاختيار.
    assert 'name="image_file"' in html
    assert 'type="hidden" name="image_id"' in html
    assert "uploadImage(f)" in html


def test_escape_closes_the_topmost_dialog(html):
    """Escape يغلق أعلى نافذة — النوافذ div.veil لا <dialog>، فبلا مستمعٍ
    صريح كان الزر بلا أثر (رصد الجولة على نافذة «تمويل محفظة مصنع»)."""
    assert '"Escape"' in html
    assert "#dlgHost .veil" in html


def test_login_screen_probes_me_only_with_a_session_marker(html):
    """لا 401 أحمر في كونسول كل زائر: جسّ /me عند الإقلاع مشروط بعلامة جلسة
    محلية تُختم عند الدخول وتُمسح عند الخروج/فشل الجس."""
    assert 'localStorage.getItem("silk_has_session")' in html
    assert 'localStorage.setItem("silk_has_session", "1")' in html
    assert 'localStorage.removeItem("silk_has_session")' in html


def test_tier_badges_are_arabic(html):
    """أسماء الباقات معرّبة أمام المستخدم — silver/gold الخام رصدها المالك."""
    assert "const TIER_AR" in html
    for name in ("أساسية", "فضية", "ذهبية", "بلاتينية"):
        assert name in html
    # (الموجة الثنائية: القراءة عبر dd(TIER_AR, TIER_EN, …) الموافقة للغة.)
    # الشارة انتقلت من أسفل الشريط الجانبي إلى بطاقة الحساب في «الملف
    # التعريفي» (النمط العالمي 2026-08-19) — النداء الحرفي نفسه باقٍ.
    assert "dd(TIER_AR, TIER_EN, ent.tier)" in html   # شارة الملف التعريفي
    # §58 (الموجة نفسها): الشارة تُصفَّر لغير المصنع — loadFactory وحده يملؤها،
    # وبلا التصفير كانت باقة دخولِ مصنعٍ سابق في التبويب تبقى ظاهرة لأدمِن بعده.
    assert '$("whoTier").textContent = ""' in html
    assert "dd(TIER_AR, TIER_EN, a.tier)" in html     # جدول الحسابات


def test_dialog_tables_wrap_instead_of_clipping(html):
    """جدول داخل نافذةٍ يلتفّ ولا يُقصّ من الحافة (رصد الجولة: عمود الثقة
    في نافذة التقرير كان مبتوراً) — قاعدة .tbl العامة تبقى حرفياً."""
    assert ".dlg .tbl th{white-space:normal}" in html
    assert ".tbl{width:100%;overflow-x:auto}" in html   # المحرّم البايتي كما هو


def test_admin_studies_table_offers_the_same_report_buttons(html):
    """قرار المالك 2026-08-19: جدول «كل الدراسات» يفتح التقرير كما يفتحه العميل.

    وبإعادة استعمال الزرّين نفسيهما لا بنسخةٍ ثانية — العرض القانوني واحد
    (LAW §7): أي مسار عرضٍ موازٍ ينحرف عن الأصل بصمت.
    """
    body = html.split("function renderAdminStudies(")[1].split("\nfunction ")[0]
    assert "viewReportBtn(s)" in body, (
        "جدول الأدمِن بلا زرّ «عرض التقرير» — الفجوة التي أمر المالك بسدّها")
    assert "pdfBtn(s.id)" in body, "جدول الأدمِن بلا زرّ تنزيل PDF"
    assert 'th_actions' in html, "رأس عمود الإجراءات مفقود من جدول الأدمِن"
    # التكلفة سطحُ أدمِن حصراً — ولا تُقرأ من حمولة التقرير (المجرَّدة أصلاً).
    assert 'ME.role !== "silk_admin"' in html, (
        "سطر التكلفة غير محصور بدور الأدمِن")


# ═════════ إصلاحات الفحص البصري (2026-08-19) — قفلٌ لكل عطبٍ رُصد ═══════════
def test_chart_labels_are_ltr_and_the_chart_has_a_bounded_size(html):
    """تسمياتٌ لاتينية داخل سياق RTL + رسمٌ بمقياس بلا حدّ.

    `text-anchor="end"` كان ينقلب في سياق الصفحة العربية فيخرج النصّ خارج
    إطار الرسم ولا يظهر من رمز الدولة إلا حرف؛ و`width:100%` بلا ارتفاع كان
    يُضخّم الأعمدة على 1440px ويُضائل الحروف على 390px.
    """
    body = html.split("function renderMarketsChart(")[1].split("\nfunction ")[0]
    assert body.count('direction: "ltr"') >= 2, (
        "نصوص المخطّط بلا اتجاه صريح — تنقلب داخل سياق RTL وتُقتطع")
    assert "host.clientWidth" in body, (
        "عرض المخطّط لم يعد مقاساً من حاويته — يعود المقياس بلا حدّ")
    # والقياس لا يقع إلا والحاوية مرئيّة: `loadHome` تسبق فتح اللوح.
    assert "ResizeObserver" in html, (
        "لا مراقب حجم — القياس يقع والحاوية مخفيّة فيسقط إلى عرضٍ ثابت")
    assert 'svg.style.height = "auto"' in body, (
        "بلا ارتفاع تابع للنسبة يعود التصغير وفراغُ الأسفل عند التضييق")
    assert 'height: String(H)' in body and "preserveAspectRatio" in body, (
        "المخطّط بلا ارتفاع صريح أو بلا نسبة أبعاد — يتضخّم/يتضاءل بلا حدّ")


def test_the_section_title_and_primary_action_have_one_source_each(html):
    """عنوانٌ واحد (الرأس) وفعلٌ رئيسيّ واحد (شريط الأدوات) — لا ازدواج."""
    for dead in ('id="newStudyBtn2"', 'id="newStudyBtn3"'):
        assert dead not in html, f"{dead}: نسخةٌ ثانية من زرّ «دراسة جديدة» عادت"
    for panel in ("studiesPanel", "homePanel", "profilePanel"):
        block = html.split(f'id="{panel}"')[1].split("</section>")[0]
        assert "<h2" not in block, (
            f"{panel}: ترويسةٌ تكرّر عنوان القسم المطبوع في الرأس")


def test_the_session_email_lives_in_the_profile_alone(html):
    """البريد في موضعٍ واحد: «الملف التعريفي». لا في ذيل الشريط الجانبي.

    السابقة (رصد المالك البصري): كان معروضاً في `#whoAmI` أسفل الشريط وفي
    `#pfEmail` داخل الملف معاً — حقيقةٌ واحدة في موضعين، ونصفُ الشاشة يحمل
    عنواناً لا يقود إلى فعل. الذيل يحمل الآن الاسم واسم المنشأة من `/me`
    (`first_name`/`last_name`/`account_name`) — أو يُسقِط سطرَه، ولا يخترع.
    """
    assert 'id="pfEmail" dir="ltr"' in html, "بريد الملف التعريفي غاب"
    aside = html.split("<aside")[1].split("</aside>")[0]
    assert "whoAmI" not in aside, "عنصر البريد عاد إلى الشريط الجانبي"
    assert "ME.email" not in aside, "بريدٌ يُسنَد داخل الشريط الجانبي"
    # الذيل يُبنى في JS خارج <aside> — احرس الإسناد نفسه: البريد يجوز حرفاً
    # واحداً للأڤاتار (`charAt(0)`) لا نصّاً كاملاً في أيّ عنصر هوية.
    for host in ("whoName", "whoOrg"):
        line = [ln for ln in html.splitlines()
                if f'$("{host}").textContent' in ln]
        assert line, f"{host} بلا إسناد"
        for ln in line:
            assert "ME.email" not in ln, f"{host} يعرض البريد: {ln.strip()}"
    assert "first_name" in html and "account_name" in html, (
        "الذيل لا يقرأ حقول الهوية الحقيقية")
    # اسم المنشأة لدور المصنع حصراً: الأدمِن/المحلّل مربوطان بحساب الخزنة،
    # فعرض «Silk (operator/vault)» منشأةً لهما وصفٌ خاطئ لا فراغ (§58).
    org = [ln for ln in html.splitlines() if "const org =" in ln]
    assert len(org) == 1 and 'ME.role === "factory"' in org[0], (
        f"اسم المنشأة بلا تصفيةٍ بالدور: {org}")
    # عزل ثنائي الاتجاه: اسمٌ لاتينيّ ينتهي بمحرفٍ محايد ينقلب داخل RTL.
    for cls in (".nm{", ".sub{"):
        block = html.split(f"aside.side .foot {cls}")[1].split("}")[0]
        assert "unicode-bidi:plaintext" in block, f"{cls} بلا عزل ثنائي الاتجاه"
    # البريد صار في «الملف التعريفي» وحده، فلا يجوز أن يمحوه فشلُ محمّلِ دور:
    # `fillProfile` تُنادى قبل التوزيع على الأدوار، لا بعده فقط.
    # R6 (FE-20): حارسُ التداخل يلفّ `loadAll`؛ جسمُها الفعليّ في `_loadAllOnce`.
    body = html.split("async function _loadAllOnce()")[1].split("\n}")[0]
    assert body.index("fillProfile();") < body.index("if (isAdmin) await loadAdmin();"), (
        "fillProfile بعد محمّلات الدور فقط — فشلُ أحدها يمحو البريد من الشاشة")


def test_the_toolbars_live_inside_the_header_row(html):
    """الرأس كان صفّاً شبه فارغ وفوقه صفُّ أدوات — دمجٌ يستردّ صفّاً كاملاً."""
    header = html.split("<header class=\"top\">")[1].split("</header>")[0]
    for bar in ('id="factoryBar"', 'id="adminBar"', 'id="notifBtn"'):
        assert bar in header, f"{bar} خارج الرأس — عاد الصفّ الضائع"


def test_narrow_tables_advertise_their_horizontal_scroll(html):
    """عمود «الحالة» كان يختفي على 390px بلا أيّ إشارة إلى وجود تمرير."""
    # الشريط الدائم لا التدرّج: خلفيّات الخلايا تُرسَم فوق خلفية الحاوية
    # فيظهر التدرّج شرائطَ مقطّعة (ملاحظة مراجعة ذاتية §58 على هذه الموجة).
    assert "overflow-x:scroll" in html, (
        "شريط التمرير عاد اختيارياً — الاقتطاع يعود بلا دليل عليه")
    assert ".tbl::-webkit-scrollbar" in html, "شريط تمرير الجدول غير مُنسَّق"


def test_unknown_label_values_never_reach_the_screen(html):
    """قيمةٌ خارج خريطة التسميات كانت تُطبَع رمزاً إنجليزياً خاماً للعميل."""
    body = html.split("const dd = (arMap, enMap, k) => {")[1].split("\n};")[0]
    assert 'ar_en("غير معروف", "Unknown")' in body, (
        "البديل عاد رمزاً خاماً بدل نصٍّ محايد مُعرَّب")
    assert "console.warn" in body, "القيمة المجهولة لا تُسجَّل للتشخيص"


def test_the_login_screen_is_a_real_form(html):
    """مديرو كلمات المرور لا يعرضون الحفظ/الملء إلا داخل <form>."""
    assert '<form id="loginForm"' in html, "شاشة الدخول بلا نموذج حقيقي"
    assert '$("loginForm").addEventListener("submit"' in html, (
        "النموذج بلا معالج إرسال — الإرسال الافتراضي يعيد تحميل الصفحة")
    assert 'placeholder="name@company.com"' in html, (
        "العنوان النائب عاد بريداً يبدو حقيقياً")
    assert '$("pw").addEventListener("keydown"' not in html, (
        "مستمع Enter اليدوي عاد فوق الإرسال — نداءُ دخولٍ مزدوج")
    # حقلٌ فارغ لا يصل الخادم: محاولةٌ فاشلة تُحتسَب في خانق الدخول (١٠/٣٠٠ث)
    # فتقفل الحساب على من يضغط Enter من حقل البريد بعادةٍ متكرّرة.
    form = html.split('$("loginForm").addEventListener("submit"')[1].split("\n});")[0]
    assert "if (!email || !pw)" in form, (
        "الإرسال بلا حارس حقلٍ فارغ — يحرق محاولات خانق الدخول")
