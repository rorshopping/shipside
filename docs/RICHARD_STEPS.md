# Richard steps — what only you can do

Everything that needs your identity, 2FA, or a dashboard permission. Everything
else is done and live. Time cost: ~10 minutes total.

## 1. Answer App Privacy for the two staged apps (5 min) → unlocks the first sales

Both apps are fully staged by the packaged CLI (version, metadata, build
attached, age rating set, review contact, content rights, review submission
container open). Apple blocks the final item until the App Privacy questions
are answered — they are not API-settable (this is exactly the product's
documented boundary).

For each app, open and click through:

- **AprilReady** (the dogfood target): https://appstoreconnect.apple.com/apps/6804449080/distribution/ios
- **ValidUntil Radar**: https://appstoreconnect.apple.com/apps/6804450034/distribution/ios

Clicks: App Privacy (or the version page → App Privacy link) → **Edit/Start** →
answer the data-collection questions ("Data Not Collected" is the honest answer
if the app collects nothing) → **Save/Publish**. That's it.

Then flip the staged submissions (or ask the agent to):

```
cd C:\Users\Richard\Documents\Cursor_Projects\shipside-dogfood
C:\Users\Richard\Documents\Cursor_Projects\shipside\.venv-dogfood\Scripts\shipside submit --yes
```

(this currently points at AprilReady — for ValidUntil also upload 6.7"
screenshots first: the required APP_IPHONE_67 set is empty, which `shipside
plan` will tell you.)

## 2. Create the Stripe webhook endpoint (2 min) → instant license fulfillment

The Windows stripe CLI's machine key lacks "Webhook Endpoints Write", so I
could not create it. Until this exists, fulfillment still works (activate-time
Stripe lookup — proven in production by Whisper Dictate), but the webhook makes
it instant.

- Dashboard → Developers → Webhooks → **Add endpoint**
- URL: `https://whisperdictate.vercel.app/api/stripe-webhook`
- Events: `checkout.session.completed`, `invoice.paid`, `customer.subscription.deleted`
- Copy the **signing secret** (whsec_…) then:
  ```
  cd C:\Users\Richard\Documents\Projects\whisper-dictate\website
  vercel env add STRIPE_WEBHOOK_SECRET production
  ```
  and paste `EXISTING_VALUE,NEW_WHSEC` (comma-joined — the API supports
  several secrets). If you don't know the existing value:
  `vercel env pull` shows it (do not commit that file).
- Redeploy: `vercel --prod --yes`

Note: the **Becker Hub** webhook (account-wide) also receives Shipside
checkouts — worth a glance that it ignores unknown products instead of
creating junk records.

## 3. Publish to PyPI (optional, 10 min) → `pipx install shipside`

Until now install is `pipx install git+https://github.com/rorshopping/shipside`.
For the bare name: create a PyPI account, add a Trusted Publisher on
pypi.org for project `shipside` pointing at GitHub repo `rorshopping/shipside`,
workflow `.github/workflows/publish.yml` (a tiny workflow tagging releases).
Then update the install line in README.md + landing page.

## 4. Housekeeping (1 min)

- Smoke-test data in the license store: `shipside-smoke@example.com` is the
  trial on this machine (keep until Oct 15 — the CLI here runs on it),
  `wd-smoke@example.com` is an API smoke row, safe to revoke via
  whisperdictate-admin whenever.
- Watch the launch threads for replies:
  - HN: https://news.ycombinator.com/item?id=49924051
  - r/iOSProgramming: https://old.reddit.com/r/iOSProgramming/comments/1wv4qp7/
  - r/SideProject: https://old.reddit.com/r/SideProject/comments/1wv4rq6/
  - X: https://x.com/RichardBcker1 (5-post thread)
- Optional: custom domain for shipside-app.vercel.app (Vercel project
  `shipside-app` → Domains).
- The hourly first-sale watchdog is running as the automation
  "Shipside first-sale watch (hourly stripe + license check)".
