"""`shipside metadata` - push listing text into the editable version.

Reads deliver-compatible locale folders:

    metadata/
      en-US/
        name.txt subtitle.txt description.txt keywords.txt
        promotional_text.txt release_notes.txt
        support_url.txt marketing_url.txt privacy_policy_url.txt (optional)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .. import playbooks, report
from ..asc import AscError
from ..steps import (
    editable_version,
    ensure_app_info_localization,
    ensure_version_localization,
    find_app,
    get_app_info,
)

VERSION_FIELDS = {  # file stem -> version-localization attribute
    "description": "description",
    "keywords": "keywords",
    "promotional_text": "promotionalText",
    "release_notes": "whatsNew",
    "support_url": "supportUrl",
    "marketing_url": "marketingUrl",
}
APP_INFO_FIELDS = {
    "name": "name",
    "subtitle": "subtitle",
    "privacy_policy_url": "privacyPolicyUrl",
}
LIMITS = {"name": 30, "subtitle": 30, "keywords": 100, "promotional_text": 170, "description": 4000}
LOCALE_RE = re.compile(r"^[a-z]{2}(-[A-Za-z0-9]{2,8})?$")


def read_locale_dir(d: Path) -> dict:
    fields = {}
    for f in sorted(d.iterdir()):
        if f.is_file() and f.suffix == ".txt":
            fields[f.stem] = f.read_text(encoding="utf-8").strip()
    return fields


def validate(fields: dict) -> "list[tuple[str, str]]":
    problems = []
    for stem, limit in LIMITS.items():
        if stem in fields and len(fields[stem]) > limit:
            problems.append((stem, f"{len(fields[stem])}/{limit} chars - TOO LONG"))
    return problems


def push_locale(c, vid: str, info_id: "str | None", locale: str, fields: dict, log=print) -> int:
    """Push one locale; returns 0 ok, 1 soft-failed (field locked)."""
    soft = 0
    v_fields = {}
    for stem, attr in VERSION_FIELDS.items():
        if stem in fields:
            v_fields[attr] = fields[stem]
    ai_fields = {}
    for stem, attr in APP_INFO_FIELDS.items():
        if stem in fields and fields[stem]:
            ai_fields[attr] = fields[stem]

    try:
        ensure_version_localization(c, vid, locale, v_fields)
        for stem in ("description", "keywords", "promotional_text", "support_url", "marketing_url"):
            if stem in fields:
                log(report.ok(f"{locale}: {stem} ({len(fields[stem])} chars)"))
    except AscError as e:
        if e.status == 409:
            playbooks.print_playbook("whatsnew-locked-409", log=log)
            soft = 1
        else:
            raise

    if info_id and ai_fields:
        try:
            ensure_app_info_localization(c, info_id, locale, ai_fields)
            for stem in ("name", "subtitle", "privacy_policy_url"):
                if stem in fields and fields[stem]:
                    log(report.ok(f"{locale}: {stem}"))
        except AscError as e:
            if e.status == 409:
                log(report.warn(f"{locale}: app info fields rejected (409) - name/subtitle may be locked"))
                soft = 1
            else:
                raise
    return soft


def run(c, cfg, args) -> int:
    bid = getattr(args, "bundle_id", None)
    from ..config import bundle_id as resolve_bid

    bid = resolve_bid(cfg, bid)
    meta_dir = Path(args.dir or cfg.get("metadata", "dir") or "metadata")
    if not meta_dir.is_dir():
        print(report.err(f"metadata directory not found: {meta_dir}"))
        print(report.info("expected layout: metadata/<locale>/description.txt ... (fastlane deliver compatible)"))
        return 1

    app = find_app(c, bid)
    if not app:
        print(report.err(f"No app record for {bid}"))
        playbooks.print_playbook("app-not-found")
        return 1
    version = editable_version(c, app["id"])
    if not version:
        print(report.err("No editable version (PREPARE_FOR_SUBMISSION / REJECTED) on this app."))
        print(report.info("run: shipside plan   - it creates the next version, then re-run shipside metadata"))
        return 1
    vid = version["id"]
    info = get_app_info(c, app["id"])
    print(report.head(f"Pushing metadata to version {attrs(version).get('versionString')}"))

    locales = sorted(d.name for d in meta_dir.iterdir() if d.is_dir() and LOCALE_RE.match(d.name))
    if not locales:
        print(report.err(f"no locale folders under {meta_dir} (expected e.g. metadata/en-US/)"))
        return 1
    print(report.info(f"locales: {', '.join(locales)}"))
    print()

    soft_fail = 0
    for locale in locales:
        fields = read_locale_dir(meta_dir / locale)
        problems = validate(fields)
        for stem, msg in problems:
            print(report.err(f"{locale}: {stem} {msg}"))
        if problems:
            return 1
        soft_fail += push_locale(c, vid, info["id"] if info else None, locale, fields)

    print()
    if soft_fail:
        print(report.warn("metadata pushed with warnings (see above)"))
        return 2
    print(report.ok(f"metadata pushed for {len(locales)} locale(s)"))
    return 0
