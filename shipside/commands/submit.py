"""`shipside submit` / `shipside plan` - dry-run plan, then execute the submission.

plan  = every step with status ok / fix / blocked, nothing written.
submit --yes = run the fixes (version, age rating, review details, content
rights, build attach), create the review submission and submit for review.

The submit step is the only irreversible action in Shipside and requires --yes.
"""
from __future__ import annotations

import time

from .. import playbooks, report
from ..asc import AscError, attrs
from ..config import bundle_id
from ..steps import (
    add_review_submission_item,
    age_rating_declaration_id,
    attached_build,
    attach_build,
    create_review_details,
    create_review_submission,
    create_version,
    editable_version,
    find_app,
    latest_valid_build,
    list_versions,
    next_version_string,
    open_review_submission,
    review_details,
    review_submission_items,
    screenshot_sets,
    set_age_rating,
    set_content_rights,
    submit_review_submission,
    get_app_info,
)

OK, FIX, BLOCKED, MANUAL = "ok", "fix", "blocked", "manual"

# reviewSubmissionItems: relationship key is SINGULAR, resource type PLURAL.
REL_MAP = {
    "appStoreVersions": ("appStoreVersion", "appStoreVersions"),
    "subscriptions": ("subscription", "subscriptions"),
    "inAppPurchasesV2": ("inAppPurchaseV2", "inAppPurchasesV2"),
}


class Step:
    def __init__(self, title, status, detail="", action=None, playbook=None):
        self.title, self.status, self.detail = title, status, detail
        self.action = action
        self.playbook = playbook
        self.manual_hint = None
        self.result = ""

    def line(self) -> str:
        mark = {OK: report.ok, FIX: report.warn, BLOCKED: report.err, MANUAL: report.info}[self.status]
        label = {"ok": "ok  ", "fix": "fix ", "blocked": "STOP", "manual": "manl"}[self.status]
        head = mark(f"[{label}] ") + self.title
        if self.detail:
            head += report.c(f"  - {self.detail}", report.DIM)
        return head


def build_plan(c, cfg, bid: str, version_string: "str | None", include_items: "list[tuple[str, str]]"):
    """Collect the submission plan. Returns (steps, ctx). ctx holds resolved
    ids for the executor; early-return is fine for blocked plans."""
    steps: "list[Step]" = []
    ctx = {}

    def add(title, status, detail="", action=None, playbook=None):
        steps.append(Step(title, status, detail, action, playbook))

    app = find_app(c, bid)
    if not app:
        add("app record", BLOCKED, f"none for {bid}", playbook="app-not-found")
        return steps, ctx
    ctx["app_id"] = app["id"]
    a = attrs(app)
    add(
        "app record",
        OK,
        f"{a.get('name')} ({app['id'][:8]})",
    )

    # version
    versions = list_versions(c, app["id"])
    version = editable_version(c, app["id"])
    vs = version_string or next_version_string(versions)
    if version:
        ctx["vid"] = version["id"]
        add("editable version", OK, f"{attrs(version).get('versionString')} ({attrs(version).get('appStoreState')})")
        if attrs(version).get("appStoreState") == "REJECTED":
            steps[-1].playbook = "review-rejected"
    else:
        def make_version():
            created = create_version(c, app["id"], vs, cfg.get("app", "copyright") or "")
            return created["data"]["id"]
        add("editable version", FIX, f"none - will create {vs}", action=make_version)
        ctx["pending_version_string"] = vs

    vid = ctx.get("vid")

    def _with_vid(fn):
        def run():
            real_vid = ctx.get("vid") or fn()
            ctx["vid"] = real_vid
            return real_vid
        return run

    # build
    build = latest_valid_build(c, app["id"])
    if not build:
        add("build", BLOCKED, "no VALID build - upload one first", playbook="no-valid-build")
    else:
        ba = attrs(build)
        add("build", OK, f"{ba.get('version')} uploaded {(ba.get('uploadedDate') or '')[:10]}")
        ctx["build_id"] = build["id"]
        if vid:
            try:
                current = attached_build(c, vid)
            except AscError:
                current = None
            if current and current.get("id") == build["id"]:
                pass
            else:
                add(
                    "attach build",
                    FIX,
                    f"attach {ba.get('version')} to the version",
                    action=lambda: attach_build(c, ctx["vid"], ctx["build_id"]),
                    playbook="attach-build-conflict-409",
                )

    # metadata
    if vid:
        try:
            locs = c.get_all(f"/v1/appStoreVersions/{vid}/appStoreVersionLocalizations")
            en = next((l for l in locs if attrs(l).get("locale") == "en-US"), None)
            desc_len = len(attrs(en).get("description") or "") if en else 0
            if desc_len > 0:
                add("metadata", OK, f"en-US description {desc_len} chars")
            else:
                add("metadata", FIX, "en-US description empty", action=None, playbook=None)
                steps[-1].manual_hint = "run: shipside metadata"
        except AscError:
            add("metadata", MANUAL, "could not read version localizations")
                # screenshots
        try:
            shot_total = 0
            for loc in locs:
                sets = screenshot_sets(c, loc["id"])
                for s in sets:
                    shot_total += len(c.get_all(f"/v1/appScreenshotSets/{s['id']}/appScreenshots"))
            if shot_total:
                add("screenshots", OK, f"{shot_total} on the version")
            else:
                add("screenshots", BLOCKED, "none on any locale - review requires them",
                    playbook="screenshot-size")
                steps[-1].manual_hint = "run: shipside screenshots <dir>"
        except AscError:
            add("screenshots", MANUAL, "could not read screenshot sets")

    # age rating
    overrides = {k: v for k, v in cfg.section("age_rating").items() if k != "age_band"}
    try:
        aid = age_rating_declaration_id(c, app["id"])
        decl = c.get(f"/v1/ageRatingDeclarations/{aid}")
        da = attrs(decl)
        answered = sum(1 for k, v in da.items() if v and k not in ("ageBand",))
        if da.get("ageBand") and answered >= 10:
            add("age rating", OK, f"band {da.get('ageBand')}, {answered} answers")
        else:
            def fix_age():
                return set_age_rating(c, app["id"], overrides, log=print)
            add("age rating", FIX, f"incomplete ({answered} answers) - will set 4_PLUS + NONE defaults",
                action=fix_age, playbook="age-rating-stuck")
    except AscError:
        # Reads intermittently 403 on some apps - attempt the write in execute
        # instead; set_age_rating surfaces Apple's real error if it persists.
        def fix_age():
            return set_age_rating(c, app["id"], overrides, log=print)
        add("age rating", FIX, "unreadable - will attempt to set during execute",
            action=fix_age, playbook="age-rating-stuck")

    # review details
    if vid:
        rd = review_details(c, vid)
        contact = cfg.section("review")
        have_contact = all(contact.get(k) for k in ("first_name", "last_name", "email", "phone"))
        if rd:
            add("review contact", OK, attrs(rd).get("contactEmail", "?"))
        elif have_contact:
            def fix_rd():
                return create_review_details(
                    c, ctx["vid"], contact,
                    contact.get("notes") or "Test account not required.",
                )
            add("review contact", FIX, f"will create from shipside.toml ({contact.get('email')})",
                action=fix_rd)
        else:
            add("review contact", BLOCKED, "missing - run `shipside init` or fill [review] in shipside.toml")

    # content rights
    if not a.get("contentRightsDeclaration"):
        add("content rights", FIX, "will set DOES_NOT_USE_THIRD_PARTY_CONTENT",
            action=lambda: set_content_rights(c, app["id"], log=print),
            playbook="content-rights-500")
    else:
        add("content rights", OK, a.get("contentRightsDeclaration"))

    # privacy reminder (cannot be verified with a standard API key)
    add("privacy labels", MANUAL, "not settable via API - confirm App Privacy answers in the web UI",
        playbook="privacy-labels")

    # review submission
    rs = open_review_submission(c, app["id"])
    if rs:
        ctx["rs_id"] = rs["id"]
        add("review submission", OK, f"open container {rs['id'][:8]} ({attrs(rs).get('state')})")
    else:
        def make_rs():
            rs_id = create_review_submission(c, app["id"])
            ctx["rs_id"] = rs_id
            return rs_id
        add("review submission", FIX, "will create", action=make_rs)

    if include_items:
        add("extra review items", FIX, ", ".join(t for t, _ in include_items),
            action=lambda: [
                add_review_submission_item(c, ctx["rs_id"], *REL_MAP.get(t, (t, t)), i)
                for t, i in include_items
            ])

    if vid:
        ctx["vid"] = vid
    return steps, ctx


def run(c, cfg, args) -> int:
    bid = bundle_id(cfg, getattr(args, "bundle_id", None))
    include_items = []
    for sub in getattr(args, "include_subscription", None) or []:
        include_items.append(("subscriptions", sub))
    for iap in getattr(args, "include_iap", None) or []:
        include_items.append(("inAppPurchasesV2", iap))

    t0 = time.time()
    print(report.head(("PLAN (dry run) - " if args.plan else "SUBMIT - ") + bid))
    print()
    try:
        steps, ctx = build_plan(c, cfg, bid, getattr(args, "version_string", None), include_items)
    except AscError as e:
        _print_asc_error(e)
        return 1

    for s in steps:
        print(s.line())
        if s.status == BLOCKED and s.playbook:
            playbooks.print_playbook(s.playbook)
    print()
    blocked = [s for s in steps if s.status == BLOCKED]
    fixes = [s for s in steps if s.status == FIX]

    if args.plan or blocked:
        if blocked:
            print(report.err(f"{len(blocked)} blocker(s) - resolve them, then re-run"))
        else:
            print(report.info(f"plan looks clean: {len(fixes)} automated step(s), nothing written in plan mode"))
        return 1 if blocked else 0

    if not getattr(args, "yes", False):
        print(report.warn(f"{len(fixes)} automated step(s) ready. This ends with an IRREVERSIBLE submit for review."))
        print(report.info("dry run again: shipside plan    execute: shipside submit --yes"))
        return 2

    # execute
    app_id = ctx["app_id"]
    print(report.head("Executing..."))
    n = 0
    try:
        for s in fixes:
            n += 1
            print(report.step(n, s.title))
            if s.manual_hint and not s.action:
                print(report.info("  " + s.manual_hint))
                continue
            s.action()
        print(report.step(n + 1, "creating/refreshing review submission"))
        rs_id = ctx.get("rs_id") or create_review_submission(c, app_id)
        ctx["rs_id"] = rs_id
        vid = ctx.get("vid")
        items = review_submission_items(c, rs_id)
        have = any(
            (it.get("relationships", {}).get("appStoreVersion", {}).get("data") or {}).get("id") == vid
            for it in items
        )
        if not have and vid:
            add_review_submission_item(c, rs_id, "appStoreVersion", "appStoreVersions", vid)
            print(report.info("  version added to submission"))
        for t, i in include_items:
            rel = {"appStoreVersions": "appStoreVersion", "subscriptions": "subscription",
                   "inAppPurchasesV2": "inAppPurchaseV2"}.get(t, t)
            add_review_submission_item(c, rs_id, rel, t, i)
            print(report.info(f"  {t}:{i} added"))

        print(report.step(n + 2, "SUBMITTING FOR REVIEW (irreversible)"))
        submit_review_submission(c, rs_id)
    except AscError as e:
        _print_asc_error(e)
        return 1

    # poll final state
    final_state = "?"
    for _ in range(6):
        time.sleep(5)
        try:
            v = c.get(f"/v1/appStoreVersions/{vid}")
            final_state = attrs(v.get("data")).get("appStoreState")
            if final_state in ("WAITING_FOR_REVIEW",):
                break
        except AscError:
            pass
    print()
    print(report.head("Submission report"))
    print(report.kv("version", f"{ctx.get('pending_version_string') or ''} {final_state}"))
    print(report.kv("review submission", f"{rs_id[:8]} ({final_state})"))
    print(report.kv("API calls", c.http_calls))
    print(report.kv("elapsed", f"{time.time() - t0:.0f}s"))
    if final_state == "WAITING_FOR_REVIEW":
        print()
        print(report.ok("Submitted. The version is with App Review. Apple emails status changes."))
        return 0
    print(report.warn(f"Submitted, but the version state reads {final_state} - check ASC web."))
    return 2


def _print_asc_error(e: AscError) -> None:
    print(report.err(f"ASC API {e.method} {e.path.split('?')[0]} -> {e.status}"))
    if e.detail():
        print(report.c(e.detail(), report.DIM))
    pb = None
    if e.status == 401:
        pb = "key-auth-401"
    elif e.status == 403:
        pb = "key-forbidden-403"
    elif e.status == 405 and "appStoreVersions" in e.path:
        pb = "version-create-405"
    if pb:
        playbooks.print_playbook(pb)
