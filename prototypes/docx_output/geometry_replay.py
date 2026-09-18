"""Offline sealed geometry replay with private overlays; no model or renderer calls."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from .common import ROOT, Json, digest, private_dir, read, save
from .geometry import monkey_adapter, native_adapter, pp_adapter
from .geometry.candidate import TransformChain, attach


def replay(manifest_path: Path, output: Path) -> Json:
    """Verify all input seals before writing a new private, non-overwriting bundle."""
    manifest = read(manifest_path)
    providers = [entry["provider"] for entry in manifest["sources"]]
    if len(set(providers)) != len(providers):
        raise ValueError("DUPLICATE_PROVIDER_USE_SEPARATE_REPLAY")
    files = [manifest["image"], *manifest["sources"]]
    for entry in files:
        path = Path(entry["path"])
        if not path.is_absolute():
            path = manifest_path.parent / path
        if digest(path) != entry["sha256"]:
            raise ValueError("SEALED_INPUT_HASH_MISMATCH")
        entry["resolved"] = path
    if output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    page = manifest["page"]
    chain = TransformChain(**manifest["transform"])
    if list(chain.page_size_pt) != [page["width_pt"], page["height_pt"]]:
        raise ValueError("PAGE_TRANSFORM_MISMATCH")
    image_entry = manifest["image"]
    with Image.open(image_entry["resolved"]) as original:
        if list(original.size) != list(chain.raster_size_px):
            raise ValueError("IMAGE_TRANSFORM_MISMATCH")
        canvas = original.convert("RGB")
    try:
        for entry in manifest["sources"]:
            evidence = {**entry.get("evidence", {}), "response_sha256": entry["sha256"]}
            body = read(entry["resolved"])
            if entry["provider"] == "native":
                geometry = body["geometry"]
                # Native observations must describe the same visible page, never a
                # merely similarly sized PDF selected behind the user's back.
                if entry.get("page_image_sha256") != image_entry["sha256"]:
                    raise ValueError("NATIVE_IMAGE_BINDING_MISSING")
                if [geometry["width_pt"], geometry["height_pt"]] != list(chain.page_size_pt):
                    raise ValueError("NATIVE_PAGE_MISMATCH")
                adapted = native_adapter.adapt(body, page["page_index"], evidence)
            elif entry["provider"] in {"monkey", "pp"}:
                adapter = monkey_adapter if entry["provider"] == "monkey" else pp_adapter
                adapted = adapter.adapt(body, page["page_index"], chain, evidence)
            else:
                raise ValueError("UNKNOWN_PROVIDER")
            attach(page, adapted)
        from jsonschema import Draft202012Validator

        validator = Draft202012Validator(read(ROOT / "specs/geometry-candidate.schema.json"))
        for candidate in page.get("geometry_candidates", []):
            validator.validate(candidate)
        private_dir(output)
        save(output / "candidates.json", page)
        colors = {"monkey": "red", "pp": "blue", "native": "green"}
        hashes = {"candidates.json": digest(output / "candidates.json")}
        for provider in sorted({e["provider"] for e in manifest["sources"]}):
            overlay = canvas.copy()
            try:
                draw = ImageDraw.Draw(overlay)
                for candidate in page.get("geometry_candidates", []):
                    if candidate["provider"] != provider:
                        continue
                    points = [
                        (x * canvas.width / page["width_pt"], y * canvas.height / page["height_pt"])
                        for x, y in candidate["quad_pt"]
                    ]
                    draw.line([*points, points[0]], fill=colors[provider], width=2)
                path = output / f"{provider}-overlay.png"
                overlay.save(path)
                path.chmod(0o600)
                hashes[path.name] = digest(path)
            finally:
                overlay.close()
        receipt = {
            "schema_version": "geometry-replay/1",
            "manifest_sha256": digest(manifest_path),
            "artifacts": hashes,
            "model_calls": 0,
            "reused_responses": len(manifest["sources"]),
            "candidate_count": len(page.get("geometry_candidates", [])),
            "rejection_count": len(page.get("geometry_rejections", [])),
            "sources_unchanged": all(digest(e["resolved"]) == e["sha256"] for e in files),
            "visual_acceptance": "NOT_RUN",
            "word_acceptance": "NOT_RUN",
            "layout_benefit": "NOT_VERIFIED",
        }
        save(output / "receipt.json", receipt)
        return receipt
    finally:
        canvas.close()


def main() -> None:
    """Expose the same pure adapters through an offline, explicit-input CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    replay(args.manifest, args.output_dir)
    print("GEOMETRY_REPLAY_WRITTEN")


if __name__ == "__main__":
    main()
