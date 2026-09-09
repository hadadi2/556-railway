"""Retain source indices instead of treating Google region scores as market shares."""
from dataclasses import fields, replace
import copy
import json
from silk_data_layer import DataPoint
from silk_evidence_contract import raw_snapshots

REGION_NOTE = ("اهتمام بحث نسبي من 0 إلى 100. القيمة 100 أعلى اهتمام نسبي "
               "بين المناطق المرصودة، وليست 100% من البحث أو المشترين. غياب "
               "منطقة أو ظهور صفر لا يثبت غياب الطلب أو البحث فيها.")


def normalized_reports(reports):
    result = dict(reports or {})
    allowed = {f.name for f in fields(DataPoint)}
    for name, report in result.items():
        if not hasattr(report, "findings"):
            continue
        findings, seen, changed = [], set(), False
        for dp in report.findings:
            rows = raw_snapshots([dp])
            regional = [r for r in rows if "google trends" in str(r.get("source", "")).lower()
                        and isinstance(r.get("value"), dict)
                        and "region" in r["value"] and "interest" in r["value"]]
            if not regional:
                findings.append(dp)
                continue
            # The source records preserve every cited fact, including any other
            # source mixed into the agent's interpretation. Do not edit numbers.
            changed = True
            for raw in rows:
                row = copy.deepcopy(raw)
                if raw in regional:
                    row["unit"] = "relative_search_interest_index_0_100"
                    row["note"] = REGION_NOTE
                key = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
                if key not in seen:
                    seen.add(key)
                    findings.append(DataPoint(**{k: v for k, v in row.items() if k in allowed}))
        if changed:
            result[name] = replace(report, findings=findings)
    return result
