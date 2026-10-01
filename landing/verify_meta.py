"""Verify the landing page's share metadata is actually correct.

Exists because the og:/twitter: tags were missing entirely for the whole life
of the product, and a missing tag is invisible in a browser - you only find
out when a link renders bare on X/HN/Reddit. This makes the regression
detectable instead.

Run:  python landing/verify_meta.py
Exit: 0 = all checks pass, 1 = at least one failure
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = HERE / "index.html"

# OpenGraph tags use property=, Twitter tags use name=. Getting this wrong is
# silent in a browser and in most crawlers, so the attribute is asserted here
# rather than just the presence of the string.
REQUIRED = [
    ("og:type", "property", "website"),
    ("og:title", "property", None),
    ("og:description", "property", None),
    ("og:url", "property", "https://shipside-app.vercel.app/"),
    ("og:image", "property", "https://shipside-app.vercel.app/og.png"),
    ("og:image:width", "property", "1200"),
    ("og:image:height", "property", "630"),
    ("twitter:card", "name", "summary_large_image"),
    ("twitter:title", "name", None),
    ("twitter:description", "name", None),
    ("twitter:image", "name", "https://shipside-app.vercel.app/twitter.png"),
]


def main() -> int:
    html = PAGE.read_text(encoding="utf-8")
    head = html.split("</head>")[0]
    fails = []

    for prop, attr, expect in REQUIRED:
        m = re.search(r'<meta %s="%s" content="([^"]*)"' % (attr, re.escape(prop)), head)
        if not m:
            fails.append(f"missing {prop} (as {attr}=)")
        elif expect and m.group(1) != expect:
            fails.append(f"{prop} is {m.group(1)!r}, expected {expect!r}")

    if not re.search(r'<link rel="canonical" href="https://shipside-app\.vercel\.app/"', head):
        fails.append("missing or wrong canonical")

    # absolute URLs only - relative og:image is ignored by X and Facebook
    for prop, attr in (("og:image", "property"), ("og:url", "property"), ("twitter:image", "name")):
        m = re.search(r'<meta %s="%s" content="([^"]*)"' % (attr, re.escape(prop)), head)
        if m and not m.group(1).startswith("https://"):
            fails.append(f"{prop} is not absolute: {m.group(1)}")

    # the emoji data: URI favicon rendered as tofu everywhere - must be gone
    if re.search(r'<link rel="icon" href="data:', html):
        fails.append("data: URI favicon still present (renders as tofu)")
    if 'href="/favicon.svg"' not in html:
        fails.append("favicon.svg not linked")

    # the images the tags point at must exist and be non-trivial
    for fname, min_bytes in [("og.png", 5000), ("twitter.png", 5000)]:
        p = HERE / fname
        if not p.exists():
            fails.append(f"{fname} missing (tags point at it)")
        elif p.stat().st_size < min_bytes:
            fails.append(f"{fname} suspiciously small ({p.stat().st_size}B)")

    for extra in ("robots.txt", "sitemap.xml", "favicon.svg"):
        if not (HERE / extra).exists():
            fails.append(f"{extra} missing")

    if fails:
        print("FAIL")
        for f in fails:
            print(f"  - {f}")
        return 1
    print(f"PASS - {len(REQUIRED) + 8} share/SEO checks green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
