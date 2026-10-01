"""`shipside state` - the full read-only App Store Connect status report."""
from __future__ import annotations

import time

from .. import playbooks, report
from ..asc import AscError, attrs
from ..config import bundle_id
from ..steps import (
    attached_build,
    editable_version,
    find_app,
    latest_builds,
    list_versions,
    screenshot_sets,
    open_review_submission,
)


def run(c, cfg, args) -> int:
    bid = bundle_id(cfg, getattr(args, "bundle_id", None))
    t0 = time.time()
    print(report.head(f"App Store Connect state - {bid}"))
    print()

    app = find_app(c, bid)
    if not app:
        print(report.err(f"No app record found for bundle id {bid}"))
        playbooks.print_playbook("app-not-found")
        return 1
    a = attrs(app)
    print(report.kv("app id", app["id"]))
    print(report.kv("name", a.get("name")))
    print(report.kv("primary locale", a.get("primaryLocale")))
    print(report.kv("sku", a.get("sku")))
    print(report.kv("bundle id", a.get("bundleId")))
    print(report.kv("content rights", a.get("contentRightsDeclaration") or "(unset)"))
    print()

    # app info localizations (name / subtitle / privacy policy)
    try:
        locs = c.get_all(f"/v1/apps/{app['id']}/appInfos?include=appInfoLocalizations")
        rows = []
        for inc in locs.get("included", []):
            if inc.get("type") == "appInfoLocalizations":
                ia = inc.get("attributes") or {}
                rows.append([
                    ia.get("locale", "?"),
                    ia.get("name") or "-",
                    ia.get("subtitle") or "-",
                    "yes" if ia.get("privacyPolicyUrl") else "MISSING",
                ])
        if rows:
            print(report.head("Listing (app info localizations)"))
            print(report.table(rows, headers=("locale", "name", "subtitle", "privacy url")))
            print()
    except AscError as e:
        print(report.warn(f"could not read app info localizations: {e.status}"))

    # versions
    versions = list_versions(c, app["id"])
    if versions:
        rows = [
            [v["attributes"].get("versionString"), v["attributes"].get("appStoreState"), v["id"][:8]]
            for v in versions
        ]
        print(report.head("Versions"))
        print(report.table(rows, headers=("version", "state", "id")))
        print()

    editable = editable_version(c, app["id"])
    if editable:
        vid = editable["id"]
        print(report.head(f"Editable version: {attrs(editable).get('versionString')} ({attrs(editable).get('appStoreState')})"))
        try:
            b = attached_build(c, vid)
            if b:
                ba = attrs(b)
                print(report.kv("build attached", f"{ba.get('version')} (uploaded {ba.get('uploadedDate', '')[:10]})"))
            else:
                print(report.kv("build attached", report.c("none", report.YELLOW)))
        except AscError:
            print(report.kv("build attached", "?"))
        try:
            vlocs = c.get_all(f"/v1/appStoreVersions/{vid}/appStoreVersionLocalizations")
            for loc in vlocs:
                la = attrs(loc)
                loc_id = loc["id"]
                try:
                    sets = screenshot_sets(c, loc_id)
                    counts = []
                    for s in sets:
                        n = len(c.get_all(f"/v1/appScreenshotSets/{s['id']}/appScreenshots"))
                        if n:
                            counts.append(f"{s['attributes'].get('screenshotDisplayType')}:{n}")
                    shots = ", ".join(counts) if counts else "none"
                except AscError:
                    shots = "?"
                print(report.kv(
                    f"loc {la.get('locale')}",
                    f"desc {len(la.get('description') or '')} chars, keywords: {'yes' if la.get('keywords') else 'NO'}, screenshots: {shots}",
                ))
        except AscError as e:
            print(report.warn(f"could not read version localizations: {e.status}"))
        print()

    # builds
    builds = latest_builds(c, app["id"], 5)
    if builds:
        rows = [
            [
                attrs(b).get("version"),
                attrs(b).get("processingState"),
                (attrs(b).get("uploadedDate") or "")[:16],
            ]
            for b in builds
        ]
        print(report.head("Recent builds"))
        print(report.table(rows, headers=("build", "processing state", "uploaded")))
        print()
        invalid = [b for b in builds if attrs(b).get("processingState") == "INVALID"]
        if invalid:
            playbooks.print_playbook("invalid-binary")

    # review submissions
    try:
        subs = c.get_all(f"/v1/apps/{app['id']}/reviewSubmissions")
        if subs:
            rows = [[s["id"][:8], attrs(s).get("state"), (attrs(s).get("submittedDate") or "")[:16]] for s in subs[:5]]
            print(report.head("Review submissions"))
            print(report.table(rows, headers=("id", "state", "submitted")))
            print()
    except AscError:
        pass

    # IAPs
    try:
        iaps = c.get_all(f"/v1/apps/{app['id']}/inAppPurchasesV2?limit=50")
        if iaps:
            rows = [
                [attrs(i).get("productId"), attrs(i).get("state"), attrs(i).get("inAppPurchaseType")]
                for i in iaps
            ]
            print(report.head("In-app purchases"))
            print(report.table(rows, headers=("product id", "state", "type")))
            print()
            stuck = [i for i in iaps if attrs(i).get("state") == "MISSING_METADATA"]
            if stuck:
                playbooks.print_playbook("sub-missing-metadata")
    except AscError:
        pass

    # next action
    print(report.hr())
    state = attrs(editable).get("appStoreState") if editable else None
    if state == "REJECTED":
        print(report.info("next: respond in Resolution Center, fix, then shipside submit --yes (playbook: review-rejected)"))
    elif editable is None:
        print(report.info("next: no editable version - shipside plan   (creates one, or shows the web fallback)"))
    elif not builds or all(attrs(b).get("processingState") != "VALID" for b in builds):
        print(report.info("next: upload a build, then shipside submit --yes   (playbook: no-valid-build)"))
    else:
        print(report.info("next: shipside plan   (dry-run the submission and see every blocker)"))
    print(report.info(f"{c.http_calls} API calls in {time.time() - t0:.1f}s"))
    return 0
