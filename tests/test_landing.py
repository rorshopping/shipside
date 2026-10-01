"""Landing page share metadata must stay intact.

The og:/twitter: tags were absent for the entire life of the product, so every
link Richard shared (X thread, Show HN, two Reddit posts) rendered as bare
text. Nothing caught it, because a missing meta tag is invisible locally.

These tests run the standalone verifier as a subprocess so the shipped page
and the checker can never drift, and add a few assertions the standalone
script makes about the repo as a whole.
"""
import subprocess
import sys
from pathlib import Path

LANDING = Path(__file__).resolve().parents[1] / "landing"


def test_share_meta_is_complete():
    """verify_meta.py exits 0 only when every share tag is present and correct."""
    r = subprocess.run(
        [sys.executable, str(LANDING / "verify_meta.py")],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"landing share metadata broken:\n{r.stdout}\n{r.stderr}"


def test_no_data_uri_favicon():
    """The emoji data: URI favicon rendered as tofu in every renderer tried."""
    html = (LANDING / "index.html").read_text(encoding="utf-8")
    assert 'rel="icon" href="data:' not in html
    assert 'href="/favicon.svg"' in html


def test_social_card_images_exist():
    for name in ("og.png", "twitter.png"):
        p = LANDING / name
        assert p.exists(), f"{name} missing - og/twitter tags point at it"
        assert p.stat().st_size > 5000, f"{name} looks like a stub"


def test_pricing_on_page_matches_live_stripe_prices():
    """The page advertises $19/mo and $149/yr; drift from Stripe is a refund risk.

    Verified against the live account on 2026-10-02:
      prod_VMVV4oiHbtYpn4 -> price_1ULmV74... 14900 usd/year
                          -> price_1ULmV7...  1900 usd/month
    """
    html = (LANDING / "index.html").read_text(encoding="utf-8")
    assert "$19" in html and "$149" in html
    assert "SHIPDAY" in html


def test_both_checkout_links_present():
    """Both live payment links must be on the page and they must differ."""
    html = (LANDING / "index.html").read_text(encoding="utf-8")
    monthly = "https://buy.stripe.com/5kQfZa5RieSF4vS29M9AA06"
    yearly = "https://buy.stripe.com/14A5kw4Ne4e11jGdSu9AA05"
    assert monthly in html, "monthly checkout link missing"
    assert yearly in html, "yearly checkout link missing"
    assert monthly != yearly
