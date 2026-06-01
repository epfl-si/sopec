#!/usr/bin/env python3
"""Sync ArgoCD applications from apps.yaml."""
import json, os, ssl, sys, urllib.error, urllib.request

CLI_DIR   = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CLI_DIR)

sys.path.insert(0, CLI_DIR)
from common import (
    BOLD, GREEN, YELLOW, RED, DIM, NC,
    print_header, env_config, get_token, token_valid, load_token, save_token,
)

ARGOCD_NS = "openshift-gitops"
REPO_URL  = "https://github.com/epfl-si/sopec.git"
PROJECT   = "svc0176"
APPS_FILE = os.path.join(REPO_ROOT, "apps.yaml")
SSL_CTX   = ssl.create_default_context()

# ─── curl fallback (ArgoCD-only) ───────────────────────────────────────────────

def _curl_paste() -> str:
    import re
    print(f"{DIM}Paste curl from DevTools, Ctrl+D to finish:{NC}", file=sys.stderr)
    m = re.search(r"argocd\.token=([^;'\"]+)", sys.stdin.read())
    if not m:
        print(f"{RED}argocd.token not found.{NC}", file=sys.stderr)
        sys.exit(1)
    return m.group(1)


def get_argocd_token(env: str, server: str) -> str:
    try:
        return get_token(env, server)
    except Exception as e:
        print(f"{YELLOW}SSO failed ({e}), falling back to curl paste.{NC}", file=sys.stderr)
        token = _curl_paste()
        save_token(env, token)
        return token

# ─── ArgoCD API ────────────────────────────────────────────────────────────────

def _api(base: str, path: str, token: str, method: str = "GET", body=None) -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}"}
    data = None
    if body:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=SSL_CTX) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


def list_apps(base: str, token: str) -> list[str]:
    status, data = _api(base, f"/api/v1/applications?project={PROJECT}", token)
    if status != 200:
        raise RuntimeError(f"Failed to list apps (HTTP {status})")
    return [a["metadata"]["name"] for a in (data.get("items") or [])]


def get_desired(env: str) -> list[str]:
    import yaml
    with open(APPS_FILE) as f:
        data = yaml.safe_load(f)
    return [a["name"] for a in data.get("apps", []) if env in a.get("envs", [])]

# ─── Sync ──────────────────────────────────────────────────────────────────────

def sync(env: str, dry_run: bool):
    cfg  = env_config(env)
    base = f"https://{cfg['argocd_server']}"

    token = get_argocd_token(env, cfg["argocd_server"])
    print(f"{GREEN}✓{NC} Token ready\n")

    desired      = get_desired(env)
    desired_set  = {f"sopec-{a}" for a in desired}
    existing     = list_apps(base, token)
    existing_set = set(existing)
    errors = 0

    for app in desired:
        name = f"sopec-{app}"
        if name in existing_set:
            print(f"  {YELLOW}skipped{NC}  {name} {DIM}(already exists){NC}")
            continue
        if dry_run:
            print(f"  {DIM}[dry-run]{NC} {GREEN}create{NC}  {name}")
            continue
        payload = {
            "metadata": {"name": name, "namespace": ARGOCD_NS},
            "spec": {
                "project": PROJECT,
                "source": {"repoURL": REPO_URL, "path": f"apps/{app}/overlays/{env}", "targetRevision": "HEAD"},
                "destination": {"server": "https://kubernetes.default.svc", "namespace": cfg["namespace"]},
                "syncPolicy": {"automated": {"prune": False, "selfHeal": True}, "syncOptions": ["ServerSideApply=true"]},
            },
        }
        status, _ = _api(base, "/api/v1/applications", token, "POST", payload)
        if status in (200, 201):
            print(f"  {GREEN}created{NC}  {name}")
        else:
            print(f"  {RED}error{NC}    {name} {DIM}(HTTP {status}){NC}")
            errors += 1

    for name in existing:
        if name not in desired_set:
            if dry_run:
                print(f"  {DIM}[dry-run]{NC} {RED}delete{NC}  {name}")
                continue
            status, _ = _api(base, f"/api/v1/applications/{name}", token, "DELETE")
            if status == 200:
                print(f"  {RED}deleted{NC}  {name}")
            else:
                print(f"  {RED}error{NC}    {name} {DIM}(HTTP {status}){NC}")
                errors += 1

    print()
    if errors:
        print(f"{RED}Finished with {errors} error(s).{NC}")
        sys.exit(1)
    print(f"{GREEN}✓ All done.{NC}")


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    env, dry_run = "test", False
    for arg in args:
        if arg in ("test", "--test"):   env = "test"
        elif arg in ("prod", "--prod"): env = "prod"
        elif arg == "--dry-run":        dry_run = True
        else:
            print("Usage: sopec deploy [test|prod] [--dry-run]", file=sys.stderr)
            sys.exit(1)
    if env not in ("test", "prod"):
        print(f"Unknown env: {env}", file=sys.stderr)
        sys.exit(1)
    cfg = env_config(env)
    print_header("deploy", env=env, server=f"https://{cfg['argocd_server']}", namespace=cfg["namespace"])
    sync(env, dry_run)


if __name__ == "__main__":
    main()
