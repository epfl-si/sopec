#!/usr/bin/env python3
"""SSO login via PKCE OAuth2 — ArgoCD and OpenShift."""
import base64, hashlib, http.server, json, pathlib, secrets, socket, ssl, sys, threading, urllib.parse, urllib.request, webbrowser

_SUCCESS_HTML = (pathlib.Path(__file__).parent / "success.html").read_bytes()

ARGOCD_CLIENT_ID    = "argo-cd-cli"
ARGOCD_SCOPES       = "openid profile email groups offline_access"
ARGOCD_PORTS        = [8085, 8086, 8087, 8088]

OPENSHIFT_CLIENT_ID = "openshift-browser-client"
OPENSHIFT_PORTS     = [8090, 8091, 8092, 8093]


def _bind_port(ports: list[int]) -> int:
    for p in ports:
        try:
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("localhost", p))
            s.close()
            return p
        except OSError:
            continue
    raise RuntimeError(f"No registered callback port available: {ports}")


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(96)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _pkce_flow(auth_url: str, token_url: str, client_id: str, ports: list[int], label: str) -> str:
    """PKCE OAuth2 flow: open browser, listen for callback, return access token."""
    port = _bind_port(ports)
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)
    redirect_uri = f"http://localhost:{port}/auth/callback"
    ctx = ssl.create_default_context()

    full_auth_url = auth_url + "?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id,
        "redirect_uri": redirect_uri, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": state,
    })

    result: dict = {"token": None, "error": None}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "error" in params:
                result["error"] = params["error"][0]
                self._reply(400, b"Authentication failed.")
            elif "code" not in params:
                result["error"] = "missing code"
                self._reply(400, b"Missing code parameter.")
            elif params.get("state", [""])[0] != state:
                result["error"] = "state mismatch"
                self._reply(400, b"State mismatch.")
            else:
                body = urllib.parse.urlencode({
                    "grant_type": "authorization_code", "code": params["code"][0],
                    "redirect_uri": redirect_uri, "client_id": client_id,
                    "code_verifier": verifier,
                }).encode()
                try:
                    req = urllib.request.Request(
                        token_url, data=body,
                        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
                    )
                    with urllib.request.urlopen(req, context=ctx) as r:
                        resp = json.loads(r.read())
                    result["token"] = resp.get("access_token") or resp.get("id_token")
                    self._reply(200, _SUCCESS_HTML)
                except Exception as e:
                    result["error"] = str(e)
                    self._reply(500, f"Token exchange failed: {e}".encode())
            done.set()

        def _reply(self, code: int, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    srv = http.server.HTTPServer(("localhost", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print(f"Opening browser for {label} SSO...", file=sys.stderr)
    print(f"Callback listening on http://localhost:{port}", file=sys.stderr)
    if not webbrowser.open(full_auth_url):
        print(f"\nOpen manually:\n  {full_auth_url}", file=sys.stderr)

    done.wait(timeout=300)
    srv.shutdown()

    if result["token"]:
        return result["token"]
    raise RuntimeError(result["error"] or "Timeout")


def login(argocd_server: str) -> str:
    """ArgoCD SSO — returns id_token."""
    base = f"https://{argocd_server}"
    auth_url  = f"{base}/api/dex/auth?" + urllib.parse.urlencode({
        "scope": ARGOCD_SCOPES,
    })
    # inject scope into auth URL separately since _pkce_flow builds its own params
    port = _bind_port(ARGOCD_PORTS)
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)
    redirect_uri = f"http://localhost:{port}/auth/callback"
    ctx = ssl.create_default_context()

    full_auth_url = f"{base}/api/dex/auth?" + urllib.parse.urlencode({
        "client_id": ARGOCD_CLIENT_ID, "response_type": "code", "scope": ARGOCD_SCOPES,
        "redirect_uri": redirect_uri, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": state,
    })
    token_url = f"{base}/api/dex/token"

    result: dict = {"token": None, "error": None}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "error" in params:
                result["error"] = params["error"][0]; self._reply(400, b"Authentication failed.")
            elif "code" not in params:
                result["error"] = "missing code"; self._reply(400, b"Missing code.")
            elif params.get("state", [""])[0] != state:
                result["error"] = "state mismatch"; self._reply(400, b"State mismatch.")
            else:
                body = urllib.parse.urlencode({
                    "grant_type": "authorization_code", "code": params["code"][0],
                    "redirect_uri": redirect_uri, "client_id": ARGOCD_CLIENT_ID,
                    "code_verifier": verifier,
                }).encode()
                try:
                    req = urllib.request.Request(token_url, data=body,
                        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
                    with urllib.request.urlopen(req, context=ctx) as r:
                        resp = json.loads(r.read())
                    result["token"] = resp.get("id_token") or resp.get("access_token")
                    self._reply(200, _SUCCESS_HTML)
                except Exception as e:
                    result["error"] = str(e); self._reply(500, f"Token exchange failed: {e}".encode())
            done.set()

        def _reply(self, code, body):
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_): pass

    srv = http.server.HTTPServer(("localhost", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("Opening browser for ArgoCD SSO...", file=sys.stderr)
    print(f"Callback listening on http://localhost:{port}", file=sys.stderr)
    if not webbrowser.open(full_auth_url):
        print(f"\nOpen manually:\n  {full_auth_url}", file=sys.stderr)
    done.wait(timeout=300)
    srv.shutdown()
    if result["token"]:
        return result["token"]
    raise RuntimeError(result["error"] or "Timeout")


def login_openshift(oauth_server: str) -> str:
    """OpenShift OAuth PKCE — returns access_token usable with kubectl --token."""
    base = f"https://{oauth_server}"
    return _pkce_flow(
        auth_url  = f"{base}/oauth/authorize",
        token_url = f"{base}/oauth/token",
        client_id = OPENSHIFT_CLIENT_ID,
        ports     = OPENSHIFT_PORTS,
        label     = "OpenShift",
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: sopec sso <argocd-server-hostname>", file=sys.stderr)
        sys.exit(1)
    try:
        print(login(sys.argv[1]))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
