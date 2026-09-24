#!/usr/bin/env python3
"""Copy a template Google Doc from Templates/ into every Canvas group's folder.

Usage:
    python distribute_file.py --course "CMPSC 156" --term "Fall 2026" \
        --group-set "Project Groups" --folder-name "20264-CS156-F26" \
        --file-name "Team Agreement, {team}"

Run create_team_folders.py first: this script expects GroupFolders and each
team's folder to already exist. It looks for a folder named Templates inside
GroupFolders, expects exactly one Google Doc in it, and copies that doc into
each team's folder, substituting the team name for {team} in --file-name.

See README.md for setup and details.
"""

from __future__ import annotations

import argparse
import logging
import sys

import canvas_api
import file_distribution
import google_drive
from create_team_folders import read_canvas_token, resolve_ids

DEFAULT_CANVAS_URL = "https://ucsb.instructure.com"
DEFAULT_EMAIL_DOMAIN = "ucsb.edu"
DEFAULT_TOKEN_FILE = "CANVAS_API_TOKEN"
DEFAULT_CREDENTIALS_FILE = "credentials.json"
DEFAULT_GOOGLE_TOKEN_FILE = "token.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
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
        "--file-name", required=True,
        help="Name for the copied file in each team's folder; {team} is replaced by the team's name, "
             "e.g. 'Team Agreement, {team}'",
    )
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("distribute_file")
    if not args.folder_name.strip():
        raise SystemExit("--folder-name must not be blank.")
    if not args.file_name.strip():
        raise SystemExit("--file-name must not be blank.")
    if args.term and not args.course:
        raise SystemExit("--term only makes sense together with --course.")
    if args.dry_run:
        log.info("DRY RUN: nothing will be created or changed in Google Drive.")

    try:
        canvas = canvas_api.CanvasClient(args.canvas_url, read_canvas_token(args.canvas_token_file))
        course_id, group_set_id = resolve_ids(canvas, args, log)
        log.info("Reading groups from Canvas...")
        teams = canvas_api.fetch_teams(canvas, course_id, group_set_id, args.email_domain)
        log.info("Found %d group(s).", len(teams))
        if not teams:
            log.warning("The group set has no groups; nothing to do.")
            return 0

        log.info("Connecting to Google Drive...")
        creds = google_drive.load_credentials(args.credentials, args.token)
        drive = google_drive.Drive(creds, dry_run=args.dry_run)
        result = file_distribution.distribute_file(drive, teams, args.folder_name.strip(), args.file_name)

        log.info("")
        log.info("%s: %d team(s)", file_distribution.did(drive, "Copied", "would copy"), len(result.copied))
        log.info("Already present: %d team(s)", len(result.already_present))
        if result.missing_team_folders:
            log.warning(
                "No team folder (run create_team_folders.py first): %s",
                ", ".join(result.missing_team_folders),
            )
    except (canvas_api.CanvasError, google_drive.DriveError, ValueError) as e:
        log.error("ERROR: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
