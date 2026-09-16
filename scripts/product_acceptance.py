"""Offline upload-to-Word runner and immutable evaluate-only evidence bundles."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from acceptance.metrics import evaluate, semantic_hash

ROOT = Path(__file__).resolve().parents[1]
Json = dict[str, Any]


def digest(path: Path) -> str:
    """Hash exact artifact bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Json:
    """Read a local JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return value


def member(root: Path, name: str) -> Path:
    """Resolve only local relative evidence members, rejecting symlinks and traversal."""
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("INVALID_EVIDENCE_PATH")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or any(
        p.is_symlink() for p in [path, *path.parents] if p != root.parent
    ):
        raise ValueError("INVALID_EVIDENCE_PATH")
    return path


def write(path: Path, value: Any) -> None:
    """Write a new private file; never overwrite results or earlier run evidence."""
    with path.open("x", encoding="utf-8") as stream:
        path.chmod(0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def verify(root: Path, hashes: Json) -> None:
    """Fail closed on any missing or changed sealed member."""
    for name, expected in hashes.items():
        if digest(member(root, name)) != expected:
            raise ValueError("EVIDENCE_HASH_MISMATCH")


def evaluate_only(bundle: Path, output: Path) -> Json:
    """Recompute a new score from sealed artifacts, with no conversion or model calls."""
    seal = read(bundle / "seal.json")
    required = {"run.json", "auto.docx", "truth.json", "source-map.json", "input.pdf"}
    if not required.issubset(seal):
        raise ValueError("INCOMPLETE_EVIDENCE_SEAL")
    verify(bundle, seal)
    run = read(bundle / "run.json")
    revision = run.get("revision", "auto")
    if revision not in {"auto", "reviewed"}:
        raise ValueError("INVALID_REVISION")
    artifact = revision + ".docx"
    if artifact not in seal:
        raise ValueError("UNSEALED_OUTPUT")
    sources = read(bundle / "source-map.json")
    if sources["docx_sha256"] != digest(bundle / artifact):
        raise ValueError("SOURCE_MAP_OUTPUT_MISMATCH")
    if (
        digest(bundle / "input.pdf") != run["source_sha256"]
        or digest(bundle / "truth.json") != run["annotation_sha256"]
    ):
        raise ValueError("REFERENCE_IDENTITY_MISMATCH")
    if sorted(p["page"] for p in sources["pages"]) != sorted(run["selected_pages"]):
        raise ValueError("SELECTED_PAGE_MISMATCH")
    truth = read(bundle / "truth.json")
    if truth["source_sha256"] != run["source_sha256"]:
        raise ValueError("REFERENCE_SOURCE_MISMATCH")
    result = evaluate(bundle / artifact, truth, sources)
    result.update(
        {
            "identity": {
                k: run[k]
                for k in [
                    "sample_id",
                    "document_family",
                    "source_sha256",
                    "annotation_sha256",
                    "source_tree_sha256",
                    "source_commit",
                    "dirty",
                    "profile",
                ]
            },
            "artifact_sha256": seal[artifact],
            "revision": revision,
            "auto_sha256": seal["auto.docx"],
            "rendering_status": run["rendering"]["status"],
            "rendering": run["rendering"],
            "request_budget": 0,
            "request_attempted": 0,
        }
    )
    result["evaluator_sha256"] = semantic_hash(
        {p.name: digest(p) for p in sorted((ROOT / "scripts/acceptance").glob("*.py"))}
    )
    result.pop("semantic_sha256")
    result["semantic_sha256"] = semantic_hash(result)
    write(output, result)
    return result


def run_sample(dataset: Path, sample_id: str, entry: str, output: Path) -> Json:
    """Run one explicitly selected frozen native sample and seal its real output."""
    verify(dataset, read(dataset / "seal.json"))
    manifest = read(dataset / "manifest.json")
    if manifest["status"] != "FROZEN":
        raise ValueError("DATASET_NOT_FROZEN")
    sample = next((item for item in manifest["items"] if item["sample_id"] == sample_id), None)
    if sample is None or not sample["local_read_authorized"]:
        raise ValueError("SAMPLE_NOT_AUTHORIZED")
    # Reserve/holdout execution must be a deliberate later protocol, never a default selection.
    if sample["usage"] != "initial" or sample["split"] != "development":
        raise ValueError("DEVELOPMENT_SAMPLE_REQUIRED")
    if sample["category"] != "N":
        raise ValueError("OFFLINE_NATIVE_SAMPLE_REQUIRED")
    source = member(dataset / "corpus", sample["private_path"])
    annotation = member(dataset / "annotations", sample["annotation_path"])
    if digest(source) != sample["source_sha256"]:
        raise ValueError("SOURCE_HASH_MISMATCH")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    output.chmod(0o700)
    shutil.copyfile(source, output / "input.pdf")
    (output / "input.pdf").chmod(0o600)
    jobs = ROOT / "tmp/docx-demo" / ("acceptance-" + uuid.uuid4().hex)
    command = [
        sys.executable,
        str(ROOT / "scripts/acceptance/worker.py"),
        "--entry",
        entry,
        "--input",
        str((output / "input.pdf").resolve()),
        "--pages",
        ",".join(map(str, sample["selected_pages"])),
        "--jobs",
        str(jobs),
    ]
    started = time.monotonic()
    try:
        process = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, timeout=180, check=False
        )
        write(
            output / "process.private.json",
            {"returncode": process.returncode, "stdout": process.stdout, "stderr": process.stderr},
        )
        if process.returncode:
            raise ValueError("CONVERSION_FAILED")
        worker = json.loads(process.stdout)
        job = Path(worker["job"])
        if job.parent != jobs or worker["pipeline_calls"] != 1 or worker["network_attempts"]:
            raise ValueError("CONVERSION_BUDGET_VIOLATION")
        for name, src in [
            ("auto.docx", job / "auto.docx"),
            ("source-map.json", job / "source-map.auto.json"),
            ("truth.json", annotation),
        ]:
            shutil.copyfile(src, output / name)
            (output / name).chmod(0o600)
        # Render only this newly-created job. No legacy job or reviewed output is changed.
        sys.path.insert(0, str(ROOT))
        from prototypes.docx_output.render import render
        from prototypes.docx_output.writer import fonts

        qa = render(job)
        rendering = {
            "status": "RENDERED"
            if qa["render_status"] == "RENDERED"
            else "FAILED"
            if qa.get("renderer")
            else "PENDING",
            "renderer": qa.get("renderer"),
            "version": qa.get("renderer_version"),
            "fonts": fonts(),
            "human_acceptance": "PENDING",
            "artifacts": {},
        }
        if rendering["status"] == "RENDERED":
            shutil.copytree(job / "rendered/auto", output / "rendered")
            rendering["artifacts"] = {
                str(p.relative_to(output)): digest(p)
                for p in sorted((output / "rendered").glob("*"))
                if p.is_file()
            }
        code_paths = [
            *sorted((ROOT / "prototypes/docx_output").rglob("*.py")),
            *sorted((ROOT / "scripts/acceptance").glob("*.py")),
            ROOT / "scripts/product_acceptance.py",
            ROOT / "scripts/docx_demo.py",
        ]
        source_tree = {str(p.relative_to(ROOT)): digest(p) for p in code_paths}
        environment = {
            "python": platform.python_version(),
            "platform": platform.system(),
            "architecture": platform.machine(),
            "packages": {
                name: importlib.metadata.version(name)
                for name in ["python-docx", "lxml", "pypdfium2", "Pillow", "fastapi", "httpx"]
            },
        }
        run = {
            "schema_version": "product-run/1.0",
            "environment": environment,
            "run_id": output.name,
            "sample_id": sample_id,
            "document_family": sample["document_family"],
            "source_sha256": digest(source),
            "annotation_sha256": digest(annotation),
            "dataset_seal_sha256": digest(dataset / "seal.json"),
            "selected_pages": sample["selected_pages"],
            "profile": {"mode": "native", "content_provider": "ovis-pp", "network": "offline"},
            "entry": entry,
            "api_surface": "in_process_TestClient" if entry == "api" else None,
            "pipeline_calls": worker["pipeline_calls"],
            "request_budget": 0,
            "request_attempted": worker["network_attempts"],
            "elapsed_seconds": time.monotonic() - started,
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
            "source_tree_sha256": semantic_hash(source_tree),
            "source_files": source_tree,
            "rendering": rendering,
            "reviewed": {"status": "NOT_RUN", "artifact": None},
        }
        write(output / "run.json", run)
        sealed = {
            str(p.relative_to(output)): digest(p)
            for p in output.rglob("*")
            if p.is_file() and p.name != "process.private.json"
        }
        write(output / "seal.json", sealed)
        return evaluate_only(output, output / "result.json")
    except (ValueError, OSError, subprocess.SubprocessError):
        write(
            output / "failure.json",
            {
                "execution_status": "FAILED",
                "elapsed_seconds": time.monotonic() - started,
                "human_acceptance": "PENDING",
            },
        )
        raise


def import_reviewed(bundle: Path, docx: Path, output: Path) -> Json:
    """Create a new reviewed bundle while preserving the original automatic bytes and seal."""
    seal = read(bundle / "seal.json")
    verify(bundle, seal)
    run = read(bundle / "run.json")
    if run.get("revision", "auto") != "auto":
        raise ValueError("AUTO_BASE_REQUIRED")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    for name in ["input.pdf", "auto.docx", "truth.json"]:
        shutil.copyfile(member(bundle, name), output / name)
        (output / name).chmod(0o600)
    shutil.copyfile(docx, output / "reviewed.docx")
    (output / "reviewed.docx").chmod(0o600)
    sources = read(bundle / "source-map.json")
    sources["docx_sha256"] = digest(output / "reviewed.docx")
    sources["binding_origin"] = "auto_source_bookmarks_no_new_geometry_inferred"
    write(output / "source-map.json", sources)
    run.update(
        {
            "revision": "reviewed",
            "parent_seal_sha256": digest(bundle / "seal.json"),
            "rendering": {
                "status": "PENDING",
                "renderer": None,
                "version": None,
                "human_acceptance": "PENDING",
                "artifacts": {},
            },
            "manual_override_count": None,
            "human_active_minutes": None,
        }
    )
    write(output / "run.json", run)
    write(output / "seal.json", {p.name: digest(p) for p in output.iterdir() if p.is_file()})
    return evaluate_only(output, output / "result.json")


def main() -> int:
    """Provide native CLI/API runs and deterministic offline rescoring."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--sample-id", required=True)
    run.add_argument("--entry", choices=["cli", "api"], required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    score = sub.add_parser("evaluate-only")
    score.add_argument("--bundle", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    reviewed = sub.add_parser("import-reviewed")
    reviewed.add_argument("--bundle", type=Path, required=True)
    reviewed.add_argument("--docx", type=Path, required=True)
    reviewed.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == "run":
            result = run_sample(
                args.dataset.resolve(), args.sample_id, args.entry, args.output_dir.resolve()
            )
        elif args.command == "import-reviewed":
            result = import_reviewed(
                args.bundle.resolve(), args.docx.resolve(), args.output_dir.resolve()
            )
        else:
            result = evaluate_only(args.bundle.resolve(), args.output.resolve())
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({"execution_status": "FAILED", "error_class": type(exc).__name__}))
        return 2
    print(
        json.dumps(
            {
                "execution_status": result["execution_status"],
                "content_status": result["content_status"],
                "structure_status": result["structure_status"],
                "semantic_sha256": result["semantic_sha256"],
            }
        )
    )
    return 1 if "FAIL" in [result["content_status"], result["structure_status"]] else 0


if __name__ == "__main__":
    raise SystemExit(main())
