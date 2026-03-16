# Troubleshooting Guide

## Common Issues and Solutions

---

### 1. Callback Plugin Not Sending Data to Elasticsearch

**Symptoms:**
- Playbooks run successfully but no documents appear in `fda-demo-ansible-executions`
- No warnings or errors in Ansible output related to `elastic_audit`

**Checks:**

```bash
# Verify the callback plugin is enabled in ansible.cfg
grep callback_whitelist ansible.cfg
# Expected: callback_whitelist = elastic_audit

# Verify environment variables are set
echo $ELASTICSEARCH_URL
echo $ELASTIC_API_KEY    # or ELASTIC_PASSWORD
echo $ANSIBLE_EXECUTIONS_INDEX

# Test Elasticsearch connectivity directly
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  "$ELASTICSEARCH_URL/_cluster/health" | python3 -m json.tool

# Check if the target index exists
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  "$ELASTICSEARCH_URL/fda-demo-ansible-executions/_count" | python3 -m json.tool

# Run a playbook with verbose output to see callback warnings
ansible-playbook playbooks/simulation/simulate_high_cpu.yml -vvv 2>&1 | grep elastic_audit
```

**Solutions:**
- Source the `.env` file before running playbooks: `source env/.env`
- Ensure `callback_plugins` directory is in the path configured in `ansible.cfg`
- Verify the `elastic_audit.py` file exists in `callback_plugins/`
- Check that Elasticsearch is reachable from the Ansible control node
- If using a self-signed certificate, the plugin uses `CERT_NONE` by default (no additional config needed for demo)

---

### 2. EDA Rulebook Not Triggering Remediation

**Symptoms:**
- Elastic alerts fire but no remediation playbook runs
- EDA controller appears idle after alert

**Checks:**

```bash
# Verify EDA is running and listening on the webhook port
ansible-rulebook --rulebook eda/rulebooks/elastic_webhook_rulebook.yml \
  -i inventory/hosts.yml --vars eda/rulebooks/eda_vars.yml -v

# Check if the webhook port is open
ss -tlnp | grep 5000
# or on macOS:
lsof -i :5000

# Test the webhook endpoint manually
curl -X POST http://localhost:5000/endpoint \
  -H "Content-Type: application/json" \
  -d '{
    "rule": {"name": "FDA - High CPU Usage"},
    "alert_type": "high_cpu",
    "alert_id": "test-123",
    "host": "test-host",
    "context": {"host": "test-host"}
  }'

# Check EDA logs for rule matching
# EDA logs appear on stdout when run with -v or -vv
```

**Solutions:**
- Verify the Kibana webhook connector URL points to the EDA controller host and port (default 5000)
- Check that the alert rule name matches the regex patterns in the rulebook (e.g., `.*high.cpu.*`)
- Ensure `ansible.eda` collection is installed: `ansible-galaxy collection install ansible.eda`
- Verify the `eda_vars.yml` is being loaded (pass with `--vars`)
- Check firewall rules allow traffic from Kibana/Elasticsearch to the EDA webhook port

---

### 3. Elastic Agent Enrollment Fails

**Symptoms:**
- `deploy_elastic_agent.yml` playbook fails during agent installation
- Agent service does not start or cannot connect to Fleet

**Checks:**

```bash
# On the managed host, check agent status
sudo elastic-agent status

# Check agent logs
sudo journalctl -u elastic-agent -f

# Verify Fleet Server is reachable from managed host
curl -sk https://<fleet-url>:8220/api/status

# Verify enrollment token is valid (from Kibana Fleet UI or API)
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  "$KIBANA_HOST/api/fleet/enrollment_api_keys" | python3 -m json.tool
```

**Solutions:**
- Verify `FLEET_URL` and `FLEET_ENROLLMENT_TOKEN` are set correctly in `.env`
- Ensure port 8220 is open between managed hosts and Fleet Server
- Check that the enrollment token has not expired or been revoked
- Verify the Elastic Agent version matches the Fleet Server version
- If using self-signed certificates, ensure the agent trusts the CA or use `--insecure` flag

---

### 4. Kibana Alert Rules Not Firing

**Symptoms:**
- Simulated conditions (high CPU, disk full) do not produce alerts
- Alert rules show as "Active" but no actions are triggered

**Checks:**

```bash
# Check rule status via Kibana API
curl -sk -H "kbn-xsrf: true" \
  -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  "$KIBANA_HOST/api/alerting/rules/_find?search=FDA" | python3 -m json.tool

# Check rule execution log
curl -sk -H "kbn-xsrf: true" \
  -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  "$KIBANA_HOST/internal/alerting/rules/_find?search=FDA&fields=executionStatus" \
  | python3 -m json.tool

# Verify metrics data is arriving in Elasticsearch
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  "$ELASTICSEARCH_URL/metrics-*/_search?size=1&sort=@timestamp:desc" \
  | python3 -m json.tool

# Check connector (webhook action) status
curl -sk -H "kbn-xsrf: true" \
  -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  "$KIBANA_HOST/api/actions/connectors" | python3 -m json.tool
```

**Solutions:**
- Verify the index pattern in the alert rule matches the indices where metrics are being written
- Check that the alert threshold is realistic (default CPU threshold is 85%)
- Ensure the webhook connector is configured and points to the correct EDA URL
- Check that the rule schedule interval is appropriate (1m for CPU, 5m for disk)
- Verify the alert rule was created successfully (run `configure_elastic_alerts.yml` again)
- Look at Kibana Stack Management > Rules for execution status and error messages

---

### 5. Kibana Dashboard Import Fails

**Symptoms:**
- NDJSON import via Kibana UI shows errors
- Saved objects fail to load

**Checks:**

```bash
# Verify NDJSON file format (each line must be valid JSON)
cat kibana/dashboards/*.ndjson | python3 -c "
import sys, json
for i, line in enumerate(sys.stdin, 1):
    try:
        json.loads(line.strip())
    except json.JSONDecodeError as e:
        print(f'Line {i}: {e}')
"

# Import via API
curl -sk -X POST "$KIBANA_HOST/api/saved_objects/_import?overwrite=true" \
  -H "kbn-xsrf: true" \
  -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  --form file=@kibana/dashboards/your_dashboard.ndjson
```

**Solutions:**
- Ensure the NDJSON file was exported from a compatible Kibana version (8.x)
- Check that index patterns referenced in the dashboard exist in the target environment
- Import index patterns first (`kibana/index_patterns/index_patterns.ndjson`) before dashboards
- If objects reference missing dependencies, use the `?overwrite=true` parameter
- Verify the Kibana version matches the version the dashboard was exported from

---

### 6. Audit Trail Writes Failing

**Symptoms:**
- Playbooks run but audit trail documents are missing from `fda-demo-audit-trail`
- Warnings about HTTP errors in playbook output

**Checks:**

```bash
# Verify the index template exists
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  "$ELASTICSEARCH_URL/_index_template/fda-demo-audit-trail" | python3 -m json.tool

# Verify the write index exists
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  "$ELASTICSEARCH_URL/_alias/fda-demo-audit-trail" | python3 -m json.tool

# Check ILM policy status
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  "$ELASTICSEARCH_URL/fda-demo-audit-trail-*/_ilm/explain" | python3 -m json.tool

# Test a manual write to the audit index
curl -sk -X POST "$ELASTICSEARCH_URL/fda-demo-audit-trail/_doc" \
  -H "Content-Type: application/json" \
  -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  -d '{"@timestamp":"2026-01-01T00:00:00Z","test":true}' | python3 -m json.tool
```

**Solutions:**
- Run the Elasticsearch setup script to create templates and indices: `bash elasticsearch/setup_elasticsearch.sh`
- Verify the API key has write permissions to `fda-demo-audit-trail*` indices
- Check that the ILM policy exists: `fda-audit-retention`
- If the write alias is missing, recreate the initial index with the alias (the setup script handles this)
- Ensure the `audit_log` role defaults match your environment variables

---

## Debug Commands Quick Reference

```bash
# Source environment
source env/.env

# Check Elasticsearch cluster health
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" "$ELASTICSEARCH_URL/_cluster/health?pretty"

# List all FDA demo indices
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" "$ELASTICSEARCH_URL/_cat/indices/fda-demo-*?v"

# Count documents in each index
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" "$ELASTICSEARCH_URL/fda-demo-ansible-executions/_count"
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" "$ELASTICSEARCH_URL/fda-demo-audit-trail/_count"
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" "$ELASTICSEARCH_URL/fda-demo-eda-events/_count"

# View latest audit trail entries
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
  "$ELASTICSEARCH_URL/fda-demo-audit-trail/_search?size=5&sort=@timestamp:desc&pretty"

# Check ILM policies
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" "$ELASTICSEARCH_URL/_ilm/policy/fda-audit-retention?pretty"

# Verify index templates
curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" "$ELASTICSEARCH_URL/_index_template/fda-demo-*?pretty"

# Test EDA webhook port
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/endpoint

# Run Ansible with maximum verbosity
ansible-playbook <playbook.yml> -vvvv

# Check Ansible callback plugins available
ansible-doc -t callback -l | grep elastic
```

## Log Locations

| Component | Log Location |
|---|---|
| Elastic Agent | `journalctl -u elastic-agent` or `/opt/Elastic/Agent/data/elastic-agent-*/logs/` |
| Elasticsearch | Kibana Stack Management > Logs, or container logs |
| Kibana | Kibana server logs (container/systemd) |
| Ansible | stdout (default), or configure `log_path` in `ansible.cfg` |
| EDA Controller | stdout when run with `-v` flag |
| Callback Plugin | Ansible warnings (prefixed with `elastic_audit:`) |
