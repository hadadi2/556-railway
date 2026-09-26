#!/usr/bin/env python3
"""دخانُ PDF داخل صورة النشر — PDF smoke test inside the deploy image (البند ٢٨٤).

فحوصُ PDF في CI كانت تعمل على LibreOffice مشغّل Ubuntu، بينما الإنتاجُ يشغّل
LibreOffice الخاصّ بـDebian في `python:3.11-slim` مع خطّ IBM Plex — ووظيفةُ
`docker-health` كانت تضرب `/health` فقط. فرفضٌ يقع على مكتبة الإنتاج وخطّه
(البلاغ: «توليد ملف PDF معطَّل على الخادم») لا يراه CI أبداً.

يُشغَّل داخل الحاوية المبنيّة:
    docker exec silk-ci python tools/pdf_smoke.py
يحوّل دراساتٍ عربيةً حقيقيةَ الشكل (مدوّنات `tools/canonical_*`، لا بيانات حيّة
ولا شبكة ولا مفاتيح) عبر دوالّ الإنتاج نفسِها (docx ⇐ LibreOffice ⇐ فحص الأقواس)،
ويطبع نسخةَ LibreOffice وحضورَ الخطّ الرسميّ. يخرج بـ1 على أيّ فشل.
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# (المدوّنة، الدالة، نوعُ التقرير) — اختيرت لأنها رُفِضت على المقياس القديم:
# صفُّ «أقصى خسارة» في خليّتَي جدول، وأقواسُ فقرةٍ ملفوفة، وعرضُ /analyze الكلاسيكي.
CASES = (
    ("canonical_india_honey", "india_honey_research_blob", "client"),
    ("canonical_morocco_juice", "morocco_juice_research_blob", "client"),
    ("canonical_dza_peanut_butter", "dza_research_blob", "research"),
    ("canonical_netherlands", "netherlands_research_blob", "client"),
)


def _lo_version(soffice: str) -> str:
    try:
        out = subprocess.run([soffice, "--version"], capture_output=True,
                             text=True, timeout=60)
        return (out.stdout or out.stderr).strip() or "?"
    except Exception as e:  # noqa: BLE001 — تشخيصيّ
        return f"? ({type(e).__name__})"


def main() -> int:
    import silk_render
    import silk_reports
    soffice = silk_reports._find_soffice()  # noqa: SLF001
    print("soffice:", soffice or "MISSING")
    if not soffice:
        return 1
    print("LibreOffice:", _lo_version(soffice))
    print("IBM Plex Sans Arabic:", silk_reports.has_plex_arabic_font())
    try:
        import fitz  # noqa: F401 — pymupdf تبعيةُ إنتاج؛ بلاها لا يقع فحصُ الأقواس
    except ImportError:
        print("pymupdf: MISSING — the bracket gate would be skipped in production")
        return 1
    import shutil
    failed = 0
    for module, fn, kind in CASES:
        view = silk_render.build_view(getattr(importlib.import_module(module), fn)())
        render = (silk_reports.render_client_pdf if kind == "client"
                  else silk_reports.render_research_pdf)
        td = tempfile.mkdtemp(prefix="silk_smoke_")
        try:
            # البوّابةُ تعمل داخل `render` نفسِها — نجاحُه هو الحكم؛ العدُّ للسجلّ فقط.
            out = render(view, os.path.join(td, "r.pdf"))
            print(f"OK   {module}:{kind} {os.path.getsize(out)}B brackets "
                  f"(ok, inverted, skipped)={silk_reports.bracket_orientation_counts(out)}")
        except Exception as e:  # noqa: BLE001 — كلُّ فشلٍ يُطبَع ثمّ يُحسَب
            failed += 1
            code = silk_reports.pdf_error_detail(e)["error"]
            print(f"FAIL {module}:{kind} {code}: {type(e).__name__}: {e}")
        finally:
            shutil.rmtree(td, ignore_errors=True)
    print(f"{len(CASES) - failed}/{len(CASES)} PDFs produced")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
