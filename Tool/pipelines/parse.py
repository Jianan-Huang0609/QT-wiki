from __future__ import annotations

import argparse

from Tool.parsers import parse_document
from Tool.pipelines.common import load_manifest, manifest_path, parsed_output_path, save_json


def parse_one(document_id: str) -> str:
    manifest = load_manifest(document_id)
    canonical = parse_document(manifest["stored_path"], manifest)
    output_path = parsed_output_path(document_id)
    canonical.save(output_path)

    manifest["parse_status"] = canonical.parse_status
    manifest["parsed_output"] = str(output_path)
    manifest["title"] = canonical.document.title
    save_json(manifest_path(document_id), manifest)
    return str(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a raw document into CanonicalDocument JSON.")
    parser.add_argument("--document-id", required=True, help="Document id generated during ingest.")
    args = parser.parse_args()

    output = parse_one(args.document_id)
    print(f"PARSED {args.document_id} -> {output}")


if __name__ == "__main__":
    main()
