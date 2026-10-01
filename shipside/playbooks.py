"""Known failure modes and their exact recovery steps.

Every entry here was paid for in a real submission. The runtime prints the
matching playbook when the corresponding API error appears, so the operator
never has to rediscover it. Fuller narratives: docs/PLAYBOOKS.md.
"""
from __future__ import annotations

WEB_BASE = "https://appstoreconnect.apple.com/apps"

PLAYBOOKS = {
    "version-create-405": {
        "title": "ASC refused to create the app version via API (HTTP 405)",
        "why": (
            "Some apps sit in a state where the REST API cannot create an "
            "appStoreVersion (this is the 405 version-creation deadlock). "
            "Apple only accepts the first version creation from the web UI in "
            "that state - the API is not wrong, it is locked out."
        ),
        "steps": [
            "Open https://appstoreconnect.apple.com/apps and click your app.",
            "Go to 'Distribution' (or 'App Store' > '+ iOS App Version').",
            "Click the + next to the version list, enter the version number, 'Create'.",
            "Re-run: shipside state   - the CLI will pick up the editable version.",
        ],
    },
    "app-not-found": {
        "title": "No App Store Connect app record for this bundle id",
        "why": (
            "The ASC REST API has no endpoint to CREATE an app record (only "
            "GET/PATCH /v1/apps exist - verified). The first app record must "
            "be created once, in the web UI (or via fastlane produce)."
        ),
        "steps": [
            "Open https://appstoreconnect.apple.com/apps > '+ New App'.",
            "Enter Name, Primary Language, Bundle ID (select the registered one), SKU.",
            "Re-run: shipside state",
        ],
    },
    "key-auth-401": {
        "title": "App Store Connect rejected the API key (401)",
        "why": (
            "The JWT was signed but Apple did not accept it: key id, issuer "
            "id, or the .p8 file do not match, or the key was revoked."
        ),
        "steps": [
            "Check ASC: Users and Access > Integrations > App Store Connect API > keys.",
            "The Issuer ID is displayed at the top of that page - it must match asc.issuer_id.",
            "The Key ID column must match asc.key_id, and asc.key_path must point at that key's .p8.",
            "Key role must be at least 'App Manager' to create versions and submit.",
            "Re-run: shipside doctor",
        ],
    },
    "key-forbidden-403": {
        "title": "API key is not allowed to do this (403)",
        "why": (
            "Either the key role is too low (Developer cannot create/patch "
            "versions), or the resource belongs to a different team."
        ),
        "steps": [
            "Users and Access > Integrations > edit the key role to 'App Manager' (or Admin).",
            "Confirm the key belongs to the same team as the app.",
        ],
    },
    "no-valid-build": {
        "title": "No VALID build is attached / available",
        "why": (
            "A submission needs a processed build. Builds upload via Xcode, "
            "xcodebuild + altool, or Transporter - Shipside drives the web "
            "API, not the binary upload."
        ),
        "steps": [
            "Upload the archive: Xcode > Product > Archive > Distribute App, or",
            "  xcrun altool --upload-app -f App.ipa -t ios --apiKey <KEY_ID> --apiIssuer <ISSUER>",
            "Processing takes 5-30 min; Apple's intake lags - poll, don't re-upload.",
            "Run: shipside state   - it waits with you and attaches the newest VALID build.",
        ],
    },
    "invalid-binary": {
        "title": "Build shows INVALID in App Store Connect",
        "why": (
            "Apple rejected the binary during processing (ITMS-… errors arrive "
            "by email minutes after 'Processing' finishes). The version and "
            "metadata survive - only the build must be replaced."
        ),
        "steps": [
            "Open the ITMS email - it names the exact cause. Common ones:",
            "  ITMS-91055: missing privacy manifest -> add PrivacyInfo.xcprivacy (see docs/PLAYBOOKS.md).",
            "  ITMS-90474: iOS deployment target mismatch with UIRequiredDeviceCapabilities.",
            "  ITMS-90022/90023: icon contents/alpha (flatten the 1024px icon, no alpha).",
            "  ITSAppUsesNonExemptEncryption missing -> set false in Info.plist.",
            "Fix, bump CURRENT_PROJECT_VERSION (build number), re-upload.",
            "Do NOT create a new version - re-run: shipside submit --yes   (it picks the new VALID build).",
        ],
    },
    "whatsnew-locked-409": {
        "title": "'What's New' cannot be set on this version (409)",
        "why": (
            "whatsNew is locked on a first-ever version - ASC rejects the "
            "field while the app has no approved version yet. Release notes "
            "become settable from the second version on."
        ),
        "steps": [
            "Ignore for the first release - this is expected.",
            "From v1.0.1 on, put release notes in metadata/<locale>/release_notes.txt.",
        ],
    },
    "attach-build-conflict-409": {
        "title": "Could not attach the build (409 conflict)",
        "why": (
            "The build usually already belongs to this version (retry after a "
            "500 - a 409 on the retried PATCH means the first PATCH landed), "
            "or the build bit-lifts a higher minimum OS than the version."
        ),
        "steps": [
            "Run: shipside state   - if 'Build attached' shows, this is already done.",
            "If the build's minimum OS exceeds the version's, raise the version's minimum OS in ASC web.",
        ],
    },
    "screenshot-size": {
        "title": "Screenshot size rejected",
        "why": (
            "The 6.7-inch set (APP_IPHONE_67) accepts 1290x2796 and "
            "1320x2868. Note: APP_IPHONE_69 is NOT a valid enum value - "
            "ASC's 6.9-inch slots are served by the 67 set. Shipside falls "
            "back automatically; this message means every fallback failed."
        ),
        "steps": [
            "Export screenshots at 1320x2868 (iPhone 16 Pro Max) or 1290x2796.",
            "Re-run: shipside screenshots <dir>",
        ],
    },
    "sub-missing-metadata": {
        "title": "In-app purchase / subscription stuck in MISSING_METADATA",
        "why": (
            "Four known causes: (1) no subscriptionAvailabilities was POSTed "
            "(API-created subs never get one, and it is a CREATE-only resource "
            "- GET returns 403); (2) territory prices were not fanned out "
            "(availableInNewTerritories alone opens storefronts but does not "
            "PRICE them - inline prices per storefront are required); (3) the "
            "review screenshot is not exactly 640x920 - other sizes PUT with "
            "200 but the subscription stays MISSING_METADATA forever; (4) an "
            "orphaned screenshot reservation - recover its id via the "
            "appStoreReviewScreenshot relationship, DELETE it, re-create."
        ),
        "steps": [
            "Re-create the availability (POST subscriptionAvailabilities, do not GET first).",
            "Fan out inline prices: GET /equalizations, then PATCH inline price per territory base price.",
            "Upload a 640x920 review screenshot to the subscription.",
            "State recomputes async in ~5-75s - poll; sandbox test-purchases propagate 30-60 min later.",
        ],
    },
    "privacy-labels": {
        "title": "Privacy nutrition labels cannot be set with an API key",
        "why": (
            "The App Privacy answers are not exposed to standard API keys. "
            "They must be set once in the web UI (or via fastlane's "
            "upload_app_privacy_details_to_app_store)."
        ),
        "steps": [
            "ASC > your app > App Privacy > Edit: answer the data-collection questions.",
            "'Data Not Collected' is the honest answer for offline-only apps.",
            "In code, also ship PrivacyInfo.xcprivacy so the build passes ITMS-91055.",
        ],
    },
    "age-rating-stuck": {
        "title": "Age rating could not be saved via API",
        "why": (
            "The declaration PATCH rejects one attribute at a time; Shipside "
            "iterates automatically. If it still fails, a field is missing "
            "from the known enum list."
        ),
        "steps": [
            "ASC > your app > App Privacy > Edit > Age Rating questionnaire.",
            "Copy the attribute name from the error above into [age_rating] in shipside.toml.",
        ],
    },
    "content-rights-500": {
        "title": "contentRightsDeclaration PATCH failed",
        "why": (
            "This endpoint 500s intermittently. Shipside retries and applies "
            "the flip trick (set USES_THIRD_PARTY_CONTENT, then back to "
            "DOES_NOT_USE_THIRD_PARTY_CONTENT)."
        ),
        "steps": [
            "Retry once more (transient).",
            "Falling back: ASC > App Information > Content Rights > answer in web, then re-run.",
        ],
    },
    "review-rejected": {
        "title": "Version is REJECTED",
        "why": (
            "App Review returned the version. The same version object is "
            "reused - reply in Resolution Center, fix, resubmit."
        ),
        "steps": [
            "Read the rejection in ASC > the version > Resolution Center.",
            "Fix, reply to the reviewer there (required), then: shipside submit --yes",
        ],
    },
}


def print_playbook(pid: str, log=print) -> None:
    pb = PLAYBOOKS.get(pid)
    if not pb:
        return
    log("")
    log(f"  PLAYBOOK: {pb['title']}")
    log(f"  why: {pb['why']}")
    for s in pb["steps"]:
        log(f"    - {s}")
    log("")
