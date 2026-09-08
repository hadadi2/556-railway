# Feature: /research pipeline resilience — persist paid stages, stream heavy calls, truthful failure

**Goal:** a `/research` run never re-pays for a stage that already completed, never spends the writer on a dead analyst, never loses a paid stage to a timeout or a blob overwrite, and never tells the user money was returned when only a seat/reservation was released.

**Architecture:** extend the existing mission-checkpoint pattern (`silk_missions._checkpoint` → `silk_storage.save_mission_checkpoint`, `silk_missions.py:586`) to a sibling `research_stages` table; make `_run_research_pipeline` resumable per stage; stream the two heavy calls inside the provider seam (`silk_llm_provider.AnthropicProvider._post`) so callers only pass `stream=True`; writer truncation continues from the retained partial instead of regenerating; the platform bridge message reads the result, not a contextvar.

**Stack:** Python 3.14 stdlib + `requests`, FastAPI (`api.py`), SQLite (`silk_storage.py`), hermetic pytest with fake `requests.post` (pattern: `tests/test_wave_p5_writer_max_tokens_and_leaks.py::_resp`, `_env`).

**Evidence base:** Phase 1/2 audit (static code review, file:line) + owner-confirmed live branch (b): missions completed → analyst `ReadTimeout` swallowed → writer ran on the error string → `ReadTimeout` → `report=None` → `analyst_layer_failed` → platform seat released, USD ledger kept actual spend.

**Discipline (CLAUDE.md LAW):** TDD per task (RED → run → GREEN → run → locked files). One file per task; diff shown before the next task. No commits until the owner says so (repo rule). Honesty bucket for the final report: **hermetic only** unless rungs 2–3 are run.

**Locked contracts that must stay green (not negotiable):**
- `_LONG_TIMEOUT` default 300 / env-overridable; writer & analyst pass it; regular missions do not (`tests/test_wave_p1_ai_timeout_and_failure_reasons.py:75-125`, `tests/test_wave_p2_writer_trace_regen_sanitize.py:80,150`).
- `last_error` reset-at-start, `ReadTimeout` vs `ConnectTimeout` vs HTTP status+body (`tests/test_wave_p3_*`).
- Zero-text `max_tokens` escalation is bounded and traced per attempt (`tests/test_wave_p5_writer_max_tokens_and_leaks.py:151-180`, caps `[16000, 32000]`, `_MAX_TOKENS_RETRIES == 3`).
- Mission checkpoints + market stamp + `resume_market_mismatch` (`tests/test_wave13_resilience.py`, `tests/test_persistent_volume.py`, `tests/test_regression_registry.py::_guard_cross_market_checkpoint_leak`).
- Quality gate `analyst_layer_failed` semantics (`tests/test_wave_p1_*`).
- `docs/LESSONS.md` anchors (`tests/test_lessons_enforcement.py`).

**Test runner note:** full `python -m pytest tests/ -q` hangs on this Windows box (known); every task runs its own file + the locked files above, targeted.

---

## Tasks

### T1 — `silk_storage.py`: stage checkpoints + merge-not-overwrite (gaps #1, #6)

- File: `silk_storage.py`
- Test: `tests/test_wave_p6_pipeline_resilience.py` (new) —
  - `test_stage_checkpoint_roundtrip`: `save_stage_checkpoint(aid, "analyst", {"summary": "…"}, status="succeeded", market_iso3="NLD")` → `load_stage_checkpoints(aid)` returns `{"analyst": {"status": "succeeded", "payload": {...}, "completed_at": ...}}`; second save same key **replaces** (PK `(analysis_id, stage)`), never duplicates.
  - `test_stage_checkpoint_market_filter`: `load_stage_checkpoints(aid, market_iso3="KWT")` hides an `NLD` row; `NULL`-stamped legacy rows are not hidden (same contract as `load_mission_checkpoints`).
  - `test_mark_research_failed_merges_prior_blob` **(required test c)**: row with a full result blob `{product, deep_research:{missions,analyst,verdict}, data_economics}` → `mark_research_failed(aid, "X")` → blob still has every prior key, plus `status="failed"`, `error="X"`, `failed_at`; `status` column `failed`. Empty/NULL blob → today's small dict (unchanged behaviour). Corrupt JSON → today's small dict (no crash).
- Code:
  - `init_db`: `CREATE TABLE IF NOT EXISTS research_stages (analysis_id INTEGER NOT NULL, stage TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT, market_iso3 TEXT, completed_at TEXT, PRIMARY KEY (analysis_id, stage))` — additive, no ALTER on existing tables.
  - `save_stage_checkpoint(analysis_id, stage, payload, status="succeeded", market_iso3=None, path=None)` — `json.dumps(payload, default=_json_default)`, `INSERT … ON CONFLICT(analysis_id, stage) DO UPDATE`; touches `analyses.updated_at` like the mission checkpoint does.
  - `load_stage_checkpoints(analysis_id, market_iso3=None, path=None) -> dict[str, dict]`.
  - `mark_research_failed`: read `json_blob`; if it parses to a `dict`, `blob.update(status="failed", error=…, failed_at=now)` and write it back; else the current small dict.
- Command: `python -m pytest tests/test_wave_p6_pipeline_resilience.py -q -k "stage_checkpoint or mark_research_failed"` then `python -m pytest tests/test_wave13_resilience.py tests/test_persistent_volume.py tests/test_regression_registry.py -q`
- Expected: RED — `AttributeError: module 'silk_storage' has no attribute 'save_stage_checkpoint'` and merge test fails on missing `product` key; GREEN after code; locked files green.
- Commit (deferred to owner): "نقاط تفتيش المراحل + الدمج لا الاستبدال في mark_research_failed"

### T2 — `api.py`: persist analyst/verdict/leads the moment they return; reconcile exactly once (gaps #1, #7)

- File: `api.py` (`_run_research_pipeline`)
- Test: same file —
  - `test_pipeline_checkpoints_analyst_verdict_leads`: drive `_run_research_pipeline` through the FastAPI app with a fake provider (analyst returns a valid findings JSON, writer returns text) and `persist=True`; after the run, `load_stage_checkpoints(aid)` has `analyst` (payload = `to_synthesis_input(analyst_out)` + `raw_report` serialized like a mission report, status `succeeded`), `verdict` (payload = `_to_jsonable(verdict)` after `promote_engine_verdict`/cap), `leads` (payload = `importer_leads`). Order assertion: the `analyst` row's `completed_at` exists **before** the writer fake is first called (record a timestamp in the writer fake).
  - `test_usd_reservation_released_exactly_once` **(required test d)**: `SILK_PAID_DAILY_USD_CAP=10`, `SILK_RESEARCH_EXPECTED_USD=3.0`, fake usage → actual ≈ 1.0; monkeypatch `_attach_quality_gate` to raise after `reconcile_usd` ran; sync `/research` returns 500; `silk_usage.usd_spent_today()` == 1.0 (not −1.0/0.0 floored), i.e. delta applied once; `progress_json.usd_reconciled is True`.
- Code:
  - After `analyst_out = analyze_market(...)` (`api.py:1634`): `_stage_checkpoint(analysis_id, "analyst", {..}, status="failed" if analyst_out["diagnostics"]["analyst_failed"] else "succeeded", market_ref.iso3)` — a local helper mirroring `silk_missions._checkpoint` (try/except-swallow, log warning; checkpoint is an improvement, never a run condition).
  - After the HS-cap step (`api.py:1690`): `_stage_checkpoint(analysis_id, "verdict", _to_jsonable(verdict))`.
  - After `importer_leads = …` (`api.py:1671`): `_stage_checkpoint(analysis_id, "leads", importer_leads)`.
  - After `silk_usage.reconcile_usd(...)` (`api.py:1766`): `silk_storage.update_research_progress(analysis_id, usd_reconciled=True)` when `analysis_id` is not None.
- Command: `python -m pytest tests/test_wave_p6_pipeline_resilience.py -q -k "checkpoints_analyst or exactly_once"` then `python -m pytest tests/test_wave_p1_ai_timeout_and_failure_reasons.py tests/test_wave_p2_writer_trace_regen_sanitize.py tests/test_wave13_resilience.py -q`
- Expected: RED — no `analyst` stage row; ledger shows the delta twice (≈ −1.0 → floored 0.0); GREEN after code.
- Commit (deferred): "حفظ المحلل والحكم والروابط فور عودتها + مصالحة الدولار مرّة واحدة"

### T3 — `api.py`: hard-fail the analyst — no writer on an error string; persist what exists; return partial (gaps #4, #12)

- File: `api.py` (`_run_research_pipeline`)
- Test: same file —
  - `test_analyst_timeout_does_not_invoke_writer` **(required test a)**: fake provider: missions succeed; the analyst call (identified by the `_ANALYST_MISSION` system prompt or `allowed_tools=[]`) raises `requests.exceptions.ReadTimeout` inside `requests.post`; writer fake counts calls. Assert writer calls == 0; `result["deep_research"]["report"] == {"report": None, "review_cycles": 0, "unresolved_notes": [], "failure_reason": <contains "ReadTimeout">, "skipped": "writer", "skip_reason": "analyst_call_failed", "error_type": "ReadTimeout", "retryable": True}`; `deep_research.missions` has 12 keys; `deep_research.verdict` present (jury stage 1 still runs); `research_stages.analyst.status == "failed"`; run stored `completed`; ops log has `analyst_failure`; quality gate still yields `analyst_layer_failed` (unchanged semantics).
  - `test_analyst_permanent_error_is_not_retryable`: same with HTTP 400 → `retryable False`, `error_type "HTTPError"`, `status_code 400` carried.
  - `test_analyst_uncategorized_findings_still_reach_writer`: analyst returns findings with no `[category]` tags (`all_missing_cause == "findings_present_but_uncategorized"`) → writer **is** called (only a failed *call* skips it).
- Code:
  - Immediately after `analyze_market` returns: `_analyst_err = silk_llm_provider.last_error()` (read before any other LLM call).
  - `analyst_call_failed = analyst_out["diagnostics"].get("all_missing_cause") == "analyst_call_failed"`.
  - If `analyst_call_failed`: `report_out = {"report": None, "review_cycles": 0, "unresolved_notes": [], "failure_reason": failure_reason(), "skipped": "writer", "skip_reason": "analyst_call_failed", "error_type": …, "status_code": …, "retryable": _retryable(_analyst_err)}`; `silk_ops_log.record_error("analyst_failure", …)`; **do not** call `write_reviewed_report`. Everything else (synthesis stage 1, engine decision, leads, view, gate, save) runs as today.
  - `_retryable(err)`: type in `{"ReadTimeout","ConnectTimeout","ConnectionError"}` or `status_code in {408, 429, 500, 502, 503, 529}` → True; `refusal`, 4xx otherwise → False; unknown → True (conservative: allow a regen).
  - Stage-2 synthesis `with_ai` is left as today (cheap, and it has the jury fallback) — scope discipline.
- Command: `python -m pytest tests/test_wave_p6_pipeline_resilience.py -q -k "analyst_timeout or permanent_error or uncategorized"` then `python -m pytest tests/test_wave_p1_ai_timeout_and_failure_reasons.py -q`
- Expected: RED — writer called once; GREEN after code; `analyst_layer_failed` tests unchanged.
- Commit (deferred): "فشل المحلل يوقف الكاتب لا يُطعِمه نصَّ الخطأ — نتيجة جزئية محفوظة"

### T4 — `api.py`: resume reuses persisted stages; regen reads them; failed rows return partial data (gaps #1, #2)

- File: `api.py` (`_research_impl`, `_run_research_pipeline`, `POST /analyses/{id}/report`, `GET /analyses/{id}`)
- Test: same file —
  - `test_resume_reuses_persisted_analyst_and_does_not_rerun_missions` **(required test b)**: seed a `completed` research row with 12 succeeded mission checkpoints, an `analyst` stage (`succeeded`), no report text; `POST /research {"resume": id}` with a fake provider that **fails** any mission/analyst-shaped call and counts writer calls → `deep_research` not called (patch `silk_missions.deep_research` to raise), `analyze_market` not called (patch to raise), writer called once, response `analysis_id == id`, report text present.
  - `test_resume_reruns_failed_analyst_only`: same seed but `analyst` stage `failed` → `analyze_market` called once, `deep_research` not called.
  - `test_completed_with_report_is_pure_replay`: seed with report text → zero provider calls (today's contract, `api.py:2201-2207`).
  - `test_regen_endpoint_prefers_stage_checkpoint`: blob's `dr.analyst` absent but stage row present → writer receives the stage summary.
  - `test_get_failed_analysis_returns_partial_missions`: `mark_research_failed` on a row whose blob lacks `deep_research` → `GET /analyses/{id}` carries `deep_research.missions` (from checkpoints) and `partial: True`.
- Code:
  - `_run_research_pipeline(..., resume_stages: dict | None = None)`: if `resume_reports` covers all 12 `MISSION_ORDER` keys with none failed → skip `deep_research` (reuse dict; `trace_id` from the stored result or a new `resume-{id}` trace). If `resume_stages["analyst"]` exists with `status == "succeeded"` → rebuild `analyst_out`/`analyst_input` from payload, skip `analyze_market` (still checkpoint nothing new). Verdict is **recomputed** (deterministic jury + one cheap call; keeps live `DataPoint` objects for `build_view`), leads reused when the `leads` stage exists.
  - `_research_impl` resume branch (`api.py:2201-2207`): replay only when `deep_research.report.report` is non-empty; otherwise load `load_stage_checkpoints(id, market_iso3=…)` and fall through.
  - `POST /analyses/{id}/report`: `analyst_summary` from the `analyst` stage payload when present (fallback: blob as today).
  - `GET /analyses/{id}`: for `kind == "research"` rows with `status == "failed"` and no `deep_research.missions` in the blob, attach `{"deep_research": {"missions": checkpoints, "stages": stage rows}, "partial": True}` — read-time only, no DB writes.
- Command: `python -m pytest tests/test_wave_p6_pipeline_resilience.py -q -k "resume or regen_endpoint or partial_missions"` then `python -m pytest tests/test_wave13_resilience.py tests/test_wave_p2_writer_trace_regen_sanitize.py tests/test_regression_registry.py -q`
- Expected: RED — `analyze_market` raises from the patch (it was called); GREEN after code.
- Commit (deferred): "الاستئناف يعيد استعمال المحلل المحفوظ — لا دفع مرّتين"

### T5 — `silk_llm_provider.py`: stream the heavy calls (gap #5 — root fix)

- File: `silk_llm_provider.py`
- Test: `tests/test_wave_p6_streaming_provider.py` (new, hermetic) —
  - `test_streamed_complete_tools_matches_non_streamed_shape`: fake `requests.post` asserting `kw["stream"] is True` and `kw["json"]["stream"] is True`, returning an object whose `iter_lines()` yields SSE (`message_start` with `usage.input_tokens`, `content_block_start` text, `content_block_delta` `text_delta` ×3, `content_block_start` tool_use, `content_block_delta` `input_json_delta` ×2, `content_block_stop`, `message_delta` with `stop_reason="tool_use"` + `usage.output_tokens`, `message_stop`) → returned dict has `content=[{"type":"text","text":"…"},{"type":"tool_use","id":…,"name":…,"input":{…}}]`, `stop_reason`, `usage` → identical to what `complete_tools(stream=False)` returns for the equivalent JSON.
  - `test_streamed_complete_returns_text_and_stop_reason_and_usage`: `complete(..., stream=True)` → text; `last_stop_reason() == "end_turn"`; `silk_context` counter received `input/output` tokens once.
  - `test_streamed_idle_timeout_returns_partial_and_flags`: `iter_lines` raises `requests.exceptions.ReadTimeout` after two deltas → `complete` returns the partial text, `last_stop_reason() == "aborted_timeout"`, `last_error()["type"] == "ReadTimeout"`.
  - `test_streamed_total_ceiling_aborts`: monkeypatch `time.monotonic` to jump past `SILK_AI_STREAM_TOTAL_S` → partial returned, `last_error()["type"] == "StreamTotalTimeout"`.
  - `test_default_is_non_streamed_and_unchanged`: `stream` omitted → `requests.post` called without `stream=True` and without `"stream"` in the payload (existing p3/p5 tests stay green).
  - `test_stream_retry_only_before_first_byte`: `ConnectTimeout` on first attempt → retried; once bytes have arrived, a `ReadTimeout` is **not** retried.
- Code:
  - `complete(..., stream=False)` / `complete_tools(..., stream=False)` / `_post(..., stream=False)`.
  - Streamed branch: `payload["stream"] = True`; `requests.post(..., stream=True, timeout=(min(10, t), _stream_idle_s()))`; iterate `resp.iter_lines(decode_unicode=True)`, parse `event:`/`data:` pairs, assemble `{"content": [...], "stop_reason": ..., "usage": {...}}`; total ceiling `_stream_total_s()` checked per event; on idle/total abort close the response, set `_last_error`, set `_last_stop_reason = "aborted_timeout"` and **return the partial assembly** (complete → partial text; complete_tools → partial dict).
  - Envs: `SILK_AI_STREAM_IDLE_S` (default 120), `SILK_AI_STREAM_TOTAL_S` (default 900). The caller's `timeout` argument is still received and recorded (locked trace field), used as the floor of the total ceiling: `total = max(timeout, SILK_AI_STREAM_TOTAL_S)`.
  - `_record_usage` fed from `message_start.usage` + `message_delta.usage`.
  - HTTP error on a streamed request (non-2xx before body) → `raise_for_status` as today (retry policy for 429/529 unchanged).
- Command: `python -m pytest tests/test_wave_p6_streaming_provider.py tests/test_wave_p3_writer_diagnostics_and_json_leak.py tests/test_wave_p5_writer_max_tokens_and_leaks.py -q`
- Expected: RED — `TypeError: complete_tools() got an unexpected keyword argument 'stream'`; GREEN after code; p3/p5 untouched.
- Commit (deferred): "بثّ نداءي المحلل والكاتب — مهلة خمول لا جدار ٣٠٠ث"

### T6 — `silk_llm_runtime.py` + `silk_market_analyst.py`: thread `stream=True` to the analyst only

- Files: `silk_llm_runtime.py` (`run_llm_agent`, `_run_loop`), `silk_market_analyst.py` (`analyze_market`) — two files, two diffs, one task (the change is a single kwarg threaded through).
- Test: `tests/test_wave_p6_pipeline_resilience.py` —
  - `test_analyst_passes_stream_true_regular_mission_does_not`: patch `silk_llm_runtime._call_tools` to capture kwargs → `analyze_market` → `stream is True`; `run_llm_agent(MISSIONS["pricing_scout"], …)` → `stream` False/absent (sibling of `test_regular_mission_still_uses_default_timeout_not_long_one`).
  - `test_analyst_partial_on_aborted_timeout_is_parsed_or_declared`: `_call_tools` returns a partial dict with `stop_reason="aborted_timeout"` and truncated JSON text → `_run_loop` tries `_parse_output`; unparseable → gap text names the abort; parseable → findings kept.
- Code: `_call_tools(..., stream=False)` in `silk_ai_judge.py` is **not** touched here — `silk_llm_runtime` imports it; add `stream: bool = False` to `run_llm_agent`/`_run_loop` and pass it on; `analyze_market` passes `stream=True`. (`silk_ai_judge._call`/`_call_tools` gain the pass-through kwarg in T7.)
- Command: `python -m pytest tests/test_wave_p6_pipeline_resilience.py -q -k "stream_true or aborted_timeout"` then `python -m pytest tests/test_wave_p1_ai_timeout_and_failure_reasons.py -q`
- Expected: RED — kwarg missing; GREEN after code.
- Commit (deferred): "المحلل يبثّ؛ البعثات كما هي"

### T7 — `silk_ai_judge.py`: writer continues from the partial instead of regenerating; per-attempt snapshot; stream (gaps #3, #11)

- File: `silk_ai_judge.py` (`deep_report`, `_continue_truncated_report`, `write_reviewed_report`, `_call`, `_call_tools`)
- Test: `tests/test_wave_p6_writer_continuation.py` (new) —
  - `test_truncation_with_text_continues_instead_of_regenerating` **(required test e)**: first call returns `stop_reason="max_tokens"` with 3 of 11 sections; assert the second call's prompt contains the continuation marker and the tail of attempt 1, `max_tokens == _MAX_TOKENS_CEILING`, and **no** call re-sends the bare draft prompt; final text = draft + continuation; trace stages `["draft", "draft_continue"]`.
  - `test_continuation_is_capped`: continuation still truncated → at most `SILK_WRITER_CONTINUATIONS` (default 2) continuation calls, then the §5 contract (`None`, partial persisted via the returned `partial_text` field — see below).
  - `test_zero_text_max_tokens_still_escalates` — keeps `tests/test_wave_p5…::test_writer_escalation_is_bounded_and_traces_each_attempt` semantics: `content: []` → regeneration at doubled cap (the only case where there is nothing to continue).
  - `test_on_attempt_fires_before_every_writer_call`: `write_reviewed_report(..., on_stage=cb)` → `cb("writer")` called once per draft attempt **and** per continuation (so `snapshot_research_progress` refreshes `updated_at` between attempts).
  - `test_writer_passes_stream_and_long_timeout`: captured `_call` kwargs → `stream is True` and `timeout == _LONG_TIMEOUT` (locked field intact).
  - `test_aborted_timeout_partial_enters_continuation`: streamed partial with `last_stop_reason() == "aborted_timeout"` → continuation path, not `None`.
- Code:
  - `_call(..., stream=False)` / `_call_tools(..., stream=False)` pass-through to the provider.
  - `deep_report`: attempt 1 at `_WRITER_MAX_TOKENS` with `stream=True`. If `stop_reason in {"max_tokens", "aborted_timeout"}` **and** `best` is non-empty → `_continue_truncated_report` loop, capped by `SILK_WRITER_CONTINUATIONS` (default 2), each continuation traced as `draft_continue{n}` and preceded by `on_attempt("writer")`. If `best` is empty (zero-text) → today's doubled-cap regeneration (unchanged, `_MAX_TOKENS_RETRIES` stays 3, caps `[16000, 32000]`). §5 "no partial delivery" kept: still-incomplete → `None`, but `write_reviewed_report` returns `partial_text` alongside so `api.py` can checkpoint it as stage `writer_partial` (T9 wires it) — paid text is never discarded from disk even when it is not delivered.
  - `deep_report(..., on_attempt=None)`; `write_reviewed_report` passes `on_attempt=lambda: _stage("writer")`.
- Command: `python -m pytest tests/test_wave_p6_writer_continuation.py tests/test_wave_p5_writer_max_tokens_and_leaks.py tests/test_wave_p2_writer_trace_regen_sanitize.py tests/test_wave_p1_ai_timeout_and_failure_reasons.py -q`
- Expected: RED — second call re-sends the draft prompt at 32000; GREEN after code; p5 zero-text test still green.
- Commit (deferred): "الكاتب يُكمِل من الجزء المحفوظ لا يعيد التوليد — لقطة تقدّم لكل محاولة"

### T8 — `silk_synthesis.py`: explicit timeout + error capture (gap #10)

- File: `silk_synthesis.py`
- Test: `tests/test_wave_p6_pipeline_resilience.py` —
  - `test_synthesis_stage2_uses_long_timeout_and_records_error`: patch `silk_ai_judge._call` capturing kwargs → `timeout == _LONG_TIMEOUT`; when it returns `None` with `last_error={"type":"ReadTimeout"}` → `verdict["ai_error"] == {"type": "ReadTimeout", ...}` and the jury verdict is unchanged.
- Code: `_call(_PRINCIPLE, ..., max_tokens=900, timeout=_LONG_TIMEOUT)`; on `None`, `verdict["ai_error"] = last_error()`.
- Command: `python -m pytest tests/test_wave_p6_pipeline_resilience.py -q -k synthesis_stage2` then `python -m pytest tests/test_smoke.py -q -k synth`
- Expected: RED — `timeout` missing from kwargs; GREEN after code.
- Commit (deferred): "مهلة صريحة لحكم المرحلة ٢ + تسجيل سبب فشله"

### T9 — `api.py`: budget guard at stage boundaries + structured stage log + writer-partial checkpoint (gaps #9, #13)

- File: `api.py`
- Test: `tests/test_wave_p6_pipeline_resilience.py` —
  - `test_budget_guard_halts_before_writer_with_clear_message`: `SILK_RESEARCH_MAX_USD=0.01`, fake usage making the analyst cost 0.02 → writer not called; `budget_status == {"exhausted": True, "caps_hit": ["SILK_RESEARCH_MAX_USD=0.01"], "halted_before": "writer", "message": <Arabic, no env-var jargon in the client view>}`; stages persisted; run `completed`.
  - `test_daily_usd_cap_halts_mid_run`: `SILK_PAID_DAILY_USD_CAP` nearly exhausted → same shape with `caps_hit=["SILK_PAID_DAILY_USD_CAP=…"]`.
  - `test_stage_transition_logs_and_progress`: caplog has `stage_transition analysis_id=<id> stage=analyst duration_s=… tokens_in=… tokens_out=… cost_usd=…` for every transition; `progress_json.stage_seconds` accumulates per stage; trace has `kind="stage"` events with the same fields; final `economics["stage_seconds"]` equals today's values (no regression in `stage_top_sinks`).
  - `test_writer_partial_is_checkpointed`: writer returns `None` with `partial_text` → `research_stages.writer_partial` row exists.
- Code:
  - `_stage_mark(stage)` helper replaces the five bare `_stage_marks[...] = _mono.monotonic()` lines: records the mark, computes the previous stage's duration and token/cost delta from `silk_context.data_counter()`, `log.info(...)`, `silk_trace.append_event(trace_id, kind="stage", ...)`, `update_research_progress(analysis_id, stage_seconds=...)`.
  - `_budget_ok(stage)` before analyst, before synthesis stage 2 (`with_ai`), before writer: per-run `SILK_RESEARCH_MAX_USD` (unset = off) and daily `silk_usage.would_exceed_usd_cap(0.0)` using `estimate_cost_usd(counter["llm_usage"])`. Breach → skip the paid call (`tail_with_ai=False` / `report_out` with `skipped: "writer", skip_reason: "budget"`), never abort a call in flight.
  - `budget_status` from `_research_budget_status` extended with `halted_before` + `message`; `silk_render` already strips internal plumbing from client text (`_strip_internal_plumbing`) — reuse for `message`.
  - Checkpoint `writer_partial` when `report_out.get("partial_text")`.
- Command: `python -m pytest tests/test_wave_p6_pipeline_resilience.py -q -k "budget or stage_transition or writer_partial"` then `python -m pytest tests/test_wave_p1_ai_timeout_and_failure_reasons.py tests/test_wave13_resilience.py -q`
- Expected: RED — writer called despite cap; no `stage_transition` log lines; GREEN after code.
- Commit (deferred): "حارس ميزانية عند حدود المراحل + سجلّ انتقال مهيكل"

### T10 — `silk_platform/engine_bridge.py` (+ one call site in `silk_platform/api.py`): truthful message; relaunch resumes (gaps #2, #8)

- Files: `silk_platform/engine_bridge.py`; `silk_platform/api.py` (one kwarg at `:1341`); `api.py` `_platform_deep_run` (one kwarg → `ResearchRequest(resume=...)`). Three diffs, shown separately.
- Test: `tests/test_wave_p6_platform_bridge.py` (new) —
  - `test_empty_reason_never_claims_money_returned`: result from branch (b) (`report.failure_reason` mentions ReadTimeout, `skip_reason`/`error_type` present, `data_economics.cost_usd_estimate=1.87`) → message contains "أُرجع مقعد الإطلاق", contains "التكلفة الفعلية المسجَّلة 1.87$", contains "لا تُستردّ", names the failed layer from the result (not from `silk_llm_provider.last_error()` — set the contextvar to a different type in the test and assert it is **not** echoed), and says relaunch resumes from the saved run. Nothing says "أُرجعت الحصة" alone.
  - `test_finish_failure_stores_analysis_id_when_result_was_saved`: `_finish_failure(..., analysis_id=42)` → `studies.analysis_id == 42`, state `draft`, seat released once (existing rowcount guard).
  - `test_relaunch_passes_resume_when_study_has_prior_analysis`: fake gateway runner capturing kwargs; study row with `analysis_id=42`, same product/market → `resume == 42`; different market → no `resume`.
  - `test_platform_deep_run_threads_resume`: `_platform_deep_run(..., resume=42)` builds `ResearchRequest(resume=42, ...)`.
- Code:
  - `_empty_reason(result)`: read `deep_research.report.{failure_reason, skip_reason, error_type, retryable}` and `data_economics.cost_usd_estimate`; drop the `last_error()` read.
  - `_finish_failure(..., analysis_id=None)`: `UPDATE studies SET … analysis_id = COALESCE(?, analysis_id)`; `_thread_body` passes `(result or {}).get("analysis_id")` on the "not substantive" branch.
  - `run_study_async(..., resume_analysis_id=None)` → `_thread_body` → `_run_engine` → `_run_engine_deep(kwargs["resume"]=…)` only when `_runner_takes(runner, "resume")`; `silk_platform/api.py:1341` passes `study.get("analysis_id")` when `study.market_pref`/`product` unchanged since that analysis (compare against the stored request snapshot via `get_research_run`).
  - Seat-release policy untouched.
- Command: `python -m pytest tests/test_wave_p6_platform_bridge.py tests/test_platform_pivot_deletion_guard.py -q` then `python -m pytest tests/ -q -k "platform and (launch or study)" --timeout 120` (targeted; if it hangs, list the platform files and run them individually)
- Expected: RED — message still "أُرجعت الحصة"; `resume` absent; GREEN after code.
- Commit (deferred): "رسالة الفشل تقول الحقيقة: مقعدٌ أُرجع والتكلفة مسجَّلة — وإعادة الإطلاق تستأنف"

### T11 — docs + locks (house rule, CLAUDE.md «التحديث الذاتي»)

- Files: `docs/LESSONS.md` (one row: «المرحلة المدفوعة تُحفَظ فور عودتها — الكاتب لا يُطعَم نصّ الخطأ — الإكمال من الجزء لا إعادة التوليد»), `tests/test_lessons_enforcement.py` (anchor: `silk_storage.save_stage_checkpoint`, `api._retryable`/skip branch, `silk_ai_judge` continuation cap), `docs/DEEP_RESEARCH_DECISIONS.md` (ledger entry, Arabic, claims anchored to file:line, deviations declared: verdict recomputed on resume; seat policy unchanged; `_MAX_TOKENS_RETRIES` unchanged), `.claude/skills/writer-timeout-open-case/SKILL.md` (streaming now evidence-justified by branch b; new decision-table row for `aborted_timeout`).
- Command: `python -m pytest tests/test_lessons_enforcement.py -q`
- Expected: green; anchors resolve.
- Commit (deferred): "درسٌ جديد + قفله: لا مرحلة مدفوعة بلا نقطة تفتيش"

---

## Verification (before any "done" claim)

1. Per task: its test file RED → GREEN, then the locked files listed in the task.
2. End: `python -m pytest tests/test_wave_p6_pipeline_resilience.py tests/test_wave_p6_streaming_provider.py tests/test_wave_p6_writer_continuation.py tests/test_wave_p6_platform_bridge.py tests/test_wave_p1_ai_timeout_and_failure_reasons.py tests/test_wave_p2_writer_trace_regen_sanitize.py tests/test_wave_p3_writer_diagnostics_and_json_leak.py tests/test_wave_p5_writer_max_tokens_and_leaks.py tests/test_wave13_resilience.py tests/test_persistent_volume.py tests/test_regression_registry.py tests/test_lessons_enforcement.py tests/test_smoke.py -q`
3. `/code-review` on the working diff (§58); every high+ finding fixed or logged as accepted risk in the ledger.
4. Honesty bucket in the final report: **hermetic only** unless rung 2 (`SILK_RUN_E2E=1 pytest tests/test_rung2_real_server.py`) and rung 3 (Playwright) are run and green — owner decides whether I attempt them on this machine.
5. Manual verification recipe for the owner (cheap, no full research): `POST /analyses/{id}/report` on the branch-(b) analysis id → writer runs once over the saved analyst stage; `GET /research/{id}/status` shows `stage_seconds`; trace shows `kind="stage"` events and `stream: true` on `report_call`.

## Out of scope (explicitly)
USD-ledger semantics; seat-release policy; mission loop/budgets; `_LONG_TIMEOUT` default; `_MAX_TOKENS_RETRIES`; any render-path change beyond `partial`/`budget_status` fields; Postgres; style refactors.
