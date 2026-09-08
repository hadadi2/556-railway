#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""قياسُ «قبل/بعد» على حدّ المنتج ← HS6 — before/after measurement harness.

يعمل على **الشجرتين**: يكتشف وجودَ `silk_hs_pipeline` فيقيس المسارَ الجديد،
وإلا يقيس السلوكَ القديم بالضبط كما كانت البوّابةُ تراه:

    الاعتمادُ التلقائي (قبل) = `resolve(name)` يعيد رمزاً وثقتُه ≥ العتبة
    الاعتمادُ التلقائي (بعد) = `classify(name)` يعيد `approved`

المخرَجُ JSON على stdout كي يُقارَن آلياً بين تشغيلين:

    git stash && python tools/hs_before_after.py > before.json && git stash pop
    python tools/hs_before_after.py > after.json

**التوقّعُ مشتقٌّ من المرجع** (`evals/hs_golden_set.csv`) لا مخترَع — راجع عمود
`evidence` هناك. صفر شبكة، صفر نداء نموذج، حتميّ تماماً.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


def _golden() -> list[dict]:
    p = os.path.join(_ROOT, "evals", "hs_golden_set.csv")
    with open(p, encoding="utf-8") as f:
        body = [ln for ln in f if not ln.lstrip().startswith("#")]
    return [r for r in csv.DictReader(body) if (r.get("product") or "").strip()]


def _decide(name: str):
    """(رمزٌ مُعتمَدٌ تلقائياً أو None، الثقة كما يراها الحارسُ الذي يحجب)."""
    try:
        import silk_hs_pipeline as P            # الشجرة الجديدة
        out = P.classify(name)
        code = (out["final_hs_code"]
                if out["classification_status"] == P.APPROVED else None)
        return code, out["confidence"], out["classification_status"]
    except ImportError:                          # الشجرة القديمة
        import silk_hs_confirm as C
        from silk_hs_resolver import resolve
        dp = resolve(name)
        ok = bool(dp.value) and dp.confidence >= C.min_confidence()
        return (dp.value if ok else None), dp.confidence, (
            "approved" if ok else "blocked")


def main() -> int:
    rows = _golden()
    auto_right = auto_wrong = refused_right = refused_wrong = 0
    none_confidence = 0
    wrong_cases: list[dict] = []
    t0 = time.perf_counter()
    for r in rows:
        name = r["product"]
        want = (r.get("expect_hs6") or "").strip() or None
        forbidden = [c for c in (r.get("forbidden_hs6") or "").split(";")
                     if c.strip()]
        code, conf, status = _decide(name)
        if conf is None:
            none_confidence += 1
        if code:
            # اعتمادٌ تلقائيّ: هل هو الرمزُ الذي يسنده المرجع؟
            if want and code == want:
                auto_right += 1
            else:
                auto_wrong += 1
                wrong_cases.append({"product": name, "got": code,
                                    "expected": want,
                                    "forbidden_hit": code in forbidden,
                                    "confidence": conf})
        else:
            (refused_right if want is None else refused_wrong).__int__()
            if want is None:
                refused_right += 1
            else:
                refused_wrong += 1
    elapsed = time.perf_counter() - t0

    total = len(rows)
    print(json.dumps({
        "tree": "after" if _has_pipeline() else "before",
        "cases": total,
        "auto_approved_correct": auto_right,
        "auto_approved_incorrect": auto_wrong,
        "false_positive_rate": round(auto_wrong / total, 4),
        "refused_correctly": refused_right,
        "refused_but_reference_supports_a_code": refused_wrong,
        "confirmation_rate": round((total - auto_right - auto_wrong) / total, 4),
        "confidence_is_none_count": none_confidence,
        "seconds_for_all_cases": round(elapsed, 2),
        "ms_per_case": round(elapsed / total * 1000, 1),
        "incorrect_auto_approvals": wrong_cases,
    }, ensure_ascii=False, indent=1))
    return 0


def _has_pipeline() -> bool:
    try:
        import silk_hs_pipeline  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
