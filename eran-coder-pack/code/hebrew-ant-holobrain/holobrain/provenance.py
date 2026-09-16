from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class SourceKind(StrEnum):
    OPERATOR_OWNED_VOICE = "operator_owned_voice"
    OPERATOR_OWNED_CAMERA = "operator_owned_camera"
    LICENSED_LOCAL_MEDIA = "licensed_local_media"
    OPEN_ML_DATASET = "open_ml_dataset"
    ISAAC_SIM_SYNTHETIC = "isaac_sim_synthetic"
    YOUTUBE_OR_PODCAST = "youtube_or_podcast"
    HEDER_OR_MINOR_VOICE = "heder_or_minor_voice"
    GOOGLE_STREET_VIEW = "google_street_view"


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    kind: SourceKind
    local_path: Path | None
    rights_evidence: str
    written_permission: bool = False
    guardian_consent: bool = False
    privacy_review_passed: bool = False


def validate_training_source(record: SourceRecord) -> None:
    if record.kind is SourceKind.GOOGLE_STREET_VIEW:
        raise ValueError("Google Street View content is forbidden for model training")
    if record.kind is SourceKind.YOUTUBE_OR_PODCAST:
        if record.local_path is None or not record.written_permission:
            raise ValueError(
                "YouTube/podcast training requires a local file and explicit rights"
            )
    if record.kind is SourceKind.HEDER_OR_MINOR_VOICE:
        if not (
            record.written_permission
            and record.guardian_consent
            and record.privacy_review_passed
        ):
            raise ValueError(
                "minor voice requires written permission, guardian consent, and privacy review"
            )
    if not record.rights_evidence.strip():
        raise ValueError("rights evidence is required")
    if record.local_path is not None and not record.local_path.is_file():
        raise ValueError("approved source path does not exist")
