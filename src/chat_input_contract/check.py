"""In-memory live comparison against an explicitly reviewed baseline."""
from dataclasses import dataclass
from pathlib import Path
from . import capture
from .core import validate_snapshot
from .explain import explain_snapshots
from .io import load_json


@dataclass(frozen=True)
class PreparedCheck:
    baseline: dict
    capture: capture.PreparedCapture
    baseline_path: Path

    @property
    def protected(self):
        return (self.baseline_path, *self.capture.protected)


def prepare_check(manifest_path, baseline_path):
    baseline_path = Path(baseline_path).resolve()
    baseline = load_json(baseline_path)
    validate_snapshot(baseline)
    prepared = capture.prepare_capture(manifest_path)
    return PreparedCheck(baseline, prepared, baseline_path)


def check_prepared(prepared, *, include_content=False):
    candidate = capture.capture_prepared(prepared.capture)
    return explain_snapshots(prepared.baseline, candidate, include_content=include_content)


def check_manifest(manifest_path, baseline_path, *, include_content=False):
    """Return explanatory report v2. Never write or update either input."""
    return check_prepared(prepare_check(manifest_path, baseline_path), include_content=include_content)
