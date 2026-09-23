import unittest
from unittest.mock import MagicMock, call

from canvas_api import Member, Team
from google_drive import Drive, DriveError
import team_folders
from team_folders import (
    check_unique_names,
    index_sheet_values,
    members_sheet_values,
    natural_key,
    normalize_values,
    plan_permission_changes,
    sync_sheet,
    sync_team_folders,
)


class PureHelperTests(unittest.TestCase):
    def test_natural_sort(self):
        names = ["Group 10", "Group 2", "group 1", "Alpha"]
        self.assertEqual(sorted(names, key=natural_key), ["Alpha", "group 1", "Group 2", "Group 10"])

    def test_members_sheet_values(self):
        team = Team("t", 1, [Member("A B", "ab@x.edu"), Member("C D", "cd@x.edu")])
        self.assertEqual(
            members_sheet_values(team),
            [["Member", "Email"], ["A B", "ab@x.edu"], ["C D", "cd@x.edu"]],
        )

    def test_index_sheet_values(self):
        self.assertEqual(
            index_sheet_values([("t1", "http://a"), ("t2", "http://b")]),
            [["Group", "Folder"], ["t1", "http://a"], ["t2", "http://b"]],
        )

    def test_normalize_values_ignores_trailing_blanks_and_whitespace(self):
        self.assertEqual(
            normalize_values([["Member ", "Email"], ["A", "a@x", ""], [], ["", ""]]),
            [["Member", "Email"], ["A", "a@x"]],
        )
        self.assertEqual(normalize_values([]), [])

    def test_duplicate_names_rejected_case_insensitively(self):
        with self.assertRaises(ValueError):
            check_unique_names([Team("Team A", 1), Team("team a", 2)])
        check_unique_names([Team("Team A", 1), Team("Team B", 2)])  # no error


def perm(pid, email, role, ptype="user"):
    return {"id": pid, "emailAddress": email, "role": role, "type": ptype}


class PermissionPlanTests(unittest.TestCase):
    def test_new_folder_adds_all_members(self):
        plan = plan_permission_changes([perm("o", "prof@x.edu", "owner")], {"a@x.edu", "b@x.edu"}, set())
        self.assertEqual(plan.add, ["a@x.edu", "b@x.edu"])
        self.assertEqual((plan.upgrade, plan.remove, plan.other), ([], [], []))

    def test_existing_writer_not_re_added(self):
        plan = plan_permission_changes([perm("p1", "A@X.EDU", "writer")], {"a@x.edu"}, set())
        self.assertEqual(plan.add, [])

    def test_reader_member_is_upgraded(self):
        plan = plan_permission_changes([perm("p1", "a@x.edu", "reader")], {"a@x.edu"}, set())
        self.assertEqual(plan.upgrade, [("p1", "a@x.edu")])

    def test_departed_student_is_removed_but_staff_is_kept(self):
        perms = [
            perm("o", "prof@x.edu", "owner"),
            perm("p1", "a@x.edu", "writer"),
            perm("p2", "gone@x.edu", "writer"),
            perm("p3", "ta@x.edu", "writer"),
            perm("any", None, "reader", ptype="anyone"),
        ]
        plan = plan_permission_changes(perms, {"a@x.edu"}, {"a@x.edu", "gone@x.edu"})
        self.assertEqual(plan.add, [])
        self.assertEqual(plan.remove, [("p2", "gone@x.edu")])
        self.assertEqual(plan.other, ["ta@x.edu"])

    def test_owner_who_is_a_member_is_left_alone(self):
        plan = plan_permission_changes([perm("o", "prof@x.edu", "owner")], {"prof@x.edu"}, {"prof@x.edu"})
        self.assertEqual((plan.add, plan.upgrade, plan.remove), ([], [], []))


class FakeDrive:
    """In-memory stand-in for google_drive.Drive."""

    def __init__(self):
        self.items = {}  # id -> dict(name, parent, mime)
        self.perms = {}  # id -> list of permission dicts
        self.values = {}  # spreadsheet id -> values
        self.writes = []
        self.dry_run = False
        self._n = 0

    def _new_id(self):
        self._n += 1
        return f"id{self._n}"

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

    def find_or_create(self, name, parent_id, mime):
        found = self.find_by_name(name, parent_id, mime)
        if found:
            return found[0]["id"], False
        new_id = self._new_id()
        self.items[new_id] = {"name": name, "parent": parent_id, "mime": mime}
        self.perms[new_id] = [perm("owner", "prof@x.edu", "owner")]
        return new_id, True

    def find_or_create_folder(self, name, parent_id=None):
        return self.find_or_create(name, parent_id, team_folders.FOLDER_MIME)

    def find_existing_folder(self, name, parent_id=None):
        # Same rules as google_drive.Drive.find_existing_folder.
        found = self.find_by_name(name, parent_id, team_folders.FOLDER_MIME)
        if len(found) != 1:
            raise DriveError(f"{len(found)} folders named '{name}'")
        return found[0]["id"]

    def find_or_create_spreadsheet(self, name, parent_id):
        return self.find_or_create(name, parent_id, "sheet")

    def list_permissions(self, fid):
        return list(self.perms[fid])

    def add_anyone_reader(self, fid):
        self.perms[fid].append(perm(self._new_id(), None, "reader", "anyone"))

    def add_writer(self, fid, email):
        self.perms[fid].append(perm(self._new_id(), email, "writer"))

    def set_role(self, fid, pid, role):
        for p in self.perms[fid]:
            if p["id"] == pid:
                p["role"] = role

    def remove_permission(self, fid, pid):
        self.perms[fid] = [p for p in self.perms[fid] if p["id"] != pid]

    def read_values(self, sid, cell_range="A:B"):
        return self.values.get(sid, [])

    def write_values(self, sid, values, value_input_option="RAW"):
        self.values[sid] = values
        self.writes.append((sid, value_input_option))

    # convenience for assertions
    def emails_with_role(self, fid, role):
        return {p["emailAddress"] for p in self.perms[fid] if p["role"] == role and p["type"] == "user"}

    def find_id(self, name):
        return next(i for i, d in self.items.items() if d["name"] == name)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.drive = FakeDrive()
        self.drive.find_or_create_folder("Top")  # the parent folder must already exist
        self.teams = [
            Team("Group 2", 2, [Member("Bo Bee", "bo@x.edu")]),
            Team("Group 10", 10, [Member("Al Ay", "al@x.edu"), Member("Cy See", "cy@x.edu")]),
        ]
        self.students = {"al@x.edu", "bo@x.edu", "cy@x.edu", "dee@x.edu"}

    def test_first_run_creates_everything(self):
        result = sync_team_folders(self.drive, self.teams, self.students, "Top")
        gf_id, index_id = result.group_folders_id, result.index_id
        d = self.drive
        top = d.find_id("Top")
        self.assertEqual(d.items[gf_id]["parent"], top)
        self.assertTrue(any(p["type"] == "anyone" and p["role"] == "reader" for p in d.perms[gf_id]))

        g2, g10 = d.find_id("Group 2"), d.find_id("Group 10")
        self.assertEqual(d.items[g2]["parent"], gf_id)
        self.assertEqual(d.emails_with_role(g2, "writer"), {"bo@x.edu"})
        self.assertEqual(d.emails_with_role(g10, "writer"), {"al@x.edu", "cy@x.edu"})

        members_sheet = d.find_id("Group 10 Members")
        self.assertEqual(d.items[members_sheet]["parent"], g10)
        self.assertEqual(d.values[members_sheet], [["Member", "Email"], ["Al Ay", "al@x.edu"], ["Cy See", "cy@x.edu"]])

        self.assertEqual(d.items[index_id]["parent"], gf_id)
        self.assertEqual(
            d.values[index_id],
            [["Group", "Folder"],
             ["Group 2", f"https://drive.google.com/drive/folders/{g2}"],
             ["Group 10", f"https://drive.google.com/drive/folders/{g10}"]],
        )
        self.assertIn((index_id, "USER_ENTERED"), d.writes)
        self.assertEqual(
            result.team_folders,
            [("Group 2", f"https://drive.google.com/drive/folders/{g2}"),
             ("Group 10", f"https://drive.google.com/drive/folders/{g10}")],
        )

    def test_missing_parent_folder_is_an_error(self):
        with self.assertRaises(DriveError):
            sync_team_folders(self.drive, self.teams, self.students, "Does Not Exist")
        self.assertEqual(len(self.drive.items), 1)  # nothing was created

    def test_duplicate_parent_folder_is_an_error(self):
        self.drive.items["dup"] = {"name": "Top", "parent": None, "mime": team_folders.FOLDER_MIME}
        with self.assertRaises(DriveError):
            sync_team_folders(self.drive, self.teams, self.students, "Top")

    def test_second_run_changes_nothing(self):
        sync_team_folders(self.drive, self.teams, self.students, "Top")
        before_items = dict(self.drive.items)
        before_perms = {k: list(v) for k, v in self.drive.perms.items()}
        self.drive.writes.clear()
        sync_team_folders(self.drive, self.teams, self.students, "Top")
        self.assertEqual(self.drive.items, before_items)
        self.assertEqual(self.drive.perms, before_perms)
        self.assertEqual(self.drive.writes, [])

    def test_membership_changes_are_applied(self):
        sync_team_folders(self.drive, self.teams, self.students, "Top")
        # Cy moves from Group 10 to Group 2; Dee joins Group 10; Group 3 is new.
        new_teams = [
            Team("Group 2", 2, [Member("Bo Bee", "bo@x.edu"), Member("Cy See", "cy@x.edu")]),
            Team("Group 10", 10, [Member("Al Ay", "al@x.edu"), Member("Dee Dee", "dee@x.edu")]),
            Team("Group 3", 3, []),
        ]
        sync_team_folders(self.drive, new_teams, self.students, "Top")
        d = self.drive
        g2, g10 = d.find_id("Group 2"), d.find_id("Group 10")
        self.assertEqual(d.emails_with_role(g2, "writer"), {"bo@x.edu", "cy@x.edu"})
        self.assertEqual(d.emails_with_role(g10, "writer"), {"al@x.edu", "dee@x.edu"})
        self.assertEqual(d.values[d.find_id("Group 10 Members")], [["Member", "Email"], ["Al Ay", "al@x.edu"], ["Dee Dee", "dee@x.edu"]])
        self.assertEqual(d.values[d.find_id("Group 3 Members")], [["Member", "Email"]])
        self.assertEqual([row[0] for row in d.values[d.find_id("GroupFolders Index")]], ["Group", "Group 2", "Group 3", "Group 10"])
        # Only one of each thing exists.
        self.assertEqual(len(d.find_by_name("GroupFolders", d.find_id("Top"), team_folders.FOLDER_MIME)), 1)
        self.assertEqual(len(d.find_by_name("Group 2", d.find_id("GroupFolders"), team_folders.FOLDER_MIME)), 1)

    def test_staff_added_by_hand_are_kept(self):
        sync_team_folders(self.drive, self.teams, self.students, "Top")
        g2 = self.drive.find_id("Group 2")
        self.drive.add_writer(g2, "ta@x.edu")
        sync_team_folders(self.drive, self.teams, self.students, "Top")
        self.assertIn("ta@x.edu", self.drive.emails_with_role(g2, "writer"))

    def test_unmatched_folders_are_reported_not_deleted(self):
        gf_id = sync_team_folders(self.drive, self.teams, self.students, "Top").group_folders_id
        self.drive.find_or_create_folder("Old Group", gf_id)
        with self.assertLogs(team_folders.log, level="WARNING") as captured:
            sync_team_folders(self.drive, self.teams[:1], self.students, "Top")
        self.assertTrue(any("Old Group" in line and "Group 10" in line for line in captured.output))
        self.assertIsNotNone(self.drive.find_id("Old Group"))


class SyncSheetTests(unittest.TestCase):
    def test_sheet_not_rewritten_when_only_formatting_differs(self):
        drive = FakeDrive()
        parent, _ = drive.find_or_create_folder("p")
        sid = sync_sheet(drive, parent, "S", [["Member", "Email"], ["A", "a@x"]], "RAW")
        drive.values[sid] = [["Member ", "Email"], ["A", "a@x", ""], []]  # as Sheets might return it
        drive.writes.clear()
        sync_sheet(drive, parent, "S", [["Member", "Email"], ["A", "a@x"]], "RAW")
        self.assertEqual(drive.writes, [])


class DryRunTests(unittest.TestCase):
    def test_dry_run_drive_makes_no_api_calls_for_writes(self):
        drive = Drive.__new__(Drive)
        drive.drive = MagicMock()
        drive.sheets = MagicMock()
        drive.dry_run = True
        drive.drive.files().list().execute.return_value = {"files": []}
        fid, created = drive.find_or_create_folder("X")  # find_by_name reads via the (mocked) API
        self.assertTrue(created)
        self.assertTrue(Drive.is_placeholder(fid))
        drive.add_writer(fid, "a@x.edu")
        drive.add_anyone_reader(fid)
        drive.write_values(fid, [["a"]])
        self.assertEqual(drive.list_permissions(fid), [])
        self.assertEqual(drive.read_values(fid), [])
        drive.drive.files().create.assert_not_called()
        drive.drive.permissions().create.assert_not_called()
        drive.sheets.spreadsheets().values().update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
