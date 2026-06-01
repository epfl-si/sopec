#!/usr/bin/env python3
"""
Apply K8s secrets from apps/*/base/secrets.yaml.

Template syntax:  {{ .env.<path> }}
Resolved as:      keybase fs read <KB_ROOT>/<app>/secrets.yml  →  <env>.<path>

Everything stays in memory — no temp files.
"""
import os, re, subprocess, sys, yaml
from pathlib import Path
from typing import Optional
from common import env_config, ensure_oc_login, GREEN, YELLOW, RED, NC, print_header

CLI_DIR   = Path(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = CLI_DIR.parent
APPS_DIR  = REPO_ROOT / "apps"
KB_ROOT   = "/keybase/team/epfl_sopec"

# {{ .env.<path> }}    → Keybase at <env>.<path>
# {{ .global.<path> }} → Keybase at <path>  (no env prefix)
# {{ .suffix }}        → "-test" | ""
_ENV_RE    = re.compile(r'\{\{\s*\.env\.([^\s}]+)\s*\}\}')
_GLOBAL_RE = re.compile(r'\{\{\s*\.global\.([^\s}]+)\s*\}\}')
_SUFFIX_RE = re.compile(r'\{\{\s*\.suffix\s*\}\}')

def info(m):  print(f"{GREEN}[secrets]{NC} {m}")
def warn(m):  print(f"{YELLOW}[secrets]{NC} {m}")
def error(m): print(f"{RED}[secrets]{NC} {m}", file=sys.stderr)


def kb_load(app: str) -> dict:
    r = subprocess.run(
        ["keybase", "fs", "read", f"{KB_ROOT}/{app}/secrets.yml"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"keybase read failed: {r.stderr.strip()}")
    return yaml.safe_load(r.stdout)


def kbv(data: dict, path: str) -> str:
    d = data
    for key in path.split("."):
        d = d[key]
    return str(d)


def render(template: str, env: str, kb_data: Optional[dict]) -> str:
    suffix = "-test" if env == "test" else ""

    def _get(data: dict, path: str) -> str:
        try:
            return kbv(data, path).strip().replace("\\", "\\\\")
        except (KeyError, TypeError):
            raise KeyError(f"Keybase path not found: {path}")

    out = _ENV_RE.sub(lambda m: _get(kb_data, f"{env}.{m.group(1)}"), template)
    out = _GLOBAL_RE.sub(lambda m: _get(kb_data, m.group(1)), out)
    out = _SUFFIX_RE.sub(suffix, out)
    return out


def apply(content: str, ns: str):
    r = subprocess.run(
        ["kubectl", "apply", "-n", ns, "-f", "-"],
        input=content, text=True, capture_output=True,
    )
    for line in r.stdout.strip().splitlines():
        print(f"  {line}")
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())


def _needs_keybase(template: str) -> bool:
    return bool(_ENV_RE.search(template) or _GLOBAL_RE.search(template))


def process_app(app: str, env: str, ns: str):
    secrets_file = APPS_DIR / app / "base" / "secrets.yaml"
    if not secrets_file.exists():
        warn(f"no secrets.yaml for '{app}' — skipping")
        return

    info(f"--- {app} ---")
    template = secrets_file.read_text()

    kb_data: Optional[dict] = kb_load(app) if _needs_keybase(template) else None
    apply(render(template, env, kb_data), ns)


def main(args=None):
    if args is None:
        args = sys.argv[1:]

    env, apps = "test", []
    for arg in args:
        if arg in ("test", "--test"):   env = "test"
        elif arg in ("prod", "--prod"): env = "prod"
        else:                           apps.append(arg)

    if env not in ("test", "prod"):
        print(f"Unknown env: {env}", file=sys.stderr)
        sys.exit(1)

    cfg = env_config(env)
    ns  = cfg["namespace"]
    print_header("secrets", env=env, namespace=ns)

    ensure_oc_login(cfg["api_url"], cfg["context"])

    if apps:
        target = apps
    else:
        target = sorted(p.parent.parent.name for p in APPS_DIR.glob("*/base/secrets.yaml"))

    if not target:
        warn("No secrets.yaml files found in apps/*/base/")
        return

    info(f"Applying secrets — env: {env} ({ns})")
    errors = 0
    for app in target:
        try:
            process_app(app, env, ns)
        except Exception as e:
            error(f"{app}: {e}")
            errors += 1

    print()
    if errors:
        print(f"{RED}Finished with {errors} error(s).{NC}", file=sys.stderr)
        sys.exit(1)
    print(f"{GREEN}✓ All secrets applied.{NC}")


if __name__ == "__main__":
    main()
