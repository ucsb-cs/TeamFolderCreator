import unittest

from canvas_api import Team
from google_drive import DOCUMENT_MIME, FOLDER_MIME, SPREADSHEET_MIME
import file_distribution
from file_distribution import delete_group_file, distribute_file, distributed_file_name


class PureHelperTests(unittest.TestCase):
    def test_substitutes_team_placeholder(self):
        self.assertEqual(distributed_file_name("Team Agreement, {team}", "s26-01"), "Team Agreement, s26-01")

    def test_pattern_without_placeholder_is_used_verbatim(self):
        self.assertEqual(distributed_file_name("Agreement", "s26-01"), "Agreement")


class FakeDrive:
    """Minimal in-memory stand-in for google_drive.Drive, just what file_distribution needs."""

    def __init__(self):
        self.items = {}  # id -> dict(name, parent, mime)
        self.trashed = []  # ids passed to trash_file, in order
        self.dry_run = False
        self._n = 0

    def _new_id(self):
        self._n += 1
        return f"id{self._n}"

    def add(self, name, parent, mime):
        new_id = self._new_id()
        self.items[new_id] = {"name": name, "parent": parent, "mime": mime}
        return new_id

    def find_by_name(self, name, parent_id, mime=None):
        return [
            {"id": i, "name": d["name"], "mimeType": d["mime"]}
            for i, d in self.items.items()
            if d["name"] == name and d["parent"] == parent_id and (mime is None or d["mime"] == mime)
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
        if self.dry_run:
            return f"dry-run:copy:{name}"
        return self.add(name, parent_id, self.items[file_id]["mime"])

    def trash_file(self, file_id):
        self.trashed.append(file_id)
        if not self.dry_run:
            del self.items[file_id]

    def find_id(self, name, parent=None):
        return next(i for i, d in self.items.items() if d["name"] == name and (parent is None or d["parent"] == parent))

    def names_in(self, parent):
        return sorted(d["name"] for d in self.items.values() if d["parent"] == parent)


PATTERN = "Agreement, {team}"


class DistributeFileTests(unittest.TestCase):
    def setUp(self):
        self.drive = FakeDrive()
        top = self.drive.add("Top", None, FOLDER_MIME)
        self.group_folders = self.drive.add("GroupFolders", top, FOLDER_MIME)
        self.templates = self.drive.add("Templates", self.group_folders, FOLDER_MIME)
        self.template_doc = self.drive.add(PATTERN, self.templates, DOCUMENT_MIME)
        self.team_a = self.drive.add("Group 2", self.group_folders, FOLDER_MIME)
        self.team_b = self.drive.add("Group 10", self.group_folders, FOLDER_MIME)
        self.teams = [Team("Group 2", 2), Team("Group 10", 10)]

    def test_copies_template_into_each_team_folder(self):
        result = distribute_file(self.drive, self.teams, "Top", PATTERN)
        self.assertEqual(result.copied, ["Group 2", "Group 10"])
        self.assertEqual(result.replaced, [])
        self.assertEqual(result.missing_team_folders, [])
        doc_a = self.drive.find_id("Agreement, Group 2", self.team_a)
        doc_b = self.drive.find_id("Agreement, Group 10", self.team_b)
        self.assertEqual(self.drive.items[doc_a]["mime"], DOCUMENT_MIME)
        self.assertEqual(self.drive.items[doc_b]["mime"], DOCUMENT_MIME)
        self.assertEqual(self.drive.trashed, [])

    def test_template_is_chosen_by_name_among_several(self):
        self.drive.add("Future Questions - {team}", self.templates, DOCUMENT_MIME)
        self.drive.add("P03 - {team}", self.templates, DOCUMENT_MIME)
        result = distribute_file(self.drive, self.teams, "Top", "P03 - {team}")
        self.assertEqual(result.copied, ["Group 2", "Group 10"])
        self.assertEqual(self.drive.names_in(self.team_a), ["P03 - Group 2"])
        self.assertEqual(self.drive.names_in(self.team_b), ["P03 - Group 10"])

    def test_template_may_be_any_file_type(self):
        self.drive.add("Retro {team}", self.templates, SPREADSHEET_MIME)
        distribute_file(self.drive, self.teams, "Top", "Retro {team}")
        sheet = self.drive.find_id("Retro Group 2", self.team_a)
        self.assertEqual(self.drive.items[sheet]["mime"], SPREADSHEET_MIME)

    def test_second_run_replaces_existing_copies(self):
        distribute_file(self.drive, self.teams, "Top", PATTERN)
        old_a = self.drive.find_id("Agreement, Group 2", self.team_a)
        old_b = self.drive.find_id("Agreement, Group 10", self.team_b)
        result = distribute_file(self.drive, self.teams, "Top", PATTERN)
        self.assertEqual(result.copied, ["Group 2", "Group 10"])
        self.assertEqual(result.replaced, ["Group 2", "Group 10"])
        self.assertEqual(self.drive.trashed, [old_a, old_b])
        self.assertEqual(self.drive.names_in(self.team_a), ["Agreement, Group 2"])
        self.assertEqual(self.drive.names_in(self.team_b), ["Agreement, Group 10"])
        self.assertNotIn(old_a, self.drive.items)

    def test_clobber_removes_duplicates_but_leaves_other_files_and_folders(self):
        dup1 = self.drive.add("Agreement, Group 2", self.team_a, DOCUMENT_MIME)
        dup2 = self.drive.add("Agreement, Group 2", self.team_a, DOCUMENT_MIME)
        other = self.drive.add("Group 2 Members", self.team_a, SPREADSHEET_MIME)
        subfolder = self.drive.add("Agreement, Group 2", self.team_a, FOLDER_MIME)
        distribute_file(self.drive, self.teams, "Top", PATTERN)
        self.assertEqual(sorted(self.drive.trashed), sorted([dup1, dup2]))
        self.assertIn(other, self.drive.items)
        self.assertIn(subfolder, self.drive.items)
        docs = [i for i, d in self.drive.items.items()
                if d["parent"] == self.team_a and d["name"] == "Agreement, Group 2" and d["mime"] == DOCUMENT_MIME]
        self.assertEqual(len(docs), 1)

    def test_dry_run_trashes_and_copies_nothing(self):
        distribute_file(self.drive, self.teams, "Top", PATTERN)
        self.drive.dry_run = True
        before = dict(self.drive.items)
        result = distribute_file(self.drive, self.teams, "Top", PATTERN)
        self.assertEqual(result.replaced, ["Group 2", "Group 10"])
        self.assertEqual(self.drive.items, before)

    def test_missing_team_folder_is_skipped_with_warning(self):
        teams = self.teams + [Team("Group 99", 99)]
        with self.assertLogs(file_distribution.log, level="WARNING") as captured:
            result = distribute_file(self.drive, teams, "Top", PATTERN)
        self.assertEqual(result.missing_team_folders, ["Group 99"])
        self.assertTrue(any("Group 99" in line for line in captured.output))

    def test_no_matching_template_is_an_error_listing_what_is_there(self):
        self.drive.add("P03 - {team}", self.templates, DOCUMENT_MIME)
        with self.assertRaises(ValueError) as ctx:
            distribute_file(self.drive, self.teams, "Top", "Nope - {team}")
        self.assertIn("'Nope - {team}'", str(ctx.exception))
        self.assertIn("P03 - {team}", str(ctx.exception))
        self.assertEqual(self.drive.names_in(self.team_a), [])

    def test_empty_templates_folder_is_an_error(self):
        del self.drive.items[self.template_doc]
        with self.assertRaises(ValueError):
            distribute_file(self.drive, self.teams, "Top", PATTERN)

    def test_two_templates_with_the_same_name_is_an_error(self):
        self.drive.add(PATTERN, self.templates, DOCUMENT_MIME)
        with self.assertRaises(ValueError):
            distribute_file(self.drive, self.teams, "Top", PATTERN)

    def test_missing_templates_folder_is_an_error(self):
        drive = FakeDrive()
        top = drive.add("Top", None, FOLDER_MIME)
        drive.add("GroupFolders", top, FOLDER_MIME)
        with self.assertRaises(ValueError):
            distribute_file(drive, self.teams, "Top", PATTERN)

    def test_custom_group_folder_name(self):
        drive = FakeDrive()
        top = drive.add("Top", None, FOLDER_MIME)
        renamed_group_folders = drive.add("CS156-F26-GroupFolders", top, FOLDER_MIME)
        templates = drive.add("Templates", renamed_group_folders, FOLDER_MIME)
        drive.add(PATTERN, templates, DOCUMENT_MIME)
        team_folder = drive.add("Group 2", renamed_group_folders, FOLDER_MIME)
        result = distribute_file(
            drive, [Team("Group 2", 2)], "Top", PATTERN, group_folder_name="CS156-F26-GroupFolders",
        )
        self.assertEqual(result.copied, ["Group 2"])
        self.assertTrue(drive.find_by_name("Agreement, Group 2", team_folder, DOCUMENT_MIME))


class DeleteGroupFileTests(unittest.TestCase):
    def setUp(self):
        self.drive = FakeDrive()
        top = self.drive.add("Top", None, FOLDER_MIME)
        self.group_folders = self.drive.add("GroupFolders", top, FOLDER_MIME)
        self.templates = self.drive.add("Templates", self.group_folders, FOLDER_MIME)
        self.template_doc = self.drive.add(PATTERN, self.templates, DOCUMENT_MIME)
        self.team_a = self.drive.add("Group 2", self.group_folders, FOLDER_MIME)
        self.team_b = self.drive.add("Group 10", self.group_folders, FOLDER_MIME)
        self.teams = [Team("Group 2", 2), Team("Group 10", 10)]
        distribute_file(self.drive, self.teams, "Top", PATTERN)

    def test_trashes_the_file_from_each_team_folder(self):
        result = delete_group_file(self.drive, self.teams, "Top", PATTERN)
        self.assertEqual(result.deleted, ["Group 2", "Group 10"])
        self.assertEqual(result.not_found, [])
        self.assertEqual(self.drive.names_in(self.team_a), [])
        self.assertEqual(self.drive.names_in(self.team_b), [])
        self.assertIn(self.template_doc, self.drive.items)  # Templates/ is untouched

    def test_leaves_other_files_alone(self):
        other = self.drive.add("Group 2 Members", self.team_a, SPREADSHEET_MIME)
        delete_group_file(self.drive, self.teams, "Top", PATTERN)
        self.assertIn(other, self.drive.items)

    def test_reports_teams_without_the_file(self):
        delete_group_file(self.drive, self.teams, "Top", PATTERN)
        result = delete_group_file(self.drive, self.teams, "Top", PATTERN)
        self.assertEqual(result.deleted, [])
        self.assertEqual(result.not_found, ["Group 2", "Group 10"])

    def test_does_not_need_the_template_to_exist(self):
        del self.drive.items[self.template_doc]
        result = delete_group_file(self.drive, self.teams, "Top", PATTERN)
        self.assertEqual(result.deleted, ["Group 2", "Group 10"])

    def test_dry_run_trashes_nothing(self):
        self.drive.dry_run = True
        before = dict(self.drive.items)
        result = delete_group_file(self.drive, self.teams, "Top", PATTERN)
        self.assertEqual(result.deleted, ["Group 2", "Group 10"])
        self.assertEqual(self.drive.items, before)

    def test_missing_team_folder_is_skipped_with_warning(self):
        teams = self.teams + [Team("Group 99", 99)]
        with self.assertLogs(file_distribution.log, level="WARNING"):
            result = delete_group_file(self.drive, teams, "Top", PATTERN)
        self.assertEqual(result.missing_team_folders, ["Group 99"])


if __name__ == "__main__":
    unittest.main()
