#!/usr/bin/env bash
# deploy.sh — Sync ArgoCD applications from apps.yaml
# Usage: ./deploy.sh [test|--test|prod|--prod] [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

ENV="test"
DRY_RUN=""
for arg in "$@"; do
  case "$arg" in
    test|--test)   ENV="test" ;;
    prod|--prod)   ENV="prod" ;;
    --dry-run)     DRY_RUN="--dry-run" ;;
    *) echo "Usage: $0 [test|prod] [--dry-run]" >&2; exit 1 ;;
  esac
done

ARGOCD_NAMESPACE="openshift-gitops"
REPO_URL="https://github.com/epfl-si/sopec.git"
PROJECT="svc0176"
APPS_FILE="${SCRIPT_DIR}/apps.yaml"

case "$ENV" in
  test)
    ARGOCD_SERVER="openshift-gitops-server-openshift-gitops.apps.ocpitst0001.xaas.epfl.ch"
    DESTINATION_SERVER="https://kubernetes.default.svc"
    DESTINATION_NAMESPACE="svc0176t-isas-fsd"
    ;;
  prod)
    ARGOCD_SERVER="openshift-gitops-server-openshift-gitops.apps.ocpitsp0001.xaas.epfl.ch"
    DESTINATION_SERVER="https://kubernetes.default.svc"
    DESTINATION_NAMESPACE="svc0176p-isas-fsd"
    ;;
  *)
    echo "Usage: $0 [test|prod] [--dry-run]" >&2
    exit 1
    ;;
esac

ARGOCD_BASE="https://${ARGOCD_SERVER}"
TOKEN_FILE="${SCRIPT_DIR}/.token"

# Colors
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
DIM='\033[2m'
RESET='\033[0m'

# ─── YAML PARSING ──────────────────────────────────────────────────────────────
get_desired_apps() {
  python3 - "$ENV" "$APPS_FILE" <<'PYEOF'
import yaml, sys
env, path = sys.argv[1], sys.argv[2]
with open(path) as f:
    data = yaml.safe_load(f)
for app in data.get('apps', []):
    if env in app.get('envs', []):
        print(app['name'])
PYEOF
}

# ─── TOKEN MANAGEMENT ──────────────────────────────────────────────────────────
token_valid() {
  local token="$1"
  local exp now
  exp=$(python3 -c "
import base64, json, sys
payload = sys.argv[1].split('.')[1]
payload += '=' * (4 - len(payload) % 4)
print(json.loads(base64.urlsafe_b64decode(payload)).get('exp', 0))
" "$token" 2>/dev/null) || return 1
  now=$(date +%s)
  [[ "$exp" -gt "$now" ]]
}

get_cached_token() {
  [[ -f "$TOKEN_FILE" ]] || return 0
  python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    print(json.load(f).get(sys.argv[2], ''))
" "$TOKEN_FILE" "$ENV" 2>/dev/null || true
}

save_token() {
  local token="$1"
  python3 -c "
import json, sys
path, env, tok = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    tokens = json.load(open(path))
except Exception:
    tokens = {}
tokens[env] = tok
json.dump(tokens, open(path, 'w'), indent=2)
" "$TOKEN_FILE" "$ENV" "$token"
  chmod 600 "$TOKEN_FILE"
}

acquire_token_sso() {
  python3 "${SCRIPT_DIR}/scripts/argocd-sso-login.py" "$ARGOCD_SERVER"
}

acquire_token_curl() {
  echo -e "${DIM}Paste a curl command copied from your browser DevTools, then press Ctrl+D:${RESET}" >&2
  echo >&2
  local curl_cmd
  curl_cmd=$(cat)
  local token
  token=$(echo "$curl_cmd" | grep -oP "argocd\.token=\K[^;'\"]+" | head -1)
  if [[ -z "$token" ]]; then
    echo -e "${RED}Error: argocd.token not found in the curl command.${RESET}" >&2
    return 1
  fi
  echo "$token"
}

get_token() {
  local cached
  cached=$(get_cached_token)
  if [[ -n "$cached" ]] && token_valid "$cached"; then
    echo -e "${DIM}Using cached token.${RESET}" >&2
    echo "$cached"
    return
  elif [[ -n "$cached" ]]; then
    echo -e "${YELLOW}Cached ${ENV} token expired.${RESET}" >&2
  fi

  local token
  if token=$(acquire_token_sso); then
    echo -e "${GREEN}✓${RESET} SSO login successful." >&2
  else
    echo -e "${YELLOW}SSO login failed, falling back to curl paste.${RESET}" >&2
    token=$(acquire_token_curl) || exit 1
  fi

  save_token "$token"
  echo "$token"
}

# ─── APPLICATION MANAGEMENT ────────────────────────────────────────────────────
list_existing_apps() {
  local token="$1"
  local response http_code body
  response=$(curl -s -w "\n%{http_code}" \
    -H "Authorization: Bearer ${token}" \
    "${ARGOCD_BASE}/api/v1/applications?project=${PROJECT}" 2>/dev/null) || true
  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | head -n -1)
  if [[ "$http_code" != "200" ]]; then
    echo -e "${RED}Error: failed to list applications (HTTP ${http_code})${RESET}" >&2
    return 1
  fi
  echo "$body" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for app in (data.get('items') or []):
    print(app['metadata']['name'])
"
}

create_app() {
  local app="$1"
  local token="$2"
  local name="sopec-${app}"

  if [[ "$DRY_RUN" == "--dry-run" ]]; then
    echo -e "  ${DIM}[dry-run]${RESET} ${GREEN}create${RESET}  ${name}"
    return
  fi

  local payload
  payload=$(cat <<EOF
{
  "metadata": {
    "name": "${name}",
    "namespace": "${ARGOCD_NAMESPACE}"
  },
  "spec": {
    "project": "${PROJECT}",
    "source": {
      "repoURL": "${REPO_URL}",
      "path": "apps/${app}/overlays/${ENV}",
      "targetRevision": "HEAD"
    },
    "destination": {
      "server": "${DESTINATION_SERVER}",
      "namespace": "${DESTINATION_NAMESPACE}"
    },
    "syncPolicy": {
      "automated": { "prune": false, "selfHeal": true },
      "syncOptions": ["ServerSideApply=true"]
    }
  }
}
EOF
)

  local response http_code
  response=$(curl -s -w "\n%{http_code}" \
    -X POST \
    -H "Authorization: Bearer ${token}" \
    -H "Content-Type: application/json" \
    -d "$payload" \
    "${ARGOCD_BASE}/api/v1/applications" 2>/dev/null) || { echo -e "  ${RED}error${RESET}    ${name}" >&2; return 1; }

  http_code=$(echo "$response" | tail -1)
  if [[ "$http_code" == "200" || "$http_code" == "201" ]]; then
    echo -e "  ${GREEN}created${RESET}  ${name}"
  else
    echo -e "  ${RED}error${RESET}    ${name} ${DIM}(HTTP ${http_code})${RESET}" >&2
    return 1
  fi
}

delete_app() {
  local name="$1"
  local token="$2"

  if [[ "$DRY_RUN" == "--dry-run" ]]; then
    echo -e "  ${DIM}[dry-run]${RESET} ${RED}delete${RESET}  ${name}"
    return
  fi

  local http_code
  http_code=$(curl -sf -o /dev/null -w "%{http_code}" \
    -X DELETE \
    -H "Authorization: Bearer ${token}" \
    "${ARGOCD_BASE}/api/v1/applications/${name}" 2>/dev/null) || http_code="000"

  if [[ "$http_code" == "200" ]]; then
    echo -e "  ${RED}deleted${RESET}  ${name}"
  else
    echo -e "  ${RED}error${RESET}    ${name} ${DIM}(HTTP ${http_code})${RESET}" >&2
    return 1
  fi
}

# ─── SYNC ──────────────────────────────────────────────────────────────────────
sync_apps() {
  local token="$1"
  local errors=0

  # Desired state from apps.yaml for current env
  mapfile -t desired_names < <(get_desired_apps)
  declare -A desired_set
  for name in "${desired_names[@]}"; do
    desired_set["sopec-${name}"]=1
  done

  # Actual state from ArgoCD
  local existing_raw
  if ! existing_raw=$(list_existing_apps "$token"); then
    echo -e "${RED}Aborting: cannot safely sync without knowing current state.${RESET}" >&2
    return 1
  fi
  mapfile -t existing_apps <<< "$existing_raw"
  declare -A existing_set
  for name in "${existing_apps[@]}"; do
    [[ -n "$name" ]] && existing_set["$name"]=1
  done

  # Create apps that should exist but don't
  for name in "${desired_names[@]}"; do
    local full_name="sopec-${name}"
    if [[ -v existing_set["$full_name"] ]]; then
      echo -e "  ${YELLOW}skipped${RESET}  ${full_name} ${DIM}(already exists)${RESET}"
    else
      create_app "$name" "$token" || errors=$((errors + 1))
    fi
  done

  # Delete apps that exist but are no longer desired
  for full_name in "${existing_apps[@]}"; do
    if [[ ! -v desired_set["$full_name"] ]]; then
      delete_app "$full_name" "$token" || errors=$((errors + 1))
    fi
  done

  return $errors
}

# ─── MAIN ──────────────────────────────────────────────────────────────────────
echo -e "${BOLD}SOPEC Sync${RESET} — env: ${BOLD}${ENV}${RESET}"
echo -e "${DIM}  server:    ${ARGOCD_BASE}${RESET}"
echo -e "${DIM}  namespace: ${DESTINATION_NAMESPACE}${RESET}"
echo

TOKEN=$(get_token)
echo -e "${GREEN}✓${RESET} Token extracted"
echo

ERRORS=0
sync_apps "$TOKEN" || ERRORS=$?

echo
if [[ "$ERRORS" -gt 0 ]]; then
  echo -e "${RED}Finished with ${ERRORS} error(s).${RESET}"
  exit 1
else
  echo -e "${GREEN}✓ All done.${RESET}"
fi
