#!/usr/bin/env bash
###############################################################################
# setup_elasticsearch.sh
# Provisions Elasticsearch index templates and initial indices
# for the FDA Ansible Observability demo.
###############################################################################

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../env/.env"

if [[ -f "${ENV_FILE}" ]]; then
  info "Loading environment from ${ENV_FILE}"
  set -a
  source "${ENV_FILE}"
  set +a
else
  warn "No .env file found at ${ENV_FILE} -- using existing environment variables"
fi

ELASTICSEARCH_HOST="${ELASTICSEARCH_HOST:-https://localhost:9200}"

if [[ -n "${ELASTIC_API_KEY:-}" ]]; then
  AUTH_HEADER="Authorization: ApiKey ${ELASTIC_API_KEY}"
  info "Authenticating with API key"
elif [[ -n "${ELASTIC_PASSWORD:-}" ]]; then
  ELASTIC_USER="${ELASTIC_USER:-elastic}"
  AUTH_HEADER="Authorization: Basic $(echo -n "${ELASTIC_USER}:${ELASTIC_PASSWORD}" | base64)"
  info "Authenticating as user '${ELASTIC_USER}'"
else
  error "Neither ELASTIC_API_KEY nor ELASTIC_PASSWORD is set. Cannot authenticate."
  exit 1
fi

info "Elasticsearch host: ${ELASTICSEARCH_HOST}"

# ---------------------------------------------------------------------------
# Helper: make an Elasticsearch API call
# ---------------------------------------------------------------------------
es_request() {
  local method="$1"
  local path="$2"
  local body="${3:-}"

  local curl_args=(
    -s -w "\n%{http_code}"
    -X "${method}"
    -H "Content-Type: application/json"
    -H "${AUTH_HEADER}"
    -k
    "${ELASTICSEARCH_HOST}/${path}"
  )

  if [[ -n "${body}" ]]; then
    curl_args+=(-d "@${body}")
  fi

  curl "${curl_args[@]}"
}

parse_response() {
  local response="$1"
  local http_code
  http_code="$(echo "${response}" | tail -n1)"
  local body
  body="$(echo "${response}" | sed '$d')"
  echo "${http_code}|${body}"
}

check_result() {
  local description="$1"
  local response="$2"
  local parsed http_code body

  parsed="$(parse_response "${response}")"
  http_code="${parsed%%|*}"
  body="${parsed#*|}"

  if [[ "${http_code}" =~ ^2 ]]; then
    success "${description} (HTTP ${http_code})"
  else
    error "${description} FAILED (HTTP ${http_code})"
    echo "  Response: ${body}"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# 1. Test connectivity
# ---------------------------------------------------------------------------
echo ""
info "============================================"
info "Step 1: Testing connectivity"
info "============================================"

RESPONSE=$(es_request GET "")
check_result "Elasticsearch cluster reachable" "${RESPONSE}"

# ---------------------------------------------------------------------------
# 2. Create Index Templates
# ---------------------------------------------------------------------------
echo ""
info "============================================"
info "Step 2: Creating index templates"
info "============================================"

TEMPLATES=(
  "fda-demo-ansible-executions:ansible_executions_template.json"
  "fda-demo-audit-trail:audit_trail_template.json"
  "fda-demo-eda-events:eda_events_template.json"
)

for entry in "${TEMPLATES[@]}"; do
  name="${entry%%:*}"
  file="${entry##*:}"
  RESPONSE=$(es_request PUT "_index_template/${name}" \
    "${SCRIPT_DIR}/index_templates/${file}")
  check_result "Index template '${name}'" "${RESPONSE}"
done

# ---------------------------------------------------------------------------
# 3. Create Initial Indices
# ---------------------------------------------------------------------------
echo ""
info "============================================"
info "Step 3: Creating initial indices"
info "============================================"

INDICES=(
  "fda-demo-ansible-executions"
  "fda-demo-audit-trail"
  "fda-demo-eda-events"
)

for idx in "${INDICES[@]}"; do
  # Check if index already exists
  EXISTS_RESPONSE=$(es_request HEAD "${idx}" 2>&1 || true)
  EXISTS_CODE="$(echo "${EXISTS_RESPONSE}" | tail -n1)"

  if [[ "${EXISTS_CODE}" == "200" ]]; then
    warn "Index '${idx}' already exists -- skipping"
  else
    tmpfile=$(mktemp)
    echo '{}' > "${tmpfile}"
    RESPONSE=$(es_request PUT "${idx}" "${tmpfile}")
    rm -f "${tmpfile}"
    check_result "Index '${idx}'" "${RESPONSE}"
  fi
done

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
info "============================================"
success "Elasticsearch setup complete!"
info "============================================"
echo ""
info "Created resources:"
info "  - Index Template:   fda-demo-ansible-executions"
info "  - Index Template:   fda-demo-audit-trail"
info "  - Index Template:   fda-demo-eda-events"
info "  - Index:            fda-demo-ansible-executions"
info "  - Index:            fda-demo-audit-trail"
info "  - Index:            fda-demo-eda-events"
echo ""
