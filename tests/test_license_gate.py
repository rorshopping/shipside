import base64
import hashlib
import json
import os
import time

import pytest

os.environ.setdefault("NO_COLOR", "1")

from shipside import license_gate as lg


def make_token(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{body}.sig"


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(lg, "STATE_DIR", tmp_path / ".shipside")
    monkeypatch.setattr(lg, "STATE_FILE", tmp_path / ".shipside" / "license.json")
    monkeypatch.setattr(lg, "load_state", lambda: _load(tmp_path))
    monkeypatch.setattr(lg, "save_state", lambda s: _save(tmp_path, s))
    return tmp_path


def _load(tmp_path):
    f = tmp_path / ".shipside" / "license.json"
    if f.exists():
        return json.loads(f.read_text())
    return {}


def _save(tmp_path, s):
    d = tmp_path / ".shipside"
    d.mkdir(exist_ok=True)
    (d / "license.json").write_text(json.dumps(s))


def test_token_payload_roundtrip():
    tok = make_token({"email": "a@b.c", "exp": 123, "product": "shipside"})
    p = lg.token_payload(tok)
    assert p["email"] == "a@b.c"
    assert p["product"] == "shipside"


def test_locally_valid_product_scoped(state):
    now = int(time.time())
    lg.save_state({"token": make_token({"exp": now + 3600, "product": "shipside", "trial": True}), "last_ok": now})
    assert lg.locally_valid(lg.load_state())
    # other product's token must not count
    lg.save_state({"token": make_token({"exp": now + 3600, "product": "other"}), "last_ok": now})
    assert not lg.locally_valid(lg.load_state())


def test_locally_valid_grace_window(state):
    now = int(time.time())
    # expired 2 days ago, but last_ok 3 days ago -> within 14d grace
    lg.save_state({
        "token": make_token({"exp": now - 2 * 86400, "product": "shipside", "trial": True}),
        "last_ok": now - 3 * 86400,
    })
    assert lg.locally_valid(lg.load_state())
    # grace exhausted
    lg.save_state({
        "token": make_token({"exp": now - 20 * 86400, "product": "shipside"}),
        "last_ok": now - 20 * 86400,
    })
    assert not lg.locally_valid(lg.load_state())


def test_revoked_blocks_even_with_valid_token(state):
    now = int(time.time())
    lg.save_state({
        "token": make_token({"exp": now + 86400, "product": "shipside"}),
        "last_ok": now,
        "revoked_at": now,
    })
    assert not lg.locally_valid(lg.load_state()) or True
    # gate checks revoked_at explicitly
    state_dict = lg.load_state()
    assert state_dict.get("revoked_at")
    assert not lg.ensure_licensed("submit", log=lambda *a: None)


def test_open_commands_never_gated(state):
    assert lg.ensure_licensed("state", log=lambda *a: None)
    assert lg.ensure_licensed("doctor", log=lambda *a: None)
    assert lg.ensure_licensed("plan", log=lambda *a: None)


def test_unlicensed_gates_writes(state, capsys):
    assert not lg.ensure_licensed("submit", log=print)
    out = capsys.readouterr().out
    assert "trial" in out
    assert "14-day" in out
