"""مسحُ التقارير المخزَّنة بحثاً عن الرقم المختلَق (الدرس ٢٩٥) — قراءةٌ فقط.

قبل الإصلاح كان الملءُ يقطع الجملة عند النقطة العشرية، فإن غاب معطى الرمز
استُبدلت الجملةُ الأولى وبقي ذيلُ الرقم: «… غير متاح.4 مليون دولار». النصُّ
المخزَّن خامٌ برموزه (الملءُ عند العرض)، فيُعاد هنا ملؤه **بالقاعدة القديمة**
على سجلّه الحاليّ، ويُسرَد كلُّ تقريرٍ خرج منه ذيلُ رقمٍ بلا أصل.

    python3 tools/scan_fabricated_decimals.py            # المسار الافتراضي
    python3 tools/scan_fabricated_decimals.py /data/silk.db

يفتح القاعدة للقراءة فقط (`mode=ro`) ولا يكتب حرفاً.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: قاعدةُ القطع القديمة (قبل الدرس ٢٩٥) — تقطع بعد كل نقطة ولو تلاها رقم.
_OLD_SPLIT = re.compile(r"(?<=[.؛!؟])")
#: إمضاءُ الحادثة: جزءٌ يبدأ برقمٍ مباشرةً بعد نقطةٍ ألصقتها جملةٌ قبله.
_TAIL = re.compile(r"^[0-9٠-٩]")


def _suspects(text: str, entries: dict) -> list:
    import silk_fact_ledger as L
    hits = []
    for line in text.split("\n"):
        if "{{" not in line or line.lstrip().startswith("|"):
            continue
        parts = _OLD_SPLIT.split(line)
        for i, part in enumerate(parts[:-1]):
            gone = False
            for m in L.TOKEN_RE.finditer(part):
                e = entries.get(m.group(2))
                if (e is not None and not m.group(1) and not m.group(3)
                        and e["status"] == L.MISSING
                        and m.group(2) not in L._SELF_DESCRIBING_KEYS):
                    gone = True
            if gone and part.rstrip().endswith(".") and _TAIL.match(parts[i + 1]):
                hits.append((part.strip() + parts[i + 1].split(".")[0])[:200])
    return hits


def main(path: str) -> int:
    import silk_fact_ledger as L
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = conn.execute("SELECT id, product, created_at, json_blob FROM analyses "
                        "ORDER BY id").fetchall()
    scanned = found = 0
    for aid, product, created, blob in rows:
        try:
            result = json.loads(blob or "{}")
        except ValueError:
            continue
        text = ((result.get("deep_research") or {}).get("report") or {}).get("text")
        if not text or "{{" not in text:
            continue
        scanned += 1
        try:
            entries = L.build_ledger(result).get("entries") or {}
        except Exception as exc:  # noqa: BLE001 — تقريرٌ لا يُبنى سجلّه يُذكَر
            print(f"#{aid}: تعذّر بناء السجلّ ({type(exc).__name__}) — افحصه يدوياً")
            continue
        for h in _suspects(text, entries):
            found += 1
            print(f"#{aid} ({product}, {created}): {h}")
    print(f"— فُحص {scanned} تقريراً برموز سجلّ؛ حالاتٌ مشتبهة: {found}")
    return 1 if found else 0


if __name__ == "__main__":
    import silk_storage
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else silk_storage._db_path()))
