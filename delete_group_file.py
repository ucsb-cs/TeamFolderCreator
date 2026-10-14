#!/usr/bin/env python3
"""Remove a file distributed by distribute_file.py from every Canvas group's folder.

Usage:
    python delete_group_file.py --course "CMPSC 156" --term "Fall 2026" \
        --group-set "Project Groups" --folder-name "20264-CS156-F26" \
        --file-name "Team Agreement, {team}"

Takes the same options as distribute_file.py. For each team it looks in the
team's folder for a file named like --file-name (with {team} replaced by the
team name) and moves it to the trash. Use it to clean up after distributing
a file with the wrong name or contents. Nothing in Templates/ is touched.

Trashed files can be restored from Google Drive's Trash for 30 days.

See README.md for setup and details.
"""

from __future__ import annotations

import logging
import sys

import file_distribution
import google_drive
from canvas_api import Team
from distribute_file import build_parser, run


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(
        __doc__.split("\n\n")[0],
        file_name_help="Name of the file to remove from each team's folder; "
                       "{team} is replaced by the team's name, e.g. 'Team Agreement, {team}'",
    )
    args = parser.parse_args(argv)

    def action(drive: google_drive.Drive, teams: list[Team], log: logging.Logger) -> None:
        result = file_distribution.delete_group_file(
            drive, teams, args.folder_name.strip(), args.file_name, args.group_folder_name.strip()
        )
        log.info("")
        log.info("%s: %d team(s)", file_distribution.did(drive, "Trashed", "would trash"), len(result.deleted))
        log.info("No such file: %d team(s)", len(result.not_found))
        if result.missing_team_folders:
            log.warning(
                "No team folder (run create_team_folders.py first): %s",
                ", ".join(result.missing_team_folders),
            )

    return run(args, "delete_group_file", action)


if __name__ == "__main__":
    sys.exit(main())
