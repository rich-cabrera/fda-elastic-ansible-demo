# Demo Runbook: Elastic Observability + Ansible for FDA

Step-by-step script for presenting the FDA demo. Each act builds on the previous one to tell a complete story about automated, auditable infrastructure management in an FDA-regulated environment.

**Total estimated time:** 25-35 minutes (excluding Q&A)

---

## Pre-Demo Checklist

Before starting the demo, verify the following:

- [ ] Environment variables configured: `source env/.env`
- [ ] Elasticsearch is running and accessible: `curl -sk "$ELASTICSEARCH_URL/_cluster/health"`
- [ ] Kibana is running and accessible: open `$KIBANA_HOST` in browser
- [ ] Elasticsearch indices are set up: `bash elasticsearch/setup_elasticsearch.sh`
- [ ] Ansible collections installed: `ansible-galaxy collection install -r collections/requirements.yml`
- [ ] Managed hosts are reachable: `ansible managed_hosts -m ping`
- [ ] Elastic Agent is deployed (or ready to deploy during Act 2)
- [ ] Terminal windows arranged: one for commands, one for EDA output
- [ ] Kibana dashboards imported (if available)

---

## Act 1: Setting the Stage

**Estimated time:** 3-5 minutes

**Goal:** Establish the current state of the environment and introduce the compliance challenge.

### Steps

1. **Open Kibana in the browser**
   - Navigate to the Infrastructure Observability view
   - Show the managed hosts with normal metrics (CPU, memory, disk)

2. **Show the empty (or minimal) audit trail**
   ```bash
   curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
     "$ELASTICSEARCH_URL/fda-demo-audit-trail/_count" | python3 -m json.tool
   ```

3. **Show the Elasticsearch indices**
   ```bash
   curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
     "$ELASTICSEARCH_URL/_cat/indices/fda-demo-*?v&s=index"
   ```

4. **Show the ILM policy (no delete phase)**
   - Navigate to Kibana > Stack Management > Index Lifecycle Policies
   - Highlight: hot -> warm -> cold, NO delete phase
   - "In an FDA environment, you never delete records"

### Talking Points

- "This is a standard Elastic Observability deployment monitoring infrastructure hosts."
- "What makes this different for FDA is the audit trail. Every action that modifies infrastructure must be recorded with who did it, when, what changed, and what it looked like before and after."
- "We have three indices: one for playbook execution telemetry, one for the compliance audit trail, and one for event-driven automation events."
- "The ILM policy moves data through hot, warm, and cold tiers but never deletes -- this is critical for 21 CFR Part 11 compliance."

---

## Act 2: Deploy the Integration

**Estimated time:** 5-7 minutes

**Goal:** Show how Ansible automates the deployment and configuration, with everything audited.

### Steps

1. **Deploy Elastic Agent** (skip if already deployed)
   ```bash
   ansible-playbook playbooks/deployment/deploy_elastic_agent.yml \
     -e fleet_url=$FLEET_URL \
     -e fleet_enrollment_token=$FLEET_ENROLLMENT_TOKEN
   ```

2. **Show the host in Fleet**
   - Navigate to Kibana > Fleet > Agents
   - Point out the newly enrolled agent
   - "Ansible deployed and enrolled the agent automatically"

3. **Configure alert rules**
   ```bash
   ansible-playbook playbooks/configuration/configure_elastic_alerts.yml
   ```

4. **Show the alert rules in Kibana**
   - Navigate to Kibana > Stack Management > Rules
   - Show the three rules: FDA - High CPU Usage, FDA - Disk Full Warning, FDA - Service Down
   - Show the webhook action on each rule

5. **Show the audit trail entries from deployment**
   ```bash
   curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
     "$ELASTICSEARCH_URL/fda-demo-audit-trail/_search?size=5&sort=@timestamp:desc&pretty"
   ```

### Talking Points

- "Every step of the deployment was recorded in the audit trail -- not because someone remembered to log it, but because the callback plugin and audit role do it automatically."
- "The alert rules are configured with webhook actions that will call our Event-Driven Ansible controller. This closes the loop between detection and response."
- "Notice the correlation IDs on each audit entry. These let us trace the full lifecycle of any action."

---

## Act 3: The Incident

**Estimated time:** 5-8 minutes

**Goal:** Simulate an infrastructure incident and show Elastic detecting it in real-time.

### Steps

1. **Start the EDA rulebook** (in a separate terminal)
   ```bash
   source env/.env
   ansible-rulebook --rulebook eda/rulebooks/elastic_webhook_rulebook.yml \
     -i inventory/hosts.yml \
     --vars eda/rulebooks/eda_vars.yml -v
   ```
   - "EDA is now listening on port 5000 for webhooks from Elastic"

2. **Open Kibana to the host metrics view**
   - Show CPU usage at normal levels
   - Keep this visible during the simulation

3. **Simulate high CPU usage**
   ```bash
   ansible-playbook playbooks/simulation/simulate_high_cpu.yml
   ```
   - "We are running stress-ng on the managed host to simulate a runaway process"

4. **Watch Elastic detect the anomaly**
   - In Kibana, watch CPU metrics climb past the 85% threshold
   - "Elastic Agent is reporting metrics every few seconds. The alert rule checks every minute."
   - Wait for the alert to fire (may take 1-2 minutes)

5. **Show the alert in Kibana**
   - Navigate to Observability > Alerts
   - Point out the "FDA - High CPU Usage" alert
   - "Elastic has detected the anomaly and is about to send a webhook to EDA"

### Talking Points

- "In a real FDA manufacturing environment, this could be a process control system, a LIMS server, or a validation system running hot."
- "The key here is speed. Elastic detects the issue within a minute. A human operator might not notice for hours."
- "Watch the EDA terminal -- you will see the webhook arrive momentarily."

---

## Act 4: Automated Remediation

**Estimated time:** 5-8 minutes

**Goal:** Show the automated response and how every step is audited.

### Steps

1. **Show EDA receiving the webhook**
   - In the EDA terminal, point out the incoming event
   - "EDA matched this to Rule 1: Remediate High CPU Alert"
   - "It is now running `remediate_high_cpu.yml` with the alert's correlation ID"

2. **Watch the remediation playbook execute**
   - The playbook output will show:
     - AUDIT: Log remediation start
     - Capture current CPU state (before state)
     - Identify the top CPU consuming process
     - Renice the process
     - Wait and re-evaluate
     - Escalate if needed (SIGTERM, then SIGKILL)
     - Final verification (after state)
     - AUDIT: Log remediation complete

3. **Show CPU normalizing in Kibana**
   - Switch to Kibana metrics view
   - Watch CPU drop back to normal levels
   - "The remediation playbook identified the stress-ng process, reniced it, and if needed, terminated it"

4. **Show the execution telemetry**
   ```bash
   curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
     "$ELASTICSEARCH_URL/fda-demo-ansible-executions/_search?size=10&sort=@timestamp:desc&pretty"
   ```
   - "The callback plugin captured every single task: what ran, how long it took, what the result was"

### Talking Points

- "No human intervention was required. The entire loop -- detect, alert, remediate, verify -- happened automatically."
- "But here is what matters for FDA: every step was audited. The playbook logged the before state, every action it took, and the after state."
- "The correlation ID from the original Elastic alert is carried through the entire remediation. You can trace from detection to resolution with a single ID."
- "Notice the protected process list in the playbook. It will never kill systemd, sshd, or the Elastic Agent itself. This is the kind of safety rail you need in a regulated environment."

---

## Act 5: The Audit Trail

**Estimated time:** 5-7 minutes

**Goal:** Show the complete compliance story -- the full lifecycle is traceable and reportable.

### Steps

1. **Open the Compliance Dashboard in Kibana**
   - Show the audit trail entries for this incident
   - Filter by the correlation ID from the remediation
   - Walk through the timeline:
     - Alert fired (detection)
     - Remediation started (response)
     - CPU state captured (before state)
     - Process reniced/killed (action taken)
     - CPU verified normal (after state)
     - Remediation completed (resolution)

2. **Query the audit trail directly**
   ```bash
   # Find all events for the most recent correlation ID
   curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
     "$ELASTICSEARCH_URL/fda-demo-audit-trail/_search" \
     -H "Content-Type: application/json" \
     -d '{
       "query": {"match_all": {}},
       "sort": [{"@timestamp": "desc"}],
       "size": 20
     }' | python3 -m json.tool
   ```

3. **Show the execution index entries**
   ```bash
   curl -sk -H "Authorization: ApiKey $ELASTIC_API_KEY" \
     "$ELASTICSEARCH_URL/fda-demo-ansible-executions/_search" \
     -H "Content-Type: application/json" \
     -d '{
       "query": {"match_all": {}},
       "sort": [{"@timestamp": "desc"}],
       "size": 10
     }' | python3 -m json.tool
   ```

4. **Highlight 21 CFR Part 11 fields**
   - Point out on any document:
     - `@timestamp` -- When it happened
     - `ansible_user` -- Who (or what service account) performed the action
     - `correlation_id` -- Links all related events
     - `cfr_part11_electronic_record: true` -- Explicitly tagged
     - `cfr_part11_audit_trail: true` -- Part of the audit trail
     - Before/after state fields (in audit trail documents)

5. **Show the ILM policy one more time**
   - "These records will move through hot, warm, and cold storage but will never be deleted"

### Talking Points

- "This is the story FDA auditors want to see. Something happened, we know exactly what it was, we know what the system did about it, and we can prove the outcome."
- "Every record has a timestamp, an actor, a correlation ID, and before/after state. This is 21 CFR Part 11 section 11.10(d) -- audit trails."
- "The callback plugin and audit role work together. The callback captures execution-level detail -- every task, every result. The audit role captures business-level context -- what changed and why."
- "And because the ILM policy has no delete phase, these records are permanent. An auditor can come back in five years and query this same data."
- "This entire demo ran without a single manual log entry. The audit trail is a natural byproduct of the automation itself."

---

## Cleanup

After the demo, clean up simulated conditions:

```bash
# Stop any running stress tests
ansible-playbook playbooks/simulation/cleanup_simulations.yml

# Stop the EDA rulebook (Ctrl+C in the EDA terminal)

# Optionally, clear demo data (DO NOT do this during the demo)
# curl -sk -X POST "$ELASTICSEARCH_URL/fda-demo-*/_delete_by_query" \
#   -H "Authorization: ApiKey $ELASTIC_API_KEY" \
#   -H "Content-Type: application/json" \
#   -d '{"query": {"match_all": {}}}'
```

---

## Timing Summary

| Act | Description | Estimated Time |
|-----|-------------|---------------|
| Pre-demo | Environment verification | 5 min (before audience arrives) |
| Act 1 | Setting the Stage | 3-5 min |
| Act 2 | Deploy the Integration | 5-7 min |
| Act 3 | The Incident | 5-8 min |
| Act 4 | Automated Remediation | 5-8 min |
| Act 5 | The Audit Trail | 5-7 min |
| **Total** | | **23-35 min** |

Allow 10-15 minutes for Q&A after the demo.

---

## Tips for Presenters

- **Pre-deploy the agent** if you want to save time. Acts 3-5 are the most impactful.
- **Use two monitors** if possible: one for terminal commands, one for Kibana.
- **Keep the EDA terminal visible** during Acts 3-4 so the audience can see events arriving in real-time.
- **Practice the timing** of the stress simulation. It takes 1-2 minutes for Elastic to fire the alert after CPU crosses the threshold.
- **Have the correlation ID ready** to paste into Kibana filters during Act 5.
- **If the alert does not fire quickly**, talk through the architecture while waiting. The detection interval is configurable (default 1 minute).
- **Emphasize the "no manual logging" point.** The biggest value proposition is that compliance is a byproduct of automation, not an additional burden.
