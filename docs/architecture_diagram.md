# Architecture Diagram

## System Overview

```
                          +---------------------------+
                          |         KIBANA             |
                          |  - Dashboards              |
                          |  - Compliance Dashboard    |
                          |  - Alert Rule Management   |
                          |  (port 5601)               |
                          +------+--------+------------+
                                 |        |
                          reads  |        | creates alert rules
                                 v        v
+------------------+      +---------------------------+      +---------------------+
|  MANAGED HOSTS   |      |     ELASTICSEARCH          |      |   AUDIT TRAIL       |
|  (Linux servers) | ---> |  - fda-demo-ansible-exec   | <--- |   INDEX             |
|                  |      |  - fda-demo-audit-trail    |      | fda-demo-audit-trail|
|  Elastic Agent   |      |  - fda-demo-eda-events     |      +---------------------+
|  (port 8220      |      |  (port 9200)               |             ^
|   Fleet enroll)  |      +------+---------------------+             |
+--------+---------+             |                                   |
         ^                       | Alert fires                       |
         |                       v                                   |
         |               +---------------------------+               |
         |               |    ALERT RULE              |               |
         |               |  - High CPU threshold      |               |
         |               |  - Disk Full threshold     |               |
         |               |  - Service Down query      |               |
         |               +------+--------------------+               |
         |                       |                                   |
         |                       | Webhook (HTTP POST)               |
         |                       v                                   |
         |               +---------------------------+               |
         |               |   EDA CONTROLLER           |               |
         |               |  ansible-rulebook           |               |
         |               |  (port 5000 webhook)        |               |
         |               +------+--------------------+               |
         |                       |                                   |
         |                       | Runs playbook                     |
         |                       v                                   |
         |               +---------------------------+               |
         +-------------- |   ANSIBLE PLAYBOOK         | -------------+
           remediates    |  - remediate_high_cpu.yml   |  writes audit
                         |  - remediate_disk_full.yml  |  records
                         |  - remediate_service_down   |
                         +---------------------------+
                                  |
                                  | callback plugin (elastic_audit)
                                  v
                         +---------------------------+
                         |   ELASTICSEARCH            |
                         | fda-demo-ansible-executions|
                         |  (execution telemetry)     |
                         +---------------------------+
```

## Data Flow

```
DETECTION LOOP:
  Managed Host --> Elastic Agent --> Elasticsearch --> Alert Rule
       ^                                                  |
       |                                                  | webhook
       |                                                  v
       +--- Ansible Playbook <--- EDA Controller <--------+

AUDIT LOOP (parallel to all operations):
  Ansible Playbook ---> audit_log role ---> Elasticsearch (audit trail)
  Ansible Playbook ---> elastic_audit callback ---> Elasticsearch (executions)
  All indices -------> Compliance Dashboard (Kibana)
```

## Integration Points

### 1. Elastic Agent to Elasticsearch (Metrics Ingestion)
- **Protocol:** HTTPS (TLS)
- **Port:** 8220 (Fleet Server enrollment), 9200 (Elasticsearch API)
- **Auth:** Fleet enrollment token
- **Data:** System metrics (CPU, memory, disk, network), logs
- **Direction:** Managed hosts push metrics to Elasticsearch via Fleet Server

### 2. Elasticsearch Alert Rules to EDA (Webhook)
- **Protocol:** HTTP POST
- **Port:** 5000 (EDA webhook listener)
- **Auth:** Webhook secret (`EDA_WEBHOOK_SECRET`)
- **Data:** Alert payload (rule name, host, alert_id, context)
- **Direction:** Kibana alerting framework sends webhook to EDA controller
- **Alert types:** High CPU, Disk Full, Service Down

### 3. EDA Controller to Ansible Playbooks (Remediation)
- **Mechanism:** `ansible-rulebook` runs matched playbook locally
- **Data passed:** `target_hosts`, `correlation_id`, `service_name` (via extra_vars)
- **Rulebook:** `eda/rulebooks/elastic_webhook_rulebook.yml`
- **Rules match on:** `event.payload.rule.name` pattern or `event.payload.alert_type`

### 4. Ansible Playbooks to Managed Hosts (Remediation Execution)
- **Protocol:** SSH
- **Port:** 22
- **Auth:** SSH keys (configured in inventory)
- **Actions:** renice processes, restart services, kill runaway processes
- **Privilege:** `become: true` (sudo)

### 5. Ansible Callback Plugin to Elasticsearch (Execution Telemetry)
- **Protocol:** HTTPS
- **Port:** 9200
- **Auth:** API key (`ELASTIC_API_KEY`) or basic auth (`ELASTIC_PASSWORD`)
- **Index:** `fda-demo-ansible-executions`
- **Data:** Playbook start/end, task results (ok/failed/skipped/unreachable), per-host summaries
- **Method:** Bulk API (`_bulk` endpoint)

### 6. Audit Log Role to Elasticsearch (Compliance Audit Trail)
- **Protocol:** HTTPS
- **Port:** 9200
- **Auth:** API key or basic auth
- **Index:** `fda-demo-audit-trail`
- **Data:** Action, category, before/after state, actor, timestamp, correlation_id
- **21 CFR Part 11 fields:** Always included in every document

### 7. Kibana Dashboards (Visualization)
- **Protocol:** HTTPS
- **Port:** 5601
- **Reads from:** All three indices
- **Dashboards:** Infrastructure overview, compliance audit trail, remediation history

## Ports and Protocols Summary

| Component           | Port  | Protocol | Direction     | Purpose                        |
|---------------------|-------|----------|---------------|--------------------------------|
| Elasticsearch       | 9200  | HTTPS    | Inbound       | API, indexing, queries         |
| Kibana              | 5601  | HTTPS    | Inbound       | UI, dashboards, alert mgmt    |
| Fleet Server        | 8220  | HTTPS    | Inbound       | Agent enrollment and checkin   |
| EDA Webhook         | 5000  | HTTP     | Inbound       | Receives alert webhooks        |
| SSH (managed hosts) | 22    | SSH      | Outbound      | Ansible remediation execution  |

## Elasticsearch Indices

| Index Name                       | Purpose                              | ILM Policy            |
|----------------------------------|--------------------------------------|-----------------------|
| `fda-demo-ansible-executions`    | Playbook execution telemetry         | fda-audit-retention   |
| `fda-demo-audit-trail`           | 21 CFR Part 11 audit records         | fda-audit-retention   |
| `fda-demo-eda-events`            | EDA event processing logs            | fda-audit-retention   |

All indices use the `fda-audit-retention` ILM policy which moves data through hot, warm, and cold phases with **no delete phase** to ensure record permanence for FDA compliance.
