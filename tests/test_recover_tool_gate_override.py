"""أداةُ الاسترداد التشغيلية (`tools/recover_and_verify.py`) — التعامل مع حجب
بوابة الجودة (بلاغ تحليل 20 الحيّ: `quality_gate_fail` على تصدير العميل).

الأداةُ تصل خادماً حيّاً، فنحاكي `_req` وحدَه (لا شبكة): عند 409 من التصدير مع
`--override` + مفتاح المالك تُعيد المحاولة بـ`?override=1` وترويسة `X-Owner-Key`
فتُسلَّم النسخة موسومةً بملاحظات البوابة بدل حجبها (LESSONS 46/53؛ فلسفة #230 على
طبقة التصدير). هرمتي بالكامل. Run:
  python3 -m pytest tests/test_recover_tool_gate_override.py -q
"""
import importlib.util
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_tool():
    path = os.path.join(_ROOT, "tools", "recover_and_verify.py")
    spec = importlib.util.spec_from_file_location("recover_and_verify", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _complete_report_json() -> bytes:
    secs = ["الخلاصة التنفيذية", "منهجية البحث ونطاقه",
            "نظرة عامة على السوق وحجمه", "ديناميكيات السوق",
            "تحليل المستهلك والطلب", "المشهد التنافسي",
            "التنظيم والوصول للسوق", "اللوجستيات وسلسلة الإمداد",
            "تقييم المخاطر", "التوصيات الاستراتيجية", "الملاحق"]
    text = "\n".join(f"## {i}. {s}\nفقرة." for i, s in enumerate(secs, 1))
    return json.dumps({"deep_research": {"report": {
        "report": text, "incomplete": False}}}).encode()


_GATE_409 = json.dumps({"detail": {
    "error": "quality_gate_fail", "message": "محجوب",
    "blocked_checks": ["section_structure", "trends_hollow_completion"]}}).encode()


def test_blocked_checks_parses_live_error_shape():
    m = _load_tool()
    assert m._blocked_checks(_GATE_409) == [
        "section_structure", "trends_hollow_completion"]
    assert m._blocked_checks(b'{"detail":"x"}') == []
    assert m._blocked_checks(b"<html>") == []


def test_export_falls_back_to_owner_override_on_gate_block(capsys):
    """409 quality_gate_fail على التصدير + --override + مفتاح مالك ⇒ إعادةُ
    التصدير بـ?override=1 وترويسة X-Owner-Key، فيُسلَّم موسوماً."""
    m = _load_tool()
    calls = []

    def fake_req(method, url, key, timeout=900.0, owner_key=None):
        calls.append({"method": method, "url": url, "owner_key": owner_key})
        if method == "POST":
            return 200, _complete_report_json(), "application/json"
        # تصدير: أوّلاً 409 (بلا تجاوز)، ثم 200 متى حمل ?override=1
        if "override=1" in url:
            assert owner_key == "ownersecret"          # الترويسة مُرِّرت
            return 200, b"BYTES", "application/pdf"
        return 409, _GATE_409, "application/json"

    m._req = fake_req
    argv = ["recover_and_verify.py", "--id", "20", "--base", "http://x",
            "--key", "k", "--override", "--owner-key", "ownersecret"]
    old = sys.argv
    sys.argv = argv
    try:
        rc = m.main()
    finally:
        sys.argv = old
    out = capsys.readouterr().out
    override_exports = [c for c in calls
                        if c["method"] == "GET" and "override=1" in c["url"]]
    assert len(override_exports) == 3               # md/docx/pdf أُعيدت بالتجاوز
    assert all(c["owner_key"] == "ownersecret" for c in override_exports)
    assert "تجاوزُ مالكٍ" in out                      # سُلِّمت موسومة
    assert "trends_hollow_completion" in out          # الفحوصُ الحاجبة معلَنة


def test_gate_block_without_override_reports_and_guides(capsys):
    """409 بلا --override ⇒ لا تسليم، لكن تُعلَن الفحوصُ الحاجبة وتُرشِد للمخارج
    (--fresh / إعادةُ البعثة / --override) — لا حجبٌ صامت."""
    m = _load_tool()

    def fake_req(method, url, key, timeout=900.0, owner_key=None):
        if method == "POST":
            return 200, _complete_report_json(), "application/json"
        return 409, _GATE_409, "application/json"

    m._req = fake_req
    argv = ["recover_and_verify.py", "--id", "20", "--base", "http://x",
            "--key", "k"]
    old = sys.argv
    sys.argv = argv
    try:
        rc = m.main()
    finally:
        sys.argv = old
    out = capsys.readouterr().out
    assert rc == 1                                    # لا ادعاءَ نجاح
    assert "بوابةُ الجودة حجبت" in out
    assert "trends_hollow_completion" in out
    assert "--fresh" in out and "--override" in out   # المخارجُ مُرشَدة
