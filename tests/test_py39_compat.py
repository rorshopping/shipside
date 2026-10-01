"""Prove the 3.9/3.10 fallback import in config.py actually engages.

The bug CI found on 2026-10-02 was a hard `import tomllib`, which is stdlib
only from 3.11. This test hides tomllib to force the fallback branch, so the
guard is verified rather than assumed. Without it, the next refactor could
re-introduce a crash for every buyer on 3.9/3.10 and the suite would still be
green on 3.12+.
"""
import builtins
import importlib
import sys

import pytest


def _reload_config_without_tomllib():
    """Re-import shipside.config with tomllib unavailable, like Python 3.9."""
    for name in list(sys.modules):
        if name == "shipside.config" or name.startswith("shipside."):
            del sys.modules[name]
    # drop the editable-install path entry so the fresh import is used
    real_import = builtins.__import__

    def guarded(name, *a, **k):
        if name == "tomllib":
            raise ModuleNotFoundError("No module named 'tomllib'")
        return real_import(name, *a, **k)

    builtins.__import__ = guarded
    try:
        return importlib.import_module("shipside.config")
    finally:
        builtins.__import__ = real_import
        for name in list(sys.modules):
            if name == "shipside.config" or name.startswith("shipside."):
                del sys.modules[name]


def test_config_imports_without_stdlib_tomllib():
    mod = _reload_config_without_tomllib()
    assert mod is not None
    # the fallback must expose the same API surface the code uses
    assert hasattr(mod.tomllib, "loads")
    assert hasattr(mod.tomllib, "load")


def test_fallback_still_reads_a_toml_file(tmp_path):
    mod = _reload_config_without_tomllib()
    p = tmp_path / "shipside.toml"
    p.write_text('[bundle]\nid = "com.example.app"\n', encoding="utf-8")
    cfg = mod.load(p)
    assert cfg.effective("bundle", "id") == "com.example.app"


def test_pyproject_declares_tomli_for_old_python():
    """The fallback needs a real dependency, not just a conditional import."""
    import pathlib

    pyproject = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert "tomli" in text
    assert "python_version < '3.11'" in text
    assert 'requires-python = ">=3.9"' in text
