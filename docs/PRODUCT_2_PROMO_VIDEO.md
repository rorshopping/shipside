# Product 2 one-pager: Shipside Motion (working name)

*The second product under the Shipside brand — launch once Shipside v0.1 has
paying users.*

## What

**App promo videos, generated.** The customer points Shipside Motion at their
App Store screenshots (or the ASC API fetches them — we already have that
client), answers five questions (tone, target audience, hook, music vibe,
locale), and gets a vertical (9:16) promo video for TikTok/Reels/Shorts +
a landscape cut for the web — rendered by the local HyperFrames pipeline that
already produces Richard's app promo videos.

Input: bundle id (or screenshot folder). Output: 15/30s vertical + 1080p
landscape MP4, captioned, on-brand, first render in under 10 minutes.

## Why it's the right second product

- **Same buyer.** Everyone who pays $19/mo to ship an app needs store videos
  next; the purchase moment is adjacent (submission → launch marketing).
- **Same license stack.** The multi-product license API (product field,
  per-product trials, STRIPE_PRICE_MAP) shipped on day one — adding product
  `shipside-motion` is a config row and a price.
- **Same distribution.** The Shipside landing page gets a second section; the
  X/Reddit audiences overlap perfectly.
- **The hard part exists.** HyperFrames (composition, registry, render farm
  adapter, media-use resolution) is production-proven on this machine; the
  work is productization (wizard, templates, queue), not invention.

## MVP scope (2–3 weeks part-time)

1. `shipside motion init` — pick an app, pull its 6.7"/6.9" screenshots via
   the ASC client (already built), ask 5 tone questions.
2. Three HyperFrames templates to start: **feature tour** (screenshot +
   captions + beat-synced zooms), **problem→solution** (hook card, pain,
   reveal), **UGC-style** (phone-frame, captions, hands-free narration via
   local TTS).
3. Render locally, deliver MP4 + a preview GIF; re-render on feedback.
4. License gate: same gate module (`shipside license`), product-scoped.
5. Pricing: $29/mo or $290/yr (rendering costs are local/GPU — high margin),
   SHIPDAY honored for Shipside subscribers as a cross-perk.

## Explicitly out of MVP

Cloud rendering, Android store shots, voice cloning, multi-language dubs
(all natural v2+).

## Launch trigger & story

Ship when Shipside has ≥10 paying/trialing developers; the launch story writes
itself: "the CLI that ships your app now cuts its launch video." The demo
assets pipeline (terminal-capture → HyperFrames title cards) already exists
from product 1's own demo.
