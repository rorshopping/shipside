"""Shipside CLI entry point."""
from __future__ import annotations

import argparse
import sys

from . import __version__, report
from .asc import AscError, Client
from .config import ConfigError, load, require_asc_config, wizard
from .license_gate import ensure_licensed

ABOUT = """Shipside - ship iOS apps to App Store Connect from the command line.

  shipside init          config wizard (writes shipside.toml)
  shipside doctor        verify credentials and access, read-only
  shipside state         full status report for the configured app
  shipside plan          dry-run the submission: every blocker, nothing written
  shipside metadata      push metadata/<locale>/*.txt into the editable version
  shipside screenshots   upload a folder of PNGs (6.7"/6.9" trap handled)
  shipside submit        create version + fixes + submit for review (--yes to fire)
  shipside trial         start the 14-day free trial (all features)
  shipside license       activate / status

Every command runs with YOUR OWN App Store Connect API key on YOUR machine.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="shipside", description=ABOUT, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"shipside {__version__}")
    p.add_argument("--config", help="path to shipside.toml (default: walk up from cwd)")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("init", help="config wizard")

    sp = sub.add_parser("doctor", help="verify ASC credentials and access")
    sp.add_argument("--bundle-id")

    sp = sub.add_parser("state", help="read-only App Store Connect status report")
    sp.add_argument("--bundle-id")

    sp = sub.add_parser("plan", help="dry-run the submission (alias of submit --plan)")
    sp.add_argument("--bundle-id")
    sp.add_argument("--version-string")

    sp = sub.add_parser("metadata", help="push metadata/<locale>/*.txt into the editable version")
    sp.add_argument("dir_", nargs="?", metavar="dir", help="metadata dir (default: ./metadata)")
    sp.add_argument("--bundle-id")

    sp = sub.add_parser("screenshots", help="upload a folder of PNGs to the editable version")
    sp.add_argument("dir", help="folder of PNGs (1320x2868 or 1290x2796)")
    sp.add_argument("--locale", help="default: en-US")
    sp.add_argument("--display-type", help="default: APP_IPHONE_67 (serves 6.7\"/6.9\" slots)")
    sp.add_argument("--keep", action="store_true", help="do not clear existing screenshots first")
    sp.add_argument("--strict", action="store_true", help="fail on non-standard PNG sizes")
    sp.add_argument("--bundle-id")

    sp = sub.add_parser("submit", help="plan + fixes + submit for review")
    sp.add_argument("--yes", action="store_true", help="REQUIRED to actually submit (irreversible)")
    sp.add_argument("--plan", action="store_true", help="dry run, nothing written")
    sp.add_argument("--version-string")
    sp.add_argument("--bundle-id")
    sp.add_argument("--include-subscription", action="append", help="subscription id to ride along")
    sp.add_argument("--include-iap", action="append", help="IAP id to ride along")

    sp = sub.add_parser("trial", help="start the 14-day free trial")
    sp.add_argument("--email", required=True)

    sp = sub.add_parser("license", help="license activate/status")
    lp = sp.add_subparsers(dest="license_command", metavar="activate|status")
    ap = lp.add_parser("activate", help="activate with the purchase email or a license key")
    ap.add_argument("--email")
    ap.add_argument("--key", help="manual license key (offline sales)")
    lp.add_parser("status", help="show license/trial state")

    return p


def _client(cfg):
    key_id, issuer_id, key_path = require_asc_config(cfg)
    return Client(key_id, issuer_id, key_path, log=lambda m: print(report.info(m)))


def _dispatch(args, cfg) -> int:
    from .license_gate import activate, start_trial, status_lines

    cmd = args.command

    if cmd == "init":
        wizard()
        return 0

    if cmd == "trial":
        st, body = start_trial(args.email)
        if st == 200:
            from .license_gate import fmt_exp, load_state
            s = load_state()
            print(report.ok(f"Trial active until {fmt_exp(s.get('exp'))} - every feature, no card."))
            return 0
        print(report.err(body.get("error") or f"trial failed (HTTP {st})"))
        return 1

    if cmd == "license":
        sub = getattr(args, "license_command", None) or "status"
        if sub == "activate":
            if not args.email and not args.key:
                print(report.err("usage: shipside license activate --email you@example.com  (or --key)"))
                return 1
            st, body = activate(args.email or "", args.key or "")
            if st == 200:
                from .license_gate import fmt_exp, load_state
                print(report.ok(f"Activated - license valid until {fmt_exp(load_state().get('exp'))}."))
                return 0
            print(report.err(body.get("error") or f"activation failed (HTTP {st})"))
            print(report.info(f"Buy at https://shipside-app.vercel.app - then activate with the purchase email."))
            return 1
        for line in status_lines():
            print(line)
        return 0

    # everything below talks to ASC
    c = _client(cfg)

    if cmd == "doctor":
        from .commands import state as state_cmd
        print(report.head("Shipside doctor"))
        print(report.kv("config", cfg.path or "(none - using env vars)"))
        print(report.kv("key file", c.key_path))
        try:
            tok = c.token()
            print(report.ok(f"JWT signed (len {len(tok)})"))
        except Exception as e:
            print(report.err(f"cannot sign JWT: {e}"))
            return 1
        try:
            apps = c.get_all("/v1/apps?limit=1")
            print(report.ok(f"API key accepted - team reachable ({len(apps)} app(s) visible)"))
        except AscError as e:
            print(report.err(f"API rejected the key: {e.status}"))
            from . import playbooks
            playbooks.print_playbook("key-auth-401" if e.status in (401,) else "key-forbidden-403")
            return 1
        try:
            from .config import bundle_id as resolve_bid
            bid = resolve_bid(cfg, getattr(args, "bundle_id", None))
            from .steps import find_app
            app = find_app(c, bid)
            if app:
                print(report.ok(f"app record found: {app['attributes'].get('name')} ({bid})"))
            else:
                print(report.warn(f"no app record for {bid} yet"))
        except ConfigError:
            print(report.info("no bundle id configured yet - run `shipside init`"))
        return 0

    if cmd == "state":
        from .commands import state as state_cmd
        return state_cmd.run(c, cfg, args)

    if cmd == "metadata":
        from .commands import metadata as metadata_cmd
        return metadata_cmd.run(c, cfg, args)

    if cmd == "screenshots":
        from .commands import screenshots as screenshots_cmd
        return screenshots_cmd.run(c, cfg, args)

    if cmd in ("submit", "plan"):
        from .commands import submit as submit_cmd
        if cmd == "plan":
            args.plan = True
        if not args.plan and not ensure_licensed("submit"):
            return 2
        return submit_cmd.run(c, cfg, args)

    print(report.err(f"unknown command {cmd}"))
    return 1


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        print(ABOUT)
        return 0

    gated = args.command not in ("init", "trial", "license") and not (
        args.command == "submit" and getattr(args, "plan", False)
    )
    if gated and not ensure_licensed(args.command if args.command != "plan" else "plan"):
        return 2

    cfg = load(getattr(args, "config", None))
    try:
        return _dispatch(args, cfg)
    except ConfigError as e:
        print(report.err(str(e)))
        return 1
    except AscError as e:
        print(report.err(f"ASC API {e.method} {e.path.split('?')[0]} -> {e.status}"))
        if e.detail():
            print(report.c(e.detail(), report.DIM))
        from . import playbooks
        if e.status == 401:
            playbooks.print_playbook("key-auth-401")
        elif e.status == 403:
            playbooks.print_playbook("key-forbidden-403")
        elif e.status == 405 and "appStoreVersions" in e.path:
            playbooks.print_playbook("version-create-405")
        return 1
    except KeyboardInterrupt:
        print(report.warn("interrupted"))
        return 130


if __name__ == "__main__":
    sys.exit(main())
