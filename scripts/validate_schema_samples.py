"""Validate the two contracted samples offline; diagnostics never include instance values."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing.exceptions import Unresolvable

ROOT = Path(__file__).resolve().parents[1]
PAIRS = (
    ('specs/layout-ir.schema.json', 'samples/sample-layout-ir-v1.1.json'),
    ('specs/job-config.schema.json', 'samples/sample-job-config.json'),
)


def references_local(value: Any) -> bool:
    """Only document-local fragments are needed by current contracts; never retrieve URIs."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {'$ref', '$dynamicRef'} and (
                not isinstance(item, str) or not item.startswith('#')
            ):
                return False
            if not references_local(item):
                return False
    elif isinstance(value, list):
        return all(references_local(item) for item in value)
    return True


def check_samples(root: Path = ROOT) -> list[dict[str, str]]:
    """Check schemas first, then instances; return only filenames and error classifications."""
    errors = []
    for schema_name, sample_name in PAIRS:
        try:
            schema = json.loads((root / schema_name).read_text(encoding='utf-8'))
            sample = json.loads((root / sample_name).read_text(encoding='utf-8'))
            if not references_local(schema):
                errors.append({'file': schema_name, 'code': 'REFERENCE_NOT_LOCAL'})
                continue
            Draft202012Validator.check_schema(schema)
            for error in Draft202012Validator(schema).iter_errors(sample):
                # Schema path identifies the violated contract without leaking instance keys/values.
                errors.append({'file': sample_name, 'code': 'INSTANCE_INVALID',
                               'schema_path': '/'.join(map(str, error.schema_path)),
                               'rule': str(error.validator)})
        except OSError:
            errors.append({'file': sample_name, 'code': 'FILE_UNAVAILABLE'})
        except (ValueError, UnicodeError):
            errors.append({'file': sample_name, 'code': 'INVALID_JSON'})
        except Unresolvable:
            errors.append({'file': schema_name, 'code': 'REFERENCE_UNRESOLVED'})
        except SchemaError:
            errors.append({'file': schema_name, 'code': 'SCHEMA_INVALID'})
    return errors


def main() -> int:
    """Validate existing samples; missing independent contracts are not invented."""
    errors = check_samples()
    print(json.dumps({'status': 'FAIL' if errors else 'PASS', 'pairs': len(PAIRS),
                      'errors': errors}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
