"""Read-only T0016 import; never import its evaluator or read ground truth."""

from pathlib import Path

from .common import DemoError, Json, digest, read, safe_path

DEFAULT_RUN = Path("tmp/raster-regression/runs/t0016-mac-20260911T030753Z-r2")
EXPECTED_JPG = "fe608629ae8af60890684c77437b3d62facd3a0c27b9fa019692890f96cbcf52"


def load(
    run: Path,
    variant: str = "jpg",
    repeat: int = 1,
    providers: tuple[str, ...] = ("pp", "ovis", "monkey"),
) -> tuple[Path, Json, Json]:
    """Select by provider/variant/repeat and verify sealed evidence bytes only."""
    seal = read(safe_path(run, "evidence-manifest.private.json"))

    def checked(name: str) -> Path:
        path = safe_path(run, name)
        if not path.is_file():
            raise DemoError(f"EVIDENCE_MISSING: {name}")
        if name not in seal or digest(path) != seal[name]:
            raise DemoError(f"EVIDENCE_HASH_MISMATCH: {name}")
        return path

    meta = read(checked("run-metadata.json"))
    if meta["execution_status"] != "COMPLETE":
        raise DemoError("REPLAY_REQUIRES_COMPLETE_RUN")
    inputs = read(checked("input-manifest.snapshot.json"))
    if inputs["variants"]["jpg"]["file_sha256"] != EXPECTED_JPG:
        raise DemoError("UNEXPECTED_REPLAY_SOURCE")
    v = inputs["variants"][variant]
    source = checked("inputs.private/" + v["filename"])
    if digest(source) != v["file_sha256"]:
        raise DemoError("INPUT_HASH_MISMATCH")
    requests = read(checked("requests.json"))["requests"]
    responses: Json = {}
    selected = []
    for provider in providers:
        matches = [
            r
            for r in requests
            if (r["provider"], r["variant_id"], r["repeat_index"]) == (provider, variant, repeat)
        ]
        if len(matches) != 1 or matches[0]["status"] != "COMPLETE":
            raise DemoError(f"COMPLETE_RESPONSE_MISSING: {provider}/{variant}/{repeat}")
        row = matches[0]
        if row["input_file_sha256"] != v["file_sha256"]:
            raise DemoError("REQUEST_INPUT_MISMATCH")
        for folder, key in [
            ("responses.private", "pruned_response_sha256"),
            ("predictions.private", "prediction_sha256"),
        ]:
            path = checked(f"{folder}/{row['request_id']}.json")
            if digest(path) != row[key]:
                raise DemoError("REQUEST_EVIDENCE_MISMATCH")
            if folder == "responses.private":
                # Collector writes strip_media(body), NOT discovery's response wrapper.
                responses[provider] = read(path)
        selected.append(row)
    provenance = {
        "source_run_id": meta["run_id"],
        "historical_tool_version": (
            "v1.1"
            if meta["tool_source_hashes"].get("scripts/raster_regression.py")
            == "89d0ed8a48c5cdca9aa9bc9ece6e081aecbb9284679d590c4cc104a305265c58"
            else "unknown"
        ),
        "historical_tool_hashes": meta["tool_source_hashes"],
        "variant_id": variant,
        "repeat_index": repeat,
        "requests": selected,
        "model_call_count": 0,
        "seal_sha256": digest(run / "evidence-manifest.private.json"),
    }
    return source, responses, provenance
