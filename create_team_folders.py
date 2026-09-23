#!/usr/bin/env python3
"""Create (or update) a Google Drive folder per Canvas group.

Usage:
    python create_team_folders.py --course "CMPSC 156" --term "Spring 2026" \
        --group-set "Project Groups" --folder-name "CS156-S26-Team-Folders"

or, with Canvas ids instead of names:

    python create_team_folders.py --course-id 32781 --group-set-id 28352 \
        --folder-name "CS156-S26-Team-Folders"

See README.md for setup and details.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import canvas_api
import google_drive
import slack_bookmarks
import team_folders

DEFAULT_CANVAS_URL = "https://ucsb.instructure.com"
DEFAULT_EMAIL_DOMAIN = "ucsb.edu"
DEFAULT_TOKEN_FILE = "CANVAS_API_TOKEN"
DEFAULT_CREDENTIALS_FILE = "credentials.json"
DEFAULT_GOOGLE_TOKEN_FILE = "token.json"
DEFAULT_SLACK_TOKEN_FILE = "SLACK_TOKEN"


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
        help="Name of an existing Google Drive folder to put GroupFolders under (must exist, exactly one)",
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
        "--update-slack-bookmarks", action="store_true",
        help="Also add a 'Google Drive Folder' bookmark to each team's Slack channel "
             "(#team-<group name>); needs a Slack token (see README)",
    )
    parser.add_argument(
        "--slack-token-file", default=DEFAULT_SLACK_TOKEN_FILE,
        help="File containing the Slack token (the SLACK_TOKEN environment variable overrides it)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Read from Canvas and Drive and report what would change, without changing anything",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug output")
    return parser.parse_args(argv)


def read_canvas_token(path: str) -> str:
    token = os.environ.get("CANVAS_API_TOKEN", "").strip()
    if token:
        return token
    try:
        with open(path) as f:
            token = f.read().strip()
    except FileNotFoundError:
        raise SystemExit(
            f"Canvas API token not found: set the CANVAS_API_TOKEN environment variable "
            f"or put the token in the file '{path}'. See README: 'Set up the Canvas token'."
        )
    if not token:
        raise SystemExit(f"Canvas token file '{path}' is empty.")
    return token


def resolve_ids(canvas: canvas_api.CanvasClient, args: argparse.Namespace, log: logging.Logger) -> tuple[str, str]:
    """Turn --course/--term and --group-set into ids, or pass the given ids through."""
    if args.course:
        course = canvas_api.find_course(canvas, args.course, args.term)
        log.info("Course: %s", canvas_api.describe_course(course))
        course_id = str(course["id"])
    else:
        course_id = args.course_id
    if args.group_set:
        group_set = canvas_api.find_group_set(canvas, course_id, args.group_set)
        log.info("Group set: %s (id %s)", group_set.get("name"), group_set.get("id"))
        group_set_id = str(group_set["id"])
    else:
        group_set_id = args.group_set_id
    return course_id, group_set_id


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("create_team_folders")
    if not args.folder_name.strip():
        raise SystemExit("--folder-name must not be blank.")
    if args.term and not args.course:
        raise SystemExit("--term only makes sense together with --course.")
    if args.dry_run:
        log.info("DRY RUN: nothing will be created or changed in Google Drive.")

    try:
        slack_token = None
        if args.update_slack_bookmarks:  # fail early if the token is missing
            slack_token = slack_bookmarks.read_slack_token(args.slack_token_file)

        canvas = canvas_api.CanvasClient(args.canvas_url, read_canvas_token(args.canvas_token_file))
        course_id, group_set_id = resolve_ids(canvas, args, log)
        log.info("Reading groups from Canvas...")
        teams = canvas_api.fetch_teams(canvas, course_id, group_set_id, args.email_domain)
        students = canvas_api.fetch_student_emails(canvas, course_id, args.email_domain)
        log.info("Found %d group(s); %d student(s) in the course roster.", len(teams), len(students))
        if not teams:
            log.warning("The group set has no groups; nothing to do.")
            return 0

        log.info("Connecting to Google Drive...")
        creds = google_drive.load_credentials(args.credentials, args.token)
        drive = google_drive.Drive(creds, dry_run=args.dry_run)
        result = team_folders.sync_team_folders(drive, teams, students, args.folder_name.strip())

        if slack_token:
            log.info("Updating Slack bookmarks...")
            slack = slack_bookmarks.SlackClient(slack_token)
            slack_bookmarks.update_slack_bookmarks(slack, result.team_folders, dry_run=args.dry_run)
    except (canvas_api.CanvasError, google_drive.DriveError, slack_bookmarks.SlackError, ValueError) as e:
        log.error("ERROR: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
