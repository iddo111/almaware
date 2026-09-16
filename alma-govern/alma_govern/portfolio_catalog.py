"""Validation for the ALMA one-place product catalog.

The catalog is deliberately curated rather than inferred from directory names.
Validation prevents stale or indirect evidence from being labelled VERIFIED and
prevents duplicate chains from silently becoming circular.
"""

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Dict, Iterable, List, Optional


VALID_STATUSES = {
    "VERIFIED", "ACTIVE", "BROKEN", "BLOCKED", "UNKNOWN", "PLANNED",
    "SUPERSEDED",
}
VALID_STRENGTHS = {"direct", "indirect", "historical"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


@dataclass(frozen=True)
class CatalogIssue:
    entry_id: str
    field: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {"entry_id": self.entry_id, "field": self.field,
                "message": self.message}


def _parse_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _safe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    path = PurePosixPath(value.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts


def _required_text(entry: Dict[str, Any], fields: Iterable[str],
                   entry_id: str) -> List[CatalogIssue]:
    issues: List[CatalogIssue] = []
    for field in fields:
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            issues.append(CatalogIssue(entry_id, field,
                                       "required non-empty text"))
    return issues


def validate_catalog(payload: Dict[str, Any],
                     workspace_root: Optional[Path] = None) -> List[CatalogIssue]:
    """Validate catalog structure, evidence strength, paths and duplicates."""

    issues: List[CatalogIssue] = []
    if payload.get("schema_version") != 1:
        issues.append(CatalogIssue("<catalog>", "schema_version", "must equal 1"))
    if not _parse_timestamp(payload.get("generated_at")):
        issues.append(CatalogIssue("<catalog>", "generated_at",
                                   "invalid ISO timestamp"))

    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        issues.append(CatalogIssue("<catalog>", "entries",
                                   "must be a non-empty list"))
        return issues

    ids: Dict[str, Dict[str, Any]] = {}
    for index, item in enumerate(entries):
        if not isinstance(item, dict):
            issues.append(CatalogIssue(f"<entry:{index}>", "entry",
                                       "must be an object"))
            continue
        raw_id = item.get("id")
        entry_id = raw_id if isinstance(raw_id, str) else f"<entry:{index}>"
        if not ID_RE.fullmatch(entry_id):
            issues.append(CatalogIssue(entry_id, "id",
                                       "invalid or missing kebab-case ID"))
        elif entry_id in ids:
            issues.append(CatalogIssue(entry_id, "id", "duplicate ID"))
        else:
            ids[entry_id] = item

        issues.extend(_required_text(item, (
            "name", "family", "purpose", "owner", "status",
            "acceptance_gate", "next_action", "safety_boundary",
        ), entry_id))

        status = item.get("status")
        if status not in VALID_STATUSES:
            issues.append(CatalogIssue(entry_id, "status", "unsupported status"))
        if not _parse_timestamp(item.get("status_at")):
            issues.append(CatalogIssue(entry_id, "status_at",
                                       "invalid ISO timestamp"))

        path_value = item.get("path")
        if not _safe_relative_path(path_value):
            issues.append(CatalogIssue(entry_id, "path",
                                       "must be a safe workspace-relative path"))
        elif workspace_root is not None and status != "PLANNED":
            if not (workspace_root / Path(path_value)).exists():
                issues.append(CatalogIssue(entry_id, "path", "path does not exist"))

        domains = item.get("public_benefit_domains")
        if not isinstance(domains, list) or not domains or not all(
                isinstance(value, str) and value.strip() for value in domains):
            issues.append(CatalogIssue(entry_id, "public_benefit_domains",
                                       "must be a non-empty string list"))

        evidence = item.get("evidence")
        direct = False
        if not isinstance(evidence, list) or not evidence:
            issues.append(CatalogIssue(entry_id, "evidence",
                                       "must be a non-empty list"))
        else:
            for ev_index, ev in enumerate(evidence):
                field = f"evidence[{ev_index}]"
                if not isinstance(ev, dict):
                    issues.append(CatalogIssue(entry_id, field,
                                               "must be an object"))
                    continue
                if not isinstance(ev.get("kind"), str) or not ev["kind"].strip():
                    issues.append(CatalogIssue(entry_id, field + ".kind",
                                               "required"))
                if not isinstance(ev.get("value"), str) or not ev["value"].strip():
                    issues.append(CatalogIssue(entry_id, field + ".value",
                                               "required"))
                if not _parse_timestamp(ev.get("observed_at")):
                    issues.append(CatalogIssue(entry_id, field + ".observed_at",
                                               "invalid ISO timestamp"))
                strength = ev.get("strength")
                if strength not in VALID_STRENGTHS:
                    issues.append(CatalogIssue(entry_id, field + ".strength",
                                               "unsupported strength"))
                if strength == "direct":
                    direct = True
        if status == "VERIFIED" and not direct:
            issues.append(CatalogIssue(entry_id, "evidence",
                                       "VERIFIED requires direct evidence"))

        duplicate_of = item.get("duplicate_of")
        if duplicate_of is not None and not isinstance(duplicate_of, str):
            issues.append(CatalogIssue(entry_id, "duplicate_of",
                                       "must be null or an ID"))
        if status == "SUPERSEDED" and not duplicate_of:
            issues.append(CatalogIssue(entry_id, "duplicate_of",
                                       "SUPERSEDED requires a canonical target"))

    for entry_id, entry in ids.items():
        target = entry.get("duplicate_of")
        if target is not None and target not in ids:
            issues.append(CatalogIssue(entry_id, "duplicate_of",
                                       "target ID not found"))

        seen = {entry_id}
        current = target
        while isinstance(current, str) and current in ids:
            if current in seen:
                issues.append(CatalogIssue(entry_id, "duplicate_of",
                                           "duplicate cycle"))
                break
            seen.add(current)
            current = ids[current].get("duplicate_of")

    return issues


def load_and_validate(path: Path,
                      workspace_root: Optional[Path] = None) -> List[CatalogIssue]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return [CatalogIssue("<catalog>", "root", "must be a JSON object")]
    return validate_catalog(payload, workspace_root=workspace_root)
