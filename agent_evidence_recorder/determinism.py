"""Verify that tracked public samples match deterministic regeneration."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from agent_evidence_recorder.sample import generate_public_samples


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sample_files(samples_dir: Path) -> dict[str, Path]:
    if not samples_dir.is_dir():
        return {}
    return {
        path.relative_to(samples_dir).as_posix(): path
        for path in sorted(samples_dir.rglob("*"))
        if path.is_file()
    }


def verify_sample_determinism(root: Path | None = None) -> dict:
    root = (root or Path.cwd()).resolve()
    samples_dir = root / "samples"
    current_files = sample_files(samples_dir)

    temp_root = Path(tempfile.mkdtemp(prefix="agent_evidence-recorder-determinism-"))
    try:
        generate_public_samples(temp_root)
        regenerated_files = sample_files(temp_root / "samples")

        current_names = set(current_files)
        regenerated_names = set(regenerated_files)
        missing_from_current = sorted(regenerated_names - current_names)
        unexpected_in_current = sorted(current_names - regenerated_names)
        shared_names = sorted(current_names & regenerated_names)
        content_mismatches = [
            name
            for name in shared_names
            if sha256_file(current_files[name]) != sha256_file(regenerated_files[name])
        ]

        checks = [
            {
                "detail": "samples",
                "name": "samples_directory_present",
                "passed": samples_dir.is_dir(),
            },
            {
                "detail": json.dumps(missing_from_current, sort_keys=True),
                "name": "no_missing_regenerated_files",
                "passed": not missing_from_current,
            },
            {
                "detail": json.dumps(unexpected_in_current, sort_keys=True),
                "name": "no_unexpected_tracked_sample_files",
                "passed": not unexpected_in_current,
            },
            {
                "detail": json.dumps(content_mismatches, sort_keys=True),
                "name": "tracked_sample_content_matches_regeneration",
                "passed": not content_mismatches,
            },
        ]
        return {
            "checks": checks,
            "current_file_count": len(current_files),
            "passed": all(check["passed"] for check in checks),
            "regenerated_file_count": len(regenerated_files),
            "schema_version": "agent_evidence_recorder.sample_determinism.v0",
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
