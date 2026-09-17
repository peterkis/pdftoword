"""Sample validation uses actual schemas on isolated copies, never historical evidence."""

import json
import shutil
from pathlib import Path

from validate_schema_samples import PAIRS, ROOT, check_samples


def test_current_samples_and_invalid_copy(tmp_path: Path) -> None:
    for schema, sample in PAIRS:
        for name in (schema, sample):
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
    assert check_samples(tmp_path) == []
    path = tmp_path / PAIRS[0][1]
    data = json.loads(path.read_text())
    data.pop('pages')
    path.write_text(json.dumps(data))
    errors = check_samples(tmp_path)
    assert errors and errors[0]['code'] == 'INSTANCE_INVALID'
    assert 'instance' not in errors[0]


def test_remote_reference_is_rejected_without_fetch(tmp_path: Path) -> None:
    for schema, sample in PAIRS:
        for name, value in ((schema, {'$ref': 'https://invalid.test/private'}), (sample, {})):
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value))
    assert all(e['code'] == 'REFERENCE_NOT_LOCAL' for e in check_samples(tmp_path))


def test_missing_file_and_broken_schema_fail(tmp_path: Path) -> None:
    assert all(e['code'] == 'FILE_UNAVAILABLE' for e in check_samples(tmp_path))
    for schema, sample in PAIRS:
        for name, value in ((schema, {'type': 123}), (sample, {})):
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value))
    assert all(e['code'] == 'SCHEMA_INVALID' for e in check_samples(tmp_path))


def test_unresolved_local_reference_has_safe_error(tmp_path: Path) -> None:
    for schema, sample in PAIRS:
        for name, value in ((schema, {'$ref': '#/$defs/missing'}), (sample, {})):
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value))
    assert all(e['code'] == 'REFERENCE_UNRESOLVED' for e in check_samples(tmp_path))
