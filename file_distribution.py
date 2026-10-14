"""Copy a template file from Templates/ into every team's folder, or remove it again.

Expects the layout that ``create_team_folders.py`` already produced::

    <folder name>/
      GroupFolders/
        Templates/
          <file named exactly like --file-name>   <- e.g. "P03 - {team}"
          ...                                     <- other templates are fine
        <team name>/                              <- must already exist
        ...

``distribute_file`` finds the template in ``Templates`` by name: the file
whose name is exactly the ``--file-name`` pattern, placeholder and all (so a
pattern of ``P03 - {team}`` looks for a file called ``P03 - {team}``). It is
then copied into each team's folder with ``{team}`` replaced by the team's
name. Any file already in the team's folder with that name is trashed first,
so re-running replaces the copies rather than duplicating them.

``delete_group_file`` is the undo: it trashes the file with that name from
every team's folder (for cleaning up after a copy with the wrong name or
contents). It does not need the template to exist.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from canvas_api import Team
from google_drive import FOLDER_MIME, Drive, folder_url

log = logging.getLogger(__name__)

TEMPLATES_FOLDER_NAME = "Templates"
TEAM_PLACEHOLDER = "{team}"


def distributed_file_name(file_name_pattern: str, team_name: str) -> str:
    return file_name_pattern.replace(TEAM_PLACEHOLDER, team_name)


@dataclass
class GroupFolders:
    """Where the team folders live, resolved once up front."""
    group_folders_id: str
    group_folder_name: str


@dataclass
class TemplateLocation(GroupFolders):
    """``GroupFolders`` plus the id of the template to copy."""
    template_id: str


@dataclass
class DistributionResult:
    copied: list[str] = field(default_factory=list)  # team names the file was copied for
    replaced: list[str] = field(default_factory=list)  # subset of copied: an old copy was trashed first
    missing_team_folders: list[str] = field(default_factory=list)  # team names with no folder yet


@dataclass
class DeletionResult:
    deleted: list[str] = field(default_factory=list)  # team names a file was trashed for
    not_found: list[str] = field(default_factory=list)  # team names that had no such file
    missing_team_folders: list[str] = field(default_factory=list)  # team names with no folder yet


def did(drive: Drive, past: str, future: str) -> str:
    """Pick the wording for a log line: what happened, or what a dry run would do."""
    return f"would {future}" if drive.dry_run else past


def find_files_named(drive: Drive, name: str, parent_id: str) -> list[dict]:
    """Non-folder items with exactly this name directly inside ``parent_id``."""
    return [f for f in drive.find_by_name(name, parent_id) if f.get("mimeType") != FOLDER_MIME]


def find_template(drive: Drive, group_folders_id: str, file_name_pattern: str) -> str:
    """Id of the one file in Templates/ named exactly ``file_name_pattern``."""
    templates_id = drive.find_existing_folder(TEMPLATES_FOLDER_NAME, group_folders_id)
    matches = find_files_named(drive, file_name_pattern, templates_id)
    if not matches:
        others = sorted(f["name"] for f in drive.list_children(templates_id) if f.get("mimeType") != FOLDER_MIME)
        hint = f" The files there are: {', '.join(repr(n) for n in others)}." if others else " The folder is empty."
        raise ValueError(
            f"No file named '{file_name_pattern}' found in the '{TEMPLATES_FOLDER_NAME}' folder.{hint} "
            f"Name the template exactly like --file-name (with the literal {TEAM_PLACEHOLDER}), then re-run."
        )
    if len(matches) > 1:
        raise ValueError(
            f"Found {len(matches)} files named '{file_name_pattern}' in the '{TEMPLATES_FOLDER_NAME}' folder; "
            "expected exactly one. Rename or trash the extras so exactly one remains, then re-run."
        )
    return matches[0]["id"]


def locate_group_folders(drive: Drive, folder_name: str, group_folder_name: str = "GroupFolders") -> GroupFolders:
    """Resolve <folder_name>/<group_folder_name>; errors if either is missing or ambiguous."""
    top_id = drive.find_existing_folder(folder_name)
    group_folders_id = drive.find_existing_folder(group_folder_name, top_id)
    return GroupFolders(group_folders_id, group_folder_name)


def locate_template(
    drive: Drive, folder_name: str, file_name_pattern: str, group_folder_name: str = "GroupFolders"
) -> TemplateLocation:
    """Resolve the group folders and the template, so a bad name fails before anything else runs."""
    where = locate_group_folders(drive, folder_name, group_folder_name)
    template_id = find_template(drive, where.group_folders_id, file_name_pattern)
    return TemplateLocation(where.group_folders_id, where.group_folder_name, template_id)


def find_team_folder(drive: Drive, team: Team, group_folders_id: str, group_folder_name: str) -> str | None:
    """Id of the team's folder, or None (after a warning) if it doesn't exist yet."""
    matches = drive.find_by_name(team.name, group_folders_id, FOLDER_MIME)
    if not matches:
        log.warning("  %s: no team folder found; run create_team_folders.py first. Skipping.", team.name)
        return None
    if len(matches) > 1:
        raise ValueError(
            f"Found {len(matches)} folders named '{team.name}' inside {group_folder_name}; "
            "expected exactly one. Rename or trash the extras so exactly one remains, then re-run."
        )
    return matches[0]["id"]


def distribute_file(
    drive: Drive,
    teams: list[Team],
    folder_name: str,
    file_name_pattern: str,
    group_folder_name: str = "GroupFolders",
    location: TemplateLocation | None = None,
) -> DistributionResult:
    """Copy Templates/<file_name_pattern> into each team's folder, replacing any existing copy.

    Pass ``location`` (from ``locate_template``) to skip re-resolving the folders and template.
    """
    if location is None:
        location = locate_template(drive, folder_name, file_name_pattern, group_folder_name)
    group_folders_id, template_id = location.group_folders_id, location.template_id

    result = DistributionResult()
    for team in teams:
        team_folder_id = find_team_folder(drive, team, group_folders_id, group_folder_name)
        if team_folder_id is None:
            result.missing_team_folders.append(team.name)
            continue

        dest_name = distributed_file_name(file_name_pattern, team.name)
        existing = find_files_named(drive, dest_name, team_folder_id)
        for old in existing:
            drive.trash_file(old["id"])
            log.info("  %s: %s existing '%s'", team.name, did(drive, "trashed", "trash"), dest_name)
        if existing:
            result.replaced.append(team.name)

        drive.copy_file(template_id, dest_name, team_folder_id)
        log.info("  %s: %s '%s' into %s", team.name, did(drive, "copied", "copy"), dest_name, folder_url(team_folder_id))
        result.copied.append(team.name)

    return result


def delete_group_file(
    drive: Drive,
    teams: list[Team],
    folder_name: str,
    file_name_pattern: str,
    group_folder_name: str = "GroupFolders",
    location: GroupFolders | None = None,
) -> DeletionResult:
    """Trash the file named by ``file_name_pattern`` (with {team} substituted) from each team's folder."""
    if location is None:
        location = locate_group_folders(drive, folder_name, group_folder_name)
    group_folders_id = location.group_folders_id

    result = DeletionResult()
    for team in teams:
        team_folder_id = find_team_folder(drive, team, group_folders_id, group_folder_name)
        if team_folder_id is None:
            result.missing_team_folders.append(team.name)
            continue

        name = distributed_file_name(file_name_pattern, team.name)
        existing = find_files_named(drive, name, team_folder_id)
        if not existing:
            log.info("  %s: no file named '%s'", team.name, name)
            result.not_found.append(team.name)
            continue
        for old in existing:
            drive.trash_file(old["id"])
        log.info(
            "  %s: %s '%s' (%d file%s)",
            team.name, did(drive, "trashed", "trash"), name, len(existing), "" if len(existing) == 1 else "s",
        )
        result.deleted.append(team.name)

    return result
