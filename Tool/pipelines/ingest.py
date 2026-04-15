from __future__ import annotations

import argparse
from pathlib import Path

from Tool.pipelines.common import build_manifest, ensure_raw_copy, manifest_path, resolve_inputs, save_json


def ingest(input_path: str) -> list[dict]:
    manifests: list[dict] = []
    for source in resolve_inputs(input_path):
        stored = ensure_raw_copy(source)
        manifest = build_manifest(stored)
        save_json(manifest_path(manifest["document_id"]), manifest)
        manifests.append(manifest)
    return manifests


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest raw enterprise documents into Raw/manifests.")
    parser.add_argument("--input", required=True, help="Path to a file or directory containing supported documents.")
    args = parser.parse_args()

    manifests = ingest(args.input)
    for manifest in manifests:
        print(f"INGESTED {manifest['document_id']} -> {manifest['stored_path']}")


if __name__ == "__main__":
    main()
