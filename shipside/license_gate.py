"""License gate: 14-day trial, email/key activation, offline grace.

Talks to the shared license API (product-scoped server-side). Local state in
~/.shipside/license.json. The HMAC token can only be verified server-side;
offline, the client trusts its own signed token until max(exp, last_ok+14d).
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import LICENSE_API_BASE, PRODUCT, TRIAL_DAYS, BUY_URL

STATE_DIR = Path.home() / ".shipside"
STATE_FILE = STATE_DIR / "license.json"
GRACE_DAYS = 14


# -- state --------------------------------------------------------------------

def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        os.chmod(STATE_FILE, 0o600)
    except OSError:
        pass


def device_id(state: "dict | None" = None) -> str:
    state = state if state is not None else load_state()
    d = state.get("device")
    if not d:
        d = uuid.uuid4().hex
        state["device"] = d
        save_state(state)
    return d


# -- token helpers ------------------------------------------------------------

def token_payload(token: str) -> "dict | None":
    try:
        body = token.split(".")[0]
        body += "=" * (-len(body) % 4)
        return json.loads(base64.urlsafe_b64decode(body.encode()).decode())
    except Exception:
        return None


def locally_valid(state: dict) -> bool:
    """Signed-token + grace-window check that works offline."""
    tok = state.get("token")
    if not tok:
        return False
    payload = token_payload(tok)
    if not payload or payload.get("product") not in (None, PRODUCT):
        return False
    now = time.time()
    exp = float(payload.get("exp") or 0)
    last_ok = float(state.get("last_ok") or 0)
    return now < max(exp, last_ok + GRACE_DAYS * 86400)


# -- API calls ----------------------------------------------------------------

def _post(path: str, payload: dict, timeout: int = 20):
    req = urllib.request.Request(
        LICENSE_API_BASE.rstrip("/") + "/" + path,
        data=json.dumps(payload).encode(),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, {"error": f"network error: {e}"}


def _apply(response: dict, trial: bool = False) -> dict:
    state = load_state()
    state.update(
        {
            "token": response.get("token") or state.get("token"),
            "email": response.get("email") or state.get("email"),
            "exp": response.get("exp") or state.get("exp"),
            "trial": bool(response.get("trial", trial)),
            "product": PRODUCT,
            "last_ok": int(time.time()),
        }
    )
    save_state(state)
    return state


def start_trial(email: str) -> "tuple[int, dict]":
    st, body = _post("trial", {"email": email, "device": device_id(), "product": PRODUCT})
    if st == 200:
        _apply(body, trial=True)
    return st, body


def activate(email: str = "", key: str = "") -> "tuple[int, dict]":
    payload = {"device": device_id(), "product": PRODUCT}
    if email:
        payload["email"] = email
    if key:
        payload["key"] = key
    st, body = _post("activate", payload)
    if st == 200:
        _apply(body)
    return st, body


def revalidate() -> bool:
    """Best-effort server re-check; updates the grace window. Never raises."""
    state = load_state()
    tok = state.get("token")
    if not tok:
        return False
    st, body = _post("validate", {"token": tok})
    if st == 200 and body.get("token"):
        _apply(body, trial=bool(body.get("trial")))
        return True
    if st == 403:
        state["revoked_at"] = int(time.time())
        save_state(state)
    return False


# -- gate ---------------------------------------------------------------------

OPEN_COMMANDS = {"init", "state", "doctor", "license", "plan"}


def ensure_licensed(command: str, log=print) -> bool:
    if command in OPEN_COMMANDS:
        return True
    state = load_state()
    if locally_valid(state) and not state.get("revoked_at"):
        # Refresh the grace window in the background; never block the run.
        import threading

        threading.Thread(target=revalidate, daemon=True).start()
        return True
    payload = token_payload(state.get("token") or "")
    if state.get("revoked_at"):
        log("License inactive (revoked or subscription ended).")
        log(f"Renew at {BUY_URL}")
        return False
    if payload and payload.get("trial") is False and payload.get("exp", 0) < time.time():
        log("License expired.")
        log(f"Renew at {BUY_URL}  -  then: shipside license activate --email you@example.com")
        return False
    log(f"Shipside needs a license for `{command}` (14-day free trial covers everything).")
    log(f"  Start trial:   shipside trial --email you@example.com")
    log(f"  Purchased?     shipside license activate --email you@example.com")
    log(f"  Buy:           {BUY_URL}")
    return False


# -- human commands -----------------------------------------------------------

def fmt_exp(exp) -> str:
    if not exp:
        return "?"
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(int(exp)))


def status_lines() -> "list[str]":
    from . import report

    state = load_state()
    payload = token_payload(state.get("token") or "")
    out = []
    if not payload:
        out.append(report.warn("No license on this machine."))
        out.append(report.info(f"Start the free {TRIAL_DAYS}-day trial: shipside trial --email you@example.com"))
        return out
    kind = "trial" if payload.get("trial") else "license"
    email = state.get("email") or payload.get("email", "?")
    exp = fmt_exp(payload.get("exp"))
    now = time.time()
    if payload.get("exp", 0) < now:
        out.append(report.err(f"{kind.capitalize()} for {email} expired {exp}."))
    else:
        out.append(report.ok(f"{kind.capitalize()} active for {email} until {exp}."))
    last_ok = state.get("last_ok")
    if last_ok:
        out.append(report.info(f"Last server check: {fmt_exp(last_ok)} (offline grace: {GRACE_DAYS} days)"))
    return out
