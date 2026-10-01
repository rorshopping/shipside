1/ Last month I shipped 5 iOS apps to App Review in ONE day. Not a sprint week — one day. The trick: everything after the binary is API-driven. Today that pipeline ships as a product: Shipside 🛳️
2/ The day hit every wall ASC has: the 405 version deadlock, builds going INVALID_BINARY mid-flight, the age-rating questionnaire (scriptable!), APP_IPHONE_69 (not a real enum), subs stuck MISSING_METADATA forever. Every wall became a playbook the CLI prints when it hits it.
3/ How it works: pipx install, shipside init (your OWN ASC key, on your machine), then:
shipside state → full status report
shipside plan → dry-run: every blocker marked ok/fix/blocked
shipside submit --yes → version + age rating + review contact + build attach + submit
4/ We dogfooded the packaged CLI the next day: staged a real app end-to-end — the age rating alone took 4 Apple round trips (their 2026 schema dropped ageBand and flipped fields to booleans). Found 5 bugs in my own CLI and 2 undocumented Apple behaviors in one afternoon.
5/ Shipside: 14-day free trial, $19/mo or $149/yr per developer — code SHIPDAY takes 40% off year one.
Demo + install: https://shipside-app.vercel.app
Source + failure catalog: https://github.com/rorshopping/shipside
