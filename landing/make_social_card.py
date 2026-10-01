"""Render the OpenGraph/social card for the Shipside landing page.

Why this exists: every share of https://shipside-app.vercel.app (X thread,
Show HN, two Reddit posts) rendered as a bare URL with no preview, because
the page shipped no og:/twitter: tags. A blank card is a dead link.

Run:  python landing/make_social_card.py
Out:  landing/og.png   (1200x630, the size X/LinkedIn/Slack render)
      landing/twitter.png (1200x600, avoids the summary_large_image crop)

Design tokens are lifted from landing/index.html :root so the card and the
page cannot drift apart.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent

# --- tokens (kept in lockstep with index.html :root) -------------------------
BG = "#0b0f14"
PANEL = "#111823"
LINE = "#1e2a3a"
TEXT = "#e6edf3"
DIM = "#8b98a9"
ACCENT = "#4cc2a9"
ACCENT2 = "#e8b64c"

MONO = r"C:\Windows\Fonts\consola.ttf"
MONO_B = r"C:\Windows\Fonts\consolab.ttf"
SANS_B = r"C:\Windows\Fonts\segoeuib.ttf"

W, H = 1200, 630
M = 72  # margin


def font(path, size):
    return ImageFont.truetype(path, size)


def base(w=W, h=H):
    """Background with the same radial glow the page header uses."""
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    # cheap radial glow: concentric translucent rings, accent-tinted
    glow_cx, glow_cy, glow_r = int(w * 0.70), -40, 460
    steps = 90
    for i in range(steps, 0, -1):
        t = i / steps
        r = int(glow_r * t)
        # blend accent into BG by alpha ~ (1-t)
        a = (1 - t) ** 2.1
        col = (
            int(int(BG[1:3], 16) + (int(ACCENT[1:3], 16) - int(BG[1:3], 16)) * a * 0.20),
            int(int(BG[3:5], 16) + (int(ACCENT[3:5], 16) - int(BG[3:5], 16)) * a * 0.20),
            int(int(BG[5:7], 16) + (int(ACCENT[5:7], 16) - int(BG[5:7], 16)) * a * 0.20),
        )
        d.ellipse(
            [glow_cx - r, glow_cy - r, glow_cx + r, glow_cy + r], outline=col, width=6
        )
    return img, d


def anchor(d, x, y, size=54, color=ACCENT):
    """A mooring anchor drawn from primitives, not a glyph.

    Two reasons not to use a character: the data: URI favicon already ships
    a broken one (U+1F6A3 renders as tofu in every card renderer tried), and
    font coverage for U+2693 on Windows is a lottery - Consolas, the mono
    face the rest of the design uses, does not have it. Vectors always work.
    """
    s = size / 54.0  # design grid is 54 units tall
    lw = max(2, int(4 * s))  # stroke weight

    def P(px, py):
        return (x + px * s, y + py * s)

    cx = 27  # centre-line x in grid units
    # stock: vertical shank
    d.line([P(cx, 6), P(cx, 42)], fill=color, width=lw)
    # ring at the top
    r = 5 * s
    d.ellipse([P(cx, 6)[0] - r, P(cx, 6)[1] - r, P(cx, 6)[0] + r, P(cx, 6)[1] + r],
              outline=color, width=lw)
    # crossbar
    d.line([P(12, 16), P(42, 16)], fill=color, width=lw)
    # curved arms sweeping up from the flukes
    d.arc([P(8, 22)[0], P(8, 22)[1], P(46, 46)[0], P(46, 46)[1]],
          start=25, end=155, fill=color, width=lw)
    # flukes (the two barbs at the tips)
    d.line([P(11, 41), P(6, 34)], fill=color, width=lw)
    d.line([P(43, 41), P(48, 34)], fill=color, width=lw)


def draw_card(w, h, out_name):
    img, d = base(w, h)

    f_kicker = font(MONO, 21)
    f_h1 = font(SANS_B, 62)
    f_h2 = font(SANS_B, 62)
    f_sub = font(SANS_B, 27)
    f_small = font(MONO, 20)
    f_price = font(MONO_B, 24)

    y = 74

    # kicker: anchor + wordmark
    anchor(d, M, y + 4, size=30)
    d.text((M + 44, y), "Shipside", font=f_kicker, fill=ACCENT)
    y += 52

    # headline, two lines
    d.text((M, y), "Ship your iOS app.", font=f_h1, fill=TEXT)
    y += 74
    d.text((M, y), "From the ", font=f_h1, fill=TEXT)
    w_tail = d.textlength("From the ", font=f_h1)
    d.text((M + w_tail, y), "command line", font=f_h2, fill=ACCENT)
    y += 100

    # subline
    d.text((M, y), "Metadata, screenshots, age rating, submit for review.", font=f_sub, fill=DIM)
    y += 44

    # proof line
    d.text((M, y), "5 apps to App Review in one day.", font=f_sub, fill=TEXT)
    y += 58

    # bottom bar: install + price
    bar_h = 62
    bar_y = h - M - bar_h
    d.rounded_rectangle([M, bar_y, w - M, bar_y + bar_h], radius=10, fill=PANEL, outline=LINE, width=2)

    d.text((M + 24, bar_y + 19), "$", font=f_price, fill=ACCENT2)
    d.text((M + 46, bar_y + 19), "pipx install shipside", font=f_price, fill=TEXT)

    px = w - M - 24
    label = "$19/mo  ·  $149/yr"
    lw = d.textlength(label, font=f_price)
    d.text((px - lw, bar_y + 19), label, font=f_price, fill=ACCENT)

    path = HERE / out_name
    img.save(path, "PNG", optimize=True)
    return path


if __name__ == "__main__":
    for name, dims in (("og.png", (1200, 630)), ("twitter.png", (1200, 600))):
        p = draw_card(dims[0], dims[1], name)
        print(f"wrote {p} ({dims[0]}x{dims[1]}, {p.stat().st_size // 1024} KB)")
