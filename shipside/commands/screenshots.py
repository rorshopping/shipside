"""`shipside screenshots` - upload a folder of PNGs to the editable version.

Handles the display-type trap: APP_IPHONE_69 is not a valid enum value; the
APP_IPHONE_67 set serves the 6.7"/6.9" slots (1320x2868 works). Falls back
automatically and prints the playbook if every candidate is rejected.
"""
from __future__ import annotations

import time
from pathlib import Path

from .. import playbooks, report
from ..asc import AscError
from ..config import bundle_id
from ..steps import (
    clear_screenshots,
    editable_version,
    ensure_screenshot_set,
    ensure_version_localization,
    find_app,
    get_app_info,
    screenshot_sets,
    upload_screenshot,
)

KNOWN_SIZES = {(1320, 2868), (1290, 2796), (1284, 2776), (1170, 2532), (1242, 2688), (1125, 2436)}
FALLBACK_TYPES = ["APP_IPHONE_67", "APP_IPHONE_65"]


def png_size(path: Path):
    """Read pixel size from a PNG header (IHDR), no dependencies."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        w = int.from_bytes(head[16:20], "big")
        h = int.from_bytes(head[20:24], "big")
        return w, h
    except Exception:
        return None


def run(c, cfg, args) -> int:
    bid = bundle_id(cfg, getattr(args, "bundle_id", None))
    shot_dir = Path(args.dir)
    if not shot_dir.is_dir():
        print(report.err(f"screenshot directory not found: {shot_dir}"))
        return 1
    shots = sorted(p for p in shot_dir.iterdir() if p.suffix.lower() == ".png")
    if not shots:
        print(report.err(f"no PNG files in {shot_dir}"))
        return 1

    print(report.head(f"Uploading {len(shots)} screenshots - {bid}"))
    for p in shots:
        size = png_size(p)
        if size and size not in KNOWN_SIZES:
            print(report.warn(f"{p.name}: {size[0]}x{size[1]} is not a standard phone size - attempting anyway"))
    if getattr(args, "strict", False):
        bad = [p for p in shots if png_size(p) not in KNOWN_SIZES]
        if bad:
            print(report.err(f"--strict: non-standard sizes: {[p.name for p in bad]}"))
            return 1

    app = find_app(c, bid)
    if not app:
        print(report.err(f"No app record for {bid}"))
        playbooks.print_playbook("app-not-found")
        return 1
    version = editable_version(c, app["id"])
    if not version:
        print(report.err("No editable version - run: shipside plan"))
        return 1
    vid = version["id"]

    locale = args.locale or cfg.get("screenshots", "locale") or "en-US"
    locs = c.get_all(f"/v1/appStoreVersions/{vid}/appStoreVersionLocalizations")
    loc = next((l for l in locs if l["attributes"].get("locale") == locale), None)
    if not loc:
        info = get_app_info(c, app["id"])
        loc_id = ensure_version_localization(c, vid, locale, {})
        print(report.info(f"created {locale} localization {loc_id}"))
    else:
        loc_id = loc["id"]

    display_types = [args.display_type] if args.display_type else []
    cfg_type = cfg.get("screenshots", "display_type")
    if cfg_type and cfg_type not in display_types:
        display_types.append(cfg_type)
    for t in FALLBACK_TYPES:
        if t not in display_types:
            display_types.append(t)

    set_id = None
    used_type = None
    existing = {s["attributes"].get("screenshotDisplayType"): s["id"] for s in screenshot_sets(c, loc_id)}
    for dt in display_types:
        try:
            set_id = existing.get(dt) or ensure_screenshot_set(c, loc_id, dt)
            used_type = dt
            break
        except AscError as e:
            print(report.warn(f"display type {dt} rejected: {str(e)[:140]}"))
    if not set_id:
        playbooks.print_playbook("screenshot-size")
        return 1
    print(report.info(f"screenshot set: {used_type} ({set_id[:8]})"))

    replace = cfg.get("screenshots", "replace", default=True) if hasattr(cfg, "get") else True
    replace = True if replace is None else bool(replace)
    if replace and not args.keep:
        clear_screenshots(c, set_id, log=print)

    t0 = time.time()
    failed = []
    for i, p in enumerate(shots, 1):
        try:
            state = upload_screenshot(c, set_id, str(p))
            mark = report.ok if state == "COMPLETE" else report.warn
            print(f"  {report.c(f'{i}/{len(shots)}', report.DIM)} {p.name}: {mark(state)}")
            if state != "COMPLETE":
                failed.append(p.name)
        except AscError as e:
            print(report.err(f"{p.name}: {e.status} {e.detail()[:160]}"))
            failed.append(p.name)

    print()
    if failed:
        print(report.err(f"{len(failed)} screenshot(s) failed: {', '.join(failed)}"))
        return 1
    print(report.ok(f"{len(shots)} screenshots uploaded to {used_type} in {time.time() - t0:.1f}s"))
    return 0
