#!/usr/bin/env python3
"""Copy a template file from Templates/ into every Canvas group's folder.

Usage:
    python distribute_file.py --course "CMPSC 156" --term "Fall 2026" \
        --group-set "Project Groups" --folder-name "20264-CS156-F26" \
        --file-name "Team Agreement, {team}"

Run create_team_folders.py first: this script expects GroupFolders and each
team's folder to already exist. It looks inside GroupFolders/Templates for a
file named exactly like --file-name (e.g. a Google Doc called
"Team Agreement, {team}"); if there is no such file it stops right away,
before reading anything from Canvas. Otherwise it copies that file into each
team's folder, substituting the team name for {team}. A file already in a team's folder with that name is
moved to the trash first, so re-running replaces the copies.

To remove the copies again, run delete_group_file.py with the same options.

See README.md for setup and details.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from typing import Any

import canvas_api
import file_distribution
import google_drive
from canvas_api import Team
from create_team_folders import read_canvas_token, resolve_ids

DEFAULT_CANVAS_URL = "https://ucsb.instructure.com"
DEFAULT_EMAIL_DOMAIN = "ucsb.edu"
DEFAULT_TOKEN_FILE = "CANVAS_API_TOKEN"
DEFAULT_CREDENTIALS_FILE = "credentials.json"
DEFAULT_GOOGLE_TOKEN_FILE = "token.json"


def build_parser(description: str, file_name_help: str) -> argparse.ArgumentParser:
    """The options shared by distribute_file.py and delete_group_file.py."""
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    course = parser.add_mutually_exclusive_group(required=True)
    course.add_argument(
        "--course", metavar="TEXT",
        help="A phrase from the Canvas course name or code, e.g. 'CMPSC 156' (must match exactly one course)",
    )
    course.add_argument("--course-id", help="Canvas course id (from the course URL); alternative to --course")
    parser.add_argument(
        "--term", metavar="TEXT",
        help="With --course: narrow the match to a term, e.g. 'Spring 2026' or 'S26'",
    )
    group_set = parser.add_mutually_exclusive_group(required=True)
    group_set.add_argument("--group-set", metavar="NAME", help="Name of the Canvas group set, e.g. 'Project Groups'")
    group_set.add_argument(
        "--group-set-id",
        help="Canvas group set id (the number after #tab- on the People > Groups page); alternative to --group-set",
    )
    parser.add_argument(
        "--folder-name", required=True,
        help="Name of the existing Google Drive folder containing GroupFolders (as created by create_team_folders.py)",
    )
    parser.add_argument(
        "--group-folder-name", default="GroupFolders",
        help="Name of the folder (under --folder-name) that holds the team folders; "
             "must match what create_team_folders.py used (its --group-folder-name, if given)",
    )
    parser.add_argument("--file-name", required=True, help=file_name_help)
    parser.add_argument("--canvas-url", default=DEFAULT_CANVAS_URL, help="Base URL of your Canvas instance")
    parser.add_argument(
        "--email-domain", default=DEFAULT_EMAIL_DOMAIN,
        help="Appended to each Canvas login id to form the student's Google account email",
    )
    parser.add_argument(
        "--canvas-token-file", default=DEFAULT_TOKEN_FILE,
        help="File containing the Canvas API token (the CANVAS_API_TOKEN environment variable overrides it)",
    )
    parser.add_argument("--credentials", default=DEFAULT_CREDENTIALS_FILE, help="Google OAuth client secrets file")
    parser.add_argument("--token", default=DEFAULT_GOOGLE_TOKEN_FILE, help="Where the Google login token is cached")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Read from Canvas and Drive and report what would change, without changing anything",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug output")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser(
        __doc__.split("\n\n")[0],
        file_name_help="Name of the template file in Templates/, and of the copy in each team's folder; "
                       "{team} is replaced by the team's name, e.g. 'Team Agreement, {team}'",
    )
    return parser.parse_args(argv)


def run(
    args: argparse.Namespace,
    logger_name: str,
    prepare: Callable[[google_drive.Drive, logging.Logger], Any],
    action: Callable[[google_drive.Drive, Any, list[Team], logging.Logger], None],
) -> int:
    """Validate args, connect to Drive and Canvas, then hand off to ``action``.

    ``prepare(drive, log)`` runs first, before anything is read from Canvas, so
    that Drive-side problems (a misspelled folder, a template that isn't there)
    fail fast. Whatever it returns is passed to ``action(drive, prepared, teams, log)``.
    """
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger(logger_name)
    if not args.folder_name.strip():
        raise SystemExit("--folder-name must not be blank.")
    if not args.file_name.strip():
        raise SystemExit("--file-name must not be blank.")
    if args.term and not args.course:
        raise SystemExit("--term only makes sense together with --course.")
    if args.dry_run:
        log.info("DRY RUN: nothing will be created or changed in Google Drive.")

    try:
        log.info("Connecting to Google Drive...")
        creds = google_drive.load_credentials(args.credentials, args.token)
        drive = google_drive.Drive(creds, dry_run=args.dry_run)
        prepared = prepare(drive, log)

        canvas = canvas_api.CanvasClient(args.canvas_url, read_canvas_token(args.canvas_token_file))
        course_id, group_set_id = resolve_ids(canvas, args, log)
        log.info("Reading groups from Canvas...")
        teams = canvas_api.fetch_teams(canvas, course_id, group_set_id, args.email_domain)
        log.info("Found %d group(s).", len(teams))
        if not teams:
            log.warning("The group set has no groups; nothing to do.")
            return 0

        action(drive, prepared, teams, log)
    except (canvas_api.CanvasError, google_drive.DriveError, ValueError) as e:
        log.error("ERROR: %s", e)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    folder_name, group_folder_name = args.folder_name.strip(), args.group_folder_name.strip()

    def prepare(drive: google_drive.Drive, log: logging.Logger) -> file_distribution.TemplateLocation:
        location = file_distribution.locate_template(drive, folder_name, args.file_name, group_folder_name)
        log.info("Found template '%s' in %s/%s/%s.", args.file_name, folder_name, group_folder_name,
                 file_distribution.TEMPLATES_FOLDER_NAME)
        return location

    def action(
        drive: google_drive.Drive,
        location: file_distribution.TemplateLocation,
        teams: list[Team],
        log: logging.Logger,
    ) -> None:
        result = file_distribution.distribute_file(
            drive, teams, folder_name, args.file_name, group_folder_name, location=location
        )
        log.info("")
        log.info("%s: %d team(s)", file_distribution.did(drive, "Copied", "would copy"), len(result.copied))
        if result.replaced:
            log.info(
                "  of which %s an existing file: %d team(s)",
                file_distribution.did(drive, "replaced", "replace"), len(result.replaced),
            )
        if result.missing_team_folders:
            log.warning(
                "No team folder (run create_team_folders.py first): %s",
                ", ".join(result.missing_team_folders),
            )

    return run(args, "distribute_file", prepare, action)


if __name__ == "__main__":
    sys.exit(main())
