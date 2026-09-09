#!/usr/bin/env python3
"""
Model baseline validation script.

Validates that documentation, configs, and task catalog are consistent
with current deployment baseline (9000/8000/8080) and target architecture (8100).

Historical ports (8102/8104/8106) must only appear in explicitly marked
historical contexts.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def check_current_ports(content: str, file_path: Path) -> list[dict]:
    """Check for old ports (8102/8104/8106) in current context."""
    violations: list[dict] = []

    # Skip historical documents
    skip_files = {
        'CHANGELOG.md',
        'ADR-003-MONKEY-GEOMETRY-AUTHORITY.md',
        '21_MIGRATION_V1_0_TO_V1_1.md',
        '23_MODEL_DEPLOYMENT_BASELINE_V1_1.md',
        'T0001_BASELINE_COMMIT.md',
        'T0014_LEGACY_REFERENCE_AUDIT.md',
    }
    if file_path.name in skip_files:
        return violations

    # Historical ports
    historical_ports = ['8102', '8104', '8106']

    # Allowed contexts for historical ports
    allowed_contexts = [
        r'历史',
        r'V1\.0',
        r'旧',
        r'原端口',
        r'曾部署',
        r'已迁移',
        r'已废弃',
        r'→',
        r'✅',
        r'已完成',
        r'早期设计',
        r'不是当前部署',
        r'不是固定',
    ]

    for i, line in enumerate(content.split('\n'), 1):
        for port in historical_ports:
            if port in line:
                # Check if line has allowed context
                has_allowed = any(
                    re.search(ctx, line, re.IGNORECASE) for ctx in allowed_contexts
                )
                if not has_allowed:
                    violations.append({
                        'file': str(file_path),
                        'line': i,
                        'type': 'incorrect_port',
                        'content': line.strip()[:100]
                    })

    return violations


def check_old_model_names(content: str, file_path: Path) -> list[dict]:
    """Check for old model names in current context."""
    violations: list[dict] = []

    # Skip allowed files
    allowed_files = {
        'CHANGELOG.md',
        'T0001_BASELINE_COMMIT.md',
        'ADR-003-MONKEY-GEOMETRY-AUTHORITY.md',
        '21_MIGRATION_V1_0_TO_V1_1.md',
    }
    if file_path.name in allowed_files:
        return violations

    # Old model names
    old_names = ['PP-DocLayout-M', 'PP-OCRv6 Small', 'PP-FormulaNet-S']

    # Allowed contexts
    allowed_contexts = [
        r'历史',
        r'旧',
        r'原',
        r'已升级',
        r'名称对照',
        r'旧模型',
        r'对照表',
        r'→',
        r'✅',
        r'已完成',
        r'V1\.0',
    ]

    for i, line in enumerate(content.split('\n'), 1):
        for old_name in old_names:
            if old_name in line:
                has_allowed = any(
                    re.search(ctx, line, re.IGNORECASE) for ctx in allowed_contexts
                )
                if not has_allowed:
                    violations.append({
                        'file': str(file_path),
                        'line': i,
                        'type': 'old_model_name',
                        'content': line.strip()[:100]
                    })

    return violations


def check_geometry_authority(content: str, file_path: Path) -> list[dict]:
    """Check geometry authority claims."""
    violations: list[dict] = []

    # Skip ADR-003 which is historical
    if file_path.name == 'ADR-003-MONKEY-GEOMETRY-AUTHORITY.md':
        return violations

    has_geometry_authority = '几何' in content and '权威' in content
    has_pp_layout = 'PP-DocLayout' in content or 'PP-DocBlockLayout' in content
    is_historical_context = '不预设' in content or '历史' in content

    if has_geometry_authority and not has_pp_layout and not is_historical_context:
        violations.append({
            'file': str(file_path),
            'line': 0,
            'type': 'missing_pp_layout',
            'content': 'Geometry section should mention PP-DocLayout variants'
        })

    return violations


def check_monkey_geometry_role(content: str, file_path: Path) -> list[dict]:
    """Check Monkey geometry role description."""
    violations: list[dict] = []

    # Check docs/08 for "几何权威" or "几何主模型"
    if file_path.name == '08_MONKEYOCRv2_INTEGRATION.md':
        for i, line in enumerate(content.split('\n'), 1):
            if '几何权威' in line and '不预设' not in line:
                violations.append({
                    'file': str(file_path),
                    'line': i,
                    'type': 'monkey_geometry_authority',
                    'content': 'Monkey should be described as geometry candidate, not authority'
                })
            if '几何主模型' in line:
                violations.append({
                    'file': str(file_path),
                    'line': i,
                    'type': 'monkey_geometry_primary',
                    'content': 'Monkey should not be described as primary geometry model'
                })

    return violations


def check_adr005_amended(content: str, file_path: Path) -> list[dict]:
    """Check ADR-005 is amended with current ports."""
    violations: list[dict] = []

    if file_path.name != 'ADR-005-MODEL-GATEWAY.md':
        return violations

    # Should have "Amended" status
    if 'Amended' not in content:
        violations.append({
            'file': str(file_path),
            'line': 0,
            'type': 'adr005_not_amended',
            'content': 'ADR-005 should have status "Accepted — Amended"'
        })

    # Should mention current ports
    if '9000' not in content or '8000' not in content or '8080' not in content:
        violations.append({
            'file': str(file_path),
            'line': 0,
            'type': 'adr005_missing_ports',
            'content': 'ADR-005 should mention current provider ports (9000/8000/8080)'
        })

    return violations


def check_docs21_historical(content: str, file_path: Path) -> list[dict]:
    """Check docs/21 is marked as historical or updated."""
    violations: list[dict] = []

    if file_path.name != '21_MIGRATION_V1_0_TO_V1_1.md':
        return violations

    # Should have historical banner or updated content
    has_banner = '历史' in content or 'Historical' in content or 'Superseded' in content
    has_updated = '当前部署对齐' in content or 'ADR-006' in content

    if not has_banner and not has_updated:
        violations.append({
            'file': str(file_path),
            'line': 0,
            'type': 'docs21_not_historical',
            'content': 'docs/21 should be marked as Historical or updated with current baseline'
        })

    return violations


def check_agents_port_rule(content: str, file_path: Path) -> list[dict]:
    """Check AGENTS.md port rule."""
    violations: list[dict] = []

    if file_path.name != 'AGENTS.md':
        return violations

    # Line 10 should not say "本地应用不得直接调用 8102/8104/8106"
    # Should mention production/gate/historical distinction
    for i, line in enumerate(content.split('\n'), 1):
        if '不得直接调用' in line and '生产' not in line:
            violations.append({
                'file': str(file_path),
                'line': i,
                'type': 'agents_port_rule',
                'content': 'AGENTS port rule should distinguish production/gate/historical'
            })
            break

    return violations


def check_start_here(repo_root: Path) -> list[dict]:
    """Check START_HERE.md for specific assertions."""
    violations: list[dict] = []
    file_path = repo_root / 'START_HERE.md'

    if not file_path.exists():
        violations.append({
            'file': 'START_HERE.md',
            'line': 0,
            'type': 'missing_file',
            'content': 'START_HERE.md not found'
        })
        return violations

    content = file_path.read_text(encoding='utf-8')

    # Should mention PP-DocLayout_plus-L for geometry
    if '几何' in content and 'PP-DocLayout' not in content:
        violations.append({
            'file': str(file_path),
            'line': 0,
            'type': 'missing_pp_layout',
            'content': 'START_HERE.md should mention PP-DocLayout_plus-L'
        })

    return violations


def check_validation_report(repo_root: Path) -> list[dict]:
    """Check VALIDATION_REPORT.md for specific assertions."""
    violations: list[dict] = []
    file_path = repo_root / 'VALIDATION_REPORT.md'

    if not file_path.exists():
        violations.append({
            'file': 'VALIDATION_REPORT.md',
            'line': 0,
            'type': 'missing_file',
            'content': 'VALIDATION_REPORT.md not found'
        })
        return violations

    content = file_path.read_text(encoding='utf-8')

    # Should have NEEDS_FIX summary
    if 'NEEDS_FIX' not in content:
        violations.append({
            'file': str(file_path),
            'line': 0,
            'type': 'missing_needs_fix',
            'content': 'VALIDATION_REPORT.md should have NEEDS_FIX summary'
        })

    return violations


def check_agents_geometry(repo_root: Path) -> list[dict]:
    """Check AGENTS.md geometry section."""
    violations: list[dict] = []
    file_path = repo_root / 'AGENTS.md'

    if not file_path.exists():
        violations.append({
            'file': 'AGENTS.md',
            'line': 0,
            'type': 'missing_file',
            'content': 'AGENTS.md not found'
        })
        return violations

    content = file_path.read_text(encoding='utf-8')

    # Geometry section should show arbitration, not hierarchy
    has_geo_section = '几何与阅读顺序' in content
    has_arbitration = 'Arbitration' in content or '仲裁' in content

    if has_geo_section and not has_arbitration:
        geo_section = content.split('几何与阅读顺序')[1][:500]
        if 'PP-DocLayout' not in geo_section:
            violations.append({
                'file': str(file_path),
                'line': 0,
                'type': 'incorrect_geometry_hierarchy',
                'content': 'AGENTS.md geometry section should show arbitration/candidates'
            })

    return violations


def check_baseline_commit(repo_root: Path) -> list[dict]:
    """Check that T0001 baseline commit document exists."""
    violations: list[dict] = []
    file_path = repo_root / 'tasks' / 'reports' / 'T0001_BASELINE_COMMIT.md'

    if not file_path.exists():
        violations.append({
            'file': 'tasks/reports/T0001_BASELINE_COMMIT.md',
            'line': 0,
            'type': 'missing_file',
            'content': 'T0001 baseline commit document not found'
        })
    else:
        content = file_path.read_text(encoding='utf-8')
        # Should have ACCEPTED status
        if 'ACCEPTED' not in content:
            violations.append({
                'file': str(file_path),
                'line': 0,
                'type': 'baseline_not_accepted',
                'content': 'T0001_BASELINE_COMMIT.md should have ACCEPTED status'
            })

    return violations


def main() -> None:
    """Main validation function."""
    repo_root = Path(__file__).parent.parent
    all_violations: list[dict] = []

    # Check specific files
    all_violations.extend(check_start_here(repo_root))
    all_violations.extend(check_validation_report(repo_root))
    all_violations.extend(check_agents_geometry(repo_root))
    all_violations.extend(check_baseline_commit(repo_root))

    # Scan documentation
    docs_dir = repo_root / 'docs'
    if docs_dir.exists():
        for md_file in docs_dir.rglob('*.md'):
            content = md_file.read_text(encoding='utf-8')
            all_violations.extend(check_current_ports(content, md_file))
            all_violations.extend(check_old_model_names(content, md_file))
            all_violations.extend(check_geometry_authority(content, md_file))
            all_violations.extend(check_monkey_geometry_role(content, md_file))
            all_violations.extend(check_docs21_historical(content, md_file))

    # Scan ADRs
    adr_dir = repo_root / 'adr'
    if adr_dir.exists():
        for adr_file in adr_dir.rglob('*.md'):
            content = adr_file.read_text(encoding='utf-8')
            all_violations.extend(check_current_ports(content, adr_file))
            all_violations.extend(check_adr005_amended(content, adr_file))

    # Scan AGENTS.md
    agents_file = repo_root / 'AGENTS.md'
    if agents_file.exists():
        content = agents_file.read_text(encoding='utf-8')
        all_violations.extend(check_current_ports(content, agents_file))
        all_violations.extend(check_agents_port_rule(content, agents_file))

    # Scan config files
    config_dir = repo_root / 'config'
    if config_dir.exists():
        for config_file in config_dir.rglob('*.json'):
            content = config_file.read_text(encoding='utf-8')
            all_violations.extend(check_current_ports(content, config_file))

    # Scan samples
    samples_dir = repo_root / 'samples'
    if samples_dir.exists():
        for sample_file in samples_dir.rglob('*.json'):
            content = sample_file.read_text(encoding='utf-8')
            all_violations.extend(check_current_ports(content, sample_file))

    # Report results
    if all_violations:
        print("\n❌ VALIDATION FAILED")
        print(f"Found {len(all_violations)} violations:\n")
        for v in all_violations:
            print(f"  File: {v['file']}")
            print(f"  Line: {v['line']}")
            print(f"  Type: {v['type']}")
            print(f"  Content: {v['content']}")
            print()

        sys.exit(1)
    else:
        print("\n✅ ALL CHECKS PASSED")
        sys.exit(0)


if __name__ == '__main__':
    main()
