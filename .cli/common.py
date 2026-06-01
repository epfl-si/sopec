"""Shared constants, token management, and kubectl helpers."""
import base64, importlib.util, json, os, subprocess, sys, time
from typing import Optional

API_BASE      = "https://api.ocpits"
API_SUFFIX    = ".xaas.epfl.ch:6443"
ARGOCD_PREFIX = "openshift-gitops-server-openshift-gitops.apps.ocpits"
ARGOCD_SUFFIX = "0001.xaas.epfl.ch"
NS_BASE       = "svc0176"
NS_SUFFIX     = "-isas-fsd"
KEYBASE_ROOT  = "/keybase/team/epfl_sopec/backups"
TOKEN_FILE    = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".token")

RED, GREEN, YELLOW, BLUE, BOLD, DIM, NC = '\033[0;31m', '\033[0;32m', '\033[1;33m', '\033[0;34m', '\033[1m', '\033[2m', '\033[0m'


def print_header(command: str, **details):
    print(f"\n{BOLD}SOPEC {command}{NC}")
    for k, v in details.items():
        print(f"{DIM}  {(k + ':'):<12} {v}{NC}")
    print()

_debug = os.environ.get("DEBUG", "0") == "1"


def set_debug(val: bool):
    global _debug
    _debug = val
    os.environ["DEBUG"] = "1" if val else "0"


def info(m: str):  print(f"{GREEN}[INFO]{NC}  {m}")
def warn(m: str):  print(f"{YELLOW}[WARN]{NC}  {m}")
def error(m: str): print(f"{RED}[ERROR]{NC} {m}", file=sys.stderr)
def debug(m: str):
    if _debug:
        print(f"{BLUE}[DEBUG]{NC} {m}")


def env_config(env: str) -> dict:
    letter = env[0]
    api_url   = f"{API_BASE}{letter}0001{API_SUFFIX}"
    namespace = f"{NS_BASE}{letter}{NS_SUFFIX}"
    argocd    = f"{ARGOCD_PREFIX}{letter}{ARGOCD_SUFFIX}"
    return {"api_url": api_url, "namespace": namespace, "argocd_server": argocd}


# ─── Token ─────────────────────────────────────────────────────────────────────

def token_valid(token: str) -> bool:
    try:
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0) > time.time()
    except Exception:
        return False


def load_token(env: str) -> str:
    try:
        return json.loads(open(TOKEN_FILE).read()).get(env, "")
    except Exception:
        return ""


def save_token(env: str, token: str):
    try:
        tokens = json.loads(open(TOKEN_FILE).read())
    except Exception:
        tokens = {}
    tokens[env] = token
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    os.chmod(TOKEN_FILE, 0o600)


def get_token(env: str, argocd_server: str) -> str:
    cached = load_token(env)
    if cached and token_valid(cached):
        print(f"{DIM}Using cached token.{NC}", file=sys.stderr)
        return cached
    if cached:
        print(f"{YELLOW}Cached {env} token expired.{NC}", file=sys.stderr)
    _cli_dir = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("sso", os.path.join(_cli_dir, "sso.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    token = mod.login(argocd_server)
    print(f"{GREEN}✓{NC} SSO login successful.", file=sys.stderr)
    save_token(env, token)
    return token


def configure_kubectl(env: str, api_url: str, token: str):
    name = f"sopec-{env}"
    subprocess.run(["kubectl", "config", "set-cluster",     name, f"--server={api_url}"], check=True, capture_output=True)
    subprocess.run(["kubectl", "config", "set-credentials", name, f"--token={token}"],   check=True, capture_output=True)
    subprocess.run(["kubectl", "config", "set-context",     name, f"--cluster={name}", f"--user={name}"], check=True, capture_output=True)
    subprocess.run(["kubectl", "config", "use-context",     name], check=True, capture_output=True)


# ─── kubectl helpers ───────────────────────────────────────────────────────────

def check_cnpg_cluster(namespace: str, cluster: str) -> Optional[str]:
    """Return primary pod name, or None on failure."""
    info("Checking CloudNativePG cluster...")
    if subprocess.run(["kubectl", "get", "cluster", cluster, "-n", namespace], capture_output=True).returncode != 0:
        error(f"Cluster {cluster} not found in {namespace}")
        return None
    status = _jsonpath(namespace, "cluster", cluster, "{.status.phase}")
    info(f"Cluster status: {status}")
    primary = _jsonpath(namespace, "cluster", cluster, "{.status.targetPrimary}")
    if not primary:
        error("No primary pod found")
        return None
    info(f"Primary pod: {primary}")
    pod_status = _jsonpath(namespace, "pod", primary, "{.status.phase}")
    if pod_status != "Running":
        error(f"Primary pod not running ({pod_status})")
        return None
    info("Primary pod is running and ready")
    return primary


def get_db_credentials(namespace: str, cluster: str) -> Optional[dict]:
    secret = f"{cluster}-app"
    info(f"Retrieving credentials from {secret}...")
    if subprocess.run(["kubectl", "get", "secret", secret, "-n", namespace], capture_output=True).returncode != 0:
        error(f"Secret {secret} not found")
        return None

    def field(f: str) -> str:
        return base64.b64decode(_jsonpath(namespace, "secret", secret, f"{{.data.{f}}}")).decode()

    info("Credentials retrieved")
    return {"user": field("username"), "password": field("password"), "dbname": field("dbname"), "host": "localhost"}


def _jsonpath(ns: str, kind: str, name: str, path: str) -> str:
    r = subprocess.run(
        ["kubectl", "get", kind, name, "-n", ns, "-o", f"jsonpath={path}"],
        capture_output=True, text=True,
    )
    return r.stdout.strip()
