"""أقفال إصلاحات التدقيق الشامل 2026-08-27 — locks for the full-audit fixes.

كل اختبار هنا يقفل **بنداً مرقّماً** من `AUDIT.md`، ويحمل في اسمه رقمه. القاعدة
البيتية: سلوكٌ جديد بلا اختبار في نفس الـPR = إصلاحٌ بلا حارس، وهو بالضبط صنف
الانحدار الذي وثّقه التدقيق نفسه في غيره.

كل اختبار يؤكّد أمرين لا أمراً واحداً: (أ) السلوك الجديد يقع فعلاً، و(ب)
السلوك القائم **لم يتغيّر** حيث لا يجب أن يتغيّر (الصمّامات المطفأة افتراضياً
خصوصاً — الكنّاس وذاكرة البحث).

هرمتي بالكامل: لا شبكة، لا مفاتيح، لا عملية خارجية.
"""
import ast
import contextlib
import os
import pathlib
import re
import sqlite3
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ROOT = pathlib.Path(__file__).resolve().parent.parent


@contextlib.contextmanager
def _env(**vals):
    """اضبط متغيرات بيئة مؤقتًا — set env vars, always restoring the old state."""
    saved = {k: os.environ.get(k) for k in vals}
    try:
        for k, v in vals.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


# ── البند ٢ — مُوصِّل SQLite واحد بمهلة قفل ──────────────────────────────────

def test_item2_shared_connector_sets_busy_timeout(tmp_path):
    """`silk_sqlite.connect` يضبط مهلة القفل فعلياً — PRAGMA حيّ لا نصّ مصدر."""
    import silk_sqlite
    conn = silk_sqlite.connect(str(tmp_path / "sub" / "x.db"))
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        # `row_factory` افتراضياً (الوصول بالاسم) — عقد المخازن القائمة.
        conn.execute("CREATE TABLE t (a INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        assert conn.execute("SELECT a FROM t").fetchone()["a"] == 1
    finally:
        conn.close()
    # أنشأ المجلد الأب — نفس ما كانت تفعله النسخ الخمس المحذوفة.
    assert (tmp_path / "sub" / "x.db").exists()


def test_item2_every_main_path_store_waits_for_the_lock(tmp_path):
    """الحادثة الأمّ: إصلاح «database is locked» وصل المنصّة وحدها.

    الخمسة كلها الآن تفتح اتصالاً ينتظر القفل بدل رمي الاستثناء فوراً. الفحص
    على **الاتصال الحقيقي** الذي يفتحه كل مخزن، لا على نصّ الملف.
    """
    import silk_ops_log
    import silk_storage
    import silk_usage
    import silk_watchdog
    checks = [
        (silk_storage._connect, str(tmp_path / "silk.db")),
        (silk_usage._connect, str(tmp_path / "usage.db")),
        (silk_watchdog._connect, str(tmp_path / "watchdog.db")),
        (silk_ops_log._connect, str(tmp_path / "ops.db")),
    ]
    for connect, path in checks:
        conn = connect(path)
        try:
            got = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert got == 30000, f"{path}: busy_timeout={got}, expected 30000"
        finally:
            conn.close()

    import silk_store
    with _env(SILK_STORE_DB=str(tmp_path / "store.db"), DATABASE_URL=None):
        conn = silk_store.connect()
        try:
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
            # مخزن الحقائق وحده يحتاج قيود FK — لم تُفقَد في التوحيد.
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            conn.close()


def test_item2_a_held_write_lock_waits_instead_of_raising(tmp_path):
    """كاتبٌ متزامن مشروع ينتظر ولا يُرمى — السلوك الذي كان مفقوداً."""
    import silk_sqlite
    path = str(tmp_path / "lock.db")
    setup = silk_sqlite.connect(path)
    setup.execute("CREATE TABLE t (a INTEGER)")
    setup.commit()
    setup.close()

    holding = threading.Event()
    released = threading.Event()

    def _hold_then_release() -> None:
        # الاتصال يُفتَح ويُغلَق في **خيطه** — كائنات sqlite مربوطة بخيطها.
        holder = silk_sqlite.connect(path)
        holder.execute("BEGIN IMMEDIATE")
        holder.execute("INSERT INTO t VALUES (1)")
        holding.set()
        time.sleep(0.3)
        holder.commit()
        holder.close()
        released.set()

    t = threading.Thread(target=_hold_then_release, daemon=True)
    t.start()
    assert holding.wait(timeout=5)
    other = silk_sqlite.connect(path)
    try:
        # بلا مهلة القفل (الافتراضي ٥ث كان يكفي هنا، لكن الحادثة الحقيقية
        # كانت أطول) — المهم أن الكتابة **تنجح بالانتظار** لا أن تُرمى.
        other.execute("INSERT INTO t VALUES (2)")
        other.commit()
    finally:
        other.close()
        t.join(timeout=5)
    assert released.is_set()


# ── البند ٩ — قفل عدّادات اقتصاد البيانات ────────────────────────────────────

def test_item9_concurrent_counter_increments_lose_nothing():
    """`+=` غير ذرّي عبر ١٢ خيط بعثة — العدّاد مُدخَل إنفاذ السقوف وصدق التكلفة."""
    import silk_context
    counter = silk_context.begin_data_counter()
    ctx = __import__("contextvars").copy_context()
    threads, per_thread, n_threads = [], 500, 8

    def _worker() -> None:
        def _run() -> None:
            for _ in range(per_thread):
                silk_context.count_data("live_fetches")
        # نفس آلية البعثات: نسخة سياق مستقلة لكل خيط تشير لنفس القاموس.
        ctx.copy().run(_run)

    for _ in range(n_threads):
        t = threading.Thread(target=_worker)
        threads.append(t)
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert counter["live_fetches"] == per_thread * n_threads


def test_item9_concurrent_llm_usage_records_lose_nothing():
    """نفس القفل يحمي رموز كلود — وهي مُدخَل تقدير التكلفة المعروض للمالك."""
    import silk_context
    counter = silk_context.begin_data_counter()
    ctx = __import__("contextvars").copy_context()

    def _worker() -> None:
        def _run() -> None:
            for _ in range(300):
                silk_context.record_llm_usage("m", 10, 5)
        ctx.copy().run(_run)

    threads = [threading.Thread(target=_worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    row = counter["llm_usage"]["m"]
    assert row["input_tokens"] == 6 * 300 * 10
    assert row["output_tokens"] == 6 * 300 * 5


# ── البند ١ — السقف الزمني الجداري داخل حلقة البعثة ─────────────────────────

def _mission_ctx():
    from silk_market_resolver import MarketRef
    return {"market": MarketRef(iso3="NLD", m49="528", name_en="Netherlands",
                                name_ar="هولندا"),
            "product": "تمور", "hs_code": "080410"}


def test_item1_wall_timeout_stops_before_the_next_paid_call(monkeypatch):
    """مهلة منقضية ⇒ صفر نداء كلود إضافي + فجوة **معلنة** بالعربية.

    الحادثة: مهلة المنسّق ناعمة — تتخلّى عن نتيجة البعثة ولا توقف خيطها، فيواصل
    حرق نداءات مدفوعة من السقف المشترك على عملٍ لن يُقرأ أبداً.
    """
    import silk_llm_runtime
    calls = []

    def _fake_call_tools(system, messages, **kw):
        calls.append(1)
        return {"content": [{"type": "text", "text": "{}"}], "stop_reason": "end_turn"}

    monkeypatch.setattr(silk_llm_runtime, "_call_tools", _fake_call_tools)
    mission = {"key": "trade_flow", "name": "تدفّق", "instructions": "x",
               "allowed_tools": []}
    # ساعة مزيّفة حتمية: أول قراءة هي بداية البعثة، وكل قراءة بعدها تقع
    # **بعد** النافذة — فالاختبار لا يتعلّق بسرعة الجهاز.
    real_monotonic = time.monotonic
    reads = {"n": 0}

    def _fake_monotonic():
        reads["n"] += 1
        return real_monotonic() + (0.0 if reads["n"] <= 1 else 10_000.0)

    monkeypatch.setattr(time, "monotonic", _fake_monotonic)
    out = silk_llm_runtime._run_loop(
        mission, _mission_ctx(), {"tool_calls": 3, "max_output_tokens": 100},
        wall_timeout_s=60)
    assert calls == [], "نداء كلود وقع بعد انقضاء النافذة الجدارية"
    gaps = " ".join(out.get("gaps") or [])
    assert "نافذتها الزمنية" in gaps, gaps
    assert out["findings"] == []


def test_item1_no_wall_timeout_keeps_todays_behaviour(monkeypatch):
    """بلا مهلة (`None`) لا يتغيّر شيء — حارس المحلل الشامل والكاتب."""
    import silk_llm_runtime
    calls = []

    def _fake_call_tools(system, messages, **kw):
        calls.append(1)
        return {"content": [{"type": "text", "text":
                             '{"findings":[],"gaps":[],"summary":"ok"}'}],
                "stop_reason": "end_turn"}

    monkeypatch.setattr(silk_llm_runtime, "_call_tools", _fake_call_tools)
    mission = {"key": "analyst", "name": "محلل", "instructions": "x",
               "allowed_tools": []}
    out = silk_llm_runtime._run_loop(
        mission, _mission_ctx(), {"tool_calls": 3, "max_output_tokens": 100})
    assert calls, "النداء لم يقع رغم غياب أي مهلة جدارية"
    assert "نافذتها الزمنية" not in " ".join(out.get("gaps") or [])


def test_item1_orchestrator_passes_a_wall_ceiling_above_its_own_deadline():
    """السقف الداخلي **أوسع** من مهلة المنسّق — السباق لصالح المنسّق دائماً."""
    import silk_missions
    assert silk_missions._WALL_GRACE_S > 0
    src = (_ROOT / "silk_missions.py").read_text(encoding="utf-8")
    assert "\"wall_timeout_s\": _MISSION_TIMEOUT_S + _WALL_GRACE_S" in src


# ── البند ٥ — مستخلِص JSON واحد ─────────────────────────────────────────────

_FENCED_WITH_TRAILING_PROSE = (
    "إليك النتيجة:\n```json\n{\"findings\": [], \"summary\": \"س\"}\n```\n"
    "ملاحظة ختامية {غير JSON}")


def test_item5_one_extractor_three_call_sites_same_answer():
    """النسخ الثلاث صارت واحدة — والحادثة الأصلية (سياج + تعليق ختامي) مقفولة."""
    import silk_ai_judge
    import silk_json
    import silk_llm_runtime
    import silk_product_intake

    expected = {"findings": [], "summary": "س"}
    assert silk_json.extract(_FENCED_WITH_TRAILING_PROSE) == expected
    assert silk_ai_judge._extract_json(_FENCED_WITH_TRAILING_PROSE) == expected
    assert silk_product_intake._extract_json(
        _FENCED_WITH_TRAILING_PROSE) == expected
    # المرشّحون: محتوى السياج أولاً ثم النصّ كاملاً احتياطاً.
    cands = silk_llm_runtime._json_candidates(_FENCED_WITH_TRAILING_PROSE)
    assert cands[0].startswith("{") and cands[-1].endswith("}")


def test_item5_failure_is_a_declared_gap_never_an_empty_object():
    """عقد البند ٦ من الدروس: الفشل `None` لا كائنٌ فارغ يبدو نجاحاً."""
    import silk_ai_judge
    import silk_json
    import silk_product_intake
    for bad in ("", None, "ليس JSON إطلاقاً، لا أقواس هنا."):
        assert silk_json.extract(bad) is None
        assert silk_ai_judge._extract_json(bad) is None
        assert silk_product_intake._extract_json(bad) is None


def test_item5_dict_only_preserves_intake_original_contract():
    """`silk_product_intake` كان يرفض المصفوفة العليا — لم يُفقَد في التوحيد."""
    import silk_json
    import silk_product_intake
    # مصفوفة عليا تحوي كائناً: المستخلِص العام يقبل ما بين أول { وآخر }،
    # أما مسار الاستقبال فيشترط كائناً في القمة.
    top_level_array = '[{"name": "x"}, {"name": "y"}]'
    assert silk_product_intake._extract_json(top_level_array) is None
    assert silk_json.extract(top_level_array, dict_only=True) is None


# ── البند ٦ — تحديث المؤشرات دفعةً واحدة ────────────────────────────────────

def test_item6_bulk_upsert_writes_the_same_rows(tmp_path):
    """الدلالات لم تتغيّر: نفس القيم، و«أحدث جلب يفوز» على نفس المفتاح."""
    import silk_store
    with _env(SILK_STORE_DB=str(tmp_path / "s.db"), DATABASE_URL=None,
              SILK_DATA_DIR=None):
        silk_store.migrate()
        n = silk_store.upsert_indicators([
            {"iso3": "NLD", "indicator": "NY.GDP.PCAP.CD", "year": 2023,
             "value": 1.0, "source": "World Bank", "confidence": 0.9,
             "note": "أولى"},
            {"iso3": "SAU", "indicator": "NY.GDP.PCAP.CD", "year": 2023,
             "value": 2.0, "source": "World Bank", "confidence": 0.9,
             "note": "أولى"},
        ])
        assert n == 2
        assert silk_store.get_indicator("NLD", "NY.GDP.PCAP.CD", 2023)["value"] == 1.0
        # نفس المفتاح مرّةً ثانية ⇒ يفوز الأحدث (لا صفّ مكرّر).
        silk_store.upsert_indicators([
            {"iso3": "NLD", "indicator": "NY.GDP.PCAP.CD", "year": 2023,
             "value": 9.0, "source": "World Bank", "confidence": 0.9,
             "note": "أحدث"}])
        row = silk_store.get_indicator("NLD", "NY.GDP.PCAP.CD", 2023)
        assert row["value"] == 9.0 and row["note"] == "أحدث"


def test_item6_collector_uses_the_batched_path_not_row_by_row():
    """~٢٠ ألف معاملة للمؤشر الواحد على قرص النشر كانت السبب — لا تعود."""
    src = (_ROOT / "silk_collectors.py").read_text(encoding="utf-8")
    assert "upsert_indicators(batch)" in src
    # النداء المفرد صفّاً صفّاً اختفى (الجمع `upsert_indicators` باقٍ عمداً).
    assert not re.search(r"upsert_indicator\(", src)


# ── البند ٨ — المسار المقوّى للوكلاء ────────────────────────────────────────

_REROUTED_AGENTS = ("silk_openalex_agent.py", "silk_eurostat_agent.py",
                    "silk_faostat_agent.py", "silk_maps_agent.py",
                    "silk_tariffs_agent.py",
                    # مراجعة §58: أخت Serper المدفوعة (`web_search_shopping`)
                    # بقيت عاريةً في النسخة الأولى — النداء المدفوع أولى
                    # الجميع بالمسار المقوّى.
                    "silk_websearch_agent.py")


def test_item8_rerouted_agents_have_no_bare_requests_get():
    """فحص AST: لا `requests.get` عارٍ في الوكلاء المُحوَّلين (لا فحص نصّي)."""
    offenders = []
    for name in _REROUTED_AGENTS:
        tree = ast.parse((_ROOT / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("get", "post")
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "requests"):
                offenders.append(f"{name}:{node.lineno}")
    assert not offenders, f"نداءات عارية خارج المسار المقوّى: {offenders}"


def test_item8_throttled_request_retries_retryable_status(monkeypatch):
    """429 تُعاد لا تُترجَم فجوةً فوراً — وهو ما يمتصّ ارتجاجة المزوّد."""
    import requests
    import silk_data_layer

    class _Resp:
        def __init__(self, code):
            self.status_code = code
            self.headers = {}

    seq = [_Resp(429), _Resp(200)]
    seen = []

    def _fake_get(url, **kw):
        seen.append(url)
        return seq.pop(0)

    monkeypatch.setattr(requests, "get", _fake_get)
    monkeypatch.setattr(silk_data_layer, "_backoff_delay", lambda *a, **k: 0.0)
    with _env(SILK_HTTP_RETRIES="3", SILK_HTTP_MIN_GAP_MS="0"):
        resp = silk_data_layer.throttled_get("https://example.test/x")
    assert resp.status_code == 200
    assert len(seen) == 2, "لم تقع إعادة المحاولة على 429"


def test_item8_throttled_request_stays_patchable_by_hermetic_tests(monkeypatch):
    """السبب الصريح لعدم استعمال الجلسة المجمّعة: اعتراض الاختبارات يجب أن يعمل."""
    import requests
    import silk_data_layer
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no net")))
    with _env(SILK_HTTP_MIN_GAP_MS="0"):
        with pytest.raises(OSError):
            silk_data_layer.throttled_get("https://example.test/y")


def test_item8_agents_degrade_to_declared_gap_when_the_network_is_cut(monkeypatch):
    """عقد عدم الاختلاق سليم بعد التحويل: فشل الشبكة ⇒ None بثقة صفر."""
    import requests
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("cut")))
    with _env(SILK_HTTP_MIN_GAP_MS="0", SILK_HTTP_RETRIES="0"):
        import silk_openalex_agent
        dps = silk_openalex_agent.openalex_search("dates netherlands",
                                                  max_records=2)
    assert dps and dps[0].value is None and dps[0].confidence == 0.0
    assert dps[0].note


# ── البند ١٠ — منع تكرار خيوط SWR ───────────────────────────────────────────

def test_item10_swr_does_not_spawn_a_second_thread_for_the_same_key(monkeypatch):
    """١٢ بعثة تسأل عن نفس المفتاح لحظةً واحدة — خيط واحد لا اثنا عشر."""
    import silk_data_layer_v2 as v2
    spawned = []

    class _FakeThread:
        def __init__(self, target=None, name=None, daemon=None, args=()):
            self._target, self._args = target, args
            spawned.append(name)

        def start(self):
            pass    # لا نشغّله: نقيس عدد الخيوط المُنشأة لا نتيجتها

    monkeypatch.setattr(threading, "Thread", _FakeThread)
    with _env(SILK_SWR=None):
        v2._swr_inflight.clear()
        v2._refresh_in_background("080410", 528, "NLD", 2023)
        v2._refresh_in_background("080410", 528, "NLD", 2023)
        v2._refresh_in_background("080410", 528, "NLD", 2022)   # مفتاح آخر
    try:
        assert len(spawned) == 2, spawned
    finally:
        v2._swr_inflight.clear()


def test_item10_inflight_key_is_released_even_when_the_refresh_raises(monkeypatch):
    """الحارس لا يعلق للأبد: `finally` يحرّر المفتاح حتى عند انفجار الجلب."""
    import silk_data_layer_v2 as v2
    v2._swr_inflight.clear()
    key = ("imports", "080410", "NLD", 2023)
    assert v2._swr_begin(key) is True
    assert v2._swr_begin(key) is False
    v2._swr_done(key)
    assert v2._swr_begin(key) is True
    v2._swr_done(key)


# ── البند ١١ — كنّاس القرص الدائم ───────────────────────────────────────────

def test_item11_janitor_can_be_explicitly_disabled(tmp_path):
    """صمّام الميزة الجديدة (الدرس ٧٠): بلا ضبطٍ لا يُحذَف شيء إطلاقاً."""
    import silk_janitor
    traces = tmp_path / "traces"
    traces.mkdir()
    old = traces / "old.jsonl"
    old.write_text("{}\n", encoding="utf-8")
    os.utime(old, (time.time() - 90 * 86400,) * 2)
    with _env(SILK_TRACE_DIR=str(traces), SILK_RETENTION_DAYS=None,
              SILK_TRACE_RETENTION_DAYS="0", SILK_CACHE_RETENTION_DAYS="0",
              SILK_OPS_RETENTION_DAYS=None):
        out = silk_janitor.sweep()
    assert out == {"traces": 0, "cache": 0, "ops_errors": 0,
                   "watchdog_records": 0}
    assert old.exists(), "حُذف ملف والكنّاس مطفأ"


def test_item11_janitor_sweeps_only_what_is_older_than_the_window(tmp_path):
    """يحذف القديم ويُبقي الحديث — لا كنسة عمياء."""
    import silk_janitor
    traces = tmp_path / "traces"
    traces.mkdir()
    old, fresh = traces / "old.jsonl", traces / "fresh.jsonl"
    for f in (old, fresh):
        f.write_text("{}\n", encoding="utf-8")
    os.utime(old, (time.time() - 30 * 86400,) * 2)
    with _env(SILK_TRACE_DIR=str(traces), SILK_TRACE_RETENTION_DAYS="7",
              SILK_RETENTION_DAYS=None, SILK_CACHE_RETENTION_DAYS=None,
              SILK_OPS_RETENTION_DAYS=None):
        out = silk_janitor.sweep()
    assert out["traces"] == 1
    assert fresh.exists() and not old.exists()


def test_item11_janitor_never_touches_the_contractual_stores(tmp_path):
    """تأكيد سلبي صريح: قاعدة التحاليل ومخزن الحقائق ودفتر المحاسبة لا تُمَسّ.

    «Never delete or modify existing data in data/silk.db» — قانون `CLAUDE.md`.
    """
    import silk_janitor
    src = (_ROOT / "silk_janitor.py").read_text(encoding="utf-8")
    for forbidden in ("silk.db", "silk_store.db", "usage.db", "analyses",
                      "indicators", "trade_flows", "paid_usage"):
        assert f"DELETE FROM {forbidden}" not in src
    # الجدولان الوحيدان القابلان للقصّ تشخيصيان بحتان.
    # الجملة الوحيدة الحاذفة مُعامَلة باسم جدولٍ من زوجين مكتوبين صراحةً.
    assert src.count("DELETE FROM") == 1
    assert 'f"DELETE FROM {table} WHERE created_at < ?"' in src
    assert '("silk_ops_log", "ops_errors")' in src
    assert '("silk_watchdog", "watchdog_records")' in src
    _ = silk_janitor    # الوحدة تُستورَد بلا شبكة ولا مفاتيح


def test_item11_scheduler_wires_the_janitor():
    """الكنّاس داخل المجدول القائم — لا خدمة cron ثانية (قرار مالك مستقر)."""
    src = (_ROOT / "silk_collectors.py").read_text(encoding="utf-8")
    assert "import silk_janitor" in src and "silk_janitor.sweep()" in src


# ── البنود ١٢/١٤/١٥ — الأمن ─────────────────────────────────────────────────

def test_item12_owner_key_is_compared_in_constant_time():
    """أعلى مفتاح سلطةً في النظام كان الوحيد المقارَن بـ`==`."""
    import silk_export_gate
    src = (_ROOT / "silk_export_gate.py").read_text(encoding="utf-8")
    assert "hmac.compare_digest" in src
    with _env(SILK_OWNER_KEY="s3cret"):
        assert silk_export_gate.override_authorized("s3cret") is True
        assert silk_export_gate.override_authorized("s3cre") is False
        assert silk_export_gate.override_authorized(None) is False
    with _env(SILK_OWNER_KEY=None):
        # غياب المفتاح على الخادم = لا تجاوزَ ممكن (لا فتحة افتراضية).
        assert silk_export_gate.override_authorized("anything") is False


def test_item14_either_production_signal_implies_a_secure_cookie():
    """حارس الإقلاع يعامل المتغيّرين إشارتَي إنتاج متكافئتين — والكوكي الآن مثله."""
    from silk_platform import api as papi
    with _env(SILK_PLATFORM_SECURE_COOKIES=None,
              SILK_PLATFORM_REQUIRE_SECRET=None):
        assert papi._secure_cookies() is False
    with _env(SILK_PLATFORM_SECURE_COOKIES="1",
              SILK_PLATFORM_REQUIRE_SECRET=None):
        assert papi._secure_cookies() is True
    with _env(SILK_PLATFORM_SECURE_COOKIES=None,
              SILK_PLATFORM_REQUIRE_SECRET="1"):
        assert papi._secure_cookies() is True, (
            "نشرٌ بإشارة الإنتاج الأخرى كان يخدم كوكي الجلسة بلا Secure")


def test_item15_redaction_covers_every_secret_named_in_env_example():
    """أول مسبار يُضاف لمفتاحٍ خارج القائمة كان سيرث قيمةً غير منقّحة."""
    import silk_diagnostics
    must_redact = ("WTO_TTD_API_KEY", "WTO_API_KEY", "MOYASAR_SECRET_KEY",
                   "TAP_SECRET_KEY", "STRIPE_SECRET_KEY", "SILK_API_KEY",
                   "SILK_OWNER_KEY", "SILK_PLATFORM_SECRET",
                   "ANTHROPIC_API_KEY", "SEARCH_API_KEY")
    env_example = (_ROOT / ".env.example").read_text(encoding="utf-8")
    for name in must_redact:
        assert name in env_example, f"{name} غير موثّق في .env.example"
        with _env(**{name: "SUPER-SECRET-VALUE"}):
            out = silk_diagnostics._redact(f"failed with key SUPER-SECRET-VALUE")
        assert "SUPER-SECRET-VALUE" not in out, f"{name} لم يُنقَّح"
        assert f"<{name}>" in out


# ── البند ٢٦ — ذاكرة نداء البحث المدفوع ─────────────────────────────────────

def _serper_payload():
    return {"organic": [{"title": "t", "snippet": "s",
                         "link": "https://example.test/a"}]}


def test_item26_search_cache_is_off_by_default(monkeypatch, tmp_path):
    """مطفأة افتراضياً ⇒ كل نداء يضرب المزوّد كما اليوم حرفياً."""
    import silk_data_layer
    import silk_websearch_agent

    hits = []

    class _R:
        status_code = 200
        headers: dict = {}

        def raise_for_status(self):
            pass

        def json(self):
            return _serper_payload()

    monkeypatch.setattr(silk_data_layer, "throttled_request",
                        lambda *a, **k: (hits.append(1), _R())[1])
    with _env(SEARCH_API_KEY="k", SERPER_API_KEY=None,
              SILK_CACHE_DIR=str(tmp_path), SILK_SEARCH_CACHE_TTL_S=None):
        silk_websearch_agent.web_search("تمور هولندا", num=1)
        silk_websearch_agent.web_search("تمور هولندا", num=1)
    assert len(hits) == 2


def test_item26_enabled_cache_saves_the_second_paid_call(monkeypatch, tmp_path):
    """مفعَّلة ⇒ الاستعلام المطابق لا يُدفَع ثمنه مرّتين (استئناف/إعادة تشغيل)."""
    import silk_data_layer
    import silk_websearch_agent

    hits = []

    class _R:
        status_code = 200
        headers: dict = {}

        def raise_for_status(self):
            pass

        def json(self):
            return _serper_payload()

    monkeypatch.setattr(silk_data_layer, "throttled_request",
                        lambda *a, **k: (hits.append(1), _R())[1])
    with _env(SEARCH_API_KEY="k", SERPER_API_KEY=None,
              SILK_CACHE_DIR=str(tmp_path), SILK_SEARCH_CACHE_TTL_S="600"):
        first = silk_websearch_agent.web_search("تمور هولندا", num=1)
        second = silk_websearch_agent.web_search("تمور هولندا", num=1)
    assert len(hits) == 1, "دُفع ثمن الاستعلام مرّتين رغم تفعيل الذاكرة"
    assert [d.value for d in first] == [d.value for d in second]


def test_item26_a_failure_is_never_cached(monkeypatch, tmp_path):
    """لا تكريس لفشل: نتيجة فارغة/خطأ لا تُخزَّن فتُخدَم لاحقاً كأنها إجابة."""
    import silk_data_layer
    import silk_websearch_agent

    def _boom(*a, **k):
        raise OSError("provider down")

    monkeypatch.setattr(silk_data_layer, "throttled_request", _boom)
    with _env(SEARCH_API_KEY="k", SERPER_API_KEY=None,
              SILK_CACHE_DIR=str(tmp_path), SILK_SEARCH_CACHE_TTL_S="600"):
        dps = silk_websearch_agent.web_search("تمور هولندا", num=1)
        assert dps[0].value is None and dps[0].confidence == 0.0
        assert not list(pathlib.Path(tmp_path).glob("*.json")), \
            "فشلٌ خُزِّن في الذاكرة"


# ── البند ٢٧ — صفحات التوثيق ────────────────────────────────────────────────

def test_item27_docs_are_disabled_once_an_api_key_is_configured():
    """الفهرس يُحرَس كما تُحرَس النقاط: مفتاحٌ مضبوط ⇒ لا خريطة سطح هجوم عامة."""
    import importlib
    import api as api_mod
    with _env(SILK_API_KEY="k", SILK_PUBLIC_DOCS=None):
        app = importlib.reload(api_mod).create_app()
        assert app.docs_url is None and app.openapi_url is None
    with _env(SILK_API_KEY=None, SILK_PUBLIC_DOCS=None):
        app = importlib.reload(api_mod).create_app()
        assert app.docs_url == "/docs"
    with _env(SILK_API_KEY="k", SILK_PUBLIC_DOCS="1"):
        app = importlib.reload(api_mod).create_app()
        assert app.docs_url == "/docs", "المخرج الصريح لا يعمل"
    importlib.reload(api_mod)


# ── البند ٢٨ — allowlist لجملة الترتيب ──────────────────────────────────────

def test_item28_order_by_allowlist_accepts_todays_calls_and_rejects_injection():
    """كل النداءات القائمة ثوابت حرفية — الحارس لا يغيّر سلوكاً، يمنع القادم."""
    from silk_platform.repository import _safe_order
    for good in ("id DESC", "id", "created_at ASC", "s.id DESC, s.name"):
        assert _safe_order(good) == good
    for bad in ("id; DROP TABLE studies", "id DESC -- x",
                "(SELECT 1)", "id DESC, (SELECT password FROM users)"):
        with pytest.raises(ValueError):
            _safe_order(bad)


def test_item28_repository_list_still_scopes_by_owner(tmp_path):
    """الحارس الجديد لم يمسّ العزل نفسه — قراءة حسابٍ لا ترى صفوف الآخر."""
    from silk_platform import db as pdb
    from silk_platform import repository
    with _env(SILK_PLATFORM_DB=str(tmp_path / "p.db")):
        pdb.apply_migrations()
        conn = pdb.connect()
        try:
            conn.execute(
                "INSERT INTO accounts (id, name, kind, created_at, updated_at) "
                "VALUES (1,'a','factory','x','x'), (2,'b','factory','x','x')")
            conn.commit()
            rows = repository.studies(conn).list(1)
            assert rows == []
        finally:
            conn.close()


# ── البند ٣٤ — حدّ سرد التحليلات ────────────────────────────────────────────

def test_item34_analyses_limit_is_forwarded_and_validated(monkeypatch):
    """الوسيط كان موجوداً في المخزن ولا يصله شيء من النقطة."""
    import importlib
    import api as api_mod
    from fastapi.testclient import TestClient
    with _env(SILK_API_KEY=None, SILK_RATE_LIMIT="0", SILK_PUBLIC_DOCS=None):
        mod = importlib.reload(api_mod)
        import silk_storage
        seen = {}

        def _fake_list(path=None, limit=None):
            seen["limit"] = limit
            return []

        monkeypatch.setattr(silk_storage, "list_analyses", _fake_list)
        client = TestClient(mod.create_app())
        assert client.get("/analyses").status_code == 200
        assert seen["limit"] is None, "غياب الوسيط غيّر السلوك القديم"
        assert client.get("/analyses?limit=5").status_code == 200
        assert seen["limit"] == 5
        assert client.get("/analyses?limit=abc").status_code == 422
    importlib.reload(api_mod)


# ── البندان ٣/٤ — أوهام تغطية CI ────────────────────────────────────────────

_E2E_WORKFLOW = _ROOT / ".github" / "workflows" / "e2e-live-shape.yml"


def test_item3_every_e2e_marked_rung_file_is_actually_run_by_the_job():
    """حارس اليتيم القادم: ملفٌ موسوم `e2e` وغائبٌ عن سطر التشغيل لا يشغّله أحد.

    الحادثة: `tests/test_rung2_factory_language_flow.py` (تدفّق لغة تقرير
    المصنع كاملاً) كان موسوماً `e2e` — فتتخطّاه الحزمة الهرمتية — وغائباً عن
    وظيفة `e2e-live-shape`، أي **لا يشغّله أيّ مسار على الإطلاق**.
    """
    workflow = _E2E_WORKFLOW.read_text(encoding="utf-8")
    marked = []
    for path in sorted((_ROOT / "tests").glob("test_rung*.py")):
        text = path.read_text(encoding="utf-8")
        if "pytest.mark.e2e" in text:
            marked.append(path.name)
    assert marked, "لم يُعثر على أي ملف رُتبة موسوم e2e — تغيّرت التسمية؟"
    missing = [n for n in marked if n not in workflow]
    assert not missing, (
        f"ملفات رُتبة موسومة e2e لا تشغّلها وظيفة e2e-live-shape: {missing}")


def test_item4_rung3_environment_gaps_fail_loudly_inside_the_job():
    """وظيفة خضراء بصفر خطوة متصفّح كانت ممكنة — لم تعد."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_rung3_mod", _ROOT / "tests" / "test_rung3_playwright_e2e.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # `pytest.fail`/`pytest.skip` يرفعان من `BaseException` لا `Exception`.
    with _env(SILK_RUN_E2E="1"):
        with pytest.raises(BaseException) as exc:
            mod._rung_gate("node مفقود")
        assert type(exc.value).__name__ == "Failed", type(exc.value).__name__
        assert "رُتبة ٣ مُلزَمة" in str(exc.value)
    with _env(SILK_RUN_E2E=None):
        with pytest.raises(BaseException) as exc2:
            mod._rung_gate("node مفقود")
        assert type(exc2.value).__name__ == "Skipped", type(exc2.value).__name__


def test_item16_ci_installs_pinned_test_tooling():
    """أدوات CI مثبَّتة كاعتماديات الإنتاج — إصدارٌ جديد لا يُحمِّر الريبو وحده."""
    reqs = (_ROOT / "requirements-ci.txt").read_text(encoding="utf-8")
    assert "pytest==" in reqs and "httpx==" in reqs
    for wf in ("ci.yml", "e2e-live-shape.yml"):
        text = (_ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert "requirements-ci.txt" in text, f"{wf} لا يستعمل التثبيت المُقيَّد"
    ci = (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pip install -r requirements.txt pytest httpx" not in ci


# ── البند ٢١ — CRUD قديم في `silk_store` (قرار المالك: يُوسَم لا يُحذَف) ─────

_LEGACY_STORE_FUNCS = ("save_analysis", "save_decision", "set_outcome",
                       "create_user", "get_user_by_email")
# P3 (تدقيق 2026-09-01، DEBT-3): القارئان `get_analysis`/`list_analyses` **حُذفا** —
# لم يكن لهما نداءٌ واحد في الريبو كلّه، واسمهما المطابق لِـ`silk_storage` الحيّة كان
# لغماً فوق فخّ تسمية. البقيّةُ لها مستهلكٌ شرعيّ (أداةُ الترحيل) فتبقى موسومة.
_DELETED_STORE_READERS = ("get_analysis", "list_analyses")


def test_item21_legacy_store_crud_is_loudly_marked():
    """الاسم المطابق لِـ`silk_storage` الحيّة لغمٌ فوق فخّ تسمية موثَّق."""
    src = (_ROOT / "silk_store.py").read_text(encoding="utf-8")
    assert "legacy-import-only" in src
    assert "silk_storage" in src, "التحذير لا يسمّي البديل الحيّ"
    for fn in _LEGACY_STORE_FUNCS:
        assert f"def {fn}(" in src, f"{fn} اختفت — الحذف قرارٌ لم يُتَّخذ"
    # الاتّجاهُ المعاكس بعد P3: القارئان المحذوفان لا يعودان بلا قرارٍ جديد.
    for fn in _DELETED_STORE_READERS:
        assert f"def {fn}(" not in src, (
            f"{fn} عادت إلى silk_store — اسمٌ مطابقٌ لِـsilk_storage الحيّة بلا نداء "
            "(حُذفت في تدقيق 2026-09-01، DEBT-3)")


def test_item21_no_production_module_imports_the_legacy_crud():
    """القفل الفعليّ: مستهلكها الشرعي الوحيد أداة الترحيل، لا مسارٌ إنتاجي.

    `import silk_store as store; store.save_analysis(...)` يعمل بلا خطأ ويكتب
    في القاعدة الخطأ — فتضيع التحاليل من كل مسارات القراءة **بصمت**.
    """
    offenders = []
    prod = (sorted(_ROOT.glob("*.py"))
            + sorted((_ROOT / "silk_platform").glob("*.py")))
    for path in prod:
        if path.name == "silk_store.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "silk_store" not in text:
            continue
        for fn in _LEGACY_STORE_FUNCS:
            for call in (f"silk_store.{fn}(", f"store.{fn}("):
                if call in text:
                    offenders.append(f"{path.name}: {call}")
    assert not offenders, (
        "مسار إنتاجي ينادي CRUD القديم في silk_store — استعمل silk_storage:\n  "
        + "\n  ".join(offenders))


def test_item26_cached_search_results_keep_their_original_fetch_date(
        monkeypatch, tmp_path):
    """قاعدة الإسناد: نتيجةٌ من الذاكرة تحمل **تاريخ جلبها الأصلي** وتُعلنه.

    ختمُها بتاريخ اليوم يقدّم بياناتٍ عمرها ساعات على أنها جُلبت الآن — وهو
    ما يحظره `CLAUDE.md` صراحةً على كل قيمةٍ تُخدَم من مخزن (مراجعة §58).
    """
    import silk_data_layer
    import silk_websearch_agent

    class _R:
        status_code = 200
        headers: dict = {}

        def raise_for_status(self):
            pass

        def json(self):
            return _serper_payload()

    monkeypatch.setattr(silk_data_layer, "throttled_request",
                        lambda *a, **k: _R())
    with _env(SEARCH_API_KEY="k", SERPER_API_KEY=None,
              SILK_CACHE_DIR=str(tmp_path), SILK_SEARCH_CACHE_TTL_S="600"):
        live = silk_websearch_agent.web_search("تمور هولندا", num=1)
        cached = silk_websearch_agent.web_search("تمور هولندا", num=1)
    assert "من الذاكرة" not in str(live[0].source)
    assert "من الذاكرة" in str(cached[0].source), cached[0].source
    assert "جُلبت أصلاً" in str(cached[0].note)


def test_item26_a_cache_hit_is_not_also_counted_as_a_live_fetch(
        monkeypatch, tmp_path):
    """`data_economics` صدقٌ معروض للمالك: الإصابة ليست جلبةً حية أيضاً."""
    import silk_context
    import silk_data_layer
    import silk_websearch_agent

    class _R:
        status_code = 200
        headers: dict = {}

        def raise_for_status(self):
            pass

        def json(self):
            return _serper_payload()

    def _fake_request(*a, **k):
        # المسار المقوّى الحقيقي يعدّ كل محاولة (البند ٨ بعد مراجعة §58)،
        # فالمموّه يحاكي ذلك — وإلا قاس الاختبار غياب العدّ لا عدم ازدواجه.
        silk_context.count_data("live_fetches")
        return _R()

    monkeypatch.setattr(silk_data_layer, "throttled_request", _fake_request)
    counter = silk_context.begin_data_counter()
    with _env(SEARCH_API_KEY="k", SERPER_API_KEY=None,
              SILK_CACHE_DIR=str(tmp_path), SILK_SEARCH_CACHE_TTL_S="600"):
        silk_websearch_agent.web_search("تمور هولندا", num=1)   # جلبة حية
        silk_websearch_agent.web_search("تمور هولندا", num=1)   # إصابة ذاكرة
    assert counter["live_fetches"] == 1, counter
    assert counter["cache_hits"] == 1, counter


def test_item11_janitor_never_deletes_a_database_file_even_if_misconfigured(
        tmp_path):
    """حارسٌ صلب (مراجعة §58): `SILK_CACHE_DIR` موجَّهٌ خطأً لجذر الوحدة."""
    import silk_janitor
    db = tmp_path / "silk.db"
    stale_json = tmp_path / "abc.json"
    for f in (db, stale_json):
        f.write_text("x", encoding="utf-8")
        os.utime(f, (time.time() - 90 * 86400,) * 2)
    with _env(SILK_CACHE_DIR=str(tmp_path), SILK_CACHE_RETENTION_DAYS="7",
              SILK_RETENTION_DAYS=None, SILK_TRACE_RETENTION_DAYS=None,
              SILK_OPS_RETENTION_DAYS=None, SILK_TRACE_DIR=str(tmp_path / "t")):
        out = silk_janitor.sweep()
    assert db.exists(), "الكنّاس حذف قاعدة إنتاج — الحارس الصلب لا يعمل"
    assert not stale_json.exists()
    assert out["cache"] == 1


def test_item12_owner_key_comparison_survives_non_ascii(monkeypatch):
    """مفتاحٌ غير ASCII كان يقلب رفضاً مقصوداً (403) إلى 500 (مراجعة §58)."""
    import silk_export_gate
    with _env(SILK_OWNER_KEY="مفتاح-المالك"):
        assert silk_export_gate.override_authorized("مفتاح-المالك") is True
        assert silk_export_gate.override_authorized("مفتاح-خاطئ") is False
        assert silk_export_gate.override_authorized("ascii-key") is False


# ── البند ٧ — استخراج عنقود البحث من `api.py` (نقل حرفيّ) ───────────────────

def test_item7_pipeline_module_never_imports_api_back():
    """الاتجاه أحاديّ: `api` ← `silk_research_pipeline`، ولا عكس.

    العنقود كان إغلاقاً يقرأ خمسة مساعِدين من نطاق `api`. الحلّ الرخيص كان
    `import api` داخل الوحدة الجديدة — وهو يخلق دورةَ استيراد ويجعل الوحدة
    غير قابلة للاختبار معزولةً (وهو نصف سبب وجود البند أصلاً). الحقن عبر
    `build()` يمنع ذلك، وهذا الحارس يقفله بـAST لا بالثقة.
    """
    tree = ast.parse((_ROOT / "silk_research_pipeline.py").read_text(
        encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.split(".")[0] == "api"]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] == "api":
                offenders.append(node.module)
    assert not offenders, f"دورة استيراد: الوحدة تستورد api ({offenders})"


def test_item7_the_cluster_actually_left_api_py():
    """النقل وقع فعلاً: الدوالّ الثماني في وحدتها، وغائبة عن `api.py`."""
    api_src = (_ROOT / "api.py").read_text(encoding="utf-8")
    mod_src = (_ROOT / "silk_research_pipeline.py").read_text(encoding="utf-8")
    moved = ("_run_research_pipeline", "_collect_importer_leads",
             "_deep_engine_decision", "_attach_deep_market_row",
             "_research_budget_status", "_default_report_style",
             "_llm_error_retryable", "_stage_checkpoint")
    for name in moved:
        assert f"def {name}(" in mod_src, f"{name} لم تصل الوحدة الجديدة"
        assert f"def {name}(" not in api_src, f"{name} ما زالت مُعرَّفة في api.py"
    # الثلاث المشتركة بقيت حيث يستعملها باقي المسارات.
    for shared in ("_view", "_attach_quality_gate", "_attach_watchdog"):
        assert f"def {shared}(" in api_src, f"{shared} غادرت api.py بالخطأ"


def test_item7_logger_identity_is_preserved():
    """المُسجِّل يبقى «api» — نقلُ الشيفرة لا ينقل هويّة سجلّها.

    ضبطُه على اسم الوحدة الجديدة أسقط سطور `stage_transition` من كل مرشِّحٍ
    يرشّح على «api» (التقطه `test_wave_p6_pipeline_resilience` فوراً).
    """
    import silk_research_pipeline
    assert silk_research_pipeline.log.name == "api"


def test_item7_build_injects_exactly_the_five_helpers():
    """`build` يحقن ما كان العنقود يقرؤه من نطاق `api` — لا أكثر ولا أقل."""
    import inspect
    import silk_research_pipeline
    sig = inspect.signature(silk_research_pipeline.build)
    assert set(sig.parameters) == {"view_fn", "attach_quality_gate",
                                   "attach_watchdog", "to_jsonable",
                                   "early_halt_enabled"}
    for p in sig.parameters.values():
        assert p.kind is inspect.Parameter.KEYWORD_ONLY, (
            f"{p.name}: الوسائط مفتاحية عمداً — نداءٌ موضعيّ يخلط ترتيبها بصمت")


def test_item8_every_retry_attempt_is_counted_as_a_paid_fetch(monkeypatch):
    """إعادة المحاولة على مزوّدٍ يُحاسِب بالنداء إنفاقٌ فعليّ لا مجّاني.

    مراجعة §58: `live_fetches` كان يُزاد **مرّةً لكل نداءٍ منطقي** بينما
    المسار المقوّى قد يُخرِج حتى أربعة طلبات Serper مدفوعة — فيُبلَّغ المالك
    بربع إنفاقه. القاعدة: كل محاولة تُحسَب.
    """
    import requests
    import silk_context
    import silk_data_layer

    class _Resp:
        def __init__(self, code):
            self.status_code = code
            self.headers = {}

    seq = [_Resp(429), _Resp(429), _Resp(200)]
    monkeypatch.setattr(requests, "post", lambda url, **kw: seq.pop(0))
    monkeypatch.setattr(silk_data_layer, "_backoff_delay", lambda *a, **k: 0.0)
    counter = silk_context.begin_data_counter()
    with _env(SILK_HTTP_RETRIES="3", SILK_HTTP_MIN_GAP_MS="0"):
        silk_data_layer.throttled_request("POST", "https://example.test/paid",
                                          json_body={"q": "x"})
    assert counter["live_fetches"] == 3, counter


def test_item11_janitor_protects_a_sqlite_journal_not_just_the_db(tmp_path):
    """`splitext` كان يرى `.db-journal` امتداداً مختلفاً (مراجعة §58)."""
    import silk_janitor
    protected = [tmp_path / n for n in
                 ("silk.db", "silk.db-wal", "silk.db-journal", "seed.csv",
                  "dump.json.gz")]
    victim = tmp_path / "cache-entry.json"
    for f in protected + [victim]:
        f.write_text("x", encoding="utf-8")
        os.utime(f, (time.time() - 90 * 86400,) * 2)
    with _env(SILK_CACHE_DIR=str(tmp_path), SILK_CACHE_RETENTION_DAYS="7",
              SILK_RETENTION_DAYS=None, SILK_TRACE_RETENTION_DAYS=None,
              SILK_OPS_RETENTION_DAYS=None, SILK_TRACE_DIR=str(tmp_path / "t")):
        silk_janitor.sweep()
    for f in protected:
        assert f.exists(), f"الكنّاس حذف ملفاً محميّاً: {f.name}"
    assert not victim.exists()


def test_item10_swr_lock_exists_before_any_thread_races_for_it():
    """الإنشاء الكسول للقفل كان هو السباق نفسه (مراجعة §58)."""
    import silk_data_layer_v2 as v2
    assert v2._swr_lock is not None
    src = (_ROOT / "silk_data_layer_v2.py").read_text(encoding="utf-8")
    assert "_swr_lock = _threading.Lock()" in src
    assert "if _swr_lock is None:" not in src


# ── عودة CI الحيّة (2026-08-27) — عزل ذاكرة الطلبات ─────────────────────────

def test_request_cache_is_isolated_per_test_like_every_other_store():
    """المخزن الخامس يُعزَل كإخوته — الثقب الذي كشفه أوّل CI حيّ بعد شهر.

    **الحادثة (direct reproduction).** `block_network()` يرقّع `socket.socket`
    ويغلق الجلسة المجمّعة — ولا يلمس `silk_cache`. و`comtrade_trade`/
    `world_bank` يمرّان بـ`cached_get` الذي يقرأ JSON من القرص **بلا socket**.
    فعلى عاملٍ متّصل: أوّل جلبٍ حيّ يملأ `data/cache/`، ثم كلّ اختبار «بلا
    شبكة» بعده يقرأ قيماً حقيقية وتسقط تأكيداتُه. اثنا عشر اختباراً سقطت هكذا
    على أوّل تشغيلة CI حقيقية، وكلّها خضراء محلياً لأن شبكة الصندوق محجوبة.

    أُعيد إنتاجها محلياً بملء `data/cache/` يدوياً ⇒ سقطت نفس الاختبارات
    بالضبط؛ ثم أُغلقت بعزل `SILK_CACHE_DIR` في `_isolated_fact_store`.
    """
    import silk_cache
    cache_dir = silk_cache._cache_dir()
    assert cache_dir, "لا مجلّد ذاكرة محلول"
    # داخل الحزمة: المجلّد **مؤقّت**، لا `data/cache` في شجرة العمل.
    assert not os.path.abspath(cache_dir).startswith(
        os.path.abspath(str(_ROOT / "data"))), (
        f"ذاكرة الطلبات غير معزولة ({cache_dir}) — اختبارٌ متّصل سيسمّم "
        "كلّ اختبار «بلا شبكة» بعده")
    src = (_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert 'monkeypatch.setenv("SILK_CACHE_DIR"' in src, (
        "عزل ذاكرة الطلبات اختفى من conftest — الثقب يعود")


def test_block_network_alone_does_not_stop_the_on_disk_cache(tmp_path):
    """توثيقٌ تنفيذيّ للآلية: الذاكرة تُغني عن الشبكة، فالعزل شرطٌ لا تحسين.

    يُثبِت أنّ قراءةً من ذاكرة الطلبات تنجح **داخل** `block_network()` — وهو
    سبب وجوب عزل المجلّد لا الاكتفاء بحجب الـsockets.
    """
    import json as _json
    import silk_cache
    from conftest import block_network
    with _env(SILK_CACHE_DIR=str(tmp_path)):
        url, params = "https://example.test/x", {"a": "1"}
        path = os.path.join(str(tmp_path), silk_cache._key(url, params) + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            _json.dump({"real": "value"}, fh)
        with block_network():
            got = silk_cache.cached_get(url, params, ttl_seconds=86400)
    assert got == {"real": "value"}, (
        "قراءةُ الذاكرة لم تنجح داخل block_network — تغيّرت الآلية، "
        "راجع منطق العزل قبل تعديل هذا الاختبار")


def test_every_network_block_closes_the_pooled_session():
    """كل حاجب شبكة يغلق الجلسة المجمّعة — لا نسخةَ تتخلّف عن الإصلاح.

    **الحادثة (أوّل CI حيّ، 2026-08-27).** `silk_data_layer._session` جلسةٌ
    دائمة تجمّع اتصالات keep-alive؛ وإعادةُ استعمال اتصالٍ مفتوحٍ **لا
    تستدعي `socket.socket`**، فترقيعُه وحده لا يحجب شيئاً. `conftest` كان
    يعرف ذلك ويغلق الجلسة — ونسختاه في `tools/gen_analyze_samples.py`
    (التي يدّعي docstringها «نفس النمط») و`tests/test_gap_sweep3.py` لا
    تفعلان. النتيجة على عاملٍ متّصل: نداءات البنك الدولي تنجح **داخل**
    الحاجز (١٣ من ٢٠ في سجلّ CI) فتخرج العيّنة المُعاد بناؤها أغنى من
    الملتزَمة ويسقط قفل §10.6.

    نفس عائلة البند ٢ في التدقيق (إصلاحٌ يصل نسخةً من عدّة نسخ متطابقة).
    """
    offenders = []
    for rel in ("tests/conftest.py", "tools/gen_analyze_samples.py",
                "tests/test_gap_sweep3.py"):
        text = (_ROOT / rel).read_text(encoding="utf-8")
        if "def _block_network" not in text and "def block_network" not in text:
            continue
        if "_session.close()" not in text:
            offenders.append(rel)
    assert not offenders, (
        "حاجب شبكة بلا إغلاق الجلسة المجمّعة — ترقيع socket وحده يُخدَع "
        f"باتصالٍ keep-alive مفتوح: {offenders}")


def test_network_block_leaves_no_instance_shadow_on_the_shared_session():
    """حاجبُ الشبكة لا يترك ظِلَّ سمةٍ يُبطل ترقيعاً لاحقاً — انحدارٌ حقيقيّ.

    **الحادثة (2026-08-27، أُدخلت في هذه الموجة ثمّ أُصلحت).**
    `_session.request` دالّةُ **صنف**. إسنادُها على النسخة يُنشئ ظِلّاً في
    `_session.__dict__`، و«استعادةُ» الأصل بإعادة الإسناد **تُبقي الظِّلّ** —
    فيبطُل بعدها كلُّ `patch("requests.sessions.Session.request")` على هذه
    الجلسة المشتركة وتمرّ نداءاتُها للشبكة الحقيقية.

    الأثر المقيس على CI: `test_wave6_trend::…graceful_gaps` و
    `test_wave5a_discovery::…auth_and_shape` يسقطان في الحزمة (بعد أن يشتغل
    قفل §10.6 الذي يستدعي المولّد) وينجحان منفردَين — تبعيةُ ترتيبٍ رفض
    مصنّفُ CI تسميتها تقلُّباً، وكان محقّاً.

    الفحص مباشر وبصفر شبكة: لا ظِلّ بعد الخروج، والترقيع اللاحق نافذ فعلاً.
    """
    import sys
    sys.path.insert(0, str(_ROOT / "tools"))
    import silk_data_layer as dl
    from gen_analyze_samples import _block_network

    before = "request" in dl._session.__dict__
    with _block_network():
        pass
    assert ("request" in dl._session.__dict__) == before, (
        "حاجبُ الشبكة ترك ظِلَّ سمةٍ على الجلسة المشتركة — كلُّ "
        "patch('requests.sessions.Session.request') بعده لن يعمل")

    # التأكيد السلوكيّ: الترقيع على مستوى الصنف يصل الجلسة فعلاً.
    from unittest.mock import patch as _patch
    with _patch("requests.sessions.Session.request",
                side_effect=OSError("cut")):
        with pytest.raises(OSError):
            dl._session.get("https://example.invalid/x")
