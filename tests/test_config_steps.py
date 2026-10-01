import os

os.environ.setdefault("NO_COLOR", "1")

from shipside.config import Config, find_config, load
from shipside.steps import next_version_string, pick


def test_find_config_walks_up(tmp_path, monkeypatch):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "shipside.toml").write_text('[bundle]\nid = "com.x.y"\n')
    monkeypatch.chdir(tmp_path / "a" / "b")
    found = find_config()
    assert found and found.name == "shipside.toml"


def test_env_fallback(monkeypatch):
    monkeypatch.setenv("ASC_KEY_ID", "ENVKEY")
    cfg = Config(None, {})
    assert cfg.effective("asc", "key_id") == "ENVKEY"


def test_config_overrides_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ASC_KEY_ID", "ENVKEY")
    p = tmp_path / "shipside.toml"
    p.write_text('[asc]\nkey_id = "TOMLKEY"\n')
    cfg = load(p)
    assert cfg.effective("asc", "key_id") == "TOMLKEY"


def test_next_version_string():
    def v(s):
        return {"attributes": {"versionString": s}}

    assert next_version_string([v("1.0")]) == "1.1"
    assert next_version_string([v("1.0"), v("2.3.9")]) == "2.3.10"
    assert next_version_string([]) == "1.1"


def test_pick_matches_attributes():
    items = [
        {"attributes": {"locale": "en-US", "name": "a"}},
        {"attributes": {"locale": "de-DE", "name": "b"}},
    ]
    assert pick(items, locale="de-DE")["attributes"]["name"] == "b"
    assert pick(items, locale="fr-FR") is None
