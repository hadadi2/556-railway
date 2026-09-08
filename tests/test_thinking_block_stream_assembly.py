"""إعادةُ تجميع كتل التفكير الممتدّ من البثّ — قفلُ الحادثة الحيّة (2026-08-23).

البلاغ الحيّ: تشغيلةٌ على الرأس المنشور ردّت HTTP 400 من واجهة Anthropic:

    messages.1.content.0.thinking: each thinking block must contain thinking

السبب: مُجمِّعُ SSE في `AnthropicProvider._consume_stream` (الموجة p6، T5)
يعرف `text_delta` و`input_json_delta` فقط. أمّا `thinking_delta` (نصُّ
التفكير) و`signature_delta` (توقيعُه) فيُسقَطان صامتَين — فتخرج كتلةُ التفكير
بنصٍّ فارغ وبلا توقيع. وفي الدور التالي تُعاد الرسالةُ نفسُها إلى الواجهة
(دورُ أداةٍ يجب أن يحمل كتلَ التفكير **حرفياً كما وصلت**) فتُرفَض بـ400.

العطلُ حتميّ لا عارض: كلُّ نداءٍ يبثّ تفكيراً ثم يستدعي أداةً يفشل بنفس
الطريقة، فإعادةُ الإطلاق تُعيد نفسَ الفشل.

العقد المقفول هنا:
- نصُّ التفكير = تسلسلُ كلّ `thinking_delta` بالترتيب، حرفياً.
- التوقيع = تسلسلُ كلّ `signature_delta`، حرفياً (يصل مقطَّعاً كالنصّ).
- الرسالةُ المجمَّعة **صالحةٌ للإرسال في الدور التالي**: لا كتلةَ تفكيرٍ بنصٍّ
  فارغ ولا بلا توقيع — وهو بالضبط ما تشترطه الواجهة.
- ترتيبُ الكتل محفوظ (التفكير قبل الأداة) وكتلةُ الأداة لم تُمَسّ.
- `redacted_thinking` يعبر كما وصل: حمولتُه `data` تصل كاملةً في
  `content_block_start` ولا دلتا لها — والحارسُ يمنع «تنقيةً» تُتلِفها.

هرمتي بالكامل — لا شبكة، لا مفتاح.
Run:  python -m pytest tests/test_thinking_block_stream_assembly.py -q
"""
import contextlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import silk_llm_provider as lp  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_provider_contextvars():
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)
    yield
    lp._last_error.set(None)
    lp._last_stop_reason.set(None)


@contextlib.contextmanager
def _env(**vals):
    saved = {k: os.environ.get(k) for k in vals}
    try:
        for k, v in vals.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _sse(event: str, data: dict) -> list[str]:
    return [f"event: {event}", f"data: {json.dumps(data)}", ""]


class _StreamResp:
    """ردّ مبثوث مُحاكى — نفس عقد `_StreamResp` في قفل T5."""

    def __init__(self, lines):
        self._lines = lines
        self.status_code = 200
        self.headers = {}
        self.text = ""
        self.closed = False

    def iter_lines(self, decode_unicode=True, **kw):
        yield from self._lines

    def close(self):
        self.closed = True

    def json(self):
        raise AssertionError("json() must not be called on a streamed response")


# ── الحمولات · the wire payloads ─────────────────────────────────────────────

THINK_PARTS = ("دعني أتحقّق من ", "بيانات الاستيراد ", "قبل الإجابة.")
SIG_PARTS = ("Er8BCkYIBRgCKkD", "9mK2vQx7hLpNs", "==")


def _thinking_then_tool_lines(redacted: bool = False) -> list[str]:
    """بثٌّ واقعيّ: كتلةُ تفكير (نصّ + توقيع، كلاهما مقطَّع) ثمّ كتلةُ أداة."""
    lines = []
    lines += _sse("message_start", {
        "type": "message_start",
        "message": {"id": "msg_think_1", "role": "assistant", "content": [],
                    "usage": {"input_tokens": 120, "output_tokens": 1}}})

    if redacted:
        # `redacted_thinking`: الحمولةُ كاملةٌ في الافتتاح — لا دلتا لها.
        lines += _sse("content_block_start", {
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "redacted_thinking",
                              "data": "EncryptedBlobAAAA=="}})
        lines += _sse("content_block_stop",
                      {"type": "content_block_stop", "index": 0})
    else:
        lines += _sse("content_block_start", {
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "thinking", "thinking": "",
                              "signature": ""}})
        for part in THINK_PARTS:
            lines += _sse("content_block_delta", {
                "type": "content_block_delta", "index": 0,
                "delta": {"type": "thinking_delta", "thinking": part}})
        for part in SIG_PARTS:
            lines += _sse("content_block_delta", {
                "type": "content_block_delta", "index": 0,
                "delta": {"type": "signature_delta", "signature": part}})
        lines += _sse("content_block_stop",
                      {"type": "content_block_stop", "index": 0})

    lines += _sse("content_block_start", {
        "type": "content_block_start", "index": 1,
        "content_block": {"type": "tool_use", "id": "toolu_think_1",
                          "name": "comtrade_imports", "input": {}}})
    lines += _sse("content_block_delta", {
        "type": "content_block_delta", "index": 1,
        "delta": {"type": "input_json_delta", "partial_json": '{"hs": "08'}})
    lines += _sse("content_block_delta", {
        "type": "content_block_delta", "index": 1,
        "delta": {"type": "input_json_delta", "partial_json": '0410"}'}})
    lines += _sse("content_block_stop",
                  {"type": "content_block_stop", "index": 1})
    lines += _sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": "tool_use", "stop_sequence": None},
        "usage": {"output_tokens": 260}})
    lines += _sse("message_stop", {"type": "message_stop"})
    return lines


def _consume(lines):
    return lp.AnthropicProvider._consume_stream(_StreamResp(lines), 60.0)


# ── الحارسُ الفعليّ: هل الرسالةُ صالحةٌ لدورٍ تالٍ؟ ────────────────────────────

def _assert_replayable(content: list[dict]) -> None:
    """يُحاكي تحقّقَ الواجهة قبل إرسال الدور التالي.

    القاعدة المخروقة حيّاً: «each thinking block must contain thinking».
    كتلةُ تفكيرٍ بلا نصّ — أو بلا توقيع — تُرفَض بـ400 حين تُعاد."""
    for i, blk in enumerate(content):
        if blk.get("type") == "thinking":
            assert blk.get("thinking"), (
                f"content[{i}]: كتلةُ تفكيرٍ بنصٍّ فارغ — الواجهة ترفض الدورَ "
                "التالي بـ«each thinking block must contain thinking»")
            assert blk.get("signature"), (
                f"content[{i}]: كتلةُ تفكيرٍ بلا توقيع — التوقيعُ جزءٌ من "
                "الكتلة ويجب أن يُعاد حرفياً")
        elif blk.get("type") == "redacted_thinking":
            assert blk.get("data"), (
                f"content[{i}]: كتلةُ تفكيرٍ محجوبة بلا حمولة `data`")


def test_streamed_thinking_block_is_byte_valid_for_a_follow_up_request():
    """القفلُ الجذر: تفكيرٌ مبثوث + أداة ⇒ الرسالةُ صالحةٌ للإعادة.

    أحمرُ قبل الإصلاح: `thinking` فارغ و`signature` غائب."""
    data, abort = _consume(_thinking_then_tool_lines())
    assert abort is None, abort
    content = data["content"]

    _assert_replayable(content)

    think = next(b for b in content if b.get("type") == "thinking")
    assert think["thinking"] == "".join(THINK_PARTS), (
        f"نصُّ التفكير لم يُجمَّع حرفياً: {think.get('thinking')!r}")
    assert think["signature"] == "".join(SIG_PARTS), (
        f"التوقيع لم يُجمَّع حرفياً: {think.get('signature')!r}")


def test_thinking_block_keeps_its_position_and_does_not_touch_the_tool_block():
    """الترتيبُ والأداةُ سليمان — الإصلاحُ لا يُعيد ترتيبَ الكتل ولا يمسّ
    وسائطَ الأداة (كتلةُ التفكير تسبق الأداةَ في الدور المُعاد)."""
    data, abort = _consume(_thinking_then_tool_lines())
    assert abort is None, abort
    content = data["content"]
    assert [b.get("type") for b in content] == ["thinking", "tool_use"]
    tool = content[1]
    assert tool["name"] == "comtrade_imports"
    assert tool["id"] == "toolu_think_1"
    assert tool["input"] == {"hs": "080410"}
    assert data["stop_reason"] == "tool_use"


def test_redacted_thinking_block_survives_assembly_intact():
    """`redacted_thinking` تصل حمولتُها كاملةً في الافتتاح بلا دلتا — الحارس
    يمنع أن يُتلِفها إصلاحُ كتلة التفكير العادية (تنقيةٌ أو إعادةُ بناء)."""
    data, abort = _consume(_thinking_then_tool_lines(redacted=True))
    assert abort is None, abort
    content = data["content"]
    _assert_replayable(content)
    assert [b.get("type") for b in content] == ["redacted_thinking", "tool_use"]
    assert content[0]["data"] == "EncryptedBlobAAAA=="


def test_thinking_deltas_on_an_unopened_index_still_accumulate_as_thinking():
    """صلابةٌ: دلتا تفكيرٍ على فهرسٍ لم يصل افتتاحُه (وسيطٌ يبتلع حدثاً) لا
    تُقلَب كتلةَ نصّ — وإلا عاد النصُّ في `text` وضاع التوقيع صامتاً."""
    lines = _sse("message_start", {
        "type": "message_start",
        "message": {"id": "m", "role": "assistant", "content": [],
                    "usage": {"input_tokens": 5, "output_tokens": 1}}})
    lines += _sse("content_block_delta", {
        "type": "content_block_delta", "index": 0,
        "delta": {"type": "thinking_delta", "thinking": "فكرةٌ بلا افتتاح"}})
    lines += _sse("content_block_delta", {
        "type": "content_block_delta", "index": 0,
        "delta": {"type": "signature_delta", "signature": "SigXYZ=="}})
    lines += _sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    lines += _sse("message_delta", {
        "type": "message_delta", "delta": {"stop_reason": "end_turn"},
        "usage": {"output_tokens": 9}})
    lines += _sse("message_stop", {"type": "message_stop"})
    data, abort = _consume(lines)
    assert abort is None, abort
    blk = data["content"][0]
    assert blk["type"] == "thinking", (
        f"دلتا تفكيرٍ على فهرسٍ غير مفتوح صارت {blk.get('type')!r}")
    assert blk["thinking"] == "فكرةٌ بلا افتتاح"
    assert blk["signature"] == "SigXYZ=="


def test_the_lock_can_actually_fail():
    """الحارسُ يحمرّ فعلاً على الشكل المعطوب (قفلٌ يُثبِت نفسَه — الدرس ١١٥:
    الأخضرُ وحدَه لا يكفي)."""
    broken = [{"type": "thinking", "thinking": "", "signature": ""},
              {"type": "tool_use", "id": "t", "name": "x", "input": {}}]
    with pytest.raises(AssertionError, match="each thinking block"):
        _assert_replayable(broken)


# ── إعادةُ التشغيل: دورٌ مبتورٌ عند max_tokens يُعاد بلا توقيع ────────────────
#
# البلاغ الثاني (المالك، 2026-08-23): الكاتبُ يعمل عند ١٦–٣٢ ألف رمز، فالبترُ
# عند `max_tokens` حدثٌ **عاديّ** لا حالةٌ حدّية. وحين يُبتَر البثُّ **داخل**
# كتلةِ تفكير، لا يصل `signature_delta` ولا `content_block_stop`: تخرج الكتلةُ
# بنصٍّ صحيحٍ وبلا توقيع. ثم تُعيدها حلقةُ التشغيل حرفياً في النداء التالي
# (توجيهُ الإنهاء القسريّ · نتائجُ الأدوات · توجيهُ إصلاح JSON) فتُرفَض
# الرسالةُ كلُّها بنفس الـ400 — «each thinking block must contain thinking».

def _thinking_block(thinking="تحليلٌ طويلٌ بُتِر", signature=None):
    blk = {"type": "thinking", "thinking": thinking}
    if signature is not None:
        blk["signature"] = signature
    return blk


def _mission_ctx():
    from silk_market_resolver import resolve_market
    ref, _ = resolve_market("Nigeria")
    mission = {"key": "t", "name": "t", "allowed_tools": [], "instructions": "x"}
    ctx = {"market": ref, "product": "تمور", "hs_code": None,
           "extra_findings": [], "extra_context": ""}
    return mission, ctx, {"tool_calls": 4, "max_output_tokens": 16000}


def _replayed_thinking_blocks(sent_messages: list) -> list[dict]:
    """كلُّ كتلةِ تفكيرٍ أُعيدت إلى الواجهة في نداءٍ لاحق."""
    out = []
    for msg in sent_messages:
        if msg.get("role") != "assistant":
            continue
        for blk in (msg.get("content") or []):
            if isinstance(blk, dict) and blk.get("type") in (
                    "thinking", "redacted_thinking"):
                out.append(blk)
    return out


def _run_loop_capturing(responses: list):
    """يُشغّل الحلقة بردودٍ مُعدّة ويُعيد (النتيجة، لقطاتُ messages لكل نداء)."""
    import copy
    from unittest.mock import patch
    import silk_llm_runtime as rt

    seen: list[list] = []
    calls = {"n": 0}

    def _fake(system, messages, tools=None, **kw):
        seen.append(copy.deepcopy(messages))
        i = calls["n"]
        calls["n"] += 1
        return responses[i] if i < len(responses) else responses[-1]

    with _env(ANTHROPIC_API_KEY="test-key"), \
            patch("silk_llm_runtime._call_tools", side_effect=_fake):
        out = rt._run_loop(*_mission_ctx())
    return out, seen


def test_truncated_thinking_block_is_never_replayed_without_its_signature():
    """القفلُ الجذر للبلاغ الثاني.

    الدور ١: بترٌ عند `max_tokens` **داخل** كتلة التفكير ⇒ نصٌّ بلا توقيع،
    ولا كتلةَ نصٍّ نهائية ⇒ الحلقةُ تُرسِل توجيهَ الإنهاء القسريّ وتُعيد
    النداء. الدور ٢ يجب ألّا يحمل كتلةَ تفكيرٍ بلا توقيع.

    أحمرُ قبل الإصلاح: الكتلةُ تُعاد كما هي فتُرفَض بـ400."""
    truncated = {"content": [_thinking_block()], "stop_reason": "max_tokens"}
    final = {"content": [{"type": "text", "text": json.dumps(
        {"findings": [], "gaps": [], "summary": "تمّ"}, ensure_ascii=False)}],
        "stop_reason": "end_turn"}
    out, seen = _run_loop_capturing([truncated, final])

    assert len(seen) >= 2, (
        f"الحلقةُ لم تُعِد النداء — لا مسارَ إعادةٍ لِيُقاس ({len(seen)} نداء)")
    for blk in _replayed_thinking_blocks(seen[1]):
        if blk.get("type") == "thinking":
            assert blk.get("signature"), (
                "أُعيدت كتلةُ تفكيرٍ بلا توقيع إلى الواجهة — نفسُ الـ400 "
                f"«each thinking block must contain thinking»: {blk!r}")
    assert out is not None


def test_a_signed_thinking_block_is_still_replayed_unmodified():
    """الحدُّ الآخر: كتلةٌ **مكتملة** (نصّ + توقيع) تُعاد حرفياً — الإصلاحُ
    يُسقِط غيرَ الصالح فقط، ولا يُجرّد الدورَ من تفكيرٍ سليمٍ يشترط العقدُ
    إعادتَه كما وصل."""
    signed = _thinking_block(thinking="تفكيرٌ مكتمل", signature="SigOK==")
    first = {"content": [signed], "stop_reason": "max_tokens"}
    final = {"content": [{"type": "text", "text": json.dumps(
        {"findings": [], "gaps": [], "summary": "تمّ"}, ensure_ascii=False)}],
        "stop_reason": "end_turn"}
    _out, seen = _run_loop_capturing([first, final])
    replayed = [b for b in _replayed_thinking_blocks(seen[1])
                if b.get("type") == "thinking"]
    assert replayed == [{"type": "thinking", "thinking": "تفكيرٌ مكتمل",
                         "signature": "SigOK=="}], (
        f"كتلةُ تفكيرٍ سليمة لم تُعَد حرفياً: {replayed!r}")


def test_a_signed_thinking_block_with_omitted_display_text_is_still_replayed():
    """`display` الافتراضيّ على النماذج الحالية `"omitted"`: الكتلةُ تصل
    **مكتملةً وموقَّعةً بنصٍّ فارغ** — الواجهةُ لا تُرجِع سلسلةَ التفكير الخام.
    قياسُ النصّ بدل التوقيع كان يُسقِطها وهي سليمة، فينقطع تسلسلُ التفكير بين
    الجولات، ويضيع الدورُ كلُّه حين لا يحمل سواها.

    أحمرُ قبل الإصلاح: `not (thinking and signature)` يقصُر على النصّ الفارغ
    فلا يقرأ التوقيعَ أصلاً."""
    signed_empty = _thinking_block(thinking="", signature="SigOK==")
    first = {"content": [signed_empty], "stop_reason": "max_tokens"}
    final = {"content": [{"type": "text", "text": json.dumps(
        {"findings": [], "gaps": [], "summary": "تمّ"}, ensure_ascii=False)}],
        "stop_reason": "end_turn"}
    _out, seen = _run_loop_capturing([first, final])

    replayed = [b for b in _replayed_thinking_blocks(seen[1])
                if b.get("type") == "thinking"]
    assert replayed == [{"type": "thinking", "thinking": "",
                         "signature": "SigOK=="}], (
        "كتلةُ تفكيرٍ موقَّعة بنصٍّ فارغ أُسقِطت من الدور المُعاد — انقطع "
        f"تسلسلُ التفكير بين الجولات: {replayed!r}")

    assert any(m.get("role") == "assistant" for m in seen[1]), (
        "الدورُ كلُّه حُذِف من الرسائل لأنّ كتلتَه الوحيدة أُسقِطت خطأً")


def test_redacted_thinking_is_replayed_even_though_it_has_no_signature():
    """`redacted_thinking` لا تحمل توقيعاً أصلاً — حمولتُها `data`. إسقاطُها
    بحجّة «بلا توقيع» يُتلِف دوراً صالحاً."""
    red = {"type": "redacted_thinking", "data": "EncryptedBlobBBBB=="}
    first = {"content": [red], "stop_reason": "max_tokens"}
    final = {"content": [{"type": "text", "text": json.dumps(
        {"findings": [], "gaps": [], "summary": "تمّ"}, ensure_ascii=False)}],
        "stop_reason": "end_turn"}
    _out, seen = _run_loop_capturing([first, final])
    assert red in _replayed_thinking_blocks(seen[1]), (
        "كتلةُ تفكيرٍ محجوبة أُسقِطت خطأً من الدور المُعاد")
