"""Domain operations against ASC: apps, versions, builds, screenshots,
review submissions, age rating, review details.

Each function either succeeds or raises AscError; playbooks are attached by
the command layer. Where Apple's API has two valid routes (it often does),
both are tried - this is the 2026-09-30 launch-day knowledge, kept current.
"""
from __future__ import annotations

import re
import time

from .asc import AscError, attrs, pick

EDITABLE_STATES = ("PREPARE_FOR_SUBMISSION", "DEVELOPER_REJECTED", "REJECTED")


# -- apps ---------------------------------------------------------------------

def find_app(c, bundle_id: str):
    apps = c.get_all(f"/v1/apps?filter[bundleId]={bundle_id}")
    return apps[0] if apps else None


# -- versions ------------------------------------------------------------------

def list_versions(c, app_id: str):
    return c.get_all(f"/v1/apps/{app_id}/appStoreVersions?limit=10")


def editable_version(c, app_id: str):
    return next((v for v in list_versions(c, app_id) if attrs(v).get("appStoreState") in EDITABLE_STATES), None)


def next_version_string(versions) -> str:
    latest = "1.0"
    for v in versions:
        s = attrs(v).get("versionString") or ""
        if re.fullmatch(r"\d+(\.\d+){0,3}", s):
            if tuple(int(p) for p in s.split(".")) > tuple(int(p) for p in latest.split(".")):
                latest = s
    parts = latest.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def create_version(c, app_id: str, version_string: str, copyright_line: str = ""):
    """Create an appStoreVersion. Two API routes exist; a 405 means Apple has
    locked API creation for this app (playbook: version-create-405)."""
    body = {
        "data": {
            "type": "appStoreVersions",
            "attributes": {
                "platform": "IOS",
                "versionString": version_string,
                "appStoreVersionState": "PREPARE_FOR_SUBMISSION",
                "releaseType": "AFTER_APPROVAL",
            },
            "relationships": {"app": {"data": {"type": "apps", "id": app_id}}},
        }
    }
    if copyright_line:
        body["data"]["attributes"]["copyright"] = copyright_line
    try:
        return c.post("/v1/appStoreVersions", body)
    except AscError as e:
        if e.status != 405:
            raise
    # Route 2: nested under the app resource.
    try:
        return c.post(f"/v1/apps/{app_id}/appStoreVersions", body)
    except AscError as e:
        if e.status == 405:
            raise AscError(405, e.body, "POST", "/v1/appStoreVersions") from None
        raise


def ensure_version_localization(c, vid: str, locale: str, fields: dict) -> str:
    """Create or PATCH the appStoreVersionLocalization for one locale."""
    locs = c.get_all(f"/v1/appStoreVersions/{vid}/appStoreVersionLocalizations")
    loc = pick(locs, locale=locale)
    if loc:
        if fields:
            c.patch(
                f"/v1/appStoreVersionLocalizations/{loc['id']}",
                {"data": {"type": "appStoreVersionLocalizations", "id": loc["id"], "attributes": fields}},
            )
        return loc["id"]
    body = {
        "data": {
            "type": "appStoreVersionLocalizations",
            "attributes": {"locale": locale, **fields},
            "relationships": {"appStoreVersion": {"data": {"type": "appStoreVersions", "id": vid}}},
        }
    }
    return c.post(f"/v1/appStoreVersions/{vid}/appStoreVersionLocalizations", body)["data"]["id"]


def get_app_info(c, app_id: str):
    infos = c.get_all(f"/v1/apps/{app_id}/appInfos")
    return infos[0] if infos else None


def ensure_app_info_localization(c, info_id: str, locale: str, fields: dict) -> str:
    locs = c.get_all(f"/v1/appInfos/{info_id}/appInfoLocalizations")
    loc = pick(locs, locale=locale)
    if loc:
        if fields:
            c.patch(
                f"/v1/appInfoLocalizations/{loc['id']}",
                {"data": {"type": "appInfoLocalizations", "id": loc["id"], "attributes": fields}},
            )
        return loc["id"]
    body = {
        "data": {
            "type": "appInfoLocalizations",
            "attributes": {"locale": locale, **fields},
            "relationships": {"appInfo": {"data": {"type": "appInfos", "id": info_id}}},
        }
    }
    return c.post(f"/v1/appInfos/{info_id}/appInfoLocalizations", body)["data"]["id"]


# -- builds --------------------------------------------------------------------

def latest_valid_build(c, app_id: str):
    builds = c.get_all(f"/v1/apps/{app_id}/builds?limit=50")
    valid = [b for b in builds if attrs(b).get("processingState") == "VALID"]
    valid.sort(key=lambda b: attrs(b).get("uploadedDate") or "", reverse=True)
    return valid[0] if valid else None


def latest_builds(c, app_id: str, n: int = 5):
    builds = c.get_all(f"/v1/apps/{app_id}/builds?limit={n}&sort=-uploadedDate")
    return builds[:n]


def attach_build(c, vid: str, build_id: str):
    """Attach a build to a version. A 409 on the *relationship-list* route
    usually means it is already attached (retry-after-500 doctrine)."""
    try:
        c.patch(
            f"/v1/appStoreVersions/{vid}/relationships/builds",
            {"data": [{"type": "builds", "id": build_id}]},
        )
        return
    except AscError as e:
        if e.status != 405 and e.status != 404:
            if e.status == 409:
                return  # already attached / concurrent write won - treat as done
            raise
    c.patch(
        f"/v1/appStoreVersions/{vid}",
        {
            "data": {
                "type": "appStoreVersions",
                "id": vid,
                "relationships": {"build": {"data": {"type": "builds", "id": build_id}}},
            }
        },
    )


def attached_build(c, vid: str):
    r = c.get(f"/v1/appStoreVersions/{vid}/build")
    return (r or {}).get("data") or None


# -- screenshots ---------------------------------------------------------------

def screenshot_sets(c, loc_id: str):
    return c.get_all(f"/v1/appStoreVersionLocalizations/{loc_id}/appScreenshotSets")


def ensure_screenshot_set(c, loc_id: str, display_type: str) -> str:
    sets = screenshot_sets(c, loc_id)
    existing = pick(sets, screenshotDisplayType=display_type)
    if existing:
        return existing["id"]
    r = c.post(
        "/v1/appScreenshotSets",
        {
            "data": {
                "type": "appScreenshotSets",
                "attributes": {"screenshotDisplayType": display_type},
                "relationships": {
                    "appStoreVersionLocalization": {
                        "data": {"type": "appStoreVersionLocalizations", "id": loc_id}
                    }
                },
            }
        },
    )
    return r["data"]["id"]


def clear_screenshots(c, set_id: str, log=print):
    for old in c.get_all(f"/v1/appScreenshotSets/{set_id}/appScreenshots"):
        c.delete(f"/v1/appScreenshots/{old['id']}")
        log(f"    removed old shot {old['id']}")


def upload_screenshot(c, set_id: str, path: str) -> str:
    from .asc import md5_checksum, upload_with_operation

    with open(path, "rb") as f:
        payload = f.read()
    r = c.post(
        "/v1/appScreenshots",
        {
            "data": {
                "type": "appScreenshots",
                "attributes": {"fileName": path.split("/")[-1].split("\\")[-1], "fileSize": len(payload)},
                "relationships": {
                    "appScreenshotSet": {"data": {"type": "appScreenshotSets", "id": set_id}}
                },
            }
        },
    )
    sid = r["data"]["id"]
    ops = r["data"]["attributes"]["uploadOperations"]
    upload_with_operation(ops[0], payload)
    r = c.patch(
        f"/v1/appScreenshots/{sid}",
        {
            "data": {
                "type": "appScreenshots",
                "id": sid,
                "attributes": {"uploaded": True, "sourceFileChecksum": md5_checksum(path)},
            }
        },
    )
    state = (r["data"]["attributes"].get("assetDeliveryState") or {}).get("state")
    # commit+poll: COMPLETE is usually immediate, but Apple sometimes needs a beat
    deadline = time.time() + 60
    while state not in ("COMPLETE", "FAILED") and time.time() < deadline:
        time.sleep(3)
        r = c.get(f"/v1/appScreenshots/{sid}")
        state = (r["data"]["attributes"].get("assetDeliveryState") or {}).get("state")
    return state or "UNKNOWN"


# -- age rating (the questionnaire IS scriptable - launch-day proof) -----------

ENUM_FIELDS = {
    "alcoholTobaccoOrDrugUseOrReferences", "gunsOrOtherWeapons",
    "medicalOrTreatmentInformation", "profanityOrCrudeHumor",
    "sexualContentGraphicAndNudity", "sexualContentOrNudity",
    "horrorOrFearThemes", "matureOrSuggestiveThemes",
    "userGeneratedContent", "violenceCartoonOrFantasy",
    "violenceRealisticProlongedGraphicOrSadistic", "violenceRealistic",
    "gamblingSimulated", "gambling", "contests", "lootBox",
    "messagingAndChat", "parentalControls", "unrestrictedWebAccess",
    "socialMedia", "socialMediaAgeRestricted", "ageAssurance",
    "healthOrWellnessTopics",
}


def age_rating_declaration_id(c, app_id: str) -> str:
    info = get_app_info(c, app_id)
    r = c.get(f"/v1/appInfos/{info['id']}/ageRatingDeclaration")
    return r["data"]["id"]


def set_age_rating(c, app_id: str, overrides: "dict | None" = None, log=print) -> bool:
    """Patch the age rating questionnaire, iterating on Apple's one-attribute-
    per-error validation until it sticks. Returns True on success."""
    aid = age_rating_declaration_id(c, app_id)
    question_attrs = {
        "alcoholTobaccoOrDrugUseOrReferences": "NONE",
        "contests": "NONE",
        "gambling": "NONE",
        "gamblingSimulated": "NONE",
        "gunsOrOtherWeapons": "NONE",
        "healthOrWellnessTopics": "NONE",
        "lootBox": "NONE",
        "medicalOrTreatmentInformation": "NONE",
        "messagingAndChat": "NONE",
        "parentalControls": "NONE",
        "profanityOrCrudeHumor": "NONE",
        "sexualContentGraphicAndNudity": "NONE",
        "sexualContentOrNudity": "NONE",
        "horrorOrFearThemes": "NONE",
        "matureOrSuggestiveThemes": "NONE",
        "unrestrictedWebAccess": "NONE",
        "userGeneratedContent": "NONE",
        "violenceCartoonOrFantasy": "NONE",
        "violenceRealisticProlongedGraphicOrSadistic": "NONE",
        "violenceRealistic": "NONE",
    }
    question_attrs.update(overrides or {})
    question_attrs = {k: v for k, v in question_attrs.items() if v}
    payload_attrs = {"ageBand": "4_PLUS", **question_attrs}

    for attempt in range(10):
        try:
            c.patch(
                f"/v1/ageRatingDeclarations/{aid}",
                {"data": {"type": "ageRatingDeclarations", "id": aid, "attributes": payload_attrs}},
            )
            log(f"    age rating set (attempt {attempt + 1})")
            return True
        except AscError as e:
            raw = e.body
            changed = False
            for name in set(re.findall(r"attribute '([A-Za-z]+)'", raw)) | set(
                re.findall(r"attribute .([A-Za-z]+)\.", raw)
            ):
                if name not in payload_attrs and name in ENUM_FIELDS:
                    payload_attrs[name] = "NONE"
                    changed = True
                    log(f"    adding required field {name}=NONE")
                m = re.search(r"attribute .(%s)\..*Expected a (\w+)" % name, raw)
                if m and m.group(2) == "BOOLEAN" and isinstance(payload_attrs.get(name), str):
                    payload_attrs[name] = False
                    changed = True
            if not changed:
                raise
            time.sleep(1)
    return False


# -- review plumbing -----------------------------------------------------------

def review_details(c, vid: str):
    try:
        r = c.get(f"/v1/appStoreVersions/{vid}/appStoreReviewDetail")
        return r.get("data") or None
    except AscError as e:
        if e.status == 404:
            return None
        raise


def create_review_details(c, vid: str, contact: dict, notes: str = ""):
    body_attrs = {
        "contactFirstName": contact["first_name"],
        "contactLastName": contact["last_name"],
        "contactEmail": contact["email"],
        "contactPhone": contact["phone"],
        "demoAccountRequired": False,
    }
    if notes:
        body_attrs["notes"] = notes
    return c.post(
        "/v1/appStoreReviewDetails",
        {
            "data": {
                "type": "appStoreReviewDetails",
                "attributes": body_attrs,
                "relationships": {
                    "appStoreVersion": {"data": {"type": "appStoreVersions", "id": vid}}
                },
            }
        },
    )


def set_content_rights(c, app_id: str, log=print):
    """contentRightsDeclaration 500s intermittently; retry + flip trick."""
    def patch(value):
        c.patch(
            f"/v1/apps/{app_id}",
            {"data": {"type": "apps", "id": app_id, "attributes": {"contentRightsDeclaration": value}}},
        )

    for attempt in range(3):
        try:
            patch("DOES_NOT_USE_THIRD_PARTY_CONTENT")
            return True
        except AscError as e:
            if e.status == 500 and attempt < 2:
                try:
                    patch("USES_THIRD_PARTY_CONTENT")
                except AscError:
                    pass
                time.sleep(2)
                continue
            raise
    return False


def open_review_submission(c, app_id: str):
    subs = c.get_all(f"/v1/apps/{app_id}/reviewSubmissions")
    for s in subs:
        if attrs(s).get("state") in ("READY_FOR_REVIEW", "UNRESOLVED_ISSUES", "WAITING_FOR_REVIEW"):
            return s
    return None


def create_review_submission(c, app_id: str) -> str:
    r = c.post(
        "/v1/reviewSubmissions",
        {
            "data": {
                "type": "reviewSubmissions",
                "attributes": {"platform": "IOS"},
                "relationships": {"app": {"data": {"type": "apps", "id": app_id}}},
            }
        },
    )
    return r["data"]["id"]


def review_submission_items(c, rs_id: str):
    return c.get_all(f"/v1/reviewSubmissions/{rs_id}/items")


def add_review_submission_item(c, rs_id: str, resource_type: str, resource_id: str):
    return c.post(
        "/v1/reviewSubmissionItems",
        {
            "data": {
                "type": "reviewSubmissionItems",
                "relationships": {
                    "reviewSubmission": {"data": {"type": "reviewSubmissions", "id": rs_id}},
                    resource_type: {"data": {"type": resource_type, "id": resource_id}},
                },
            }
        },
    )


def submit_review_submission(c, rs_id: str):
    return c.patch(
        f"/v1/reviewSubmissions/{rs_id}",
        {"data": {"type": "reviewSubmissions", "id": rs_id, "attributes": {"submitted": True}}},
    )
