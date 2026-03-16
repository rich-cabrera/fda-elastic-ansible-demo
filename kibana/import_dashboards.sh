#!/usr/bin/env bash
#
# import_dashboards.sh
# Imports Kibana index patterns and dashboards via the Saved Objects API.
#
# Required environment variables:
#   KIBANA_HOST  - Kibana URL (e.g., https://my-kibana:5601)
#   KIBANA_AUTH  - Authentication in user:password format, or an API key
#
# Optional:
#   KIBANA_SPACE - Kibana space ID (default: "default")
#

set -euo pipefail

# --- Color helpers ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

# --- Pre-flight checks ---
if [[ -z "${KIBANA_HOST:-}" ]]; then
    error "KIBANA_HOST is not set. Export it before running this script."
    echo "  Example: export KIBANA_HOST=https://my-kibana.example.com:5601"
    exit 1
fi

if [[ -z "${KIBANA_AUTH:-}" ]]; then
    error "KIBANA_AUTH is not set. Export it before running this script."
    echo "  Example: export KIBANA_AUTH=elastic:changeme"
    echo "  Or for API key: export KIBANA_AUTH=ApiKey <base64-encoded-key>"
    exit 1
fi

KIBANA_SPACE="${KIBANA_SPACE:-default}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Build the base URL (handle space routing)
if [[ "${KIBANA_SPACE}" == "default" ]]; then
    BASE_URL="${KIBANA_HOST}"
else
    BASE_URL="${KIBANA_HOST}/s/${KIBANA_SPACE}"
fi

# Determine auth header
if [[ "${KIBANA_AUTH}" == ApiKey* ]]; then
    AUTH_HEADER="Authorization: ${KIBANA_AUTH}"
else
    AUTH_HEADER="Authorization: Basic $(echo -n "${KIBANA_AUTH}" | base64)"
fi

# --- Import function ---
import_ndjson() {
    local file_path="$1"
    local description="$2"
    local filename
    filename="$(basename "${file_path}")"

    if [[ ! -f "${file_path}" ]]; then
        error "File not found: ${file_path}"
        return 1
    fi

    info "Importing ${description} (${filename})..."

    local response
    local http_code

    response=$(curl -s -w "\n%{http_code}" \
        -X POST "${BASE_URL}/api/saved_objects/_import?overwrite=true" \
        -H "${AUTH_HEADER}" \
        -H "kbn-xsrf: true" \
        --form file=@"${file_path}" \
        2>&1)

    http_code=$(echo "${response}" | tail -n1)
    local body
    body=$(echo "${response}" | sed '$d')

    if [[ "${http_code}" =~ ^2[0-9][0-9]$ ]]; then
        local success_count
        local errors_flag
        success_count=$(echo "${body}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('successCount', 0))" 2>/dev/null || echo "?")
        errors_flag=$(echo "${body}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('errors', []))" 2>/dev/null || echo "[]")

        if [[ "${errors_flag}" == "[]" ]]; then
            success "${description}: ${success_count} object(s) imported successfully"
        else
            warn "${description}: imported with warnings - ${body}"
        fi
    else
        error "${description}: HTTP ${http_code}"
        error "Response: ${body}"
        return 1
    fi
}

# --- Main ---
echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN} FDA Demo - Kibana Dashboard Importer${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
info "Target: ${BASE_URL}"
info "Space:  ${KIBANA_SPACE}"
echo ""

ERRORS=0

# Step 1: Import index patterns first
echo -e "${YELLOW}--- Step 1: Index Patterns ---${NC}"
if ! import_ndjson "${SCRIPT_DIR}/index_patterns/index_patterns.ndjson" "Index Patterns"; then
    ((ERRORS++))
fi
echo ""

# Step 2: Import dashboards
echo -e "${YELLOW}--- Step 2: Dashboards ---${NC}"

DASHBOARD_DIR="${SCRIPT_DIR}/dashboards"
DASHBOARD_FILES=(
    "ansible_operations_dashboard.ndjson|Ansible Operations Overview"
    "fda_compliance_audit_dashboard.ndjson|FDA Compliance Audit Trail"
    "eda_event_dashboard.ndjson|Event-Driven Ansible Events"
    "infrastructure_overview_dashboard.ndjson|Infrastructure Health Overview"
)

for entry in "${DASHBOARD_FILES[@]}"; do
    IFS='|' read -r file desc <<< "${entry}"
    if ! import_ndjson "${DASHBOARD_DIR}/${file}" "${desc}"; then
        ((ERRORS++))
    fi
done

echo ""
echo -e "${CYAN}========================================${NC}"
if [[ ${ERRORS} -eq 0 ]]; then
    success "All imports completed successfully!"
    echo ""
    info "Dashboards are available at:"
    info "  ${BASE_URL}/app/dashboards"
else
    error "${ERRORS} import(s) failed. Review the output above."
    exit 1
fi
echo ""
