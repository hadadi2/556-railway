#!/usr/bin/env python3
"""افحص أحدث نسخة احتياطية لكل مخزن — verify the latest backup of every store.

**لماذا (تدقيق 2026-08-27، البند ١٧).** الريبو كان يملك مسار **أخذ** النسخة
بلا أيّ فحصٍ لها ولا إجراء استرجاع موثَّق — أي أن أول مرّة تُختبَر فيها النسخة
كانت ستكون يوم الكارثة. نسخةٌ لم تُفتَح ولم يُفحَص تماسكها ليست شبكة أمان، هي
**افتراض** شبكة أمان.

**قراءة فقط بالكامل** (`mode=ro`): تفتح كل طبعة، تشغّل `PRAGMA integrity_check`،
وتعدّ صفوف الجداول الحرجة، وتطبع تاريخ الطبعة وحجمها. صفر كتابة على أيّ ملف —
لا على النسخة ولا على الإنتاج.

الاستعمال (من قشرة الخدمة على النشر، أو محلياً بعد نسخ مجلّد الطبعات):

    python3 tools/verify_backup.py
    python3 tools/verify_backup.py --dir /data/backups

يخرج بـ0 حين كل طبعةٍ موجودةٍ سليمة، وبـ1 حين تفشل واحدة أو حين لا توجد طبعات
أصلاً (غياب النسخ **فشلٌ معلَن** لا نجاحٌ صامت).

stdlib فقط عدا استيراد `silk_backup` لحلّ المجلّد الافتراضي — ويسقط لمسارٍ
صريح إن تعذّر، فيبقى قابلاً للتشغيل منسوخاً وحده.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import os
import sqlite3
import sys

# الجداول التي يعني عددُها شيئاً للمشغّل — «النسخة سليمة» وحدها لا تكفي:
# قاعدةٌ سليمةٌ **فارغة** تجتاز integrity_check وهي كارثة.
_CRITICAL_TABLES = {
    "silk": ("analyses",),
    "store": ("indicators", "trade_flows"),
    "usage": ("paid_usage",),
    "platform": ("accounts", "users", "studies"),
    "watchdog": ("watchdog_records",),
    "ops_errors": ("ops_errors",),
}


def _default_dir() -> str:
    try:
        import silk_backup
        return silk_backup.backup_dir()
    except Exception:  # noqa: BLE001 — أداةٌ مستقلّة: تعمل بمسارٍ صريح دائماً
        base = os.environ.get("SILK_BACKUP_DIR") or os.environ.get(
            "SILK_DATA_DIR") or "data"
        return os.path.join(base, "backups")


def _latest(dest: str, name: str) -> str | None:
    files = sorted(glob.glob(os.path.join(dest, f"{name}.*.db"))
                   + glob.glob(os.path.join(dest, f"{name}.*.tar")))
    return files[-1] if files else None


def _check(path: str, name: str) -> dict:
    """افحص طبعةً واحدة — integrity + عدّ الصفوف الحرجة. لا يرفع أبداً."""
    out: dict = {"name": name, "path": path, "ok": False,
                 "bytes": 0, "modified": "", "integrity": "", "rows": {},
                 "error": ""}
    try:
        out["bytes"] = os.path.getsize(path)
        out["modified"] = datetime.datetime.fromtimestamp(
            os.path.getmtime(path), datetime.timezone.utc).isoformat(
                timespec="seconds")
        if path.endswith(".tar"):
            # R5 (DB-9): أرشيفُ الصور المرفوعة — يُفتَح ويُعدّ أعضاؤه.
            import tarfile
            with tarfile.open(path, "r") as tar:
                out["rows"]["members"] = len(tar.getmembers())
            out["integrity"] = "ok"
            out["ok"] = True
            return out
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
        try:
            out["integrity"] = conn.execute(
                "PRAGMA integrity_check").fetchone()[0]
            for table in _CRITICAL_TABLES.get(name, ()):
                try:
                    out["rows"][table] = conn.execute(
                        f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                except sqlite3.Error as e:
                    out["rows"][table] = f"— ({e})"
        finally:
            conn.close()
        out["ok"] = out["integrity"] == "ok"
    except Exception as e:  # noqa: BLE001 — فشل طبعة = بند معلن لا انهيار
        out["error"] = str(e)[:300]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=None, help="مجلّد الطبعات (الافتراضي من البيئة)")
    args = ap.parse_args(argv)
    dest = args.dir or _default_dir()

    print(f"مجلّد الطبعات · backup dir: {dest}")
    if not os.path.isdir(dest):
        print("✗ المجلّد غير موجود — لا نسخ احتياطية إطلاقاً "
              "(اضبط SILK_BACKUP_HOURS أو نادِ GET /ops/backup).")
        return 1

    names = sorted({os.path.basename(f).split(".")[0]
                    for f in (glob.glob(os.path.join(dest, "*.db"))
                              + glob.glob(os.path.join(dest, "*.tar")))})
    if not names:
        print("✗ لا توجد أي طبعة في المجلّد — غيابُ النسخ فشلٌ معلَن لا نجاح.")
        return 1

    failures = 0
    for name in names:
        path = _latest(dest, name)
        if not path:
            continue
        r = _check(path, name)
        mark = "✓" if r["ok"] else "✗"
        rows = "، ".join(f"{k}={v}" for k, v in r["rows"].items()) or "—"
        print(f"{mark} {name:<12} {os.path.basename(r['path'])}  "
              f"{r['bytes'] / 1024:.0f}KB  {r['modified']}  "
              f"integrity={r['integrity'] or r['error']}  صفوف: {rows}")
        if not r["ok"]:
            failures += 1

    print()
    if failures:
        print(f"✗ {failures} طبعة فاسدة أو متعذّرة — لا تعتمد عليها؛ "
              "خذ نسخةً جديدة وافحصها قبل أن تحتاجها.")
        return 1
    print("✓ كل الطبعات المفحوصة سليمة. إجراء الاسترجاع في "
          "docs/DEPLOY_RAILWAY.md §٧ج.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
