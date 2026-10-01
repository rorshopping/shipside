"""Project config (shipside.toml): discovery, loading, env fallbacks, wizard."""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

CONFIG_NAMES = ("shipside.toml", ".shipside.toml")

DEFAULTS = {
    "bundle": {},
    "asc": {},
    "review": {},
    "app": {},
    "age_rating": {"age_band": "4_PLUS"},
    "license": {},
    "metadata": {},
    "screenshots": {"display_type": "APP_IPHONE_67", "replace": True},
}

ENV_ALIASES = {
    # config key -> (env names tried in order)
    ("asc", "key_id"): ("SHIPSIDE_ASC_KEY_ID", "ASC_KEY_ID"),
    ("asc", "issuer_id"): ("SHIPSIDE_ASC_ISSUER_ID", "ASC_ISSUER_ID"),
    ("asc", "key_path"): ("SHIPSIDE_ASC_KEY_PATH", "ASC_KEY_PATH"),
    ("bundle", "id"): ("SHIPSIDE_BUNDLE_ID",),
}


class ConfigError(Exception):
    pass


def find_config(start: "str | Path | None" = None):
    cur = Path(start or os.getcwd()).resolve()
    for d in [cur, *cur.parents]:
        for name in CONFIG_NAMES:
            p = d / name
            if p.is_file():
                return p
    return None


class Config:
    def __init__(self, path: "Path | None", data: dict):
        self.path = path
        self.data = data

    def section(self, name: str) -> dict:
        merged = dict(DEFAULTS.get(name, {}))
        merged.update(self.data.get(name) or {})
        return merged

    def get(self, *keys, default=None):
        d = self.data
        for k in keys:
            if not isinstance(d, dict) or k not in d:
                return default
            d = d[k]
        return d

    def effective(self, section: str, key: str):
        """Config value or its env fallback."""
        v = self.get(section, key)
        if v not in (None, ""):
            return v
        for env in ENV_ALIASES.get((section, key), ()):
            v = os.environ.get(env)
            if v:
                return v
        return None


def load(explicit: "str | Path | None" = None) -> Config:
    path = Path(explicit) if explicit else find_config()
    if not path or not Path(path).is_file():
        return Config(None, {})
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return Config(Path(path), data)


def require_asc_config(cfg: Config):
    key_id = cfg.effective("asc", "key_id")
    issuer_id = cfg.effective("asc", "issuer_id")
    key_path = cfg.effective("asc", "key_path")
    missing = [
        name
        for name, v in (("asc.key_id", key_id), ("asc.issuer_id", issuer_id), ("asc.key_path", key_path))
        if not v
    ]
    if missing:
        raise ConfigError(
            "Missing App Store Connect credentials: "
            + ", ".join(missing)
            + "\nRun `shipside init` (wizard) or set the ASC_KEY_ID / "
            "ASC_ISSUER_ID / ASC_KEY_PATH environment variables."
        )
    expanded = Path(os.path.expanduser(str(key_path)))
    if not expanded.is_file():
        raise ConfigError(f"API key file not found: {expanded}")
    return key_id, issuer_id, str(expanded)


def bundle_id(cfg: Config, override: "str | None" = None) -> str:
    bid = override or cfg.effective("bundle", "id")
    if not bid:
        raise ConfigError(
            "No bundle id configured. Run `shipside init`, add bundle.id to "
            "shipside.toml, or pass --bundle-id."
        )
    return bid


# -- wizard -------------------------------------------------------------------

WIZARD_FIELDS = [
    ("bundle", "id", "Bundle id", "com.example.myapp"),
    ("bundle", "name", "App name (as on the store)", "My App"),
    ("asc", "key_id", "ASC API Key ID", "ABC123XYZ9"),
    ("asc", "issuer_id", "ASC API Issuer ID", "00000000-0000-0000-0000-000000000000"),
    ("asc", "key_path", "Path to the .p8 key file", "~/.secrets/AuthKey_ABC123XYZ9.p8"),
    ("review", "first_name", "Review contact: first name", "Jane"),
    ("review", "last_name", "Review contact: last name", "Doe"),
    ("review", "email", "Review contact: email", "jane@example.com"),
    ("review", "phone", "Review contact: phone", "+1 555 0100"),
    ("app", "support_url", "Support URL", "https://example.com/support"),
    ("app", "copyright", "Copyright line", "2026 Example Inc"),
]


def _prompt(label: str, default: str) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        v = input(f"  {label}{suffix}: ").strip()
    except EOFError:
        v = ""
    return v or default


def wizard() -> Path:
    from . import report

    print(report.head("Shipside setup - answers are written to shipside.toml"))
    print(report.info("Your .p8 key is referenced by path, never copied or uploaded."))
    print()
    data = {}
    for section, key, label, default in WIZARD_FIELDS:
        data.setdefault(section, {})[key] = _prompt(label, default)
    out = Path(os.getcwd()) / "shipside.toml"
    with open(out, "w", encoding="utf-8") as f:
        for section, values in data.items():
            f.write(f"[{section}]\n")
            for k, v in values.items():
                f.write(f'{k} = "{v}"\n')
            f.write("\n")
        f.write("[age_rating]\nage_band = \"4_PLUS\"   # questionnaire fields default to NONE; override here, e.g.\n")
        f.write("# health_or_wellness_topics = \"FREQUENT_OR_INTENSE\"\n")
    print(report.ok(f"wrote {out}"))
    print(report.info("next: shipside state   (read-only check against App Store Connect)"))
    return out


if __name__ == "__main__":  # pragma: no cover
    wizard()
    sys.exit(0)
