from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import re
from datetime import datetime, timezone


def to_elastic_timestamp(value, fmt=None):
    """Convert various date formats to an ISO 8601 timestamp with UTC timezone.

    Accepts:
        - datetime objects (naive assumed UTC)
        - epoch int/float
        - ISO 8601 strings
        - Custom format strings via the optional *fmt* parameter

    Returns:
        str: ISO 8601 string with timezone, e.g. '2026-03-16T12:00:00+00:00'
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()

    if isinstance(value, str):
        value = value.strip()

        # Try explicit format first
        if fmt:
            dt = datetime.strptime(value, fmt)
            dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()

        # Try ISO 8601 parsing (Python 3.7+)
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except (ValueError, AttributeError):
            pass

        # Common fallback formats
        for candidate_fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y",
            "%b %d, %Y %H:%M:%S",
            "%b %d, %Y",
        ):
            try:
                dt = datetime.strptime(value, candidate_fmt)
                dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                continue

    raise ValueError("to_elastic_timestamp: unable to parse value: %r" % value)


_SEVERITY_MAP = {
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
    "info": 5,
}


def severity_to_int(value):
    """Map a severity string to an integer.

    Mapping:
        critical=1, high=2, medium=3, low=4, info=5

    Args:
        value (str): Severity label (case-insensitive).

    Returns:
        int: Numeric severity.

    Raises:
        ValueError: If the severity string is not recognized.
    """
    key = str(value).strip().lower()
    if key not in _SEVERITY_MAP:
        raise ValueError(
            "severity_to_int: unknown severity %r (expected one of %s)"
            % (value, ", ".join(sorted(_SEVERITY_MAP)))
        )
    return _SEVERITY_MAP[key]


_CFR_TAG_MAP = {
    "create": "21CFR11_record_creation",
    "update": "21CFR11_record_modification",
    "delete": "21CFR11_record_deletion",
    "approve": "21CFR11_electronic_signature",
    "sign": "21CFR11_electronic_signature",
    "login": "21CFR11_access_control",
    "logout": "21CFR11_access_control",
    "authenticate": "21CFR11_access_control",
    "export": "21CFR11_data_export",
    "import": "21CFR11_data_import",
    "review": "21CFR11_record_review",
    "submit": "21CFR11_record_submission",
    "audit": "21CFR11_audit_trail",
    "validate": "21CFR11_validation",
    "configure": "21CFR11_system_configuration",
    "deploy": "21CFR11_system_change",
    "install": "21CFR11_system_change",
    "backup": "21CFR11_data_integrity",
    "restore": "21CFR11_data_integrity",
}


def cfr_compliance_tag(action):
    """Return a 21 CFR Part 11 compliance tag for a given action string.

    The function checks whether the action (case-insensitive) starts with or
    contains a known keyword and returns the corresponding tag.  Falls back to
    ``21CFR11_general_operation`` if no keyword matches.

    Args:
        action (str): Description of the action being performed.

    Returns:
        str: A compliance tag string, e.g. ``21CFR11_record_creation``.
    """
    action_lower = str(action).strip().lower()

    # Direct match first
    if action_lower in _CFR_TAG_MAP:
        return _CFR_TAG_MAP[action_lower]

    # Check if action starts with or contains a keyword
    for keyword, tag in _CFR_TAG_MAP.items():
        if action_lower.startswith(keyword) or keyword in action_lower:
            return tag

    return "21CFR11_general_operation"


def sanitize_for_elasticsearch(value):
    """Sanitize a field name for Elasticsearch.

    - Replaces dots with underscores (dots conflict with nested object notation)
    - Strips leading underscores (reserved by Elasticsearch for meta-fields)
    - Collapses consecutive underscores
    - Strips trailing underscores

    Args:
        value (str): The raw field name.

    Returns:
        str: Sanitized field name safe for Elasticsearch.
    """
    s = str(value)
    s = s.replace(".", "_")
    s = s.lstrip("_")
    s = re.sub(r"_+", "_", s)
    s = s.rstrip("_")
    return s if s else "field"


class FilterModule(object):
    """Custom Jinja2 filters for Elastic integrations."""

    def filters(self):
        return {
            "to_elastic_timestamp": to_elastic_timestamp,
            "severity_to_int": severity_to_int,
            "cfr_compliance_tag": cfr_compliance_tag,
            "sanitize_for_elasticsearch": sanitize_for_elasticsearch,
        }
