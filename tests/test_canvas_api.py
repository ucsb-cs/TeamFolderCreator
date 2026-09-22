import unittest
from unittest.mock import MagicMock

import canvas_api
from canvas_api import (
    CanvasError, Member, fetch_student_emails, fetch_teams, find_course, find_group_set, user_email,
)


class UserEmailTests(unittest.TestCase):
    def test_login_id_gets_domain(self):
        self.assertEqual(user_email({"login_id": "cgaucho"}, "ucsb.edu"), "cgaucho@ucsb.edu")

    def test_login_id_that_is_already_an_address(self):
        self.assertEqual(user_email({"login_id": "CG@Example.EDU"}, "ucsb.edu"), "cg@example.edu")

    def test_falls_back_to_email_field(self):
        self.assertEqual(user_email({"email": "cg@umail.ucsb.edu"}, "ucsb.edu"), "cg@umail.ucsb.edu")

    def test_none_when_nothing_available(self):
        self.assertIsNone(user_email({"name": "Test Student"}, "ucsb.edu"))
        self.assertIsNone(user_email({"login_id": "  ", "email": ""}, "ucsb.edu"))


def fake_client(groups, members_by_group, students=(), group_set=None):
    client = MagicMock(spec=canvas_api.CanvasClient)
    client.get_group_set.return_value = group_set or {"id": 7, "name": "Teams", "course_id": 42}
    client.get_groups.return_value = groups
    client.get_group_members.side_effect = lambda gid: members_by_group[gid]
    client.get_course_students.return_value = list(students)
    return client


class FetchTeamsTests(unittest.TestCase):
    def test_builds_sorted_teams_with_members(self):
        client = fake_client(
            groups=[{"id": 2, "name": " team-b "}, {"id": 1, "name": "team-a"}],
            members_by_group={
                1: [{"name": "Zed Zulu", "login_id": "zzulu"}, {"name": "Amy Alpha", "login_id": "aalpha"}],
                2: [],
            },
        )
        teams = fetch_teams(client, "42", "7", "ucsb.edu")
        self.assertEqual([t.name for t in teams], ["team-a", "team-b"])
        self.assertEqual(
            teams[0].members,
            [Member("Amy Alpha", "aalpha@ucsb.edu"), Member("Zed Zulu", "zzulu@ucsb.edu")],
        )
        self.assertEqual(teams[1].members, [])
        self.assertEqual(teams[0].canvas_id, 1)

    def test_skips_members_without_email_and_test_student(self):
        client = fake_client(
            groups=[{"id": 1, "name": "g"}],
            members_by_group={1: [{"name": "Test Student"}, {"name": "Real", "login_id": "real"}]},
        )
        teams = fetch_teams(client, 42, 7, "ucsb.edu")
        self.assertEqual(teams[0].emails, {"real@ucsb.edu"})

    def test_rejects_group_set_from_another_course(self):
        client = fake_client(groups=[], members_by_group={}, group_set={"id": 7, "course_id": 99})
        with self.assertRaises(CanvasError):
            fetch_teams(client, 42, 7, "ucsb.edu")


class FetchStudentEmailsTests(unittest.TestCase):
    def test_collects_emails_and_ignores_test_student(self):
        client = fake_client(
            groups=[], members_by_group={},
            students=[{"name": "A", "login_id": "a"}, {"name": "Test Student"}, {"name": "B", "email": "b@x.edu"}],
        )
        self.assertEqual(fetch_student_emails(client, 42, "ucsb.edu"), {"a@ucsb.edu", "b@x.edu"})


if __name__ == "__main__":
    unittest.main()


COURSES = [
    {"id": 32781, "name": "CMPSC 156 - ADV APP PROGRAM - Spring 2026",
     "course_code": "CMPSC 156 S26", "term": {"name": "Spring 2026"}},
    {"id": 40000, "name": "CMPSC 156 - ADV APP PROGRAM - Fall 2026",
     "course_code": "CMPSC 156 F26", "term": {"name": "Fall 2026"}},
    {"id": 11722, "name": "CMPSCW   8 - INTRO TO COMP SCI - Fall 2022",
     "course_code": "CMPSCW   8 - F22", "term": {"name": "Default Term"}},
    {"id": 50000, "name": "CMPSC 1560 - IMAGINARY", "course_code": "CMPSC 1560", "term": None},
]


class FindCourseTests(unittest.TestCase):
    def client(self):
        client = MagicMock(spec=canvas_api.CanvasClient)
        client.get_courses.return_value = COURSES
        return client

    def test_course_and_term(self):
        self.assertEqual(find_course(self.client(), "cmpsc  156", "spring 2026")["id"], 32781)

    def test_term_can_be_short_code_from_course_code(self):
        self.assertEqual(find_course(self.client(), "CMPSC 156", "F26")["id"], 40000)

    def test_term_in_name_when_canvas_term_is_default(self):
        self.assertEqual(find_course(self.client(), "CMPSCW 8", "Fall 2022")["id"], 11722)

    def test_whole_word_matching(self):
        # 'CMPSC 156' must not match 'CMPSC 1560'; 'CMPSC 8' must not match 'CMPSCW 8'.
        self.assertEqual(find_course(self.client(), "CMPSC 1560")["id"], 50000)
        with self.assertRaises(CanvasError):
            find_course(self.client(), "CMPSC 8")

    def test_ambiguous_lists_candidates(self):
        with self.assertRaises(CanvasError) as ctx:
            find_course(self.client(), "CMPSC 156")
        self.assertIn("2 courses match", str(ctx.exception))
        self.assertIn("32781", str(ctx.exception))
        self.assertIn("40000", str(ctx.exception))

    def test_no_match(self):
        with self.assertRaises(CanvasError) as ctx:
            find_course(self.client(), "CMPSC 156", "Winter 2031")
        self.assertIn("No course matching", str(ctx.exception))


class FindGroupSetTests(unittest.TestCase):
    def client(self):
        client = MagicMock(spec=canvas_api.CanvasClient)
        client.get_group_sets.return_value = [
            {"id": 28347, "name": "Section Groups"}, {"id": 28352, "name": "Project Groups"},
        ]
        return client

    def test_exact_name_case_insensitive(self):
        self.assertEqual(find_group_set(self.client(), 32781, " project groups ")["id"], 28352)

    def test_missing_name_lists_available(self):
        with self.assertRaises(CanvasError) as ctx:
            find_group_set(self.client(), 32781, "Teams")
        self.assertIn("'Section Groups' (id 28347)", str(ctx.exception))
        self.assertIn("'Project Groups' (id 28352)", str(ctx.exception))
