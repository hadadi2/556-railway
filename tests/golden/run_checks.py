#!/usr/bin/env python3
"""أداة قياس الدراسات — study measurement runner (المرحلة ١، PR-A).

تشغّل فحوصات `silk_study_checks` (G0 + F1–F7) على أي دراسة وتطبع لكل فحص نجح أو
فشل مع السبب. قراءة فقط: صفر كتابة، صفر نموذج، صفر إنفاق.

المصادر (واحد منها):
    --case KEY              دراسة مرجعية مجمَّدة في tests/golden/fixtures/KEY
    --all                   كل الدراسات المرجعية (مع --baseline: مقارنة بخط الأساس)
    --analysis-id N         دراسة مخزَّنة: من قاعدة الخادم (SILK_DB أو SILK_DATA_DIR/silk.db،
                            للقراءة فقط — على Railway)، أو مع --remote عبر
                            SILK_BASE_URL + SILK_API_KEY (GET /report/refined و/evidence)
    --blob-file F.json      نتيجة نُزِّلت من GET /analyses/{id}
    --report-file F.md      نصّ تقرير (Markdown) + اختيارياً --evidence-file

خيارات: --meta F.json (hs_code، currency، fx_local_per_usd، vat_pct…)، --expected F.json
أو --expected-from KEY (قيم مرجعية لدراسة مرجعية — لإعادة توليد الدراسة نفسها)،
--fx / --vat للتجاوز، --json، --update-baseline.

رموز الخروج: 0 لا FAIL · 1 فحصٌ فشل · 2 خطأ مدخلات · 3 تراجعٌ عن خط الأساس.

    python3 tests/golden/run_checks.py --case study_001_bahrain_coffee
    python3 tests/golden/run_checks.py --all --baseline
    python3 tests/golden/run_checks.py --analysis-id 1 --remote --expected-from study_001_bahrain_coffee

Read-only runner for the deterministic study checks; exit 1 on any FAIL,
3 on a regression against tests/golden/baseline.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request

GOLDEN_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(GOLDEN_DIR, "fixtures")
BASELINE = os.path.join(GOLDEN_DIR, "baseline.json")
REPO = os.path.dirname(os.path.dirname(GOLDEN_DIR))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import silk_study_checks as C  # noqa: E402

_ICON = {C.PASS: "✓ نجح", C.WARN: "! تحذير", C.FAIL: "✗ فشل", C.SKIP: "– تُخطّي"}
_ORDER = {C.SKIP: 0, C.PASS: 1, C.WARN: 2, C.FAIL: 3}


class InputError(RuntimeError):
    pass


def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


#: الدراسات المقنَّنة (مموّهة بشكل دراساتٍ حقيقية، `tests/baseline/*.view.json`) — مرجعٌ
#: للإنذارات الكاذبة: حالة كل فحص عليها موسومة يدوياً في خط الأساس.
CODIFIED = os.path.join(REPO, "tests", "baseline")
CODIFIED_PREFIX = "codified/"


def cases() -> list:
    real = sorted(d for d in os.listdir(FIXTURES)
                  if os.path.isfile(os.path.join(FIXTURES, d, "report.md"))) \
        if os.path.isdir(FIXTURES) else []
    cod = sorted(CODIFIED_PREFIX + f[:-len(".view.json")] for f in os.listdir(CODIFIED)
                 if f.endswith(".view.json")) if os.path.isdir(CODIFIED) else []
    return real + cod


def _codified_doc(name: str) -> "C.StudyDoc":
    path = os.path.join(CODIFIED, f"{name}.view.json")
    if not os.path.isfile(path):
        raise InputError(f"لا دراسة مقنَّنة باسم {name}")
    view = _load_json(path)
    dr = view.get("deep_research") or {}
    found = {"view": view, "deep_research": dr, "hs_code": view.get("hs_code"),
             "market": dr.get("market") or {}, "product": view.get("product")}
    doc = C.StudyDoc.from_result(found)
    doc.meta = infer_meta(doc.evidence, doc.meta)
    return doc


def case_doc(key: str) -> "C.StudyDoc":
    if key.startswith(CODIFIED_PREFIX):
        return _codified_doc(key[len(CODIFIED_PREFIX):])
    d = os.path.join(FIXTURES, key)
    if not os.path.isfile(os.path.join(d, "report.md")):
        raise InputError(f"لا دراسة مرجعية باسم {key} في {FIXTURES}")
    ev = os.path.join(d, "evidence.txt")
    meta = os.path.join(d, "meta.json")
    exp = os.path.join(d, "expected.json")
    return C.StudyDoc(report=_read(os.path.join(d, "report.md")),
                      evidence=_read(ev) if os.path.isfile(ev) else "",
                      meta=_load_json(meta) if os.path.isfile(meta) else {},
                      expected=_load_json(exp) if os.path.isfile(exp) else {})


def _case_for_analysis(aid: int) -> "str | None":
    for k in cases():
        m = os.path.join(FIXTURES, k, "meta.json")
        if os.path.isfile(m) and _load_json(m).get("analysis_id") == aid:
            return k
    return None


_HEADER_RE = re.compile(r"\(HS\s*(\d{6})\)\s*—\s*السوق الأول:\s*([^—\n]+)")


def _market_locale() -> dict:
    """{الاسم/ISO3: (ISO3، العملة)} من data/market_locale.csv."""
    out: dict = {}
    path = os.path.join(REPO, "data", "market_locale.csv")
    try:
        with open(path, encoding="utf-8") as fh:
            for row in csv.reader(l for l in fh if not l.startswith("#")):
                if len(row) >= 6 and len(row[0]) == 3:
                    out[row[0].upper()] = (row[0].upper(), row[5].upper())
                    out[row[1].strip().lower()] = (row[0].upper(), row[5].upper())
    except OSError:
        pass
    return out


def infer_meta(evidence: str, base: "dict | None" = None) -> dict:
    """رمز HS والسوق من سطر رأس الأدلة، والعملة من مرجع locale — ما لا يُستنتج يبقى غائباً."""
    meta = dict(base or {})
    m = _HEADER_RE.search(evidence or "")
    if m:
        meta.setdefault("hs_code", m.group(1))
        meta.setdefault("market_ar", m.group(2).strip())
    try:
        from silk_market_resolver import resolve_market
        ref, _ = resolve_market(meta.get("market_ar") or meta.get("market_iso3") or "")
        if ref is not None:
            meta.setdefault("market_iso3", ref.iso3)
    except Exception:  # noqa: BLE001 — السوق غير المحلول = بلا عملة لا تخمين
        pass
    loc = _market_locale().get(str(meta.get("market_iso3") or "").upper())
    if loc:
        meta.setdefault("currency", loc[1])
    return meta


def _db_path() -> str:
    if os.environ.get("SILK_DB"):
        return os.environ["SILK_DB"]
    return os.path.join(os.environ.get("SILK_DATA_DIR", os.path.join(REPO, "data")), "silk.db")


def blob_from_db(aid: int, path: "str | None" = None) -> dict:
    path = path or _db_path()
    if not os.path.isfile(path):
        raise InputError(f"قاعدة التحاليل غير موجودة: {path} (اضبط SILK_DB أو SILK_DATA_DIR، أو استعمل --remote)")
    con = sqlite3.connect(f"file:{os.path.abspath(path)}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT json_blob FROM analyses WHERE id = ?", (aid,)).fetchone()
    finally:
        con.close()
    if not row:
        raise InputError(f"لا تحليل بالمعرّف {aid} في {path}")
    return json.loads(row[0])


def _get(base: str, key: str, path: str) -> dict:
    req = urllib.request.Request(base.rstrip("/") + path, headers={"X-API-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 — عنوان المشغّل
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise InputError(f"{path}: HTTP {e.code} {e.read()[:200]!r}") from None
    except (urllib.error.URLError, ValueError) as e:
        raise InputError(f"{path}: {e}") from None


def remote_doc(aid: int, meta: "dict | None" = None) -> "C.StudyDoc":
    """من الخادم: النتيجة كاملة (`GET /analyses/{id}`) فيُبنى النصّ المسلَّم والأدلة محلياً
    بالمسار نفسه للقاعدة؛ وإن تعذّرت فنصّ الكاتب (`/report/refined`) + سياق الأدلة
    (`/evidence`) بلا نسخة التقرير المضمَّنة فيه."""
    base = os.environ.get("SILK_BASE_URL", "").strip()
    key = os.environ.get("SILK_API_KEY", "").strip()
    if not base:
        raise InputError("SILK_BASE_URL غير مضبوط")
    try:
        found = _get(base, key, f"/analyses/{aid}")
        if isinstance(found, dict) and found.get("deep_research"):
            doc = C.StudyDoc.from_result(found, meta=meta)
            doc.meta = infer_meta(doc.evidence, doc.meta)
            return doc
    except InputError:
        pass
    rep = _get(base, key, f"/analyses/{aid}/report/refined").get("markdown") or ""
    ev = _get(base, key, f"/analyses/{aid}/evidence").get("context") or ""
    ev = C.strip_embedded_report(ev, rep)
    return C.StudyDoc(report=rep, evidence=ev, meta=infer_meta(ev, meta))


def build_doc(args) -> "tuple[str, C.StudyDoc]":
    meta = _load_json(args.meta) if args.meta else {}
    expected = _load_json(args.expected) if args.expected else {}
    label = ""
    if args.case:
        doc = case_doc(args.case)
        label = args.case
    elif args.analysis_id is not None:
        label = f"analysis {args.analysis_id}"
        if args.remote:
            doc = remote_doc(args.analysis_id, meta)
        else:
            found = blob_from_db(args.analysis_id)
            doc = C.StudyDoc.from_result(found, meta=meta)
            doc.meta = infer_meta(doc.evidence, doc.meta)
    elif args.blob_file:
        label = os.path.basename(args.blob_file)
        doc = C.StudyDoc.from_result(_load_json(args.blob_file), meta=meta)
        doc.meta = infer_meta(doc.evidence, doc.meta)
    elif args.report_file:
        label = os.path.basename(args.report_file)
        ev = _read(args.evidence_file) if args.evidence_file else ""
        doc = C.StudyDoc(report=_read(args.report_file), evidence=ev, meta=infer_meta(ev, meta))
    else:
        raise InputError("حدّد مصدراً: --case أو --all أو --analysis-id أو --blob-file أو --report-file")
    # القيم المرجعية والبيانات الوصفية لدراسةٍ مرجعية مطابقة (نفس المعرّف أو --expected-from)
    ref_key = args.expected_from or (_case_for_analysis(args.analysis_id)
                                     if args.analysis_id is not None and not args.case else None)
    if ref_key:
        ref = case_doc(ref_key)
        for k, v in ref.meta.items():
            if k not in ("analysis_id", "frozen_at", "frozen_from", "note_ar", "note_en"):
                doc.meta.setdefault(k, v)
        if not expected:
            expected = ref.expected
    if expected:
        doc.expected = expected
    if args.fx is not None:
        doc.meta["fx_local_per_usd"] = args.fx
    if args.vat is not None:
        doc.meta["vat_pct"] = args.vat
    if not doc.report.strip():
        raise InputError(f"{label}: لا نصّ تقرير")
    return label, doc


def render_text(label: str, findings: list) -> str:
    L = [f"الدراسة: {label}", f"النتيجة الكلية: {_ICON[C.overall(findings)]}", ""]
    for f in findings:
        L.append(f"[{f.check}] {f.title}: {_ICON[f.status]} — {f.note}")
        for it in f.items:
            if it.get("status") not in (C.FAIL, C.WARN):
                continue
            why = it.get("why") or ""
            where = it.get("where") or it.get("product") or it.get("indicator") or it.get("key") \
                or it.get("requirement") or it.get("hs_code") or ""
            txt = it.get("text") or it.get("row") or it.get("phrase") or ""
            L.append(f"    - {where}: {why}" + (f"\n      «{txt}»" if txt else ""))
    return "\n".join(L)


def _status_map(findings: list) -> dict:
    return {f.check: f.status for f in findings}


def compare_baseline(key: str, statuses: dict, baseline: dict) -> list:
    """قائمة التراجعات. نمط detect: الحالة مطابقة حرفياً (الفحص يبقى يمسك الخطأ المعروف
    ولا يبدأ يُخطئ في الصحيح). نمط quality: لا فحص يسوء (PASS < WARN < FAIL)."""
    b = baseline.get(key)
    if not b:
        return [f"{key}: لا خط أساس — شغّل --update-baseline"]
    mode = b.get("mode", "quality")
    out = []
    for check, want in (b.get("checks") or {}).items():
        got = statuses.get(check)
        if got is None:
            out.append(f"{key}/{check}: الفحص غائب")
        elif mode == "detect" and got != want:
            out.append(f"{key}/{check}: {want} ← {got} (نمط detect: يجب أن يبقى مطابقاً)")
        elif mode != "detect" and _ORDER[got] > _ORDER[want]:
            out.append(f"{key}/{check}: تراجع {want} ← {got}")
    return out


def main(argv: "list | None" = None) -> int:
    ap = argparse.ArgumentParser(description="Silk study checks (G0 + F1–F7) — read-only")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--case")
    src.add_argument("--all", action="store_true")
    src.add_argument("--analysis-id", type=int)
    src.add_argument("--blob-file")
    src.add_argument("--report-file")
    ap.add_argument("--evidence-file")
    ap.add_argument("--remote", action="store_true")
    ap.add_argument("--meta")
    ap.add_argument("--expected")
    ap.add_argument("--expected-from")
    ap.add_argument("--fx", type=float)
    ap.add_argument("--vat", type=float)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.all or args.update_baseline:
            keys = cases()
            baseline = _load_json(BASELINE) if os.path.isfile(BASELINE) else {}
            results, regressions, any_fail = {}, [], False
            for k in keys:
                findings = C.run_all(case_doc(k))
                results[k] = findings
                any_fail |= C.overall(findings) == C.FAIL
                if args.baseline:
                    regressions += compare_baseline(k, _status_map(findings), baseline)
            if args.update_baseline:
                for k, findings in results.items():
                    prev = baseline.get(k) or {}
                    baseline[k] = {"mode": prev.get("mode", "quality"),
                                   "checks": _status_map(findings)}
                with open(BASELINE, "w", encoding="utf-8") as fh:
                    json.dump(baseline, fh, ensure_ascii=False, indent=2)
                    fh.write("\n")
            if args.json:
                print(json.dumps({"cases": {k: C.summarize(v) for k, v in results.items()},
                                  "regressions": regressions}, ensure_ascii=False, indent=2))
            else:
                for k, findings in results.items():
                    print(render_text(k, findings))
                    print("-" * 60)
                if args.baseline:
                    print("خط الأساس: " + ("لا تراجع" if not regressions else "تراجع:\n- "
                                           + "\n- ".join(regressions)))
            if regressions:
                return 3
            # في وضع المقارنة: الدراسات المرجعية المعيبة عمداً (detect) تفشل بطبيعتها؛
            # الحكم هو خط الأساس لا FAIL الخام.
            return 0 if args.baseline or args.update_baseline else (1 if any_fail else 0)
        label, doc = build_doc(args)
    except InputError as e:
        print(f"خطأ مدخلات: {e}", file=sys.stderr)
        return 2
    findings = C.run_all(doc)
    if args.json:
        out = C.summarize(findings)
        out["study"] = label
        out["meta"] = doc.meta
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    else:
        print(render_text(label, findings))
    return 1 if C.overall(findings) == C.FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
