from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = '''
    name: elastic_audit
    type: notification
    short_description: Send Ansible execution audit events to Elasticsearch
    version_added: "2.0"
    description:
        - This callback plugin sends detailed audit trail documents to Elasticsearch
          for every Ansible playbook execution.
        - Captures playbook start/end, individual task results (ok, failed, skipped,
          unreachable), and a final summary with per-host totals.
        - All documents include 21 CFR Part 11 compliance fields for FDA audit trails.
        - Uses only urllib (no external dependencies required).
    requirements:
        - An accessible Elasticsearch cluster
        - Authentication via ELASTIC_API_KEY or ELASTIC_PASSWORD environment variable
    options:
        elasticsearch_url:
            description: Elasticsearch URL (read from ELASTICSEARCH_URL env var)
            env:
                - name: ELASTICSEARCH_URL
            default: "https://localhost:9200"
        elastic_api_key:
            description: Elasticsearch API key for authentication
            env:
                - name: ELASTIC_API_KEY
        elastic_password:
            description: Elasticsearch password (used with 'elastic' user if no API key)
            env:
                - name: ELASTIC_PASSWORD
        ansible_executions_index:
            description: Target index for audit documents
            env:
                - name: ANSIBLE_EXECUTIONS_INDEX
            default: "fda-demo-ansible-executions"
'''

EXAMPLES = '''
# Enable via environment variables:
#   export ELASTICSEARCH_URL="https://elasticsearch.example.com:9200"
#   export ELASTIC_API_KEY="your-api-key-here"
#   export ANSIBLE_EXECUTIONS_INDEX="fda-demo-ansible-executions"
#
# Enable in ansible.cfg:
#   [defaults]
#   callback_whitelist = elastic_audit
#
# Or via environment variable:
#   export ANSIBLE_CALLBACK_WHITELIST=elastic_audit
#
# Run a playbook and all events are automatically indexed:
#   ansible-playbook site.yml
'''

import json
import os
import ssl
import time
import uuid
from datetime import datetime, timezone

try:
    from urllib.request import Request, urlopen
    from urllib.error import URLError, HTTPError
except ImportError:
    from urllib2 import Request, urlopen, URLError, HTTPError

from ansible.plugins.callback import CallbackBase


class CallbackModule(CallbackBase):
    """Ansible callback plugin that sends execution audit events to Elasticsearch."""

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'elastic_audit'
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self, display=None):
        super(CallbackModule, self).__init__(display=display)

        self.es_url = os.environ.get('ELASTICSEARCH_URL', 'https://localhost:9200').rstrip('/')
        self.api_key = os.environ.get('ELASTIC_API_KEY', '')
        self.password = os.environ.get('ELASTIC_PASSWORD', '')
        self.index = os.environ.get('ANSIBLE_EXECUTIONS_INDEX', 'fda-demo-ansible-executions')

        self.correlation_id = None
        self.playbook_name = None
        self.start_time = None
        self.task_start_times = {}
        self.pending_docs = []

        # SSL context that does not verify certs (common for demo/internal clusters)
        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = False
        self._ssl_context.verify_mode = ssl.CERT_NONE

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _now_iso(self):
        return datetime.now(timezone.utc).isoformat()

    def _base_doc(self, doc_type):
        """Return a document with fields common to every event."""
        return {
            "@timestamp": self._now_iso(),
            "event.kind": "event",
            "event.module": "ansible",
            "event.dataset": "ansible.execution",
            "event.type": doc_type,
            "correlation_id": self.correlation_id,
            "playbook": self.playbook_name,
            "ansible_user": os.environ.get("USER", "unknown"),
            "cfr_part11_electronic_record": True,
            "cfr_part11_audit_trail": True,
        }

    def _build_auth_headers(self):
        """Build HTTP headers including authentication."""
        headers = {"Content-Type": "application/x-ndjson"}
        if self.api_key:
            headers["Authorization"] = "ApiKey %s" % self.api_key
        elif self.password:
            import base64
            creds = base64.b64encode(("elastic:%s" % self.password).encode()).decode()
            headers["Authorization"] = "Basic %s" % creds
        return headers

    def _send_bulk(self, docs):
        """Send a list of documents to Elasticsearch using the _bulk API."""
        if not docs:
            return

        body_lines = []
        for doc in docs:
            action = json.dumps({"index": {"_index": self.index}})
            body_lines.append(action)
            body_lines.append(json.dumps(doc))
        body_lines.append("")  # trailing newline required by bulk API
        payload = "\n".join(body_lines).encode("utf-8")

        url = "%s/_bulk" % self.es_url
        headers = self._build_auth_headers()

        req = Request(url, data=payload, headers=headers, method="POST")

        try:
            response = urlopen(req, context=self._ssl_context, timeout=30)
            resp_body = json.loads(response.read().decode("utf-8"))
            if resp_body.get("errors"):
                for item in resp_body.get("items", []):
                    idx = item.get("index", {})
                    if idx.get("error"):
                        self._display.warning(
                            "elastic_audit: bulk index error: %s" % json.dumps(idx["error"])
                        )
        except HTTPError as e:
            self._display.warning(
                "elastic_audit: HTTP %s sending bulk request: %s" % (e.code, e.read().decode("utf-8", errors="replace"))
            )
        except URLError as e:
            self._display.warning("elastic_audit: URL error sending bulk request: %s" % str(e.reason))
        except Exception as e:
            self._display.warning("elastic_audit: unexpected error sending bulk request: %s" % str(e))

    def _flush(self):
        """Send any pending docs and clear the buffer."""
        if self.pending_docs:
            self._send_bulk(self.pending_docs)
            self.pending_docs = []

    def _task_event(self, result, status):
        """Build and buffer a task-level event document."""
        host = result._host.get_name() if result._host else "unknown"
        task = result._task
        task_name = task.get_name() if task else "unknown"
        action = task.action if task else "unknown"

        # Calculate task duration
        task_uuid = task._uuid if task else None
        start = self.task_start_times.pop(task_uuid, None) if task_uuid else None
        duration = round(time.time() - start, 4) if start else 0.0

        # Extract result details (limit size to avoid huge docs)
        res_dict = result._result if result._result else {}
        result_details = {}
        for key in ("msg", "stdout", "stderr", "rc", "module_stdout", "module_stderr", "invocation"):
            if key in res_dict:
                val = res_dict[key]
                if isinstance(val, str) and len(val) > 2048:
                    val = val[:2048] + "...[truncated]"
                result_details[key] = val

        doc = self._base_doc("task_result")
        doc.update({
            "event.action": action,
            "host": host,
            "task_name": task_name,
            "action": action,
            "status": status,
            "duration_seconds": duration,
            "changed": res_dict.get("changed", False),
            "result_details": result_details,
        })
        self.pending_docs.append(doc)

    # ------------------------------------------------------------------
    # Playbook callbacks
    # ------------------------------------------------------------------

    def v2_playbook_on_start(self, playbook):
        self.start_time = time.time()
        self.playbook_name = os.path.basename(playbook._file_name)
        self.correlation_id = str(uuid.uuid4())

        doc = self._base_doc("playbook_start")
        doc["event.action"] = "playbook_start"
        self.pending_docs.append(doc)
        self._flush()

    def v2_playbook_on_task_start(self, task, is_conditional):
        self.task_start_times[task._uuid] = time.time()

    # ------------------------------------------------------------------
    # Runner callbacks
    # ------------------------------------------------------------------

    def v2_runner_on_ok(self, result, **kwargs):
        self._task_event(result, "ok")

    def v2_runner_on_failed(self, result, ignore_errors=False, **kwargs):
        status = "failed_ignored" if ignore_errors else "failed"
        self._task_event(result, status)

    def v2_runner_on_skipped(self, result, **kwargs):
        self._task_event(result, "skipped")

    def v2_runner_on_unreachable(self, result, **kwargs):
        self._task_event(result, "unreachable")

    # ------------------------------------------------------------------
    # Stats / summary
    # ------------------------------------------------------------------

    def v2_playbook_on_stats(self, stats):
        total_duration = round(time.time() - self.start_time, 4) if self.start_time else 0.0

        hosts = sorted(stats.processed.keys()) if stats.processed else []
        host_summaries = {}
        for host in hosts:
            summary = stats.summarize(host)
            host_summaries[host] = {
                "ok": summary.get("ok", 0),
                "changed": summary.get("changed", 0),
                "unreachable": summary.get("unreachable", 0),
                "failures": summary.get("failures", 0),
                "skipped": summary.get("skipped", 0),
                "rescued": summary.get("rescued", 0),
                "ignored": summary.get("ignored", 0),
            }

        doc = self._base_doc("playbook_summary")
        doc.update({
            "event.action": "playbook_summary",
            "duration_seconds": total_duration,
            "host_summaries": host_summaries,
            "total_hosts": len(hosts),
        })
        self.pending_docs.append(doc)
        self._flush()
