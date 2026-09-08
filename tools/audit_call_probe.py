"""مِسبارُ استدعاءٍ للتدقيق — يُثبِت **مسار التشغيل الفعليّ**، لا وجود الوحدة.

> **أداةُ تدقيقٍ فقط.** تعيش تحت `tools/` ولا تستوردها أيّ وحدة إنتاج، ولا
> تستوردها الحزمةُ الهرمتية. الموجة A لا تغيّر شيفرةَ إنتاج — هذا الملفّ
> والاختبارُ المرافق له هما الاستثناء الوحيد المسموح (أداةُ قياسٍ لازمةٌ
> لإثبات النتائج).

**المشكلة التي يحلّها.** «الوحدة موجودة في الريبو» ليست نتيجةَ تدقيق. السؤال
الحقيقيّ: *هل تُنفَّذ فعلاً على مسار دراسة المصنع؟ بأيّ مدخلات؟ وهل يصل أثرُها
إلى المُخرَج أم تُهمَل صامتةً؟* المسحُ الساكن (`grep`) يجيب عن الأول فقط،
ويخطئ حين يكون الاستيراد داخل فرعٍ لا يُنفَّذ أبداً — وهو بالضبط نمطُ العطل
الذي نبحث عنه.

**كيف يعمل.** يرقّع نقاطَ الدخول المسمّاة بمُسجِّلٍ شفّاف (يستدعي الأصل ويعيد
قيمته حرفياً — لا يغيّر سلوكاً)، ثمّ يشغّل مسارَين حقيقيَّين كاملَين داخل
العملية عبر `TestClient`:

- `POST /research` — **مسارُ دراسة المصنع** (`engine_bridge.study_mode()=="deep"`
  يستدعي هذا الجسمَ نفسَه عبر `silk_research_gateway`).
- `POST /analyze` — مسارُ اللوحة، للمقارنة: ما يعمل هنا ولا يعمل هناك.

نداءاتُ كلود مُموَّهةٌ عند حدودها الثلاثة المعروفة (`silk_llm_runtime._call_tools`،
`silk_synthesis._call`، `silk_ai_judge._call`) بنفس نمط الحزمة الهرمتية، والشبكةُ
غيرُ مطلوبة. **ما يُقاس هو الشيفرة المُنفَّذة**، لا جودةُ ما يعيده النموذج.

Run:  python3 tools/audit_call_probe.py            # تقرير نصّي
      python3 tools/audit_call_probe.py --json     # JSON للتحليل
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import tempfile
import traceback
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── نقاط الدخول المرصودة ─────────────────────────────────────────────────
#
# كلٌّ منها «قلبُ» نظامٍ من الأنظمة التي أمر المالك بإثبات مسارها. الاسمُ
# `module:attr`؛ ودالّةٌ داخل صنفٍ تُكتب `module:Class.method`.
PROBE_TARGETS = [
    # محرّك القرار الحتمي (§23–§26)
    "silk_decision:decide",
    # بوابة الجودة (§37/§38) ونقاطها الحاجزة
    "silk_quality_gate:run_quality_gate",
    "silk_quality_gate:_check_language_consistency",
    "silk_quality_gate:_check_source_coverage",
    "silk_quality_gate:_check_intersection_insufficiency",
    # تغطية المصادر (§5/§6)
    "silk_source_coverage:compute_source_coverage",
    # المحرّك الاقتصادي (§9/§18/§19)
    "silk_economics:economics_view",
    "silk_economics:landed_cost",
    "silk_economics:hhi",
    "silk_economics:margin_waterfall",
    "silk_economics:reverse_solve_max_exw",
    "silk_economics:normalize_price",
    # التوليف والحكم
    "silk_synthesis:synthesize",
    # العرض القانوني والمصدِّرات
    "silk_render:build_view",
    "silk_render:_deep_research_view",
    # التتبّع (§41–§43)
    "silk_trace:append_event",
    # المصداقية/التناقضات (§8)
    "silk_plausibility:annotate",
    "silk_plausibility:check_magnitudes",
    # الطزاجة (§7)
    "silk_staleness:is_stale_fact",
    "silk_staleness:vintage_tier",
    # التنظيم (§20)
    "silk_requirements_agent:RequirementsAgent._execute",
    # الارتباط (§30) — لا يعمل إلا ببطاقة منتج
    "correlation:correlate",
    # سدّ الفجوات
    "silk_gap_recovery:recover",
    # المستخلص المتين لمخرجات النموذج (البند ٦)
    "silk_llm_runtime:_parse_output",
    # بوّابة تأكيد رمز HS (§12)
    "silk_hs_confirm:needs_confirmation",
    # المحلّل الشامل
    "silk_market_analyst:analyze",
]



class Recorder:
    """سجلٌّ شفّاف: ينادي الأصلَ ويعيد قيمتَه حرفياً، ويسجّل ما جرى."""

    def __init__(self, name: str, fn):
        self.name, self.fn = name, fn
        self.calls: list[dict] = []

    def __call__(self, *a, **kw):
        rec: dict = {"args": _brief(a), "kwargs": sorted(kw)}
        try:
            out = self.fn(*a, **kw)
        except BaseException as e:              # noqa: BLE001 — نسجّل ثمّ نُعيد الرفع
            rec["raised"] = type(e).__name__
            self.calls.append(rec)
            raise
        rec["returned"] = _brief((out,))[:1]
        self.calls.append(rec)
        return out


def _brief(vals) -> list:
    """وصفٌ مُقتضَب لقيمةٍ — نوعُها وحجمُها، بلا إغراقٍ ولا أسرار."""
    out = []
    for v in vals:
        if v is None:
            out.append("None")
        elif isinstance(v, (str, bytes)):
            out.append(f"{type(v).__name__}[{len(v)}]")
        elif isinstance(v, dict):
            out.append(f"dict{sorted(v)[:6]}")
        elif isinstance(v, (list, tuple)):
            out.append(f"{type(v).__name__}[{len(v)}]")
        elif isinstance(v, (int, float, bool)):
            out.append(repr(v))
        else:
            out.append(type(v).__name__)
    return out


def _resolve(target: str):
    """`module:attr` أو `module:Class.method` ⇒ (الحاوية، اسم السمة)."""
    mod_name, _, path = target.partition(":")
    mod = importlib.import_module(mod_name)
    holder, attr = mod, path
    if "." in path:
        cls_name, _, attr = path.partition(".")
        holder = getattr(mod, cls_name)
    return holder, attr


def _install(targets: list[str]) -> tuple[dict, list[tuple]]:
    """رقّع كلَّ هدفٍ بمُسجِّل — يعيد (السجلّات، ما يجب استرجاعه لاحقاً)."""
    recorders: dict[str, Recorder] = {}
    undo: list[tuple] = []
    for t in targets:
        try:
            holder, attr = _resolve(t)
            original = getattr(holder, attr)
        except (ImportError, AttributeError) as e:
            recorders[t] = Recorder(t, None)
            recorders[t].calls = []
            recorders[t].missing = f"{type(e).__name__}: {e}"   # type: ignore[attr-defined]
            continue
        r = Recorder(t, original)
        recorders[t] = r
        # **دالّةٌ لا كائن.** `Recorder` كائنٌ قابلٌ للنداء، وتعيينُه سمةً على
        # **صنف** لا يمرّ ببروتوكول الواصف، فلا يُمرَّر `self` ويرفع كلُّ نداءٍ
        # `TypeError`. مِسبارٌ يكسر ما يقيسه يُنتِج «نتائجَ» هي أثرُ الأداة —
        # وهذا بالضبط ما حدث لأوّل تشغيلة (وكيل المتطلّبات: ٦ نداءات، ٦ رفوع).
        # الغلافُ دالّةٌ حقيقية فيعمل الوصف طبيعياً على الأصناف والوحدات معاً.
        def _wrapper(*a, __r=r, **kw):
            return __r(*a, **kw)
        _wrapper.__name__ = getattr(original, "__name__", attr)
        _wrapper.__doc__ = getattr(original, "__doc__", None)
        _wrapper._audit_recorder = r          # type: ignore[attr-defined]
        setattr(holder, attr, _wrapper)
        undo.append((holder, attr, original))
    return recorders, undo


def _restore(undo: list[tuple]) -> None:
    for holder, attr, original in undo:
        setattr(holder, attr, original)


# ── تمويهُ حدود كلود الثلاثة (نفس نمط الحزمة الهرمتية) ────────────────────

def _fake_call_tools(system, messages, tools=None, max_tokens=1600,
                     model=None, timeout=None):
    return {"stop_reason": "end_turn",
            "content": [{"type": "text", "text": json.dumps(
                {"findings": [], "gaps": [], "summary": "ok"})}],
            "usage": {"input_tokens": 100, "output_tokens": 50}}


def _fake_call(system, user, max_tokens=1600, model=None, timeout=None):
    return json.dumps({"verdict": "WATCH", "confidence": 0.5,
                       "reasoning": "ok"})


def _fake_call_writer(system, user, max_tokens=1600, model=None, timeout=None):
    from silk_ai_judge import report_sections
    parts = []
    for i, title in enumerate(report_sections("ar"), 1):
        parts.append(f"## {i}. {title}\n\nنصُّ مِسبارٍ للتدقيق.\n")
    return "\n".join(parts)


# ── تشغيلتان حقيقيتان ────────────────────────────────────────────────────

def _run_one(path: str) -> dict:
    """شغّل مساراً واحداً داخل العملية وأعِد ملخّصه — لا خلطَ بين مسارين."""
    from fastapi.testclient import TestClient
    import api

    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    out: dict = {}
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "probe",
                                 "SILK_API_KEY": "secret"}), \
         patch("silk_llm_runtime._call_tools", side_effect=_fake_call_tools), \
         patch("silk_synthesis._call", side_effect=_fake_call), \
         patch("silk_ai_judge._call", side_effect=_fake_call_writer), \
         patch("silk_storage._db_path", return_value=db):
        client = TestClient(api.app)
        hdr = {"X-API-Key": "secret"}
        body = ({"product": "تمور", "market": "Netherlands",
                 "hs_code": "080410", "persist": True, "async_run": False}
                if path == "/research" else
                {"product": "تمور", "top_n": 2})
        try:
            r = client.post(path, headers=hdr, json=body)
            out["status"] = r.status_code
            if r.status_code == 200:
                out["body"] = r.json()
                out["keys"] = sorted(out["body"])[:14]
            else:
                out["error_text"] = r.text[:300]
        except Exception as e:                  # noqa: BLE001
            out["error"] = f"{type(e).__name__}: {e}"
            out["tb"] = traceback.format_exc()[-800:]
    return out


def probe(targets: list[str] | None = None) -> dict:
    """النتيجة الكاملة: مَن نُودِي على **أيّ مسار**، كم مرّة، وبأيّ مدخلات."""
    targets = list(targets or PROBE_TARGETS)
    report: dict = {"targets": {t: {} for t in targets}, "paths": {}}

    for label, path in (("research", "/research"), ("analyze", "/analyze")):
        recs, undo = _install(targets)
        try:
            run_out = _run_one(path)
        finally:
            _restore(undo)
        report["paths"][label] = {k: v for k, v in run_out.items()
                                  if k != "body"}
        report[f"_{label}_body"] = run_out.get("body") or {}
        for t in targets:
            r = recs[t]
            entry: dict = {"calls": len(r.calls)}
            if getattr(r, "missing", None):
                entry["missing"] = r.missing   # type: ignore[attr-defined]
            if r.calls:
                entry["first"] = r.calls[0]
                entry["raised"] = sum(1 for c in r.calls if "raised" in c)
            report["targets"][t][label] = entry

    # أثرُ الأنظمة في المُخرَج النهائي — لا «نُودِي» وحدها بل «وصل».
    body = report.get("_research_body") or {}
    view = (body.get("view") or {})
    dr = (view.get("deep_research") or {})
    report["effect_in_research_view"] = {
        "has_view": bool(view),
        "quality_gate_attached": "quality_gate" in dr,
        "quality_gate_verdict": (dr.get("quality_gate") or {}).get("verdict"),
        "gate_checks_run": len((dr.get("quality_gate") or {}).get("findings")
                               or []),
        "source_coverage_in_gate": _coverage_in(dr),
        "decision_block": "decision" in view or "decision" in dr,
        "economics_block": bool(view.get("economics") or dr.get("economics")),
        "tam_sam_som": _tam_keys(view, dr),
        "trace_id": dr.get("trace_id"),
        "report_language": view.get("report_language"),
        "view_top_keys": sorted(view)[:30],
        "dr_top_keys": sorted(dr)[:30],
    }
    ab = report.get("_analyze_body") or {}
    av = ab.get("view") or {}
    mk = (ab.get("markets") or [])
    report["effect_in_analyze_view"] = {
        "has_view": bool(av),
        "decision_on_markets": sum(1 for m in mk if "decision" in (m or {})),
        "markets": len(mk),
        "quality_gate_attached": "quality_gate" in av,
    }
    report.pop("_research_body", None)
    report.pop("_analyze_body", None)
    return report


def _coverage_in(dr: dict) -> object:
    gate = dr.get("quality_gate") or {}
    for f in (gate.get("findings") or []):
        if "coverage" in str(f.get("check", "")):
            return f.get("check")
    return list(gate.get("skipped_checks") or [])[:6] or False


def _tam_keys(view: dict, dr: dict) -> list:
    """أينما ذُكِرت TAM/SAM/SOM في العرض — مفاتيحُها لا نثرُها."""
    found = []
    for name, blob in (("view", view), ("deep_research", dr)):
        for k in (blob or {}):
            if str(k).lower() in ("tam", "sam", "som", "tam_sam_som",
                                  "market_sizing", "sizing"):
                found.append(f"{name}.{k}")
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="أخرِج JSON خاماً")
    args = ap.parse_args()

    out = probe()
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    print("═" * 72)
    print("مِسبارُ الاستدعاء — هل تُنفَّذ الأنظمة فعلاً على مسار الدراسة؟")
    print("═" * 72)
    for label in ("research", "analyze"):
        p = out["paths"][label]
        print(f"POST /{label:<9} → status={p.get('status')} "
              f"{p.get('error') or p.get('error_text') or ''}")
    print("-" * 72)
    print(f"{'/research':<14}{'/analyze':<14}الهدف")
    print("-" * 72)
    for t in out["targets"]:
        cells = []
        for label in ("research", "analyze"):
            e = out["targets"][t].get(label, {})
            if e.get("missing"):
                cells.append("؟ مفقود")
            elif e.get("calls"):
                extra = f"!{e['raised']}" if e.get("raised") else ""
                cells.append(f"✓ ×{e['calls']}{extra}")
            else:
                cells.append("✗ صفر")
        print(f"{cells[0]:<14}{cells[1]:<14}{t}")
        miss = (out["targets"][t].get("research", {}) or {}).get("missing")
        if miss:
            print(f"{'':<28}{miss}")
    print("-" * 72)
    print("أثرُ الأنظمة في مُخرَج /research:")
    for k, v in out["effect_in_research_view"].items():
        print(f"  {k}: {v}")
    print("أثرُها في مُخرَج /analyze:")
    for k, v in out["effect_in_analyze_view"].items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
