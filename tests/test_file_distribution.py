import unittest

from canvas_api import Team
from google_drive import DOCUMENT_MIME, FOLDER_MIME
import file_distribution
from file_distribution import distribute_file, distributed_file_name


class PureHelperTests(unittest.TestCase):
    def test_substitutes_team_placeholder(self):
        self.assertEqual(distributed_file_name("Team Agreement, {team}", "s26-01"), "Team Agreement, s26-01")

    def test_pattern_without_placeholder_is_used_verbatim(self):
        self.assertEqual(distributed_file_name("Agreement", "s26-01"), "Agreement")


class FakeDrive:
    """Minimal in-memory stand-in for google_drive.Drive, just what distribute_file needs."""

    def __init__(self):
        self.items = {}  # id -> dict(name, parent, mime)
        self.dry_run = False
        self._n = 0

    def _new_id(self):
        self._n += 1
        return f"id{self._n}"

    def add(self, name, parent, mime):
        new_id = self._new_id()
        self.items[new_id] = {"name": name, "parent": parent, "mime": mime}
        return new_id

    def find_by_name(self, name, parent_id, mime):
        return [
            {"id": i, "name": d["name"], "mimeType": d["mime"]}
            for i, d in self.items.items()
            if d["name"] == name and d["parent"] == parent_id and d["mime"] == mime
        ]

    def list_children(self, parent_id, mime=None):
        return [
            {"id": i, "name": d["name"], "mimeType": d["mime"]}
            for i, d in self.items.items()
            if d["parent"] == parent_id and (mime is None or d["mime"] == mime)
        ]

    def find_existing_folder(self, name, parent_id=None):
        found = self.find_by_name(name, parent_id, FOLDER_MIME)
        if len(found) != 1:
            raise ValueError(f"{len(found)} folders named '{name}'")
        return found[0]["id"]

    def copy_file(self, file_id, name, parent_id):
        return self.add(name, parent_id, DOCUMENT_MIME)

    def find_id(self, name, parent=None):
        return next(i for i, d in self.items.items() if d["name"] == name and (parent is None or d["parent"] == parent))


class DistributeFileTests(unittest.TestCase):
    def setUp(self):
        self.drive = FakeDrive()
        top = self.drive.add("Top", None, FOLDER_MIME)
        self.group_folders = self.drive.add("GroupFolders", top, FOLDER_MIME)
        templates = self.drive.add("Templates", self.group_folders, FOLDER_MIME)
        self.template_doc = self.drive.add("Team Agreement Template", templates, DOCUMENT_MIME)
        self.team_a = self.drive.add("Group 2", self.group_folders, FOLDER_MIME)
        self.team_b = self.drive.add("Group 10", self.group_folders, FOLDER_MIME)
        self.teams = [Team("Group 2", 2), Team("Group 10", 10)]

    def test_copies_template_into_each_team_folder(self):
        result = distribute_file(self.drive, self.teams, "Top", "Agreement, {team}")
        self.assertEqual(result.copied, ["Group 2", "Group 10"])
        self.assertEqual(result.already_present, [])
        self.assertEqual(result.missing_team_folders, [])
        doc_a = self.drive.find_id("Agreement, Group 2", self.team_a)
        doc_b = self.drive.find_id("Agreement, Group 10", self.team_b)
        self.assertEqual(self.drive.items[doc_a]["mime"], DOCUMENT_MIME)
        self.assertEqual(self.drive.items[doc_b]["mime"], DOCUMENT_MIME)

    def test_second_run_does_not_duplicate(self):
        distribute_file(self.drive, self.teams, "Top", "Agreement, {team}")
        before = dict(self.drive.items)
        result = distribute_file(self.drive, self.teams, "Top", "Agreement, {team}")
        self.assertEqual(result.copied, [])
        self.assertEqual(result.already_present, ["Group 2", "Group 10"])
        self.assertEqual(self.drive.items, before)

    def test_missing_team_folder_is_skipped_with_warning(self):
        teams = self.teams + [Team("Group 99", 99)]
        with self.assertLogs(file_distribution.log, level="WARNING") as captured:
            result = distribute_file(self.drive, teams, "Top", "Agreement, {team}")
        self.assertEqual(result.missing_team_folders, ["Group 99"])
        self.assertTrue(any("Group 99" in line for line in captured.output))

    def test_no_template_doc_is_an_error(self):
        drive = FakeDrive()
        top = drive.add("Top", None, FOLDER_MIME)
        group_folders = drive.add("GroupFolders", top, FOLDER_MIME)
        drive.add("Templates", group_folders, FOLDER_MIME)
        with self.assertRaises(ValueError):
            distribute_file(drive, self.teams, "Top", "Agreement, {team}")

    def test_two_template_docs_is_an_error(self):
        templates = self.drive.find_id("Templates", self.group_folders)
        self.drive.add("Another Doc", templates, DOCUMENT_MIME)
        with self.assertRaises(ValueError):
            distribute_file(self.drive, self.teams, "Top", "Agreement, {team}")

    def test_missing_templates_folder_is_an_error(self):
        drive = FakeDrive()
        top = drive.add("Top", None, FOLDER_MIME)
        drive.add("GroupFolders", top, FOLDER_MIME)
        with self.assertRaises(ValueError):
            distribute_file(drive, self.teams, "Top", "Agreement, {team}")


if __name__ == "__main__":
    unittest.main()
