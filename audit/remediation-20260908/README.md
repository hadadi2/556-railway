# Remediation verification snapshots

These manifests record the local verification state when each suite ran on
2026-09-08. Their state labels and file checksums describe those snapshots;
they are not a claim about the current GitHub or Railway deployment state.
The corresponding source changes were subsequently merged in PR #3 as
`a548e6ab8a88919015601839585044a937cc353e`.

## Manifest format version 2

Post-merge CI job `101991777027` reported two false positives under the
`generic-api-key` rule in gitleaks v8.24.3: the `api.py` filename directly
labelled a SHA-256 digest in each JSON dictionary. The earlier exceptions
identified the original commit, so they did not match its squash commit.

Version 2 represents `changed_files_sha256` as a list of objects with `path`
and `sha256` fields. All 53 original verification pairs and all 54 double-check
pairs are preserved, along with every other captured field. The upstream
generic rule matched once in each old document and zero times in each new
document. This is a targeted regex reproduction; the full pinned gitleaks
scan remains a required CI check.

The exceptions in `.gitleaksignore` identify only the two reviewed lines in
each historical commit. There is no path-wide or rule-wide exclusion. The
original forensic evidence under `audit/20260908/` is unchanged.

Reproduce the data-preservation check from the repository root:

```python
import json
import subprocess
from pathlib import Path

baseline = "a548e6ab8a88919015601839585044a937cc353e"
for name in ("verification.json", "double-check-verification.json"):
    path = Path("audit/remediation-20260908") / name
    old = json.loads(subprocess.check_output(["git", "show", f"{baseline}:{path}"]))
    new = json.loads(path.read_text())
    assert new.pop("manifest_format_version") == 2
    entries = new["changed_files_sha256"]
    restored = {entry["path"]: entry["sha256"] for entry in entries}
    assert len(entries) == len(restored)
    new["changed_files_sha256"] = restored
    assert new == old
    print(name, len(entries), "unchanged path/checksum pairs")
```

## Deployment verification limit

Railway's current project/service, deployed commit and live start command have
not been verified. GitHub test, production-switch, browser/PDF and Docker
health checks passed for the source merge; that does not prove deployment to
Railway. The historical host in `docs/ANALYSIS.md` could not be inspected from
this environment. A current project or service link is needed to resolve the
production mapping, including which GitHub repository it deploys.
