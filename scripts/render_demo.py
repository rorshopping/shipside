"""Render the Shipside terminal demo GIF/MP4 from a captured run log.

Usage: python scripts/render_demo.py <log.txt> <outdir>
Produces outdir/demo.gif and outdir/demo.mp4. Frames are pure PIL - no
screen capture - so the demo is crisp and reproducible; the log content is
real CLI output (run-2026-10-01.log).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
GIF_W = 720
FPS = 12
FONT_SIZE = 24
PAD_X, PAD_Y, LINE_H = 36, 64, 33
VISIBLE = (H - PAD_Y - 46) // LINE_H

BG = (11, 15, 20)
BAR = (17, 24, 35)
FG = (230, 237, 243)
DIM = (120, 130, 145)
GREEN = (76, 194, 169)
YELLOW = (232, 182, 76)
RED = (229, 96, 76)
BLUE = (110, 160, 220)


def font(size=FONT_SIZE, bold=False):
    name = "consolab.ttf" if bold else "consola.ttf"
    path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / name
    if not path.exists():
        path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "consola.ttf"
    return ImageFont.truetype(str(path), size)


def line_style(text: str):
    """(color, bold) for a log line."""
    t = text.strip()
    if t.startswith("$ "):
        return GREEN, True
    if t.startswith("[ok]"):
        return GREEN, False
    if t.startswith("[!!]"):
        return YELLOW, False
    if t.startswith("[xx]"):
        return RED, False
    if t.startswith("[..]") or t.startswith("[manl]") or t.startswith("["):
        return DIM, False
    if t.startswith("---") or t.startswith("==="):
        return DIM, False
    if "Shipside" in t or "PLAN" in t or "SUBMIT" in t or "App Store Connect state" in t:
        return FG, True
    if t.startswith("PLAYBOOK") or t.startswith("#"):
        return YELLOW, False
    if t.startswith("  ") and t.strip():
        return BLUE if any(k in t for k in ("age rating set", "Trial", "Activated")) else FG, False
    return FG, False


def draw_frame(events, cursor_row, cursor_text=""):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 42], fill=BAR)
    for i, c in enumerate((255, 95, 86, 255, 189, 46, 39, 201, 63)):
        d.ellipse([16 + i * 22, 15, 26 + i * 22, 25], fill=(c, c, c) if isinstance(c, int) else c)
    d.text((W // 2 - 90, 9), "shipside — zsh", font=font(17), fill=DIM)
    f = font()
    fb = font(bold=True)
    start = max(0, cursor_row - VISIBLE + 1)
    for i, text in enumerate(events[start:cursor_row]):
        color, bold = line_style(text)
        d.text((PAD_X, PAD_Y + i * LINE_H), text, font=fb if bold else f, fill=color)
    if cursor_text:
        d.text((PAD_X, PAD_Y + (cursor_row - start) * LINE_H), cursor_text + "▌",
               font=fb, fill=GREEN)
    return img


def build_events(log_lines):
    """Yield (kind, payload) events: ('type', partial_cmd), ('line', text)."""
    for raw in log_lines:
        raw = raw.rstrip("\n")
        if raw.startswith("$ "):
            yield ("cmd", raw)
        else:
            yield ("line", raw)


def main():
    log_path, outdir = sys.argv[1], Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    log_lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
    # drop timing footers like "[exit 0, 9s]" (kept honest in the doc, noise in the demo)
    log_lines = [l for l in log_lines if not l.startswith("[exit")]

    title_card = [
        "",
        "  ╔══════════════════════════════════════════════╗",
        "  ║   SHIPSIDE  —  ship iOS apps from the CLI    ║",
        "  ║   real output · recorded 2026-10-01          ║",
        "  ╚══════════════════════════════════════════════╝",
        "",
    ]
    events = [("line", t) for t in title_card] + list(build_events(log_lines))
    end_card = [
        "",
        "  one command per mile-marker: state → plan → metadata",
        "  → screenshots → submit",
        "",
        "  14-day free trial · $19/mo or $149/yr",
        "  https://shipside-app.vercel.app",
    ]

    frames = []
    tmp = tempfile.mkdtemp(prefix="shipside_demo_")
    shown = []
    idx = 0
    n = len(events)
    while idx < n:
        kind, payload = events[idx]
        if kind == "cmd":
            # typewriter
            for k in range(1, len(payload) + 1):
                img = draw_frame(shown, len(shown), cursor_text=payload[:k])
                p = Path(tmp) / f"f{len(frames):05d}.png"
                img.save(p)
                frames.append(p)
            shown.append(payload)
            idx += 1
        else:
            shown.append(payload)
            idx += 1
            if payload == "":
                hold = 5
            elif payload.startswith("$") or payload.startswith("#"):
                hold = FPS  # pause after each command
            else:
                hold = 3
            for _ in range(hold):
                img = draw_frame(shown, len(shown))
                p = Path(tmp) / f"f{len(frames):05d}.png"
                img.save(p)
                frames.append(p)
    # hold before end card
    for _ in range(FPS * 2):
        img = draw_frame(shown, len(shown))
        p = Path(tmp) / f"f{len(frames):05d}.png"
        img.save(p)
        frames.append(p)
    # end card
    for t in end_card:
        shown.append(t)
        for _ in range(FPS):
            img = draw_frame(shown, len(shown))
            p = Path(tmp) / f"f{len(frames):05d}.png"
            img.save(p)
            frames.append(p)
    for _ in range(FPS * 5):
        img = draw_frame(shown, len(shown))
        p = Path(tmp) / f"f{len(frames):05d}.png"
        img.save(p)
        frames.append(p)

    print(f"frames: {len(frames)} ({len(frames)/FPS:.0f}s)")
    # GIF
    gif_frames = []
    for p in frames:
        img = Image.open(p).resize((GIF_W, int(H * GIF_W / W)), Image.LANCZOS)
        gif_frames.append(img)
    # keep every frame (12fps) - size ok at 720px for this content
    gif_frames[0].save(
        outdir / "demo.gif", save_all=True, append_images=gif_frames[1:],
        duration=int(1000 / FPS), loop=0, optimize=True,
    )
    # MP4
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(FPS), "-i", os.path.join(tmp, "f%05d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
         str(outdir / "demo.mp4")],
        check=True, capture_output=True,
    )
    print("wrote", outdir / "demo.gif", "and", outdir / "demo.mp4")


if __name__ == "__main__":
    main()
