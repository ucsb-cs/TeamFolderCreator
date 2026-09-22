"""Create/update the Google Drive folder structure for a set of teams.

Layout produced under the parent folder the user names (which must already
exist)::

    <folder name>/
      GroupFolders/                      readable by anyone with the link
        GroupFolders Index               spreadsheet: Group | Folder (link)
        <team name>/                     writable by that team's members
          <team name> Members            spreadsheet: Member | Email
        ...

Every step is idempotent: existing items are found by name and updated in
place, so the script can be re-run whenever the Canvas groups change.
Nothing is ever deleted; folders for groups that no longer exist in Canvas
are reported but left alone.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from googleapiclient.errors import HttpError

from canvas_api import Team
from google_drive import FOLDER_MIME, Drive, folder_url, http_error_reason, spreadsheet_url

log = logging.getLogger(__name__)

GROUP_FOLDERS_NAME = "GroupFolders"
INDEX_SHEET_NAME = "GroupFolders Index"
INDEX_HEADER = ["Group", "Folder"]
MEMBERS_HEADER = ["Member", "Email"]

# Roles that already give at least write access; no upgrade needed.
WRITE_ROLES = {"writer", "owner", "organizer", "fileOrganizer"}


# --- pure helpers (unit tested) ----------------------------------------------


def natural_key(name: str):
    """Sort key so that 'Group 2' comes before 'Group 10'."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def members_sheet_name(team_name: str) -> str:
    return f"{team_name} Members"


def members_sheet_values(team: Team) -> list[list[str]]:
    return [MEMBERS_HEADER] + [[m.name, m.email] for m in team.members]


def index_sheet_values(rows: list[tuple[str, str]]) -> list[list[str]]:
    return [INDEX_HEADER] + [[name, url] for name, url in rows]


def normalize_values(values: list[list[str]]) -> list[list[str]]:
    """Canonical form for comparing sheet contents: strip cells, drop trailing blanks."""
    rows = []
    for row in values:
        cells = [str(cell).strip() for cell in row]
        while cells and cells[-1] == "":
            cells.pop()
        rows.append(cells)
    while rows and rows[-1] == []:
        rows.pop()
    return rows


@dataclass
class PermissionPlan:
    add: list[str] = field(default_factory=list)  # emails to share with
    upgrade: list[tuple[str, str]] = field(default_factory=list)  # (permission id, email)
    remove: list[tuple[str, str]] = field(default_factory=list)  # (permission id, email)
    other: list[str] = field(default_factory=list)  # non-members left untouched


def plan_permission_changes(
    permissions: list[dict], desired_emails: set[str], removable_emails: set[str]
) -> PermissionPlan:
    """Decide which user permissions to add, upgrade or remove on a team folder.

    * Every desired email ends up with at least writer access.
    * A non-member is removed only if they are in ``removable_emails`` (the
      course's students); anyone else, e.g. staff the instructor added by
      hand, is left alone and listed in ``other``.
    * The owner is never touched.
    """
    desired = {e.lower() for e in desired_emails}
    removable = {e.lower() for e in removable_emails}

    by_email: dict[str, dict] = {}
    for perm in permissions:
        email = (perm.get("emailAddress") or "").strip().lower()
        if perm.get("type") == "user" and email:
            by_email[email] = perm

    plan = PermissionPlan()
    for email in sorted(desired):
        perm = by_email.get(email)
        if perm is None:
            plan.add.append(email)
        elif perm.get("role") not in WRITE_ROLES:
            plan.upgrade.append((perm["id"], email))
    for email, perm in sorted(by_email.items()):
        if email in desired or perm.get("role") == "owner":
            continue
        if email in removable:
            plan.remove.append((perm["id"], email))
        else:
            plan.other.append(email)
    return plan


def check_unique_names(teams: list[Team]) -> None:
    seen: dict[str, str] = {}
    for team in teams:
        key = team.name.lower()
        if key in seen:
            raise ValueError(
                f"Two Canvas groups have the same name ('{seen[key]}' and '{team.name}'). "
                "Rename one of them in Canvas so folder names are unique."
            )
        seen[key] = team.name


# --- sync steps --------------------------------------------------------------


def did(drive: Drive, past: str, future: str) -> str:
    """Pick the wording for a log line: what happened, or what a dry run would do."""
    return f"would {future}" if drive.dry_run else past


def ensure_anyone_can_read(drive: Drive, folder_id: str, label: str) -> None:
    for perm in drive.list_permissions(folder_id):
        if perm.get("type") == "anyone":
            log.info("%s: already readable by anyone with the link", label)
            return
    try:
        drive.add_anyone_reader(folder_id)
        log.info("%s: %s readable by anyone with the link", label, did(drive, "made", "make"))
    except HttpError as e:
        log.warning(
            "%s: could not enable 'anyone with the link' (%s). "
            "Your Google Workspace may forbid it; share the folder manually.",
            label, http_error_reason(e),
        )


def sync_permissions(drive: Drive, folder_id: str, team: Team, removable: set[str]) -> None:
    plan = plan_permission_changes(drive.list_permissions(folder_id), team.emails, removable)
    for email in plan.add:
        try:
            drive.add_writer(folder_id, email)
            log.info("  %s: %s with %s", team.name, did(drive, "shared", "share"), email)
        except HttpError as e:
            log.warning("  %s: could not share with %s (%s)", team.name, email, http_error_reason(e))
    for perm_id, email in plan.upgrade:
        drive.set_role(folder_id, perm_id, "writer")
        log.info("  %s: %s %s to writer", team.name, did(drive, "upgraded", "upgrade"), email)
    for perm_id, email in plan.remove:
        try:
            drive.remove_permission(folder_id, perm_id)
            log.info("  %s: %s access for %s (no longer in group)", team.name, did(drive, "removed", "remove"), email)
        except HttpError as e:
            log.warning("  %s: could not remove %s (%s)", team.name, email, http_error_reason(e))
    if plan.other:
        log.info("  %s: also shared with non-students (left as is): %s", team.name, ", ".join(plan.other))
    if not (plan.add or plan.upgrade or plan.remove):
        log.info("  %s: member access up to date", team.name)


def sync_sheet(
    drive: Drive, parent_id: str, name: str, values: list[list[str]], value_input_option: str
) -> str:
    """Create the spreadsheet if missing, then make its contents match ``values``."""
    sheet_id, created = drive.find_or_create_spreadsheet(name, parent_id)
    if created:
        log.info("  %s spreadsheet '%s'", did(drive, "created", "create"), name)
    elif normalize_values(drive.read_values(sheet_id)) == normalize_values(values):
        log.info("  spreadsheet '%s' is up to date", name)
        return sheet_id
    else:
        log.info("  %s spreadsheet '%s'", did(drive, "updating", "update"), name)
    drive.write_values(sheet_id, values, value_input_option)
    return sheet_id


def report_unmatched_folders(drive: Drive, group_folders_id: str, teams: list[Team]) -> list[str]:
    expected = {t.name.lower() for t in teams}
    extra = sorted(
        f["name"] for f in drive.list_children(group_folders_id, FOLDER_MIME)
        if f["name"].lower() not in expected
    )
    if extra:
        log.warning(
            "Folders in %s with no matching Canvas group (left untouched): %s",
            GROUP_FOLDERS_NAME, ", ".join(extra),
        )
    return extra


def sync_team_folders(
    drive: Drive, teams: list[Team], student_emails: set[str], folder_name: str
) -> tuple[str, str]:
    """Create or update everything.  Returns (GroupFolders id, index spreadsheet id)."""
    check_unique_names(teams)
    teams = sorted(teams, key=lambda t: natural_key(t.name))

    top_id = drive.find_existing_folder(folder_name)
    log.info("Found parent folder '%s'", folder_name)

    group_folders_id, created = drive.find_or_create_folder(GROUP_FOLDERS_NAME, top_id)
    log.info("%s folder '%s'", did(drive, "Created", "create") if created else "Found", GROUP_FOLDERS_NAME)
    ensure_anyone_can_read(drive, group_folders_id, GROUP_FOLDERS_NAME)

    # Anyone who is (or was) a student, or is in any group, may be removed from a
    # folder they no longer belong to.  Everyone else is left alone.
    removable = set(student_emails)
    for team in teams:
        removable |= team.emails

    index_rows: list[tuple[str, str]] = []
    for team in teams:
        folder_id, created = drive.find_or_create_folder(team.name, group_folders_id)
        log.info("%s folder '%s'", did(drive, "Created", "create") if created else "Found", team.name)
        sync_permissions(drive, folder_id, team, removable)
        sync_sheet(drive, folder_id, members_sheet_name(team.name), members_sheet_values(team), "RAW")
        index_rows.append((team.name, folder_url(folder_id)))

    # USER_ENTERED so the URLs in column B become clickable links.
    index_id = sync_sheet(drive, group_folders_id, INDEX_SHEET_NAME, index_sheet_values(index_rows), "USER_ENTERED")

    report_unmatched_folders(drive, group_folders_id, teams)

    log.info("")
    log.info("%s folder:  %s", GROUP_FOLDERS_NAME, folder_url(group_folders_id))
    log.info("%s: %s", INDEX_SHEET_NAME, spreadsheet_url(index_id))
    return group_folders_id, index_id
