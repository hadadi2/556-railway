"""مسارا HS للمصنع: صورةٌ تحسم، أو طلبُ رمزٍ يدويّ — بلا خيارات وبلا ثقة.

قرار المالك (2026-08-29): «إما المصنع موجود عنده الكود يضيفه ويعتمد عليه، أو
طلب رفع الصورة وتحليل الصورة وتحديد المنتج بدقة عالية — بدون وضع خيارات
للمصنع لكي يختار أو كتابة ثقة».

ما يجعله قراراً صحيحاً مقيسٌ لا مُدَّعى: المُحلِّل اللفظي يعيد «برتقال طازج»
لـ«عصير برتقال» بثقة 0.90، ويحسم ١٣ من ٢٠ منتجاً عادياً فقط. الخياراتُ
المعروضة لا تُصلِح مُحلِّلاً لا يعرف.

هرمتيّ بالكامل: طبقتا الرؤية والتصنيف تُستبدَلان بمقاعد، فلا شبكة ولا كلود
ولا إنفاق.
"""
import silk_hs_from_image as F


def _stub_intake(monkeypatch, *, enabled=True, ok=True, name="حلاوة طحينية",
                 ingredients=None, category="", reason="سبب داخلي"):
    import silk_product_intake as intake
    monkeypatch.setattr(intake, "enabled", lambda: enabled)

    def _fake(image_b64, media_type, kind="product", allow_vision=True,
              blocked_reason=""):
        if not ok:
            return {"ok": False, "status": "read_failed", "reason": reason,
                    "product_name": ""}
        return {"ok": True, "status": "ok", "product_name": name,
                "extraction": {"product_name_ar": name,
                               "ingredients": ingredients or [],
                               "category_hint": category, "confidence": 0.9}}
    monkeypatch.setattr(intake, "intake_image", _fake)


def _stub_classifier(monkeypatch, tier="auto", hs6="170490"):
    import silk_hs_classifier as hsc
    seen = {}

    def _fake(product, hs_code=None, ingredients=None, category=None,
              allow_claude=False, instruction=""):
        seen.update(product=product, ingredients=ingredients,
                    category=category, allow_claude=allow_claude)
        return {"tier": tier, "hs6": hs6 if tier == "auto" else None,
                "confidence": 0.93,
                "candidates": [{"hs6": "170490"}, {"hs6": "200819"}],
                "source": "llm_general", "used_llm": True}
    monkeypatch.setattr(hsc, "classify_general", _fake)
    return seen


# ═══════════ ١ — الصورة تحسم: رمزٌ واحد، بلا قائمة وبلا ثقة ══════════════════
def test_a_readable_image_yields_one_settled_code(monkeypatch):
    _stub_intake(monkeypatch)
    _stub_classifier(monkeypatch, tier="auto", hs6="170490")
    out = F.classify_from_image("Zm9v", "image/jpeg")
    assert out["ok"] is True
    assert out["hs6"] == "170490"
    assert out["product_name"] == "حلاوة طحينية"


def test_no_reply_ever_carries_options_or_a_confidence_number(monkeypatch):
    """العقدُ الذي طلبه المالك — بنيويّ لا عُرف: المفاتيحُ ممنوعة في كلّ ردّ."""
    _stub_intake(monkeypatch)
    for tier in ("auto", "candidates", "manual"):
        _stub_classifier(monkeypatch, tier=tier)
        out = F.classify_from_image("Zm9v", "image/jpeg")
        for key in F.FORBIDDEN_CLIENT_KEYS:
            assert key not in out, (tier, key, out)
    _stub_intake(monkeypatch, ok=False)
    out = F.classify_from_image("Zm9v", "image/jpeg")
    for key in F.FORBIDDEN_CLIENT_KEYS:
        assert key not in out, (key, out)


# ═══════════ ٢ — ما دون الحسم يطلب الرمز، ولا يخمّن ═════════════════════════
def test_anything_below_auto_asks_for_the_code_never_guesses(monkeypatch):
    """`candidates` و`manual` كلاهما «غير محسوم» — ولا يُكتب رمزٌ من أيّهما."""
    _stub_intake(monkeypatch)
    for tier in ("candidates", "manual"):
        _stub_classifier(monkeypatch, tier=tier)
        out = F.classify_from_image("Zm9v", "image/jpeg")
        assert out["ok"] is False and out["hs6"] is None, tier
        assert out["message"] == F.MANUAL_FALLBACK_MSG


def test_an_unreadable_image_asks_for_the_code_with_one_message(monkeypatch):
    _stub_intake(monkeypatch, ok=False, reason="لم يُرجع نموذج الرؤية نصّاً")
    out = F.classify_from_image("Zm9v", "image/jpeg")
    assert out["ok"] is False and out["message"] == F.MANUAL_FALLBACK_MSG
    # السببُ الداخليّ يُحفَظ للسجلّ ولا يُعرَض ضمن الرسالة.
    assert out["reason"] and out["reason"] not in out["message"]


def test_the_disabled_valve_asks_for_the_code_not_an_error(monkeypatch):
    """صمّامٌ مُطفأ = المسار الأوّل، لا عطلٌ يقرؤه المصنع."""
    _stub_intake(monkeypatch, enabled=False)
    out = F.classify_from_image("Zm9v", "image/jpeg")
    assert out["ok"] is False and out["message"] == F.MANUAL_FALLBACK_MSG


def test_blocked_vision_never_reaches_the_classifier(monkeypatch):
    """بلا إذنٍ لا نداءَ رؤية ولا نداءَ تصنيف — لا إنفاقَ على مسارٍ محجوب."""
    _stub_intake(monkeypatch, ok=False, reason="سقف الاستهلاك مستنفد")
    called = []
    import silk_hs_classifier as hsc
    monkeypatch.setattr(hsc, "classify_general",
                        lambda *a, **k: called.append(1) or {})
    out = F.classify_from_image("Zm9v", "image/jpeg", allow_vision=False,
                                blocked_reason="سقف الاستهلاك مستنفد")
    assert out["ok"] is False and not called


# ═══════════ ٣ — ما تقرؤه الرؤية يصل المصنّف (وهو سببُ الدقّة) ══════════════
def test_ingredients_and_category_reach_the_classifier(monkeypatch):
    """المكوّنات والفئة هما ما يميّز المصنَّع عن الخام — لا تُرمى."""
    _stub_intake(monkeypatch, name="عصير برتقال",
                 ingredients=["ماء", "مركّز برتقال"], category="مشروبات")
    seen = _stub_classifier(monkeypatch, tier="auto", hs6="200912")
    out = F.classify_from_image("Zm9v", "image/jpeg")
    assert out["hs6"] == "200912"
    assert seen["product"] == "عصير برتقال"
    assert seen["ingredients"] == ["ماء", "مركّز برتقال"]
    assert seen["category"] == "مشروبات"
    assert seen["allow_claude"] is True


def test_the_module_is_a_front_adapter_with_no_engine_imports():
    """محوّلٌ أماميّ: لا يستورد المحرّك ولا الخادم (قفل AST)."""
    import ast
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "silk_hs_from_image.py"),
        encoding="utf-8").read()
    mods = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    for banned in ("silk_engine", "silk_missions", "silk_research_pipeline",
                   "api", "silk_platform", "requests"):
        assert banned not in mods, banned
