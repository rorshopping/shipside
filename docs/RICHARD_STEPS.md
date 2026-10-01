# Richard steps — what only you can do

Everything that needs your identity, 2FA, or a dashboard permission. Everything
else is done and live. Time cost: ~15 minutes total.

**Status 2026-10-02 (mate sweep).** The sales path was verified end to end and
is intact: both payment links live and active (`plink_1ULmVv4x…` monthly,
`plink_1ULmVu4x…` yearly, `allow_promotion_codes: true`), `SHIPDAY` = 40% off
live and unredeemed, license API answering 200 on `/api/trial`, landing page and
both thank-you pages serving 200. What was actually broken was everything
*around* the checkout — see "Fixed 2026-10-02" at the bottom.

**Still zero revenue.** No customers, no subscriptions, no charges in live
mode. The product is sound; it is not being found. Items 1-4 below are the
remaining levers.

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

## 3. Publish to PyPI (10 min) → `pipx install shipside` — HIGHEST LEVERAGE

Until now install is `pipx install git+https://github.com/rorshopping/shipside`,
which needs git and a build step. For a paid CLI that is a real conversion
tax: `pipx install shipside` is the difference between one command and a
toolchain.

**The workflow is written and committed** (`.github/workflows/publish.yml`),
triggers on a published GitHub Release, and uses PyPI Trusted Publishing so
there is no API token to leak. The only thing left is the one-time PyPI
account setup, which cannot be done from CI:

1. pypi.org → sign in (create an account if needed)
2. **Project** → **New Project** → name `shipside`
3. **Project** → **Publishing** → add a GitHub publisher:
   - Owner `rorshopping`, Repository `shipside`
   - Workflow `publish.yml`, Environment blank
4. Save, then cut a release: `gh release create v0.1.0 -t "v0.1.0" -n "..."`

That publishes the wheel. Then swap the install line in `README.md` +
`landing/index.html` to the bare name. I verified the package builds and
installs cleanly (`python -m build` → wheel + sdist; fresh venv install →
`shipside --version` → `shipside 0.1.0`), so this is known-good once
registered.

## 4. Enable Vercel Web Analytics (1 min) → stop selling blind

There is currently **no analytics of any kind** on the landing page, so there
is no way to know whether anyone arrives or where from. The script tag is
already in `index.html` and is inert until you switch it on:

Vercel dashboard → project **shipside-app** → **Analytics** → **Enable**

Cookieless, no cross-site tracking, free tier. Without this you cannot tell a
working funnel from a dead one.

## 5. Housekeeping (1 min)

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

## Fixed 2026-10-02 (mate, no action needed)

The checkout was never the problem — the *funnel around it* was. Verified
against the live Stripe account and the deployed site, not assumed:

| Problem | Evidence | Fix |
|---|---|---|
| **Every share of the product rendered as a bare URL.** No `og:` or `twitter:` tags existed at all, so the 5-post X thread, Show HN and both Reddit posts showed no image, title or description. | `grep` for `og:title`/`twitter:card` on `index.html` returned 0 hits | Full OpenGraph + Twitter card set, absolute URLs, `og:image` 1200x630 |
| **No social image existed to point at.** | no `og.png` in `landing/` | `landing/make_social_card.py` renders `og.png` + `twitter.png` from the page's own design tokens; anchor drawn as vectors because the emoji glyph is tofu in every renderer |
| **Favicon was a `data:` URI wrapping an emoji** → rendered as a broken box. | codepoints `U+D83D U+DEF3` in a font that lacks the glyph | real `landing/favicon.svg`, drawn paths |
| **No analytics anywhere** — impossible to tell a live funnel from a dead one. | no analytics tag on any page | Vercel Web Analytics script added (inert until you enable it, step 4) |
| **No robots.txt / sitemap.xml** (both 404). | HTTP 404 on both | added |
| **Nothing stopped this regressing.** | no CI, no workflow files at all | `.github/workflows/test.yml` — tests on 3.9 + 3.12, a landing-metadata job, and a build-the-wheel-then-run-it job |
| **No PyPI publish path.** | `pypi.org/pypi/shipside/json` → 404 | `.github/workflows/publish.yml` written; only the one-time account step is yours (step 3) |

Regression guard: `landing/verify_meta.py` asserts all 19 share/SEO
invariants and exits non-zero on any of them, wired into
`tests/test_landing.py` and the CI. Its teeth were proven — removing `og:image`
or flipping `twitter:card` back to `property=` both make it fail.

Test suite: **11 → 16 passing**, `python -m pytest tests -q`.
