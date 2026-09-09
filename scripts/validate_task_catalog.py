#!/usr/bin/env python3
"""
Validate task catalog consistency across TICKETS.md, tickets.json, and tickets.csv.

Checks:
1. Total ticket count = 97
2. IDs are consistent across all three formats
3. All fields consistent: title, dependencies, goal, deliverables, acceptance
4. No dangling dependencies
5. T0014-T0017 appear in DEPENDENCY_GRAPH.md and EPICS.md
6. Gate task dependencies (T0014 depends_on T0001, etc.)
7. Semantic assertions (no old model names in T0201/T0205/T0708)
"""

import csv
import json
import re
import sys
from pathlib import Path


def parse_tickets_md(md_path: Path) -> list[dict]:
    """Parse TICKETS.md to extract complete ticket information."""
    with open(md_path, encoding='utf-8') as f:
        content = f.read()

    tickets = []
    # Match ticket blocks: ### T0001 — Title ... until next ### or end
    pattern = r'### (T\d{4})\s*—\s*(.+?)\n(.*?)(?=\n### |$)'
    matches = re.findall(pattern, content, re.DOTALL)

    for ticket_id, title, body in matches:
        # Parse dependencies
        deps = []
        deps_match = re.search(r'\*\*依赖\*\*[：:]\s*(.+?)(?:\n|$)', body)
        if deps_match:
            deps_str = deps_match.group(1)
            # Filter out "无" and empty values
            deps = [d.strip() for d in re.split(r'[;，,]', deps_str)
                    if d.strip() and d.strip() != '无']

        # Parse goal
        goal = ''
        goal_match = re.search(r'\*\*目标\*\*[：:]\s*(.+?)(?:\n\n|\n-|\n\*\*|$)', body, re.DOTALL)
        if goal_match:
            goal = goal_match.group(1).strip()

        # Parse deliverables - find position and extract lines until next ** field
        deliverables = []
        deliv_start = body.find('**交付物**')
        if deliv_start != -1:
            # Find next ** field after deliverables
            remaining = body[deliv_start:]
            # Find end of deliverables section
            deliv_end = len(remaining)
            for marker in ['**验收标准**', '**阻塞范围**', '**依赖**', '**目标**',
                           '**优先级**']:
                pos = remaining.find(marker, 10)  # Skip the first occurrence
                if pos != -1 and pos < deliv_end:
                    deliv_end = pos
            deliv_block = remaining[:deliv_end]
            deliverables = [
                d.strip().lstrip('- ').lstrip('[]✓x ')
                for d in deliv_block.split('\n')
                if d.strip().startswith('-') and '**' not in d
            ]

        # Parse acceptance - find position and extract lines until next section
        acceptance = []
        acc_start = body.find('**验收标准**')
        if acc_start != -1:
            remaining = body[acc_start:]
            # Find end of acceptance section
            acc_end = len(remaining)
            for marker in ['**阻塞范围**', '**依赖**', '**目标**', '**优先级**']:
                pos = remaining.find(marker, 10)
                if pos != -1 and pos < acc_end:
                    acc_end = pos
            acc_block = remaining[:acc_end]
            acceptance = [
                re.sub(r'^- \[[ x]\] ', '', a.strip()).lstrip('- ')
                for a in acc_block.split('\n')
                if a.strip().startswith('-') and '**' not in a
            ]

        tickets.append({
            'id': ticket_id,
            'title': title.strip(),
            'dependencies': deps,
            'goal': goal,
            'deliverables': deliverables,
            'acceptance': acceptance
        })

    return tickets


def parse_tickets_json(json_path: Path) -> list[dict]:
    """Parse tickets.json to extract ticket information."""
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    tickets = []
    for ticket in data.get('tickets', []):
        tickets.append({
            'id': ticket['id'],
            'title': ticket['title'],
            'goal': ticket.get('goal', ''),
            'deliverables': ticket.get('deliverables', []),
            'acceptance': ticket.get('acceptance', []),
            'dependencies': ticket.get('dependencies', [])
        })

    return tickets


def parse_tickets_csv(csv_path: Path) -> list[dict]:
    """Parse tickets.csv to extract ticket information."""
    tickets = []
    with open(csv_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            deps = []
            if row.get('dependencies'):
                deps = [d.strip() for d in row['dependencies'].split(';') if d.strip()]

            deliverables = []
            if row.get('deliverables'):
                deliverables = [d.strip() for d in row['deliverables'].split(';') if d.strip()]

            acceptance = []
            if row.get('acceptance'):
                acceptance = [a.strip() for a in row['acceptance'].split(';') if a.strip()]

            tickets.append({
                'id': row['id'],
                'title': row['title'],
                'goal': row.get('goal', ''),
                'deliverables': deliverables,
                'acceptance': acceptance,
                'dependencies': deps
            })

    return tickets


def check_dependency_graph(graph_path: Path, required_ids: set[str]) -> list[str]:
    """Check if T0014-T0017 appear in DEPENDENCY_GRAPH.md."""
    with open(graph_path, encoding='utf-8') as f:
        content = f.read()

    errors: list[str] = []
    for ticket_id in required_ids:
        if ticket_id not in content:
            errors.append(f"{ticket_id} not found in DEPENDENCY_GRAPH.md")

    return errors


def check_epics(epics_path: Path, required_ids: set[str]) -> list[str]:
    """Check if T0014-T0017 appear in EPICS.md."""
    with open(epics_path, encoding='utf-8') as f:
        content = f.read()

    errors: list[str] = []
    for ticket_id in required_ids:
        if ticket_id not in content:
            errors.append(f"{ticket_id} not found in EPICS.md")

    return errors


def check_dangling_dependencies(tickets: list[dict]) -> list[str]:
    """Check for dangling dependencies."""
    all_ids = {t['id'] for t in tickets}
    errors: list[str] = []

    for ticket in tickets:
        for dep in ticket.get('dependencies', []):
            if dep not in all_ids:
                errors.append(f"{ticket['id']} depends on non-existent {dep}")

    return errors


def check_gate_dependencies(json_tickets: list[dict]) -> list[str]:
    """Check Gate task dependency structure."""
    errors: list[str] = []

    # Build dependency map
    deps_map = {t['id']: set(t.get('dependencies', [])) for t in json_tickets}

    # Expected dependencies
    expected = {
        'T0014': {'T0001'},
        'T0015': {'T0014'},
        'T0016': {'T0015'},
        'T0017': {'T0015'},
    }

    for ticket_id, expected_deps in expected.items():
        actual_deps = deps_map.get(ticket_id, set())
        if actual_deps != expected_deps:
            errors.append(
                f"{ticket_id} dependency mismatch: "
                f"expected {expected_deps}, got {actual_deps}"
            )

    # T0016 and T0017 should not depend on each other
    if 'T0016' in deps_map and 'T0017' in deps_map['T0016']:
        errors.append("T0016 should not depend on T0017")
    if 'T0017' in deps_map and 'T0016' in deps_map['T0017']:
        errors.append("T0017 should not depend on T0016")

    return errors


def check_semantic_assertions(json_tickets: list[dict]) -> list[str]:
    """Check semantic assertions for specific tickets."""
    errors: list[str] = []

    # Tickets to check
    check_tickets = {
        'T0201': {
            'forbidden': ['PP-DocLayout-M', 'PP-DocLayout_M'],
            'in_fields': ['title', 'goal']
        },
        'T0205': {
            'forbidden': ['PP-OCRv6 Small', 'PP-OCRv6_Small'],
            'in_fields': ['title', 'goal']
        },
        'T0405': {
            'forbidden': ['Monkey可主导', 'Monkey 可主导'],
            'in_fields': ['acceptance']
        },
        'T0708': {
            'forbidden': ['Monkey 8106', '增加 Monkey 8106', '8106'],
            'in_fields': ['title', 'goal', 'deliverables']
        }
    }

    tickets_by_id = {t['id']: t for t in json_tickets}

    for ticket_id, checks in check_tickets.items():
        if ticket_id not in tickets_by_id:
            errors.append(f"{ticket_id} not found in tickets.json")
            continue

        ticket = tickets_by_id[ticket_id]

        for field in checks['in_fields']:
            value = ticket.get(field, '')
            if isinstance(value, list):
                value = ' '.join(value)

            for forbidden in checks['forbidden']:
                if forbidden.lower() in value.lower():
                    errors.append(
                        f"{ticket_id} contains forbidden '{forbidden}' in {field}"
                    )

    return errors


def compare_field(ticket_id: str, field: str,
                  md_val: str | list, json_val: str | list, csv_val: str | list) -> list[str]:
    """Compare a single field across all three formats."""
    errors: list[str] = []

    # Normalize to sets for comparison
    if isinstance(md_val, str):
        md_val = md_val.strip()
    if isinstance(json_val, str):
        json_val = json_val.strip()
    if isinstance(csv_val, str):
        csv_val = csv_val.strip()

    if isinstance(md_val, list):
        md_val = [v.strip() for v in md_val if v.strip()]
    if isinstance(json_val, list):
        json_val = [v.strip() for v in json_val if v.strip()]
    if isinstance(csv_val, list):
        csv_val = [v.strip() for v in csv_val if v.strip()]

    # Compare MD vs JSON
    if md_val != json_val:
        if isinstance(md_val, list):
            md_set, json_set = set(md_val), set(json_val)
            if md_set != json_set:
                errors.append(
                    f"{ticket_id} {field} mismatch (md vs json): "
                    f"{md_set - json_set} vs {json_set - md_set}"
                )
        else:
            errors.append(
                f"{ticket_id} {field} mismatch (md vs json): "
                f"'{md_val[:50]}' vs '{json_val[:50]}'"
            )

    # Compare MD vs CSV
    if md_val != csv_val:
        if isinstance(md_val, list):
            md_set, csv_set = set(md_val), set(csv_val)
            if md_set != csv_set:
                errors.append(
                    f"{ticket_id} {field} mismatch (md vs csv): "
                    f"{md_set - csv_set} vs {csv_set - md_set}"
                )
        else:
            errors.append(
                f"{ticket_id} {field} mismatch (md vs csv): "
                f"'{md_val[:50]}' vs '{csv_val[:50]}'"
            )

    return errors


def main() -> None:
    """Main validation function."""
    repo_root = Path(__file__).parent.parent
    errors: list[str] = []

    # Parse all three formats
    md_path = repo_root / 'tasks' / 'TICKETS.md'
    json_path = repo_root / 'tasks' / 'tickets.json'
    csv_path = repo_root / 'tasks' / 'tickets.csv'

    md_tickets = parse_tickets_md(md_path)
    json_tickets = parse_tickets_json(json_path)
    csv_tickets = parse_tickets_csv(csv_path)

    # Check total count
    expected_count = 97
    print("Ticket counts:")
    print(f"  TICKETS.md: {len(md_tickets)}")
    print(f"  tickets.json: {len(json_tickets)}")
    print(f"  tickets.csv: {len(csv_tickets)}")

    if len(md_tickets) != expected_count:
        errors.append(f"TICKETS.md has {len(md_tickets)} tickets, expected {expected_count}")
    if len(json_tickets) != expected_count:
        errors.append(f"tickets.json has {len(json_tickets)} tickets, expected {expected_count}")
    if len(csv_tickets) != expected_count:
        errors.append(f"tickets.csv has {len(csv_tickets)} tickets, expected {expected_count}")

    # Build ID sets
    md_ids = {t['id'] for t in md_tickets}
    json_ids = {t['id'] for t in json_tickets}
    csv_ids = {t['id'] for t in csv_tickets}

    # Check ID consistency
    if md_ids != json_ids:
        errors.append("ID mismatch between TICKETS.md and tickets.json")
        print(f"  Only in TICKETS.md: {md_ids - json_ids}")
        print(f"  Only in tickets.json: {json_ids - md_ids}")

    if md_ids != csv_ids:
        errors.append("ID mismatch between TICKETS.md and tickets.csv")
        print(f"  Only in TICKETS.md: {md_ids - csv_ids}")
        print(f"  Only in tickets.csv: {csv_ids - md_ids}")

    # Full field comparison
    print("\nChecking full field consistency...")
    md_by_id = {t['id']: t for t in md_tickets}
    json_by_id = {t['id']: t for t in json_tickets}
    csv_by_id = {t['id']: t for t in csv_tickets}

    fields = ['title', 'dependencies', 'goal', 'deliverables', 'acceptance']
    for ticket_id in md_ids & json_ids & csv_ids:
        md_t = md_by_id[ticket_id]
        json_t = json_by_id[ticket_id]
        csv_t = csv_by_id[ticket_id]

        for field in fields:
            errors.extend(compare_field(
                ticket_id, field,
                md_t.get(field, ''),
                json_t.get(field, ''),
                csv_t.get(field, '')
            ))

    if not any('mismatch' in e for e in errors):
        print("  Full field consistency: OK")

    # Check dangling dependencies
    errors.extend(check_dangling_dependencies(json_tickets))

    # Check T0014-T0017 in dependency graph and epics
    gate_tasks = {'T0014', 'T0015', 'T0016', 'T0017'}
    graph_path = repo_root / 'tasks' / 'DEPENDENCY_GRAPH.md'
    epics_path = repo_root / 'tasks' / 'EPICS.md'

    errors.extend(check_dependency_graph(graph_path, gate_tasks))
    errors.extend(check_epics(epics_path, gate_tasks))

    # Check Gate task dependencies
    print("\nChecking Gate task dependencies...")
    gate_errors = check_gate_dependencies(json_tickets)
    if gate_errors:
        for e in gate_errors:
            print(f"  WARNING: {e}")
        errors.extend(gate_errors)
    else:
        print("  Gate dependencies: OK")

    # Check semantic assertions
    print("\nChecking semantic assertions...")
    semantic_errors = check_semantic_assertions(json_tickets)
    if semantic_errors:
        for e in semantic_errors:
            print(f"  ERROR: {e}")
        errors.extend(semantic_errors)
    else:
        print("  Semantic assertions: OK")

    # Report results
    if errors:
        print("\n❌ VALIDATION FAILED")
        for error in errors:
            print(f"  ERROR: {error}")
        sys.exit(1)
    else:
        print("\n✅ ALL CHECKS PASSED")
        sys.exit(0)


if __name__ == '__main__':
    main()
