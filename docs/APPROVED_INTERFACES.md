# الواجهات المعتمدة — Approved Silk interfaces

Implements the owner's approved landing, factory workspace and admin overview in the existing vanilla HTML/JavaScript application.

- `web/platform-landing.html`: centred pale-blue grid hero, downward-curved transition to white, dark rounded calls to action and a blue closing band. On 7 September the owner requested replacing the dashboard picture with a research animation. The hero now shows the twelve real project missions feeding one study, with readable navy text, white surfaces and Silk blue accents. `web/research-motion.css` supplies the responsive workflow and motion; pricing and both dashboard designs are preserved. The numeric marketing counters and time promises remain removed; three concise cards cover demand, competition/pricing and entry requirements.
- `web/pricing.html`: separate pricing page matching the approved blue-gradient, four-card design. Shared `web/marketing.js` loads actual prices, allowances and features from `/platform/pricing`. Annual equivalents retain cents, annual totals remain visible, and checkout links preserve the selected cycle. Removed the unsupported popularity label.
- `web/platform.html`: shared self-hosted Cairo typography and authentic Silk logo. Factory accounts open the studies workspace. Selecting a folder exposes its actual metadata, warnings and existing action buttons. The table remains available. Search, status filters, polling, reports and permissions retain their existing paths.
- Admin overview: three primary metric cards, monthly activity chart and recent studies, with plan distribution and the remaining three metrics in a secondary column. Missing values remain `—`; no new data or service-health claims. “Overview” appears once in navigation.
- Responsive layout rules retain RTL/LTR support, keyboard focus and reduced-motion preferences. These rules have not yet been visually verified in a browser.

## Evidence

**GitHub integration, 7 September 2026:** the owner explicitly authorized upload and merge into `hadadi2/556`. A separate checkout in `silk-556` is based on its actual `main` commit `e99117588d2ae20458c703a6c338cea7badc933e`; the base tree exactly matches the earlier local design branch's base. No other repository or uncommitted user work was modified. `researchCaption` is absent from the sources; the figure's description points to the existing `researchIntro` paragraph.

**Integration self-review (manual; `/code-review` command is unavailable here):** no unaddressed high-severity findings in this diff. Reviewed action identity and permission paths, study selection and loading/logout cleanup, pricing provenance, reduced motion and local asset dependencies. Found and fixed a navigation call that bypassed the intended factory default, with a regression failing before and passing after the fix. Updated the browser flow to check all six admin metrics in their actual three-plus-three layout and explicitly visit factory overview after verifying the studies workspace opens first. These checks preserve all existing values and actions.

**Local integration verification:** full suite after the final navigation correction: 4,822 passed, 63 skipped; syntax checks passed. GitHub remains the required real-server/browser, PDF, Docker and security gate. Manual visual inspection and production deployment acceptance remain separate from these automated checks.

**Browser integration follow-up:** the first GitHub run passed 28 live-flow tests and exposed one stale assumption in the bilingual report flow: it tried to launch a study from the table while the approved workspace showed folders. That flow now selects Table view through the visible control and waits for the table before using its existing exact study-id selectors. All launch, language-independence and final Arabic/English PDF assertions are retained. The complete GitHub gate is rerun for this test-only correction.

**Research-animation revision, 7 September 2026 — hermetic only:** 25 targeted tests passed. The diagram's twelve unique mission keys match the project catalog. Tests cover manual pause, tab visibility, offscreen suspension, reduced-motion changes, public CSS serving and the portable file containing all twelve agents and four pricing cards. The motion is explanatory, not a live study run; no requests, fabricated metrics or time estimates were added. The offline exporter embeds the new stylesheet as well as the fonts and reference images.

**Continuation, 7 September 2026 — hermetic only:** 24 targeted tests passed across marketing, landing, approved interfaces and portable export. Replaced the remaining generic closing/pricing headlines and corrected Arabic study-count grammar. No layout or price changes.

**Offline deliverable:** `tools/export_silk_preview.py` produces `Silk_Complete_Preview.html` from the actual marketing pages, the shared price renderer and checked-in pricing configuration. It embeds the fonts and supplied reference images and pre-renders all four cards before JavaScript runs. The gold plan's initial button now uses the same black style as the interactive renderer. The export fails on missing source markers, duplicate anchors or external links and never rewrites project sources. Verified four embedded images decode, all embedded font bytes match project files, and the complete inline script passes Node syntax checking. Font rendering itself is not browser-verified.

The two full dashboard images in the offline file are explicitly labelled approved design references, not screenshots of the implemented app or live account data. The actual dashboards remain in `web/platform.html` and require the application and an authenticated account.

**Visual inspection remains pending:** the supervised server preview could not start because this Python application has no supported Node dev-server configuration. The subsequent direct offline-file check was rejected by the cloud browser URL policy. No alternate browser route or hosting/dependency changes were used to bypass that restriction. No screenshots of the rendered implementation were obtained in this continuation.

**Final targeted verification:** 120 passed. Includes public serving of pricing/assets, shared pricing behavior, monthly/annual links and arithmetic, bilingual copy, existing platform contracts, folder actions, and the complete PDF cluster.

**Full suite:** 4,817 passed, 63 skipped, 2 failed on obsolete literal assertions for the former “الدخول إلى البوابة” label. Both assertions were updated to the new “تسجيل الدخول” copy while preserving the actual portal-link checks, and both files passed in the final 120-test verification. The full suite was not repeated after these test-only corrections.

**PDF environment repaired:** the existing Regular/Bold/SemiBold IBM Plex Sans Arabic font files were checked against `docker/fonts.sha256`, installed in the local font directory, and fontconfig refreshed. All 19 PDF-cluster tests now pass. No PDF/report production code was changed; Docker already provisions these fonts.

**Insufficient evidence — pending:** browser screenshots, real-server/browser end-to-end checks and deployment acceptance. The existing browser flow was extended for folder selection before switching to its established table workflow, but was not run here. Do not treat this branch as visually verified or deployed.

## Review boundary

No backend, database, authentication, study engine, report generation, plan limits or checkout behavior changes. No dependency added. Landing and dashboard use the supplied `web/silk-logo.png`; no externally hosted fonts or assets. Earlier remote-upload restrictions were superseded by the owner's explicit authorization to upload and merge into `hadadi2/556`. Merge must use the ordinary pull-request flow and successful checks, without force push or bypassing protection. This work does not itself verify a production deployment.

## Rebuild the portable file

Python 3 and Node are required only for export. Supply the two approved reference PNGs as input; the resulting HTML needs no sibling files or server.

```sh
python3 tools/export_silk_preview.py \
  --factory-reference /absolute/path/to/approved-factory.png \
  --admin-reference /absolute/path/to/approved-admin.png \
  --output /absolute/path/to/Silk_Complete_Preview.html \
  --date 2026-09-07
```

Prices in that file are a dated configuration snapshot. The running pricing page continues to request `/platform/pricing`, including any authorized database overrides.
