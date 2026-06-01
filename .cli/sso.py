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


def _pkce_flow(auth_url: str, token_url: str, client_id: str, ports: list[int],
               label: str, extra_auth_params: dict = None) -> dict:
    """Run PKCE flow. Returns {"token": str, "expires_in": int}."""
    port = _bind_port(ports)
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)
    redirect_uri = f"http://localhost:{port}/auth/callback"
    ctx = ssl.create_default_context()

    auth_params = {
        "response_type": "code", "client_id": client_id,
        "redirect_uri": redirect_uri, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": state,
    }
    if extra_auth_params:
        auth_params.update(extra_auth_params)

    result: dict = {"data": None, "error": None}
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
                    token = resp.get("id_token") or resp.get("access_token")
                    result["data"] = {"token": token, "expires_in": resp.get("expires_in", 86400)}
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

        def log_message(self, *_): pass

    srv = http.server.HTTPServer(("localhost", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print(f"Opening browser for {label} SSO...", file=sys.stderr)
    print(f"Callback listening on http://localhost:{port}", file=sys.stderr)
    if not webbrowser.open(auth_url + "?" + urllib.parse.urlencode(auth_params)):
        print(f"\nOpen manually:\n  {auth_url}?{urllib.parse.urlencode(auth_params)}", file=sys.stderr)

    done.wait(timeout=300)
    srv.shutdown()

    if result["data"]:
        return result["data"]
    raise RuntimeError(result["error"] or "Timeout")


def login(argocd_server: str) -> str:
    """ArgoCD PKCE login — returns id_token."""
    base = f"https://{argocd_server}"
    resp = _pkce_flow(
        auth_url          = f"{base}/api/dex/auth",
        token_url         = f"{base}/api/dex/token",
        client_id         = ARGOCD_CLIENT_ID,
        ports             = ARGOCD_PORTS,
        label             = "ArgoCD",
        extra_auth_params = {"scope": ARGOCD_SCOPES},
    )
    return resp["token"]


_FRAGMENT_HTML = b"""<!DOCTYPE html><html><body><script>
var p={};window.location.hash.substring(1).split('&').forEach(function(x){
  var kv=x.split('=');p[kv[0]]=decodeURIComponent(kv[1]||'');});
if(p.access_token){window.location='/token?t='+p.access_token;}
else{document.write('No token in fragment.');}
</script></body></html>"""


def login_openshift(oauth_server: str) -> tuple[str, int]:
    """OpenShift implicit OAuth flow (like oc login --web) — returns (access_token, expires_in)."""
    port = _bind_port(OPENSHIFT_PORTS)
    redirect_uri = f"http://127.0.0.1:{port}"

    auth_url = f"https://{oauth_server}/oauth/authorize?" + urllib.parse.urlencode({
        "client_id":     OPENSHIFT_CLIENT_ID,
        "redirect_uri":  redirect_uri,
        "response_type": "token",
    })

    result: dict = {"token": None, "expires_in": 86400, "error": None}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/token":
                params = urllib.parse.parse_qs(parsed.query)
                token = params.get("t", [None])[0]
                if token:
                    result["token"] = token
                    self._reply(200, _SUCCESS_HTML)
                else:
                    result["error"] = "no token in query"
                    self._reply(400, b"No token.")
                done.set()
            else:
                self._reply(200, _FRAGMENT_HTML)

        def _reply(self, code: int, body: bytes):
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_): pass

    srv = http.server.HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print("Opening browser for OpenShift SSO...", file=sys.stderr)
    print(f"Callback listening on http://127.0.0.1:{port}", file=sys.stderr)
    if not webbrowser.open(auth_url):
        print(f"\nOpen manually:\n  {auth_url}", file=sys.stderr)

    done.wait(timeout=300)
    srv.shutdown()

    if result["token"]:
        return result["token"], result["expires_in"]
    raise RuntimeError(result["error"] or "Timeout")


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
