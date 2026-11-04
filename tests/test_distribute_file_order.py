import unittest
from unittest import mock

import distribute_file


class OrderOfChecksTests(unittest.TestCase):
    def run_main(self, prepare_error=None):
        calls = []
        canvas = mock.Mock()
        canvas.check_token.side_effect = lambda: calls.append("canvas token") or "Me"
        drive = mock.Mock()
        drive.check_access.side_effect = lambda: calls.append("drive login") or "me@x"

        def fake_prepare(d, name, pattern, gf):
            calls.append("template")
            if prepare_error:
                raise ValueError(prepare_error)
            return mock.Mock()

        def fake_resolve(*a, **k):
            calls.append("canvas course")
            return "1", "2"

        patches = [
            mock.patch.object(distribute_file.canvas_api, "CanvasClient", return_value=canvas),
            mock.patch.object(distribute_file, "read_canvas_token", return_value="t"),
            mock.patch.object(distribute_file.google_drive, "load_credentials", return_value=object()),
            mock.patch.object(distribute_file.google_drive, "Drive", return_value=drive),
            mock.patch.object(distribute_file.file_distribution, "prepare_distribution", side_effect=fake_prepare),
            mock.patch.object(distribute_file, "resolve_ids", side_effect=fake_resolve),
            mock.patch.object(distribute_file.canvas_api, "fetch_teams", return_value=[]),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        argv = ["--course-id", "1", "--group-set-id", "2", "--folder-name", "F", "--file-name", "X {team}"]
        return distribute_file.main(argv), calls

    def test_tokens_then_template_then_canvas(self):
        code, calls = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["canvas token", "drive login", "template", "canvas course"])

    def test_bad_template_name_stops_before_canvas_groups(self):
        code, calls = self.run_main(prepare_error="No file named 'X'")
        self.assertEqual(code, 1)
        self.assertNotIn("canvas course", calls)


class DeleteOrderTests(unittest.TestCase):
    def test_bad_folder_stops_delete_before_canvas_groups(self):
        import delete_group_file
        calls = []
        canvas = mock.Mock()
        drive = mock.Mock()
        patches = [
            mock.patch.object(distribute_file.canvas_api, "CanvasClient", return_value=canvas),
            mock.patch.object(distribute_file, "read_canvas_token", return_value="t"),
            mock.patch.object(distribute_file.google_drive, "load_credentials", return_value=object()),
            mock.patch.object(distribute_file.google_drive, "Drive", return_value=drive),
            mock.patch.object(
                delete_group_file.file_distribution, "locate_group_folders", side_effect=ValueError("no folder")
            ),
            mock.patch.object(distribute_file, "resolve_ids", side_effect=lambda *a, **k: calls.append("course")),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        argv = ["--course-id", "1", "--group-set-id", "2", "--folder-name", "F", "--file-name", "X {team}"]
        self.assertEqual(delete_group_file.main(argv), 1)
        self.assertEqual(calls, [])
