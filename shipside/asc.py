"""App Store Connect API client: ES256 JWT auth, retry/backoff, pagination.

Transport only - domain operations live in shipside.steps.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://api.appstoreconnect.apple.com"
RETRYABLE = {429, 500, 502, 503, 504}


class AscError(Exception):
    """A non-retryable (or exhausted-retry) API failure."""

    def __init__(self, status: int, body: str, method: str, path: str):
        self.status = status
        self.body = body or ""
        self.method = method
        self.path = path
        try:
            self.errors = json.loads(self.body).get("errors", [])
        except Exception:
            self.errors = []
        super().__init__(f"{method} {path} -> HTTP {status}")

    def detail(self) -> str:
        parts = []
        for e in self.errors[:4]:
            parts.append(
                "  [{}] {}: {}".format(
                    e.get("status", "?"), e.get("code", "?"), e.get("detail") or e.get("title", "")
                )
            )
        return "\n".join(parts) if parts else self.body[:800]

    def error_codes(self):
        return [e.get("code", "") for e in self.errors]


class Client:
    def __init__(self, key_id: str, issuer_id: str, key_path: str, log=None):
        self.key_id = key_id
        self.issuer_id = issuer_id
        self.key_path = os.path.expanduser(key_path)
        self._tok = None
        self._tok_exp = 0.0
        self.log = log or (lambda msg: None)
        self.http_calls = 0

    # -- auth ---------------------------------------------------------------
    def token(self) -> str:
        now = time.time()
        if self._tok and now < self._tok_exp - 120:
            return self._tok
        import jwt  # PyJWT

        with open(self.key_path, "r", encoding="utf-8") as f:
            key = f.read()
        iat = int(now) - 30
        exp = iat + 20 * 60
        self._tok = jwt.encode(
            {"iss": self.issuer_id, "iat": iat, "exp": exp, "aud": "appstoreconnect-v1"},
            key,
            algorithm="ES256",
            headers={"kid": self.key_id},
        )
        self._tok_exp = exp
        return self._tok

    # -- transport ----------------------------------------------------------
    def request(self, method: str, path: str, body=None, retries: int = 4, timeout: int = 90):
        url = path if path.startswith("http") else BASE + path
        last_err = None
        for attempt in range(retries):
            self.http_calls += 1
            req = urllib.request.Request(url, method=method)
            req.add_header("Authorization", "Bearer " + self.token())
            req.add_header("Content-Type", "application/json")
            data = json.dumps(body).encode() if body is not None else None
            try:
                with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                raw = e.read().decode(errors="replace")
                if e.code in RETRYABLE and attempt < retries - 1:
                    try:
                        wait = int(e.headers.get("Retry-After") or 0)
                    except (TypeError, ValueError):
                        wait = 0
                    wait = wait or min(45, 3 * (attempt + 1) ** 2)
                    self.log(
                        f"  HTTP {e.code} on {method} {path.split('?')[0]} - "
                        f"retrying in {wait}s ({attempt + 1}/{retries})"
                    )
                    time.sleep(wait)
                    last_err = e
                    continue
                raise AscError(e.code, raw, method, path)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    last_err = e
                    continue
                raise AscError(0, f"network error: {e}", method, path)
        raise AscError(0, f"gave up after {retries} attempts: {last_err}", method, path)

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body=None):
        return self.request("POST", path, body)

    def patch(self, path, body=None):
        return self.request("PATCH", path, body)

    def delete(self, path):
        return self.request("DELETE", path)

    def get_all(self, path: str, max_pages: int = 20):
        out, url = [], path
        for _ in range(max_pages):
            d = self.get(url) or {}
            out.extend(d.get("data") or [])
            nxt = (d.get("links") or {}).get("next")
            if not nxt:
                break
            url = nxt
        return out


# -- shared low-level helpers -----------------------------------------------

def md5_checksum(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def upload_with_operation(upload_op: dict, payload: bytes) -> None:
    """Perform one ASC asset-delivery uploadOperation (a presigned PUT)."""
    req = urllib.request.Request(upload_op["url"], data=payload, method=upload_op.get("method", "PUT"))
    for h in upload_op.get("requestHeaders", []):
        req.add_header(h.get("key", h.get("name", "")), h.get("value", ""))
    urllib.request.urlopen(req, timeout=300)


def attrs(obj: dict) -> dict:
    return (obj or {}).get("attributes") or {}


def pick(items, **match):
    """First item whose attributes contain every match key/value."""
    for it in items:
        a = it.get("attributes") or {}
        if all(a.get(k) == v for k, v in match.items()):
            return it
    return None
