#!/usr/bin/env python3
"""فحص دخان بعد النشر — post-deploy live smoke check (PART A5، أمر العمل الرئيس).

الاختبارات الهرمتية تثبت العقود لكنها **لا تلتقط فروق بيئة النشر** (تبعية
حاضرة محلياً غائبة على Railway، متغيّر تخزين غير مضبوط، مسار تصدير يرفع 501
حياً وحده). هذا السكربت يضرب النشر الحيّ فعلياً — نفس عائلة أخطاء 501 التي
تكرّرت ثلاث مرّات لا يمكن أن تُشحَن بصمت بعده:

  1. GET /health  → 200، ويطبع data_dir/persist_guard/research_ready.
  2. GET /analyses → أحدث تحليل مكتمل (إن وُجد).
  3. GET /analyses/{id}/report.md   → 200 + جسم غير فارغ.
  4. GET /analyses/{id}/report.docx → 200 + توقيع ZIP (‏docx = zip) + يُفتَح
     عبر python-docx إن كانت مثبّتة.
  5. GET /analyses/{id}/report.pdf  → 200 + توقيع %PDF (§3، أمر العمل الرئيس):
     يُثبِت أن محرّك التحويل (LibreOffice) يعمل حياً — لا يُكتشَف هرمتياً.
     503 هنا = محرّك التحويل غائب على النشر (فشل صريح لا صمت).
  6. **مسار /analyze الحيّ (Guardrail 1، LESSONS ٣١):** POST /analyze (مسح سريع
     مجانيّ، persist=true) → analysis_id حقيقيّ → GET /analyses/{id} ينجح →
     نفس فحوص التصدير الثلاثة عليه → يظهر في «بحوثي السابقة». هذا الخطُّ لم
     يُدخَّن حيًّا قط (Commands #1-6 غطّت /research حصرًا) فكتب لقرصٍ فانٍ أعاد
     المعرّف «1» ثم 404 — الآن يُثبَت حيًّا مثل /research تمامًا.
  7. **بوّابة تأكيد HS الحيّة (LESSONS ٣٥، تقرير الكويت):** المنتج الافتراضي
     لهذه الخطوة («زبدة الفول السوداني») هو **بعينه** منتج الحادثة الحية —
     يُرسَل أولاً **بلا** `hs_confirmed` فيجب أن يُرفَض ٤٢٢
     `hs_confirmation_needed` حياً (إثباتٌ حيّ أن البوّابة فشل-آمنة على
     النشر الفعلي، لا الاختبار الهرمتي فقط)، ثم يُعاد بـ`hs_confirmed=true`
     لإتمام فحوص الحفظ/التصدير المعتادة. أيّ إعادة ضبط `SILK_HS_CONFIRM_GATE=0`
     على النشر تُسقِط هذا الفحص بصمت — فيُعلَن ذلك صراحةً لا يُخفى.
  8. **بوّابة المصانع (R0، تدقيق 2026-09-01/CI-6) — اختيارية وللقراءة فقط:**
     مع `SILK_SMOKE_EMAIL/SILK_SMOKE_PASSWORD` (أو `--platform-email/
     --platform-password`): دخول → `GET /platform/me` (نفس البريد) →
     `GET /platform/studies` → `GET …/report` (عرض التقرير) لأحدث دراسة
     مكتملة. لا إطلاق ولا حذف ولا تعديل — الكتابة الوحيدة هي الدخول. بلا
     الاعتماد يُعلَن المسار «متخطّى» (ليس نجاحاً)؛ نصفُ اعتماد = خطأ ضبط
     صريح. كانت المنصّة كلّها خارج فحص الدخان: نشرٌ يُقلِع المحرّك ويُسقط
     بوّابة المصانع كان يمرّ «أخضر».

الاستعمال:
    python3 tools/post_deploy_smoke.py https://<railway-host>  [--key SILK_API_KEY]
                                        [--analyze-product "اسم منتج"]
                                        [--skip-analyze]
                                        [--platform-email E --platform-password P]
    (`--key` يقرأ `SILK_LIVE_API_KEY` من البيئة افتراضاً — لا مفتاح يعبر argv.)

يخرج برمز 0 عند نجاح كل ما هو قابل للفحص، و1 عند أوّل فشل صريح (مع سبب).
لا يختلق نجاحاً: تحليل غير موجود = فحص تصدير «متخطّى» معلَن لا «ناجح».
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.request
import urllib.error


def _get(base: str, path: str, key: str | None, raw: bool = False):
    req = urllib.request.Request(base.rstrip("/") + path)
    if key:
        req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001 — فشل شبكة = فحص فاشل صريح
        return None, str(e).encode()


def _post(base: str, path: str, payload: dict, key: str | None,
          timeout: int = 180):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + path, data=data,
                                 method="POST")
    req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("X-API-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # noqa: BLE001
        return None, str(e).encode()


def _platform_req(base: str, path: str, token: str | None = None,
                  method: str = "GET", payload: dict | None = None,
                  timeout: int = 60):
    """نداء بوّابة المصانع — Bearer لا X-API-Key. يعيد (status|None, body, headers)."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=data,
                                 method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers or {})
    except Exception as e:  # noqa: BLE001 — فشل شبكة = فحص فاشل صريح
        return None, str(e).encode(), {}


def _check_exports(base: str, aid: int, key: str | None,
                   fails: list[str]) -> None:
    """فحوص التصدير الثلاثة لمعرّفٍ محفوظ — md/docx/pdf. تُلحِق أي فشل صريح
    بـ`fails` (لا تختلق نجاحًا). 404 هنا = التحليل غير موجود (جذر LESSONS ٣١)."""
    # report.md
    st, body = _get(base, f"/analyses/{aid}/report.md", key)
    if st != 200 or not (body or b"").strip():
        fails.append(f"report.md id={aid}: HTTP {st}, حجم={len(body or b'')}")
    else:
        print(f"  ✓ report.md 200 — {len(body)} بايت")

    # report.docx — عائلة 501: هنا يُلتقَط الفشل الحيّ.
    # مراجعة شيفرة PR #147: بوابة الجودة صارت **شرط تسليم** — 409 بجسم
    # quality_gate_fail على قالب العميل نتيجةٌ مشروعة (حجب تسليم متعمَّد)
    # لا عطل نشر؛ عندها تُفحَص آلية التصدير نفسها عبر النسخة الداخلية
    # (?internal=1) التي لا تمرّ بالبوابة. أي حالة أخرى غير 200 تبقى فشلاً.
    st, body = _get(base, f"/analyses/{aid}/report.docx", key)
    if st == 409 and b"quality_gate_fail" in (body or b""):
        print(f"  ~ report.docx 409 — بوابة الجودة حجبت تسليم العميل "
              "(سلوك مقصود)؛ نفحص الآلية عبر النسخة الداخلية")
        st, body = _get(base, f"/analyses/{aid}/report.docx?internal=1", key)
    if st != 200:
        fails.append(f"report.docx id={aid}: HTTP {st} — {(body or b'')[:200]!r}")
    elif not (body[:2] == b"PK"):     # docx = حاوية ZIP
        fails.append(f"report.docx id={aid}: 200 لكن ليس ملف ZIP/docx صالحاً")
    else:
        opened = "غير مفحوص (python-docx غير مثبّتة محلياً)"
        try:
            import docx  # noqa: F401
            from docx import Document
            Document(io.BytesIO(body))
            opened = "يُفتَح عبر python-docx"
        except ImportError:
            pass
        except Exception as e:  # noqa: BLE001
            fails.append(f"report.docx id={aid}: 200 لكن python-docx فشل فتحه: {e}")
            opened = "فشل الفتح"
        print(f"  ✓ report.docx 200 — {len(body)} بايت، {opened}")

    # report.pdf — §3: المُسلَّم النهائي؛ يُثبِت أن soffice يعمل حياً.
    # نفس معاملة 409 البوابة (حجب مقصود => النسخة الداخلية تثبت الآلية).
    st, body = _get(base, f"/analyses/{aid}/report.pdf", key)
    if st == 409 and b"quality_gate_fail" in (body or b""):
        print(f"  ~ report.pdf 409 — بوابة الجودة حجبت تسليم العميل "
              "(سلوك مقصود)؛ نفحص الآلية عبر النسخة الداخلية")
        st, body = _get(base, f"/analyses/{aid}/report.pdf?internal=1", key)
    if st != 200:
        fails.append(f"report.pdf id={aid}: HTTP {st} — {(body or b'')[:200]!r} "
                     "(503 = محرّك تحويل PDF غائب على النشر)")
    elif not ((body or b"")[:5] == b"%PDF-"):
        fails.append(f"report.pdf id={aid}: 200 لكن ليس ملف PDF صالحاً")
    else:
        print(f"  ✓ report.pdf 200 — {len(body)} بايت، توقيع %PDF")


def _json_dict(body) -> dict | None:
    """JSON قاموسيّ أو None — قائمة/نصّ/جسم فاسد = فشل معلَن لدى المنادي لا تتبّع."""
    try:
        data = json.loads(body or b"")
    except Exception:  # noqa: BLE001 — الشكل غير المتوقَّع فشلٌ مسمّى لا استثناء
        return None
    return data if isinstance(data, dict) else None


def _check_platform(base: str, email: str, password: str,
                    fails: list[str]) -> str:
    """مسار بوّابة المصانع — للقراءة فقط، اختياريّ بالاعتماد (R0/CI-6).

    بلا بريد **وبلا** كلمة ⇒ «متخطّاة» معلَنة (لا نجاح مُدَّعى ولا فشل). نصفُ
    اعتماد (أحدهما فقط) ⇒ خطأ ضبط صريح — لا تخطٍّ صامت يبقي الوظيفة خضراء بلا
    فحص (مراجعة §58). معهما: دخول → `/platform/me` (نفس البريد) →
    `/platform/studies` → `GET …/report` (عرض التقرير JSON) لأحدث دراسة مكتملة
    (أعلى معرّف). لا إطلاق ولا حذف ولا تعديل — الكتابة الوحيدة هي الدخول.

    لماذا `GET …/report` لا `HEAD …/report.pdf`: FastAPI لا يضيف HEAD لمسار
    `@app.get` (405 حيّاً)، وتقرير PDF يشغّل LibreOffice ويستهلك خانق
    `pdf|<account>` (١٠/٣٠٠ث) — عرض التقرير يمرّ بنفس مسار المستأجر والبوّابة
    بلا كلفة. 409 من بوّابة التسليم/«لا تقرير بعد» سلوكٌ مقصود لا عطل نشر
    (نفس معاملة `_check_exports`).

    يعيد "skipped" | "ok" | "failed" ويُلحِق أسباب الفشل بـ`fails` بالنصّ (لا
    يختلق نجاحاً: حسابٌ بلا دراسة مكتملة = فحص التقرير متخطّى معلَناً بدوره).
    """
    email = (email or "").strip().lower()
    password = password or ""
    if not email and not password:
        print("⊘ بوّابة المصانع متخطّاة — اضبط SILK_SMOKE_EMAIL/SILK_SMOKE_PASSWORD "
              "(أو --platform-email/--platform-password) لتشغيل هذا المسار")
        return "skipped"
    if bool(email) != bool(password):
        fails.append("platform lane: SILK_SMOKE_EMAIL/SILK_SMOKE_PASSWORD نصفُ "
                     "مضبوطَين — اضبطهما معاً أو أزلهما معاً (نصفُ اعتمادٍ ليس "
                     "تخطّياً)")
        return "failed"
    st, body, _h = _platform_req(base, "/platform/auth/login", method="POST",
                                 payload={"email": email, "password": password})
    token = ((_json_dict(body) or {}).get("token") if st == 200 else None)
    if not token or not isinstance(token, str):
        fails.append(f"platform login: HTTP {st} — {(body or b'')[:160]!r}")
        return "failed"
    print("✓ POST /platform/auth/login 200 — رمز جلسة")

    st, body, _h = _platform_req(base, "/platform/me", token)
    me = _json_dict(body) if st == 200 else None
    if me is None or str(me.get("email") or "").strip().lower() != email:
        fails.append(f"GET /platform/me: HTTP {st}, "
                     f"email={(me or {}).get('email')!r} (متوقَّع {email})")
        return "failed"
    role = me.get("role")
    print(f"  ✓ GET /platform/me 200 — {me.get('email')} ({role})")

    st, body, _h = _platform_req(base, "/platform/studies", token)
    data = _json_dict(body) if st == 200 else None
    rows = data.get("studies") if data is not None else None
    if not isinstance(rows, list):
        fails.append(f"GET /platform/studies: HTTP {st} (شكل الردّ غير متوقَّع)")
        return "failed"
    print(f"  ✓ GET /platform/studies 200 — {len(rows)} دراسة")
    done = [r for r in rows
            if isinstance(r, dict) and r.get("state") == "completed"
            and r.get("analysis_id") and isinstance(r.get("id"), int)]
    if not done:
        print(f"  ⊘ لا دراسة مكتملة مرئية لهذا الحساب (role={role}, "
              f"studies={len(rows)}) — فحص التقرير متخطّى (ليس نجاحاً)")
        return "ok"
    sid = max(r["id"] for r in done)
    st, body, _h = _platform_req(base, f"/platform/studies/{sid}/report",
                                 token, timeout=180)
    data = _json_dict(body)
    if st == 409:
        detail = (data or {}).get("detail")
        code = detail.get("error") if isinstance(detail, dict) else detail
        if code in ("quality_gate_fail", "no_report_yet"):
            print(f"  ~ GET /platform/studies/{sid}/report 409 {code} — حجبٌ "
                  "مقصود (بوّابة التسليم / لا تقرير بعد)، ليس عطل نشر")
            return "ok"
    if st != 200 or data is None or not isinstance(data.get("view"), dict):
        fails.append(f"GET /platform/studies/{sid}/report: HTTP {st} — "
                     f"{(body or b'')[:160]!r}")
        return "failed"
    print(f"  ✓ GET /platform/studies/{sid}/report 200 — عرض التقرير يُبنى "
          f"(دراسة #{sid})")
    return "ok"


def _finish(fails: list[str]) -> int:
    """اطبع أسباب الفشل (إن وُجدت) وأعِد رمز الخروج — كل مخرجٍ يمرّ من هنا.

    مراجعة §58 (R0): مخرجان مبكّران (`/analyses` غير 200، لا تحليل مكتمل) كانا
    يعيدان 1 **بلا طباعة** أسباب مسار بوّابة المصانع المُلحَقة قبلهما — خروجٌ
    أحمر بلا سبب معلَن.
    """
    if fails:
        print("\n✗ فشل فحص الدخان:")
        for f in fails:
            print("  -", f)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    """المعامِلات — الافتراضات تُقرأ من البيئة وقت البناء (أسرار CI لا argv)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("base", help="live base URL, e.g. https://x.up.railway.app")
    ap.add_argument("--key", default=os.environ.get("SILK_LIVE_API_KEY") or None,
                    help="X-API-Key if auth is enabled (default: $SILK_LIVE_API_KEY)")
    ap.add_argument("--analyze-product", default="زبدة الفول السوداني",
                    help="اسم منتج المسح السريع الحيّ (خطوة /analyze)")
    ap.add_argument("--skip-analyze", action="store_true",
                    help="تخطَّ خطوة /analyze الحيّة (مثلاً بيئة بلا شبكة مصادر)")
    ap.add_argument("--platform-email",
                    default=os.environ.get("SILK_SMOKE_EMAIL", ""),
                    help="بريد حساب مصنع لمسار بوّابة المصانع (default: $SILK_SMOKE_EMAIL)")
    ap.add_argument("--platform-password",
                    default=os.environ.get("SILK_SMOKE_PASSWORD", ""),
                    help="كلمة مرور الحساب (default: $SILK_SMOKE_PASSWORD)")
    return ap


def main() -> int:
    args = _build_parser().parse_args()
    base, key = args.base, args.key
    fails: list[str] = []

    # 1) /health
    st, body = _get(base, "/health", key)
    if st != 200:
        print(f"✗ /health: HTTP {st}")
        return 1
    health = json.loads(body)
    storage = health.get("storage") or {}
    print(f"✓ /health 200 — data_dir={storage.get('data_dir')} "
          f"persist_guard={storage.get('persist_guard')} "
          f"research_ready={health.get('research_ready')}")
    if "storage" not in health and not key:
        # R7 (AUTH-18): حقولُ التشغيل مخفيّة بلا مفتاح — hidden، لا غائبة؛ مرّر --key لفحصها.
        print("• storage/version hidden without --key (R7 AUTH-18) — pass --key to verify the volume")
    elif not storage.get("data_dir"):
        fails.append("storage.data_dir فارغ — التخزين فانٍ (لا وحدة تخزين)")
    if health.get("warnings"):
        print("  ⚠ warnings:", "; ".join(health["warnings"]))
    # اللائحة ٤٣ (بلاغ حي متكرّر — رمز HS خاطئ رغم إصلاح المُصنِّف العام):
    # الصمّام فشل-آمن مفعَّل افتراضياً الآن، لكن ضبطٌ صريحٌ سابقٌ على النشر
    # (SILK_HS_CLASSIFIER=0) يبقى ممكناً ويُسقِط الإصلاح صامتاً إن لم يُفحَص
    # هنا — نفس منطق فحص بوّابة HS الحيّة أدناه، لا افتراض أن الكود يكفي.
    hsc = health.get("hs_classifier") or {}
    print(f"  hs_classifier.enabled={hsc.get('enabled')}")
    if hsc.get("enabled") is False:
        fails.append(
            "hs_classifier.enabled=False — SILK_HS_CLASSIFIER مُعطَّل صراحةً "
            "على هذا النشر؛ المُصنِّف العام لن يستدعي كلود فيعود للرمز "
            "الخاطئ (بلاغ «زبدة الفول السوداني»). أزِل هذا المتغيّر أو "
            "اضبطه على قيمةٍ غير 0/false/no/off")

    # 8) بوّابة المصانع (R0) — قبل فحوص المحرّك: نشرٌ بلا تحليل مكتمل بعد يخرج
    #    مبكّراً أدناه، ولا يجوز أن يُسقِط ذلك فحص المنصّة معه.
    _check_platform(base, args.platform_email, args.platform_password, fails)

    # 2) أحدث تحليل مكتمل
    st, body = _get(base, "/analyses", key)
    if st != 200:
        print(f"✗ /analyses: HTTP {st} — {body[:200]!r}")
        fails.append(f"GET /analyses: HTTP {st}")
        return _finish(fails)
    rows = json.loads(body)
    completed = [r for r in rows if r.get("status") in (None, "completed")]
    if not completed:
        print("⊘ لا تحليل مكتمل بعد — فحص التصدير متخطّى (ليس نجاحاً ولا فشلاً)")
        return _finish(fails)
    aid = completed[0]["id"]
    print(f"✓ /analyses 200 — أحدث تحليل مكتمل id={aid}")

    # 3-5) تصديرات أحدث تحليل مكتمل (قد يكون /research)
    _check_exports(base, aid, key, fails)

    # 6) مسار /analyze الحيّ (Guardrail 1، LESSONS ٣١): مسح سريع مجانيّ يُنشئ
    #    صفًّا حقيقيًّا، ثم إعادة فتحه + تصديره — الجذر بالضبط الذي كان يُرجِع
    #    المعرّف «1» ثم 404 لأنّ /analyze كان يكتب لقرصٍ فانٍ لا يقرأ منه أحد.
    if args.skip_analyze:
        print("⊘ خطوة /analyze الحيّة متخطّاة (--skip-analyze)")
    else:
        # 6ب) بوّابة تأكيد HS (LESSONS ٣٥): المنتج الافتراضي هو منتج حادثة
        # الكويت الحيّة بعينه — أوّل نداءٍ **بلا** hs_confirmed يجب أن يُرفَض
        # ٤٢٢ حياً؛ فشل-آمن يعني أن الصمّام مفعّلٌ افتراضياً على النشر لا
        # الاختبار الهرمتي فقط. غياب الرفض (200 أو أيّ خطأ آخر) = انحدارٌ حيّ
        # على البوّابة الأهم في هذه الجولة، لا يُمرَّر بصمت.
        st_gate, body_gate = _post(
            base, "/analyze", {"product": args.analyze_product}, key)
        if st_gate == 422:
            try:
                err = json.loads(body_gate).get("detail", {}).get("error")
            except Exception:  # noqa: BLE001
                err = None
            if err == "hs_confirmation_needed":
                print(f"  ✓ بوّابة HS الحيّة رفضت «{args.analyze_product}» "
                      "بلا تأكيد (422 hs_confirmation_needed) — فشل-آمن يعمل حياً")
            else:
                fails.append(f"POST /analyze (بلا تأكيد): 422 لكن error="
                             f"{err!r}، متوقَّع hs_confirmation_needed")
        elif st_gate == 200:
            fails.append(
                "POST /analyze (بلا تأكيد HS): 200 — بوّابة تأكيد HS لم "
                "تحجب رمزاً غير مؤكَّد حياً (LESSONS ٣٥؛ تحقّق "
                "SILK_HS_CONFIRM_GATE على النشر)")
        else:
            fails.append(f"POST /analyze (بلا تأكيد HS): HTTP {st_gate} غير متوقَّع")

        st, body = _post(base, "/analyze",
                         {"product": args.analyze_product, "persist": True,
                          "hs_confirmed": True},
                         key)
        if st != 200:
            fails.append(f"POST /analyze: HTTP {st} — {(body or b'')[:200]!r}")
        else:
            res = json.loads(body)
            qid = res.get("analysis_id")
            if qid is None:
                fails.append("POST /analyze: 200 لكن بلا analysis_id "
                             "(persist=true لم يُحفَظ — جذر LESSONS ٣١)")
            else:
                print(f"✓ POST /analyze 200 — analysis_id={qid} "
                      f"(«{args.analyze_product}»)")
                st2, _ = _get(base, f"/analyses/{qid}", key)
                if st2 != 200:
                    fails.append(f"GET /analyses/{qid}: HTTP {st2} "
                                 "(404 = الصفّ غير موجود = الجذر)")
                else:
                    print(f"  ✓ GET /analyses/{qid} 200 — إعادة الفتح تعمل")
                    _check_exports(base, qid, key, fails)
                st3, lb = _get(base, "/analyses", key)
                ids = {r.get("id") for r in json.loads(lb)} if st3 == 200 else set()
                if qid not in ids:
                    fails.append(f"analysis_id={qid} لا يظهر في «بحوثي السابقة»")
                else:
                    print(f"  ✓ id={qid} يظهر في «بحوثي السابقة»")

    if fails:
        return _finish(fails)
    print("\n✓ كل الفحوص القابلة للتنفيذ نجحت.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
