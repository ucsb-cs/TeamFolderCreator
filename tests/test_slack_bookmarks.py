import os
import unittest
from unittest.mock import patch

import slack_bookmarks
from slack_bookmarks import (
    BOOKMARK_TITLE, SlackClient, SlackError, channel_name_for_team, read_slack_token,
    sync_bookmark, update_slack_bookmarks,
)


class ChannelNameTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(channel_name_for_team("s26-01"), "team-s26-01")
        self.assertEqual(channel_name_for_team("  Group 2 "), "team-group-2")
        self.assertEqual(channel_name_for_team("O'Brien's Team"), "team-obriens-team")


class ReadTokenTests(unittest.TestCase):
    def test_missing_file_is_an_error(self):
        with patch.dict(os.environ, {"SLACK_TOKEN": ""}):
            with self.assertRaises(SlackError) as ctx:
                read_slack_token("/nonexistent/SLACK_TOKEN")
        self.assertIn("--update-slack-bookmarks needs a Slack token", str(ctx.exception))

    def test_env_var_wins(self):
        with patch.dict(os.environ, {"SLACK_TOKEN": "xoxb-env"}):
            self.assertEqual(read_slack_token("/nonexistent"), "xoxb-env")


class FakeSlack(SlackClient):
    """Replays canned Web API responses and records write calls."""

    def __init__(self, channels, bookmarks=None, private_ok=True, member=True):
        super().__init__("xoxb-fake")
        self.channels = channels  # name -> id
        self.bookmarks = bookmarks or {}  # channel id -> list of bookmark dicts
        self.private_ok = private_ok
        self.member = member
        self.writes = []
        self.calls = []

    def call(self, method, **params):
        self.calls.append(method)
        if method == "auth.test":
            return {"ok": True, "team": "Test Workspace"}
        if method == "conversations.list":
            if "private_channel" in params["types"] and not self.private_ok:
                raise SlackError("scope", "missing_scope")
            return {"ok": True, "channels": [{"name": n, "id": i} for n, i in self.channels.items()]}
        if method == "bookmarks.list":
            if not self.member:
                raise SlackError("not in channel", "not_in_channel")
            return {"ok": True, "bookmarks": list(self.bookmarks.get(params["channel_id"], []))}
        if method == "bookmarks.add":
            self.writes.append(("add", params["channel_id"], params["link"]))
            self.bookmarks.setdefault(params["channel_id"], []).append(
                {"id": "Bk-new", "title": params["title"], "link": params["link"]}
            )
            return {"ok": True}
        if method == "bookmarks.edit":
            self.writes.append(("edit", params["channel_id"], params["link"]))
            for b in self.bookmarks[params["channel_id"]]:
                if b["id"] == params["bookmark_id"]:
                    b["link"] = params["link"]
            return {"ok": True}
        raise AssertionError(f"unexpected method {method}")


TEAMS = [("s26-01", "https://drive/1"), ("s26-02", "https://drive/2"), ("s26-03", "https://drive/3")]


class UpdateBookmarksTests(unittest.TestCase):
    def test_adds_updates_and_skips(self):
        slack = FakeSlack(
            channels={"team-s26-01": "C1", "team-s26-02": "C2", "general": "C0"},
            bookmarks={"C2": [{"id": "Bk2", "title": BOOKMARK_TITLE, "link": "https://drive/old"}]},
        )
        with self.assertLogs(slack_bookmarks.log, level="INFO") as captured:
            update_slack_bookmarks(slack, TEAMS)
        self.assertEqual(slack.writes, [("add", "C1", "https://drive/1"), ("edit", "C2", "https://drive/2")])
        self.assertTrue(any("s26-03: no Slack channel #team-s26-03" in line for line in captured.output))

    def test_second_run_is_a_no_op(self):
        slack = FakeSlack(channels={"team-s26-01": "C1", "team-s26-02": "C2"})
        update_slack_bookmarks(slack, TEAMS)
        slack.writes.clear()
        update_slack_bookmarks(slack, TEAMS)
        self.assertEqual(slack.writes, [])
        # One bookmark per channel, not two.
        self.assertEqual(len(slack.bookmarks["C1"]), 1)

    def test_dry_run_writes_nothing(self):
        slack = FakeSlack(channels={"team-s26-01": "C1"})
        with self.assertLogs(slack_bookmarks.log, level="INFO") as captured:
            update_slack_bookmarks(slack, TEAMS[:1], dry_run=True)
        self.assertEqual(slack.writes, [])
        self.assertTrue(any("would add" in line for line in captured.output))

    def test_other_bookmarks_are_left_alone(self):
        slack = FakeSlack(
            channels={"team-s26-01": "C1"},
            bookmarks={"C1": [{"id": "BkX", "title": "Syllabus", "link": "https://x"}]},
        )
        update_slack_bookmarks(slack, TEAMS[:1])
        self.assertEqual([b["title"] for b in slack.bookmarks["C1"]], ["Syllabus", BOOKMARK_TITLE])

    def test_falls_back_to_public_channels_without_groups_read(self):
        slack = FakeSlack(channels={"team-s26-01": "C1"}, private_ok=False)
        update_slack_bookmarks(slack, TEAMS[:1])
        self.assertEqual(slack.calls.count("conversations.list"), 2)
        self.assertEqual(slack.writes, [("add", "C1", "https://drive/1")])

    def test_not_in_channel_is_a_warning_not_a_crash(self):
        slack = FakeSlack(channels={"team-s26-01": "C1"}, member=False)
        with self.assertLogs(slack_bookmarks.log, level="WARNING") as captured:
            update_slack_bookmarks(slack, TEAMS[:1])
        self.assertTrue(any("not a member of #team-s26-01" in line for line in captured.output))

    def test_bad_token_aborts(self):
        class BadToken(FakeSlack):
            def call(self, method, **params):
                raise SlackError("bad", "invalid_auth")
        with self.assertRaises(SlackError):
            update_slack_bookmarks(BadToken(channels={}), TEAMS)


class SyncBookmarkTests(unittest.TestCase):
    def test_outcomes(self):
        slack = FakeSlack(channels={}, bookmarks={"C1": []})
        self.assertEqual(sync_bookmark(slack, "C1", "https://a", dry_run=False), "added")
        self.assertEqual(sync_bookmark(slack, "C1", "https://a", dry_run=False), "up to date")
        self.assertEqual(sync_bookmark(slack, "C1", "https://b", dry_run=True), "would update")
        self.assertEqual(sync_bookmark(slack, "C1", "https://b", dry_run=False), "updated")


if __name__ == "__main__":
    unittest.main()
