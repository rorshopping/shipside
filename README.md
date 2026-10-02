# Shipside

**Ship iOS apps to App Store Connect from the command line** — metadata, screenshots, and the actual submission, driven by the ASC REST API with your own key, on your own machine.

Not a build tool. Shipside picks up where the archive ends: it creates the version, pushes the listing, uploads screenshots, wires the age rating and review contact, attaches the build, opens the review submission — and submits. Then it tells you exactly what Apple's API refused to do and how to fix it in two clicks.

```
pipx install git+https://github.com/rorshopping/shipside
# or: uv tool install git+https://github.com/rorshopping/shipside

cd your-app            # folder with your project
shipside init          # 10 questions -> shipside.toml (your ASC key id/issuer/.p8 path)
shipside state         # what does ASC actually say right now?
shipside plan          # dry-run the submission: every blocker, nothing written
shipside screenshots ./shots-67
shipside metadata      # fastlane-deliver-compatible metadata/<locale>/*.txt
shipside submit --yes  # fixes the fixables, submits for review
```

## Why

In one day — 2026-09-30 — this pipeline shipped **five apps** to App Review end-to-end: Adhera, Pushup Alarm, REM Sleep Alarm, InCase and RenewalRadar. That day hit every wall App Store Connect has: the 405 version-creation deadlock, an INVALID_BINARY mid-flight, the age-rating questionnaire, the 640×920 subscription screenshot trap. [The full story](docs/LAUNCH_STORY.md) and [every playbook](docs/PLAYBOOKS.md) are in this repo and encoded in the CLI: when an API call fails in a known way, Shipside prints the exact recovery steps instead of a stack trace.

## What it does

| Command | What happens | Writes? |
|---|---|---|
| `shipside init` | Config wizard: bundle id, team key id/issuer/.p8 path, review contact → `shipside.toml` | local file |
| `shipside doctor` | Signs a JWT, checks team + app access | no |
| `shipside state` | Full report: versions, builds, screenshots, IAPs, review submissions + next action | no |
| `shipside plan` | The submission dry-run: every step marked ok / fix / blocked | no |
| `shipside metadata` | Pushes listing text (deliver-compatible folders) into the editable version, with Apple's char limits enforced | yes |
| `shipside screenshots` | Uploads PNGs (1320×2868 / 1290×2796) into the 6.7" set — including the `APP_IPHONE_69`-is-not-an-enum trap | yes |
| `shipside submit --yes` | Creates the version if needed, sets age rating + review details + content rights, attaches the newest VALID build, opens the review submission, submits | **irreversible** |
| `shipside trial` / `license` | 14-day free trial, then license activation | local |

## Hard-won defaults

- **Retry with a spine**: 429/5xx back off with `Retry-After` respect; a 409 on a retried write means the first write landed — treated as success.
- **Version creation**: two API routes are tried; on the 405 deadlock you get the exact web click-path, not silence.
- **Age rating is scriptable**: the questionnaire PATCH is iterated field-by-field until Apple accepts it (this surprises people; it shouldn't).
- **whatsNew is locked on first versions**: detected, never fatal, playbook printed.
- **INVALID_BINARY**: the build is the only thing that dies — Shipside re-attaches the next VALID build instead of recreating your version.
- **Your secrets stay yours**: the .p8 is referenced by path, never copied, never uploaded. Shipside's own servers never see your ASC credentials.

## License

14-day free trial with every feature, no card. Then a **one-time purchase: $149** — perpetual license, one developer, up to 3 machines, all v0.x updates. No subscription. Launch code `SHIPDAY` takes 40% off (that's $89.40 once). Activate with the email you bought with:

```
shipside trial --email you@example.com
shipside license activate --email you@example.com
```

The license check is online with a 14-day offline grace window — airport-friendly.


## Agent / LLM usage

Shipside is built to be driven by coding agents as much as by humans. Every
command except `init` is fully non-interactive:

- Config comes from `shipside.toml` (or the `ASC_KEY_ID` / `ASC_ISSUER_ID` /
  `ASC_KEY_PATH` / `SHIPSIDE_BUNDLE_ID` environment variables — no file needed).
- `--bundle-id` overrides the configured app per invocation.
- Exit codes: `0` success, `1` blocked or failed (the playbook explains why),
  `2` needs a license or the missing `--yes` confirmation.
- `plan` and `state` are read-only and license-free — safe to run first.
- Agents should write `shipside.toml` directly instead of piping answers into
  the `init` wizard.

## Requirements

- Python 3.9+ (macOS, Linux, Windows — the ASC API is plain REST over HTTPS)
- An **App Store Connect API key** (App Manager role or higher): [Users and Access → Integrations](https://appstoreconnect.apple.com/access/integrations/api)
- Builds are still your job (Xcode / altool / Transporter) — Shipside takes it from there and prints the exact altool command when no VALID build exists.

## Status

v0.1, dogfooded in anger. See [docs/PLAYBOOKS.md](docs/PLAYBOOKS.md) for the failure catalog and [docs/LAUNCH_STORY.md](docs/LAUNCH_STORY.md) for the day this was battle-tested.

MIT licensed. Not affiliated with Apple. App Store Connect is a trademark of Apple Inc.
