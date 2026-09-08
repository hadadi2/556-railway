"""يولّد عيّنات /analyze الأربع من تشغيلة حتمية واحدة — لا شبكة، مخزن مبذور.

المشكلة (مراجعة "أرقام منفصلة بلا معنى"، PR الخلاصة الاحترافية + ترابط
/analyze): عيّنات `report_full_latest.md`/`.docx`/`analysis_latest.json`
الملتزَمة كانت راكدة — أقدم من طبقة السرد (P1) وحزمة البحث (Stage 3، §4b)
وقسم "الأسواق المرشّحة الأخرى" الجديد، فلا تعكس السلوك الحالي لطبقة العرض
(قاعدة §10.6: كل تعديل على طبقة العرض يُعيد توليد عيّناته). هذه الأداة
تشغّل محرّك حتمي حقيقي (سوقان مبذوران: الصين والإمارات) داخل حاجز شبكة
صادق، ثم تشتق الأربعة من نفس النتيجة — بلا اختلاق، كل رقم بمصدره.

Usage:  python3 tools/gen_analyze_samples.py
"""
import contextlib
import json
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SAMPLES_DIR = os.path.join(_REPO_ROOT, "samples")


@contextlib.contextmanager
def _block_network():
    """اقطع الشبكة مؤقتاً — نفس نمط tests/conftest.py::block_network.

    **إغلاق الجلسة المجمّعة شرطٌ لا تحسين** (أوّل CI حيّ بعد عودة Actions،
    2026-08-27). كانت هذه النسخة تدّعي «نفس النمط» وهي تنقصها السطرُ الأهمّ:
    `silk_data_layer._session` جلسةٌ دائمة تجمّع اتصالات keep-alive، وإعادةُ
    استعمال اتصالٍ مفتوحٍ **لا تستدعي `socket.socket` من جديد** — فترقيعُه
    وحده لا يوقفها. على عاملٍ متّصل تركَ اختبارٌ سابق اتصالاً حيّاً، فنجحت
    نداءاتُ البنك الدولي **داخل** هذا الحاجز (١٣ من ٢٠ في سجلّ CI) فخرجت
    العيّنةُ المُعاد بناؤها أغنى من الملتزَمة وسقط قفلُ §10.6.

    الدرسُ نفسُه الذي وُثّق في `tests/conftest.py` — طُبّق هناك ولم يصل
    نسختَه هنا. `tests/test_audit_2026_08_27_fixes.py` يقفل التطابق الآن.
    Closing the pooled session is required, not optional: reusing an open
    keep-alive connection never calls socket.socket again.
    """
    real = socket.socket

    def _no_net(*a, **k):
        raise OSError("network disabled for sample generation")

    # حيادُ البروكسي (أوّل CI حيّ، 2026-08-27): رسالةُ الفشل المعروضة تُشتقّ من
    # **نوع** الاستثناء (`silk_narrative._EXC_FAMILY_AR`): بيئةٌ خلف بروكسي
    # تُنتِج `ProxyError` ⇒ «تعذّر تأمين الاتصال بالمصدر»، وحجبُ socket نقيّ
    # يُنتِج `ConnectionError` ⇒ «تعذّر الاتصال بالمصدر». فالنصّ المولَّد كان
    # يحمل بصمةَ بيئة التوليد، وعيّنةٌ ملتزَمة وُلدت خلف بروكسي تخالف مخرَجَ CI
    # بلا أيّ انحدارٍ حقيقيّ. تصفيرُ متغيّرات البروكسي يجعل النكهة واحدةً
    # أينما وُلِّدت. Neutralise ambient proxy config: it changes the exception
    # type, and the failure-message flavour is derived from it.
    for _var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                 "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(_var, None)
    try:
        import silk_data_layer
        silk_data_layer._session.close()
    except Exception:  # noqa: BLE001 — أفضل جهد؛ ترقيع socket نافذ بدونه
        pass

    # **استثناءٌ قانونيٌّ واحد** (أوّل CI حيّ، 2026-08-27): لا يكفي أن نمنع
    # الشبكة — يجب أن يكون **نوعُ** الفشل واحداً أينما وُلِّدت العيّنة. رسالةُ
    # الفجوة المعروضة تُشتقّ من نوع الاستثناء (`silk_narrative._EXC_FAMILY_AR`)،
    # وأحشاءُ urllib3 تختلف بين البيئات: نفسُ الحجب أنتج على عامل CI عائلةَ
    # SSL/Proxy («تعذّر تأمين الاتصال بالمصدر») وفي صندوق التطوير عائلةَ
    # Connection («تعذّر الاتصال بالمصدر») — ففشل قفلُ §10.6 بلا أيّ انحدارٍ
    # حقيقيّ، لأن المصنوعَ الملتزَم كان يحمل بصمةَ بيئةِ توليده.
    # الحلّ: الجلسةُ المجمّعة ترفع `ConnectionError` صراحةً — نوعٌ واحد، رسالةٌ
    # واحدة، عيّنةٌ قابلةٌ لإعادة الإنتاج بايتياً في أيّ بيئة.
    # Pin the exception TYPE, not just the blocking: the rendered gap message
    # is derived from it, and urllib3 internals differ per environment.
    # **الاستعادة بالحذف لا بالإسناد** (انحدارٌ أُدخل ثمّ أُصلح، 2026-08-27):
    # `_session.request` دالّةُ **صنف** (`requests.Session.request`) لا سمةَ
    # نسخة. إسنادُها على النسخة يُنشئ ظِلّاً في `_session.__dict__`، وإعادةُ
    # إسناد الأصل في `finally` **تُبقي الظِّلّ** — فيبطُل بعدها كلُّ
    # `patch("requests.sessions.Session.request")` (المستوى الذي ترقّعه
    # الاختبارات القائمة) على هذه الجلسة المشتركة، وتمرّ نداءاتُها للشبكة
    # الحقيقية. الأثر المقيس على CI: اختباران يسقطان في الحزمة وينجحان
    # منفردَين — تبعيةُ ترتيبٍ صنّفها مصنّف CI بدقّة ورفض تسميتها تقلُّباً.
    # Restore by DELETING the instance attribute: assigning the bound method
    # back leaves a shadow that defeats later class-level patching.
    _had_own_request = False
    try:
        import requests as _rq
        import silk_data_layer as _dl
        _had_own_request = "request" in _dl._session.__dict__
        _real_request = (_dl._session.__dict__.get("request")
                         if _had_own_request else None)

        def _dead_request(*a, **k):
            raise _rq.exceptions.ConnectionError(
                "network disabled for sample generation")

        _dl._session.request = _dead_request
        _patched_session = True
    except Exception:  # noqa: BLE001 — أفضل جهد؛ ترقيع socket نافذ بدونه
        _real_request = None
        _patched_session = False

    socket.socket = _no_net
    try:
        yield
    finally:
        socket.socket = real
        if _patched_session:
            try:
                import silk_data_layer as _dl2
                if _had_own_request:
                    _dl2._session.request = _real_request   # كانت سمةَ نسخةٍ أصلاً
                else:
                    # لم تكن موجودة ⇒ الحذفُ هو الاستعادة الصحيحة، فتعود
                    # دالّةُ الصنف مرئيةً ويعمل الترقيع اللاحق كما يجب.
                    del _dl2._session.request
            except Exception:  # noqa: BLE001
                pass


def _seed_store() -> None:
    import silk_store
    silk_store.migrate()
    silk_store.upsert_trade_flows([
        {"hs6": "080410", "reporter_iso3": "CHN", "partner_iso3": "WLD",
         "year": 2021, "flow": "M", "value_usd": 4.0e7},
        {"hs6": "080410", "reporter_iso3": "CHN", "partner_iso3": "WLD",
         "year": 2022, "flow": "M", "value_usd": 5.0e7},
        {"hs6": "080410", "reporter_iso3": "CHN", "partner_iso3": "WLD",
         "year": 2023, "flow": "M", "value_usd": 6.0e7, "qty_kg": 2.0e7},
        {"hs6": "080410", "reporter_iso3": "CHN", "partner_iso3": "IRN",
         "year": 2023, "flow": "M", "value_usd": 3.0e7},
        {"hs6": "080410", "reporter_iso3": "CHN", "partner_iso3": "SAU",
         "year": 2023, "flow": "M", "value_usd": 1.8e7, "qty_kg": 8.0e6},
        {"hs6": "080410", "reporter_iso3": "CHN", "partner_iso3": "TUN",
         "year": 2023, "flow": "M", "value_usd": 1.2e7},
        {"hs6": "080410", "reporter_iso3": "ARE", "partner_iso3": "WLD",
         "year": 2021, "flow": "M", "value_usd": 1.5e7},
        {"hs6": "080410", "reporter_iso3": "ARE", "partner_iso3": "WLD",
         "year": 2023, "flow": "M", "value_usd": 2.0e7, "qty_kg": 5.0e6},
        {"hs6": "080410", "reporter_iso3": "ARE", "partner_iso3": "SAU",
         "year": 2023, "flow": "M", "value_usd": 1.4e7, "qty_kg": 4.0e6},
    ])


def build_sample_result() -> dict:
    """التشغيلةُ الحتمية التي تُشتقّ منها العيّناتُ الأربع — **بلا كتابة**.

    مفصولةٌ عن `main` كي يستطيع قفلُ §10.6
    (`tests/test_committed_samples_current.py`) أن يعيد بناءَ نفسِ المخرَج
    في الذاكرة ويقارنَه بالملتزَم، بدل أن يبقى هذا المصنوعُ خارجَ القياس."""
    os.environ["SILK_HERMETIC"] = "1"
    _seed_store()

    import silk_engine
    with _block_network():
        result = silk_engine.analyze(
            "تمور", countries=[{"iso3": "CHN", "m49": "156"},
                              {"iso3": "ARE", "m49": "784"}],
            year=2023, with_research=True, with_requirements=True,
            with_risk=True, with_trend=True)

    from silk_render import build_view
    result["view"] = build_view(result)
    return result


def main() -> None:
    result = build_sample_result()
    view = result["view"]

    from silk_reports import render_markdown, render_docx, render_brief
    md_path = os.path.join(_SAMPLES_DIR, "report_full_latest.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(view))
    print("wrote", md_path)

    docx_path = os.path.join(_SAMPLES_DIR, "report_full_latest.docx")
    render_docx(view, docx_path)
    print("wrote", docx_path)

    brief_path = os.path.join(_SAMPLES_DIR, "brief_latest.txt")
    with open(brief_path, "w", encoding="utf-8") as fh:
        fh.write(render_brief(view))
    print("wrote", brief_path)

    # analysis_latest.json — نفس شكل ردّ POST /analyze الحقيقي (result + view)
    # حرفياً: api.py._json(result) بعد إرفاق result["view"] — دون المرور عبر
    # TestClient (حاجز الشبكة يكسر نقل TestClient الداخلي — راجع اتفاقية
    # الاختبارات في CLAUDE.md)، فنستعمل مُسلسِل الـ API نفسه مباشرة.
    from api import _to_jsonable
    payload = _to_jsonable(result)
    json_path = os.path.join(_SAMPLES_DIR, "analysis_latest.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print("wrote", json_path)

    os.environ.pop("SILK_HERMETIC", None)


if __name__ == "__main__":
    main()
