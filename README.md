# Elastic Observability + Ansible Automation Platform Demo for FDA

A demonstration of closed-loop infrastructure monitoring and automated remediation using Elastic Observability and Ansible Automation Platform, designed for FDA-regulated environments with 21 CFR Part 11 compliance considerations.

## Overview

This demo shows how Elastic and Ansible work together to:

1. **Detect** infrastructure issues in real-time using Elastic Agent and Observability alerts
2. **Respond** automatically via Event-Driven Ansible (EDA) triggered by Elastic webhooks
3. **Remediate** issues with audited Ansible playbooks that log every action
4. **Audit** the entire lifecycle with tamper-evident records in Elasticsearch
5. **Report** on compliance through Kibana dashboards and generated reports

The complete detection-to-remediation loop runs autonomously while maintaining a full audit trail suitable for FDA inspection.

## Architecture

```
Managed Hosts --> Elastic Agent --> Elasticsearch --> Alert Rule
     ^                                                   |
     |                                                   | webhook
     |                                                   v
     +---- Ansible Playbook <--- EDA Controller <--------+
                |
                +--> Audit Trail (Elasticsearch) --> Compliance Dashboard (Kibana)
```

For the full architecture diagram with ports, protocols, and integration details, see [docs/architecture_diagram.md](docs/architecture_diagram.md).

## Prerequisites

| Component | Version | Purpose |
|---|---|---|
| Elasticsearch | 8.x | Metrics storage, audit trail, alerting |
| Kibana | 8.x | Dashboards, alert rule management |
| Ansible | 2.14+ | Automation engine |
| ansible-rulebook | latest | Event-Driven Ansible (EDA) controller |
| Python | 3.9+ | Required by Ansible and EDA |
| Elastic Agent | 8.x | Deployed to managed hosts for metrics collection |

### Python Packages

```bash
pip install ansible ansible-rulebook aiohttp
```

### Ansible Collections

```bash
ansible-galaxy collection install -r collections/requirements.yml
```

## Quick Start

### 1. Configure Environment

```bash
cp env/.env.example env/.env
# Edit env/.env with your Elasticsearch, Kibana, and Fleet details
source env/.env
```

### 2. Install Ansible Collections

```bash
ansible-galaxy collection install -r collections/requirements.yml
```

### 3. Set Up Elasticsearch Indices and Templates

```bash
bash elasticsearch/setup_elasticsearch.sh
```

This creates ILM policies, index templates, and initial write indices for:
- `fda-demo-ansible-executions` (playbook telemetry)
- `fda-demo-audit-trail` (compliance audit records)
- `fda-demo-eda-events` (EDA processing logs)

### 4. Deploy Elastic Agent to Managed Hosts

```bash
ansible-playbook playbooks/deployment/deploy_elastic_agent.yml \
  -e fleet_url=$FLEET_URL \
  -e fleet_enrollment_token=$FLEET_ENROLLMENT_TOKEN
```

### 5. Configure Elastic Alert Rules

```bash
ansible-playbook playbooks/configuration/configure_elastic_alerts.yml
```

Creates alert rules for High CPU, Disk Full, and Service Down with webhook actions pointing to the EDA controller.

### 6. Start the EDA Rulebook

```bash
ansible-rulebook --rulebook eda/rulebooks/elastic_webhook_rulebook.yml \
  -i inventory/hosts.yml \
  --vars eda/rulebooks/eda_vars.yml -v
```

### 7. Simulate an Incident

```bash
ansible-playbook playbooks/simulation/simulate_high_cpu.yml
```

Watch as Elastic detects the anomaly, fires an alert, EDA receives the webhook, and the remediation playbook executes automatically.

## Project Structure

```
ansible/
|-- ansible.cfg                          # Ansible configuration
|-- inventory/
|   |-- hosts.yml                        # Managed host inventory
|   +-- group_vars/all.yml               # Global variables
|-- env/
|   +-- .env.example                     # Environment variable template
|-- elasticsearch/
|   |-- setup_elasticsearch.sh           # One-time ES setup script
|   |-- index_templates/                 # Index templates for all indices
|   +-- ilm_policies/                    # ILM retention policy (no delete)
|-- kibana/
|   +-- index_patterns/                  # Kibana index pattern definitions
|-- callback_plugins/
|   +-- elastic_audit.py                 # Callback: sends execution data to ES
|-- filter_plugins/
|   +-- elastic_filters.py              # Custom Jinja2 filters
|-- eda/
|   +-- rulebooks/
|       |-- elastic_webhook_rulebook.yml # Main EDA rulebook (3 alert types)
|       |-- elastic_multi_alert_rulebook.yml
|       +-- eda_vars.yml                 # EDA configuration variables
|-- playbooks/
|   |-- deployment/
|   |   +-- deploy_elastic_agent.yml     # Deploy Elastic Agent via Fleet
|   |-- configuration/
|   |   |-- configure_elastic_alerts.yml # Create alert rules in Kibana
|   |   |-- configure_webhook_connector.yml
|   |   +-- templates/                   # Alert rule JSON templates
|   |-- remediation/
|   |   |-- remediate_high_cpu.yml       # CPU remediation (renice/kill)
|   |   +-- roles/
|   |       +-- audit_log/               # Reusable audit logging role
|   +-- simulation/
|       |-- simulate_high_cpu.yml        # Stress test CPU
|       |-- simulate_disk_full.yml       # Fill disk space
|       |-- simulate_service_down.yml    # Stop a service
|       +-- cleanup_simulations.yml      # Clean up all simulations
+-- docs/
    |-- architecture_diagram.md          # Full architecture with ports
    |-- fda_compliance_mapping.md        # 21 CFR Part 11 mapping
    +-- troubleshooting.md              # Common issues and debug commands
```

## Demo Flow

The demo is structured as a five-act narrative:

1. **Setting the Stage** -- Show the Kibana infrastructure dashboard with healthy hosts and an empty audit trail. Establish the baseline.

2. **Deploy the Integration** -- Run the deployment and configuration playbooks. Show hosts appearing in Fleet and alert rules created in Kibana.

3. **The Incident** -- Start the EDA rulebook, then simulate high CPU. Watch Elastic detect the anomaly in real-time as metrics cross the threshold.

4. **Automated Remediation** -- Observe EDA receiving the webhook, matching the rule, and launching the remediation playbook. Watch CPU normalize in Kibana as the playbook takes corrective action.

5. **The Audit Trail** -- Open the compliance dashboard showing the full lifecycle: detection, alert, remediation start, actions taken (with before/after state), and verification. Every step is traceable with correlation IDs.

For the detailed step-by-step demo script with talking points and timing, see [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md).

## FDA Compliance

This demo illustrates alignment with 21 CFR Part 11 requirements for electronic records and electronic signatures in FDA-regulated environments. Key compliance features include:

- Tamper-evident audit trails with before/after state capture
- ILM policies with no delete phase for record permanence
- Correlation IDs linking events across the detection-remediation lifecycle
- RBAC and API key authentication for access control
- TLS encryption for data in transit

For the detailed compliance mapping, see [docs/fda_compliance_mapping.md](docs/fda_compliance_mapping.md).

> **Note:** This is a demonstration. Production deployment in an FDA-regulated environment requires formal validation (IQ/OQ/PQ), change control procedures, and regulatory review.

## Additional Documentation

- [Architecture Diagram](docs/architecture_diagram.md) -- System components, data flows, ports, and protocols
- [FDA Compliance Mapping](docs/fda_compliance_mapping.md) -- 21 CFR Part 11 requirement mapping
- [Troubleshooting Guide](docs/troubleshooting.md) -- Common issues, debug commands, and log locations
- [Demo Runbook](DEMO_RUNBOOK.md) -- Step-by-step presentation script with talking points
