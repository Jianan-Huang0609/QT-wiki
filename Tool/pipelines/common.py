from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
from datetime import datetime
from pathlib import Path

from Tool.parsers import SUPPORTED_SUFFIXES

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "Raw"
MANIFEST_DIR = RAW_DIR / "manifests"
PARSED_DIR = REPO_ROOT / "Tool" / "output" / "parsed"


def save_json(path: str | Path, data: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def iter_manifest_paths() -> list[Path]:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(MANIFEST_DIR.glob("*.json"))


def load_manifest(document_id: str) -> dict:
    path = MANIFEST_DIR / f"{document_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found for document_id={document_id}")
    manifest = load_json(path)
    manifest["manifest_path"] = str(path.relative_to(REPO_ROOT))
    return manifest


def compute_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def infer_biz_domain(file_name: str, title: str = "") -> str:
    source = f"{file_name} {title}"
    if any(keyword in source for keyword in ("医疗器械", "质量管理", "规范")):
        return "medical-device-qms"
    return "generic"


def ensure_raw_copy(input_path: str | Path) -> Path:
    source = Path(input_path).resolve()
    raw_root = RAW_DIR.resolve()
    try:
        source.relative_to(raw_root)
        return source
    except ValueError:
        pass

    target = RAW_DIR / source.name
    if target.exists() and compute_sha256(target) == compute_sha256(source):
        return target.resolve()

    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        target = RAW_DIR / f"{source.stem}_{stamp}{source.suffix}"

    shutil.copy2(source, target)
    return target.resolve()


def generate_document_id(file_name: str, checksum: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"doc-{stamp}-{checksum[:8]}"


def manifest_path(document_id: str) -> Path:
    return MANIFEST_DIR / f"{document_id}.json"


def existing_manifest_for(checksum: str) -> dict | None:
    for path in iter_manifest_paths():
        manifest = load_json(path)
        if manifest.get("checksum") == checksum:
            manifest["manifest_path"] = str(path.relative_to(REPO_ROOT))
            return manifest
    return None


def build_manifest(stored_file: Path, *, source_system: str = "manual_cli") -> dict:
    checksum = compute_sha256(stored_file)
    existing = existing_manifest_for(checksum)
    if existing is not None:
        return existing

    document_id = generate_document_id(stored_file.name, checksum)
    mime_type = mimetypes.guess_type(stored_file.name)[0] or "application/octet-stream"
    manifest = {
        "document_id": document_id,
        "title": stored_file.stem,
        "file_name": stored_file.name,
        "stored_path": str(stored_file.relative_to(REPO_ROOT)),
        "mime_type": mime_type,
        "source_system": source_system,
        "biz_domain": infer_biz_domain(stored_file.name, stored_file.stem),
        "department": "unknown",
        "owner": "unknown",
        "confidentiality": "internal",
        "version": "v1",
        "checksum": checksum,
        "ingested_at": datetime.now().isoformat(timespec="seconds"),
        "parse_status": "pending",
        "parsed_output": None,
    }
    manifest["manifest_path"] = str(manifest_path(document_id).relative_to(REPO_ROOT))
    return manifest


def is_temporary_office_file(path: str | Path) -> bool:
    target = Path(path)
    return target.name.startswith("~$") and target.suffix.lower() in SUPPORTED_SUFFIXES


def resolve_inputs(input_path: str | Path) -> list[Path]:
    path = Path(input_path)
    if path.is_file():
        return [] if is_temporary_office_file(path) else [path]
    if path.is_dir():
        return sorted(
            item
            for item in path.iterdir()
            if item.is_file()
            and item.suffix.lower() in SUPPORTED_SUFFIXES
            and not is_temporary_office_file(item)
        )
    raise FileNotFoundError(f"Input path not found: {input_path}")


def purge_temporary_office_artifacts() -> dict[str, int]:
    removed = {"raw_files": 0, "manifests": 0, "parsed_outputs": 0}

    if RAW_DIR.exists():
        for path in RAW_DIR.iterdir():
            if not path.is_file() or not is_temporary_office_file(path):
                continue
            try:
                path.unlink(missing_ok=True)
                removed["raw_files"] += 1
            except PermissionError:
                continue

    for path in iter_manifest_paths():
        manifest = load_json(path)
        if not is_temporary_office_file(manifest.get("file_name", "")):
            continue

        parsed_output = manifest.get("parsed_output")
        if parsed_output:
            parsed_path = Path(parsed_output)
            if not parsed_path.is_absolute():
                parsed_path = REPO_ROOT / parsed_path
            if parsed_path.exists():
                try:
                    parsed_path.unlink(missing_ok=True)
                    removed["parsed_outputs"] += 1
                except PermissionError:
                    pass

        try:
            path.unlink(missing_ok=True)
            removed["manifests"] += 1
        except PermissionError:
            continue

    return removed


def parsed_output_path(document_id: str) -> Path:
    return PARSED_DIR / f"{document_id}.json"
