"""Publish allowlisted test metadata, never pytest output, failure messages or input values."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def public_id(nodeid: str) -> str:
    """Strip parametrized values and retain an opaque suffix to distinguish scenarios."""
    base = nodeid.split('[', 1)[0]
    if not re.fullmatch(r'tests/[A-Za-z0-9_/]+\.py(?:::[A-Za-z0-9_]+)*', base):
        base = 'unclassified_test'
    return base + '#' + hashlib.sha256(nodeid.encode()).hexdigest()[:16]


def publish_tests(source: Path, public: Path, root: Path) -> tuple[dict[str, Any], bool]:
    """Check unexpected skips and generate fresh minimal JUnit without copying raw XML."""
    try:
        data = json.loads(source.read_text(encoding='utf-8'))
        whitelist = json.loads((root / 'tests/quality-skip-allowlist.json').read_text())
        collected = data['collected']
        rows = data['results']
        if not collected or len(collected) != len(set(collected)) or set(collected) != set(rows):
            return {'status': 'INCOMPLETE_TEST_REPORT'}, False
        counts = dict.fromkeys(['PASS', 'FAIL', 'ERROR', 'SKIP', 'XFAIL', 'XPASS'], 0)
        safe = []
        valid = data['exitstatus'] == 0
        suite = ET.Element('testsuite', name='offline-quality', tests=str(len(rows)))
        for nodeid in collected:
            row = rows[nodeid]
            status = row['status']
            counts[status] += 1
            allowed = status == 'SKIP' and any(
                item == {'nodeid': nodeid, 'platform': sys.platform, 'reason': row['reason']}
                for item in whitelist
            )
            valid = valid and (status == 'PASS' or allowed)
            identifier = public_id(nodeid)
            safe.append({'id': identifier, 'status': status, 'allowed_skip': allowed})
            case = ET.SubElement(suite, 'testcase', name=identifier,
                                 time=str(row['duration_seconds']))
            if status != 'PASS':
                tag = 'skipped' if allowed else 'error' if status == 'ERROR' else 'failure'
                ET.SubElement(case, tag, message='APPROVED_PLATFORM_SKIP' if allowed else status)
        suite.set('failures', str(len(suite.findall('./testcase/failure'))))
        suite.set('errors', str(counts['ERROR']))
        suite.set('skipped', str(len(suite.findall('./testcase/skipped'))))
        ET.ElementTree(suite).write(public / 'junit.xml', encoding='utf-8', xml_declaration=True)
        summary = {'status': 'PASS' if valid else 'FAIL', 'counts': counts, 'cases': safe}
        (public / 'tests.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        return summary, valid
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'INVALID_TEST_REPORT'}, False
