# Five apps in one day

**2026-09-30.** One developer, one agent fleet, five App Store submissions
finished end-to-end in a single day: **Adhera, Pushup Alarm, REM Sleep Alarm,
InCase, RenewalRadar** — with Quilly v1.0.1 (a subscription migration riding
the same pipeline) following the same evening. No click-by-click web dances.
This is what happened, from the artifacts left in the wake (every script named
here exists, timestamped, in the working tree).

## The night before the day

The foundation had been accumulating for weeks in
[ios-launch-kit](https://github.com/rorshopping/ios-launch-kit): a JWT-signing
ASC client with retry doctrine, a 5-blocker version setup script, a
subscription bootstrap that binary-searches price points, an IPA preflight
linter, and metadata folders for 14 app slots. What the day itself added was
the last mile — the actual submission — and the scars that became Shipside.

## The day, in failures

**Adhera — the age rating refused.** The submission was assembled: build
attached, review submission created, item added. Apple bounced it. The age
rating questionnaire turned out to be *almost* scriptable —
`PATCH /v1/ageRatingDeclarations` — but it validates exactly one attribute per
error. `adhera_age2.py` → `adhera_age_final.py`: a loop that parses Apple's
error, adds the field it names, converts the type it demands, and repeats. Ten
attempts later: **AGE OK**. Then `contentRightsDeclaration` 500'd — the flip
trick (USE → DOES_NOT_USE) landed it — and `adhera_fixfinal.py` drove the item
+ submit to **WAITING_FOR_REVIEW**. The questionnaire everyone assumes is
web-only? Fully automatable.

**Pushup Alarm — the last-mile scripts.** Simulator-captured screenshots
(`pushup_simshots.sh`), then `pushup_finish.py` (12 KB of version setup, local
metadata injection, build attach) and `pushup_submit2.py` — the first
standalone *submit* script, the direct ancestor of `shipside submit`.

**REM Sleep Alarm — INVALID_BINARY.** The build died in processing mid-day.
The lesson that became a Shipside principle: *only the build dies*. Don't
touch the version, don't re-enter metadata — fix the binary, bump the build
number, re-upload, re-attach. `rem_new_version.py` shows the clean pattern
(reuse the editable version, re-seed kit metadata, attach the new build), and
`rem_finish.sh` closed it out past midnight.

**Quilly — two APIs for one job.** `quilly_asc_submit.py` had it hardest: a
new version (1.0.1), localized metadata copied forward from the live 1.0, two
locales of screenshots, *and* the Pro yearly subscription attached to the same
review submission so version and IAP ship together. It also discovered that
`APP_IPHONE_69` is not a real enum — the 67 set takes the 1320×2868 files.

**RenewalRadar — the generalization.** `rr_setup.py` stopped being app-specific:
review details, price schedule, content rights, and the iterated age rating as
reusable functions. That refactor is the moment this stopped being five scripts
and became a pipeline.

## What the day proved

1. **The submission last mile is fully API-driven** — version, metadata,
   screenshots, age rating, review details, build attach, review submission,
   submit. Only app-record creation, privacy labels, and the binary itself
   stay outside the API.
2. **Every failure mode repeats.** The 405 deadlock, the 409-that-means-success,
   the 500-flip, the locked whatsNew, the exact-size screenshot checks — hit
   once per app, five times in one day. Pattern, not accident.
3. **A prepared pipeline + an agent that can read error messages** turns a
   multi-day per-app grind into minutes per app.

Shipside is that pipeline, with the scars encoded: every error the day produced
has a playbook in `shipside/playbooks.py` and a section in
[PLAYBOOKS.md](PLAYBOOKS.md).

*Timing note: the honest end-to-end number for a prepared app — metadata and
screenshots ready, build uploaded and VALID — is a `shipside plan` and one
`shipside submit --yes`: minutes, most of it Apple's API thinking. First-time
apps add the one-time web steps (app record, privacy labels).*

## The dogfood: packaging the day into a product (2026-10-01)

Shipside v0.1 was dogfooded the day it was written: the packaged CLI
(pip-installed wheel, not the loose scripts) run against real, unshipped apps
in the same portfolio. The run log is committed at
[dogfood/run-2026-10-01.log](dogfood/run-2026-10-01.log). What the packaged
CLI did in one sitting:

- `state` on AprilReady: **13 API calls, 8.4s** — full report (listing,
  versions, builds, screenshots per set, IAP states, next action).
- `plan` → `submit --yes` staged the complete submission automatically:
  age rating questionnaire set by iterative API patch (**4 Apple round
  trips**, discovering 2026's schema drift live), review contact created,
  content rights set, review submission container opened — all idempotent
  across retries.
- The first target (ValidUntil Radar) surfaced a blocker class nobody had
  named: its `APP_IPHONE_67` set existed but was **empty** — Apple answers
  `STATE_ERROR.ENTITY_STATE_INVALID: This resource cannot be reviewed` with
  no specifics. `shipside plan` now counts the required set specifically and
  blocks early.

Five bugs in the fresh CLI were found and fixed by the run itself (response
shapes, endpoint sort rules, executor fail-fast). Two new Apple scars entered
the playbook (age-rating 2026 schema: BOOLEAN fields, no more `ageBand`; the
empty-required-set refusal). The one step left for a first-time app — App
Privacy answers — needs Apple's web session (2FA), which no tool may automate;
the final `submit --yes` flip is staged and idempotent, waiting on that
2-minute web step. That boundary is the product's honesty, not a gap: the
API simply does not expose privacy labels.
