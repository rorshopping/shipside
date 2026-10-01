# Playbooks: every way App Store Connect says no, and the way through

These are not hypotheticals. Each one was hit, paid for, and solved during the
five-app submission day of 2026-09-30 (see [LAUNCH_STORY.md](LAUNCH_STORY.md)).
Shipside detects most of them at runtime and prints the matching playbook;
this document is the full narrative.

## The 405 version-creation deadlock

`POST /v1/appStoreVersions` sometimes answers **405 Method Not Allowed** for an
app that clearly has no editable version. The endpoint exists, the key has
App Manager rights, the body is perfect — Apple just refuses. Two things work:

1. **The nested route**: `POST /v1/apps/{appId}/appStoreVersions` with the app
   relationship in the body. Shipside tries this automatically.
2. **The web**: App Store Connect → your app → Distribution → **+** next to the
   version list. If both API routes 405, Apple has locked API creation for
   this app and only the web UI will do it — once. Afterwards everything is
   API-drivable again.

A 409 while *creating* can also mean your first POST landed after a 500 retry
(the write did apply). Shipside re-reads state instead of failing.

## whatsNew is locked on first-ever versions

Setting `whatsNew` (release notes) on an app's first version returns **409**.
This is by design: there is no "previous version" to compare with. Shipside
skips the field with a warning. From v1.0.1 on it works — put the text in
`metadata/<locale>/release_notes.txt`.

## INVALID_BINARY — only the build dies

A build can flip to **INVALID** during processing minutes after a clean upload
(ITMS-xxxxx codes arrive by email). The version, metadata and screenshots all
survive. Do **not** recreate the version: fix the cause, bump the build
number, re-upload, and let Shipside attach the newest VALID build.

Common ITMS causes, all met in the field:

| Code | Cause | Fix |
|---|---|---|
| ITMS-91055 | Missing privacy manifest | Add `PrivacyInfo.xcprivacy` declaring `NSPrivacyAccessedAPITypes` (e.g. `C617.1` for `UserDefaults`), `NSPrivacyCollectedDataTypes` (usually empty), `NSPrivacyTracking = false`. Required for apps using required-reason APIs. |
| ITMS-90474 | Deployment target vs `UIRequiredDeviceCapabilities` mismatch | Align the Info.plist keys. |
| ITMS-90022/90023 | Icon problems (alpha channel in the 1024px marketing icon) | Flatten the icon: `sips -s format jpeg ... ` no — export PNG without alpha, re-add to the asset catalog (the validator reads the *compiled* catalog, loose files don't count). |
| — | Missing `ITSAppUsesNonExemptEncryption` | Set `false` in Info.plist (or patch the build via API before submit). |

## The age rating questionnaire IS scriptable

Apple's age-rating questionnaire — long assumed web-only — accepts a single
`PATCH /v1/ageRatingDeclarations/{id}` … but it validates **one attribute per
error**: you patch, it rejects the next missing field, you patch again. Ten or
more round trips. Shipside iterates automatically with the full enum map and
succeeds in one command (proven on Adhera and RenewalRadar, 2026-09-30, and
re-proven on AprilReady 2026-10-01). Field defaults are `NONE` with `ageBand
4_PLUS`; override in `shipside.toml`:

```toml
[age_rating]
age_band = "4_PLUS"
health_or_wellness_topics = "FREQUENT_OR_INTENSE"
```

**2026-10 schema drift** (found live during dogfood): Apple now types several
fields as BOOLEAN (`messagingAndChat`, `gambling`, `parentalControls`,
`userGeneratedContent`, `lootBox`, `advertising`, `unrestrictedWebAccess`,
`healthOrWellnessTopics`, `ageAssurance`), requires the new `advertising`
field, and **removed `ageBand` entirely** — the band is derived from the
answers. Shipside intersects its payload with the live declaration schema and
converts types automatically; old scripts hardcoding `ageBand` now get
`'ageBand' is not an attribute on the resource 'ageRatingDeclarations'`.

## The empty required screenshot set: "This resource cannot be reviewed"

`POST /v1/reviewSubmissionItems` answering
`STATE_ERROR.ENTITY_STATE_INVALID: This resource cannot be reviewed` means the
VERSION has an open validation gap — Apple doesn't name it. In dogfood
(2026-10-01) the cause was an **existing-but-empty `APP_IPHONE_67` set**: the
version showed 4 screenshots (all in `APP_IPHONE_65` + iPad), which `filter`
counts as "has screenshots", but review requires the 6.7"/6.9" set to be
non-empty. `shipside plan` now counts the required set specifically and blocks
early with this playbook. Other members of this error class: unanswered App
Privacy questions (see below), missing pricing, missing content rights.

## Privacy nutrition labels gate the first submission

The App Privacy questions are not settable with a standard API key, and an
unanswered privacy section blocks the first submission with the generic
"cannot be reviewed" error above. One-time web fix: ASC > app > App Privacy >
answer (for offline apps: "Data Not Collected"). The launch-day pipeline
automated it via `fastlane run upload_app_privacy_details_to_app_store` with a
`[{"data_protections": ["DATA_NOT_COLLECTED"]}]` JSON — which needs the Apple
ID web session (`fastlane spaceauth`) inside a GUI keychain session; over bare
SSH the keychain read fails with `security` exit 36.

## The 640×920 subscription screenshot trap

Auto-renewable subscriptions need their *own* review screenshot, and the
acceptance check is exact: **640×920**. Other sizes PUT with HTTP 200 and the
subscription quietly stays `MISSING_METADATA` forever. Other traps in the same
corner:

- `subscriptionAvailabilities` is **CREATE-only**: GET returns 403. Never probe
  first — just POST it (a body double-wrap gives 422 `ENTITY_UNPROCESSABLE`).
- `availableInNewTerritories: true` "opens" storefronts but **does not price
  them**. Fan out inline prices: GET `/equalizations`, then PATCH a price per
  territory (175 of them). 19 stuck subscriptions were mass-fixed this way on
  2026-08-24 (`asc_sub_pricing_fix.py` in the upstream kit).
- An orphaned screenshot reservation blocks re-uploads: recover the id via
  `GET /v1/subscriptions/{id}/relationships/appStoreReviewScreenshot`, DELETE
  it, re-create.
- State recomputes asynchronously (~5–75 s). Poll. Sandbox test purchases
  propagate 30–60 min after READY — don't chase provisioning.

## The APP_IPHONE_69 trap

`APP_IPHONE_69` is **not** a valid `screenshotDisplayType` enum value — ASC
returns 409 listing the valid values. The 6.7-inch set (`APP_IPHONE_67`)
serves the 6.7"/6.9" slots and accepts 1320×2868 (as well as 1290×2796).
Shipside defaults to the 67 set and falls back down the ladder if Apple
changes its mind.

## contentRightsDeclaration 500s

`PATCH /v1/apps/{id}` with `contentRightsDeclaration` fails with 500 often
enough to be a law. It recovers with retries and the flip trick: set
`USES_THIRD_PARTY_CONTENT`, then immediately set
`DOES_NOT_USE_THIRD_PARTY_CONTENT`. Shipside does this for you.

## filter[state] does not exist

`GET /v1/apps/{id}/appStoreVersions?filter[state]=...` → **400**. The correct
filter is `filter[appStoreState]`. Less a playbook than a scar.

## API keys cannot delete builds

There is no DELETE for builds. Expire one with `PATCH /v1/builds/{id}`
`{"expired": true}`.

## Build intake lags the upload

"Processing" can show for 5–30 minutes after altool says success. Keep polling
`shipside state` — do not re-upload, you will only queue a duplicate.

## What the API genuinely cannot do

| Task | Why | Path |
|---|---|---|
| Create the first app record | `GET/PATCH /v1/apps` only — no POST (verified) | Web once: ASC → New App (or `fastlane produce`) |
| Privacy nutrition labels | Not exposed to standard API keys | Web: App Privacy (or fastlane `upload_app_privacy_details_to_app_store`) |
| iCloud containers | No `cloudKitContainers` resource | Portal via spaceship/web |
| Binary upload | Different service (Transporter/altool) | Xcode/altool — Shipside prints the exact command |
