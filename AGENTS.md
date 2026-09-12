# Silk agent guide

Work to a verified outcome, not a first draft. Inspect only the files and guidance
relevant to the requested path; expand scope when evidence shows a dependency.

## Permanent boundaries

- Never fabricate data. Missing values remain `None` with confidence `0.0` and a
  declared note.
- SQLite stays. Do not recreate deleted prospecting/outreach or `silk_snapshot.py`.
- Preserve existing data and the canonical render path through
  `silk_render.build_view`.
- Do not merge, deploy, change production/Railway configuration, enable paid calls,
  or add paid services without the owner's explicit approval.

## Completion

Implement the requested change, run the smallest relevant tests, fix failures caused
by the change, and rerun them. Use the full suite and live-server/browser rungs only
when the affected surface or release claim requires them. Report the evidence level:
hermetic only, real-server/browser verified, or insufficient evidence.

Before a PR, run the repository self-review gate and resolve or explicitly record all
high-or-higher findings. Never call work production-ready from hermetic tests alone.

## Context router

- Architecture or multi-module boundaries: `docs/ARCHITECTURE.md` and
  `.claude/skills/architecture-map/SKILL.md`.
- Known regression or a new guard: relevant rows in `docs/LESSONS.md`, then
  `tests/test_regression_registry.py`.
- Live verification or deployment: `docs/LIVE_PROOF_RUNBOOK.md` and
  `.claude/skills/railway-operations/SKILL.md`.
- Prompt or mission changes: `.claude/skills/mission-tuning-and-evals/SKILL.md`.
- Report/render changes: `.claude/skills/render-view-and-reports/SKILL.md`.
- Tests: `.claude/skills/testing-discipline/SKILL.md`.
- PR preparation: `.claude/skills/pr-and-wave-discipline/SKILL.md`.

For other workflows, use `.claude/skills/README.md` as a router. Do not read every
document or skill before routine edits.
