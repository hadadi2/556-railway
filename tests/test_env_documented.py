"""حارس توثيق متغيّرات البيئة — every env var the code reads must be documented.

**الحادثة (تدقيق 2026-08-27، البند ١٨).** الشيفرة كانت تقرأ ١٨٣ متغيّر بيئة،
**٨٢** منها غائب عن `.env.example` — ومنها مفاتيح حوادث المال:
`SILK_RESEARCH_MAX_LLM_CALLS`، `COMTRADE_DAILY_BUDGET`،
`SILK_WRITER_MAX_TOKENS`. مشغّلٌ لا يعرف بوجود صمّامٍ لا يستطيع إدارته: يشحّ
عليه التقرير ولا يعرف أن سقفاً هو السبب، فيبحث في الشيفرة عن عطلٍ غير موجود.

التوثيق الذي يعتمد على تذكّر الكاتب ينجرف دائماً؛ هذا الاختبار يجعل الانجراف
**أحمر وقتَ الكتابة**: أضف `os.environ.get("SILK_X")` بلا سطر في
`.env.example` ⇒ يسقط. الاسم يكفي (سطر تعليق يشرحه هو الحدّ الأدنى المتوقَّع).

هرمتي: قراءة ملفات فقط، بلا شبكة ولا مفاتيح.
"""
import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parent.parent

# قراءات بيئةٍ لا تُوثَّق: أدوات ومسارات اختبارٍ لا يضبطها مشغّل الإنتاج أبداً.
# كل استثناء هنا قرارٌ مكتوب، لا نسيان. Test-only knobs, deliberately excluded.
_EXEMPT = {
    "PYTEST_CURRENT_TEST", "CI", "HOME", "PATH", "PORT", "NODE_PATH",
    "BASE_URL", "COMPLETED_ID", "RUNNING_ID",
    "PLAYWRIGHT_BROWSERS_PATH", "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD",
    "SILK_RUN_E2E", "SILK_RUN_LIVE", "SILK_PDF_ACCEPTANCE",
    "SILK_BASE_URL",
}

_ENV_READ = re.compile(
    r'(?:os\.environ\.get|os\.getenv)\(\s*["\']([A-Z0-9_]+)["\']'
    r'|os\.environ\[\s*["\']([A-Z0-9_]+)["\']')


def _source_files():
    """وحدات الإنتاج وحدها — الجذر + حزمة المنصّة (لا tests/ ولا tools/)."""
    return (sorted(_ROOT.glob("*.py"))
            + sorted((_ROOT / "silk_platform").glob("*.py")))


def test_every_env_var_read_by_production_code_is_documented():
    """كل متغيّر تقرؤه الشيفرة مذكور في `.env.example` — بلا استثناء غير مكتوب."""
    example = (_ROOT / ".env.example").read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for path in _source_files():
        for m in _ENV_READ.finditer(path.read_text(encoding="utf-8")):
            name = m.group(1) or m.group(2)
            found.setdefault(name, path.name)

    missing = sorted(n for n in found
                     if n not in _EXEMPT and n not in example)
    assert not missing, (
        "متغيّرات بيئة تقرؤها الشيفرة وغير موثّقة في .env.example:\n  "
        + "\n  ".join(f"{n}  ({found[n]})" for n in missing)
        + "\n\nوثّق كلاً منها بسطرٍ يشرح أثره وافتراضه — مشغّلٌ لا يعرف "
          "الصمّام لا يستطيع إدارته (تدقيق 2026-08-27، البند ١٨).")


# DEBT-8 (تدقيق 2026-09-01): الاتّجاهُ المعاكس — متغيّرٌ **موثَّقٌ لا تقرؤه الشيفرة**
# وعدٌ بصمّامٍ غير موجود: يضبطه المشغّل، لا يتغيّر شيء، ويظنّ أنّ المشكلة في مكانٍ آخر.
# الوثيقةُ التي تَعِد بما لا وجود له أسوأُ من الصمت.
#
# الأسماءُ تُقرَأ بثلاث طرق، والحارسُ يعرفها كلَّها وإلا كان إنذارُه كاذباً:
#   ١. حرفياً: `os.environ.get("SILK_X")` أو عبر ملفٍّ مساعد `_env_int("SILK_X", …)`.
#   ٢. **عائلةً مبنيّة**: `f"SILK_FRESH_{kind.upper()}_DAYS"` تُغطّي
#      `SILK_FRESH_TRADE_DAYS` وأخواتها؛ فالقالبُ ذاته دليلُ القراءة.
#   ٣. **خارج بايثون**: `docker/entrypoint.sh` يقرأ `SILK_RUN_AS_ROOT`، وسير CI يقرأ
#      `SILK_PDF_LOCAL_SKIP`. سطحُ التنفيذ ليس `.py` وحده.
# ولهذا يمسح الحارسُ كلَّ ما يُنفَّذ (py/sh/yml/Dockerfile) لا وحداتِ الإنتاج فقط —
# لكنّه **لا** يَعُدّ ذِكراً في وثيقةٍ قراءةً؛ فوثيقةٌ تُحيل إلى وثيقةٍ ليست صمّاماً.
_DOC_ONLY: set[str] = set()  # كلُّ إضافةٍ هنا قرارٌ مكتوب بسببه، لا نسيان.

_EXECUTABLE_SUFFIXES = (".py", ".sh", ".yml", ".yaml", ".toml", ".cfg", ".ini")
_STRING_WITH_ENV_NAME = re.compile(r'["\']([A-Za-z0-9_{}.\[\]()]*SILK_[A-Za-z0-9_{}.\[\]()]*)["\']')


def _executable_files():
    """كلُّ ما يُنفَّذ في هذا الريبو — لا `.md` ولا `.env.example` نفسه."""
    out = []
    for path in _ROOT.rglob("*"):
        if not path.is_file():
            continue
        parts = path.relative_to(_ROOT).parts
        if any(p in {".git", "node_modules", "__pycache__", ".venv", "venv",
                     "ci_venv", "htmlcov"} for p in parts):
            continue
        if path.name.startswith("Dockerfile") or path.suffix in _EXECUTABLE_SUFFIXES:
            out.append(path)
    return out


def _read_names(sources) -> tuple[set, list]:
    """(أسماءٌ حرفية، أنماطُ عائلاتٍ مبنيّة) — القالبُ `{...}` يصير `[A-Z0-9_]+`."""
    literal: set = set()
    families: list = []
    for path in sources:
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in _STRING_WITH_ENV_NAME.finditer(src):
            token = m.group(1)
            if "{" in token or "%" in token:
                pattern = re.sub(r"\{[^{}]*\}", "[A-Z0-9_]+", token)
                pattern = pattern.replace("%s", "[A-Z0-9_]+")
                if "[A-Z0-9_]+" in pattern:
                    try:
                        families.append(re.compile(pattern + "$"))
                    except re.error:
                        pass
            elif re.fullmatch(r"[A-Z0-9_]+", token):
                literal.add(token)
        # أسماءٌ غيرُ بايثونية: `$SILK_X` / `SILK_X=` في السكربتات وسير العمل.
        literal |= set(re.findall(r"\$\{?(SILK_[A-Z0-9_]+)", src))
        literal |= set(re.findall(r"^\s*(?:export\s+)?(SILK_[A-Z0-9_]+)\s*[:=]", src, re.M))
    return literal, families


def test_every_documented_env_var_is_read_or_exempt():
    """كلُّ `SILK_*` مضبوطٍ في `.env.example` تقرؤه الشيفرةُ فعلاً أو له سببٌ مكتوب."""
    example_path = _ROOT / ".env.example"
    documented = set(re.findall(r"^#?\s*(SILK_[A-Z0-9_]+)\s*=",
                                example_path.read_text(encoding="utf-8"), re.M))
    literal, families = _read_names(
        [p for p in _executable_files() if p != example_path])
    stale = sorted(
        n for n in documented
        if n not in literal and n not in _DOC_ONLY and n not in _EXEMPT
        and not any(f.match(n) for f in families))
    assert not stale, (
        "متغيّراتٌ موثّقةٌ في .env.example لا تقرؤها الشيفرة — وعدٌ بصمّامٍ غير موجود:\n  "
        + "\n  ".join(stale)
        + "\n\nاحذف السطر، أو اقرأ المتغيّر فعلاً، أو أضِف سببَ بقائه إلى `_DOC_ONLY` "
          "(تدقيق 2026-09-01، DEBT-8).")


def test_the_money_ceilings_are_documented_by_name():
    """تأكيد صريح لأخطرها: سقوف الإنفاق التي كان غيابها يُخفي سبب شُحّ التقرير."""
    example = (_ROOT / ".env.example").read_text(encoding="utf-8")
    for name in ("SILK_RESEARCH_MAX_LLM_CALLS", "SILK_RESEARCH_MAX_TOOL_CALLS",
                 "SILK_RESEARCH_MAX_USD", "COMTRADE_DAILY_BUDGET",
                 "SILK_WRITER_MAX_TOKENS", "SILK_MAX_TOKENS_CEILING",
                 "SILK_MISSION_TIMEOUT_S"):
        assert name in example, f"سقف إنفاق غير موثّق: {name}"


def test_database_url_is_documented_as_unsupported_not_as_an_option():
    """`DATABASE_URL` فرعُ توافقٍ لا مسارٌ مدعوم — قرار «SQLite فقط» مستقر.

    التدقيق رفعه سؤالاً في «يحتاج تأكيداً»: وجوده في الشيفرة بلا ذكرٍ في
    التوثيق يجعله يبدو خياراً جاهزاً. صار موثّقاً **بوصفه غير مدعوم**.
    """
    example = (_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "DATABASE_URL" in example
    # القسم المخصّص له في آخر الملف (لا أول ذكرٍ عابر) — العنوان يبدأ به.
    heading = "── DATABASE_URL"
    assert heading in example, "لا قسم مخصّص يشرح حالة DATABASE_URL"
    section = example[example.index(heading):]
    assert "SQLite" in section
    assert "غير مختبَر" in section and "لا مدعوم" in section
    assert "يُترك فارغاً" in section
