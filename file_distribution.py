"""Copy a template Google Doc from Templates/ into every team's folder.

Expects the layout that ``create_team_folders.py`` already produced::

    <folder name>/
      GroupFolders/
        Templates/
          <the template doc>          <- exactly one Google Doc
        <team name>/                  <- must already exist
        ...

For each team, the template is copied into that team's folder under a name
derived from ``--file-name``, with ``{team}`` replaced by the team's name.
Re-running is safe: if a file with the target name already exists in a
team's folder, it is left alone (never overwritten, never duplicated).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from canvas_api import Team
from google_drive import DOCUMENT_MIME, FOLDER_MIME, Drive, folder_url

log = logging.getLogger(__name__)

TEMPLATES_FOLDER_NAME = "Templates"
TEAM_PLACEHOLDER = "{team}"


def distributed_file_name(file_name_pattern: str, team_name: str) -> str:
    return file_name_pattern.replace(TEAM_PLACEHOLDER, team_name)


@dataclass
class DistributionResult:
    copied: list[str] = field(default_factory=list)  # team names the file was copied for
    already_present: list[str] = field(default_factory=list)  # team names that already had it
    missing_team_folders: list[str] = field(default_factory=list)  # team names with no folder yet


def did(drive: Drive, past: str, future: str) -> str:
    """Pick the wording for a log line: what happened, or what a dry run would do."""
    return f"would {future}" if drive.dry_run else past


def distribute_file(
    drive: Drive, teams: list[Team], folder_name: str, file_name_pattern: str
) -> DistributionResult:
    """Copy the Templates/ document into each team's folder, skipping teams already done."""
    top_id = drive.find_existing_folder(folder_name)
    group_folders_id = drive.find_existing_folder("GroupFolders", top_id)
    templates_id = drive.find_existing_folder(TEMPLATES_FOLDER_NAME, group_folders_id)

    template_matches = drive.list_children(templates_id, DOCUMENT_MIME)
    if not template_matches:
        raise ValueError(
            f"No Google Doc found in the '{TEMPLATES_FOLDER_NAME}' folder. "
            f"Put the document to distribute there, then re-run."
        )
    if len(template_matches) > 1:
        names = ", ".join(f"'{f['name']}'" for f in template_matches)
        raise ValueError(
            f"Found {len(template_matches)} Google Docs in the '{TEMPLATES_FOLDER_NAME}' folder ({names}); "
            "expected exactly one. Remove the extras so exactly one remains, then re-run."
        )
    template_id = template_matches[0]["id"]

    result = DistributionResult()
    for team in teams:
        dest_name = distributed_file_name(file_name_pattern, team.name)
        team_folder_matches = drive.find_by_name(team.name, group_folders_id, FOLDER_MIME)
        if not team_folder_matches:
            log.warning(
                "  %s: no team folder found; run create_team_folders.py first. Skipping.", team.name
            )
            result.missing_team_folders.append(team.name)
            continue
        if len(team_folder_matches) > 1:
            raise ValueError(
                f"Found {len(team_folder_matches)} folders named '{team.name}' inside GroupFolders; "
                "expected exactly one. Rename or trash the extras so exactly one remains, then re-run."
            )
        team_folder_id = team_folder_matches[0]["id"]

        existing = drive.find_by_name(dest_name, team_folder_id, DOCUMENT_MIME)
        if existing:
            log.info("  %s: '%s' already exists", team.name, dest_name)
            result.already_present.append(team.name)
            continue

        drive.copy_file(template_id, dest_name, team_folder_id)
        log.info("  %s: %s '%s' into %s", team.name, did(drive, "copied", "copy"), dest_name, folder_url(team_folder_id))
        result.copied.append(team.name)

    return result
