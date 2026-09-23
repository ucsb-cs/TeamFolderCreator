"""Optional: add a "Google Drive Folder" bookmark to each team's Slack channel.

For a team named ``s26-01`` the channel is ``#team-s26-01``.  The bookmark is
added once; on later runs it is left alone if its link is unchanged, or
edited if the folder link changed.  Teams without a channel are reported and
skipped.

Slack Web API methods used (and the scopes they need):

* auth.test            (none)              identify the workspace
* conversations.list   (channels:read)     find #team-... channels
                       (groups:read)       optional, to see private channels too
* bookmarks.list       (bookmarks:read)    see whether the bookmark already exists
* bookmarks.add/edit   (bookmarks:write)   create or update it
"""

from __future__ import annotations

import logging
import os
import re
import time

import requests

log = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api"
BOOKMARK_TITLE = "Google Drive Folder"
CHANNEL_PREFIX = "team-"
RETRIES = 3

AUTH_ERRORS = {"invalid_auth", "not_authed", "token_revoked", "token_expired", "account_inactive"}


class SlackError(Exception):
    def __init__(self, message: str, error: str = ""):
        super().__init__(message)
        self.error = error


def read_slack_token(path: str) -> str:
    """The SLACK_TOKEN environment variable, or else the contents of ``path``."""
    token = os.environ.get("SLACK_TOKEN", "").strip()
    if token:
        return token
    try:
        with open(path) as f:
            token = f.read().strip()
    except FileNotFoundError:
        raise SlackError(
            f"--update-slack-bookmarks needs a Slack token: set the SLACK_TOKEN environment "
            f"variable or put the token in the file '{path}'. See README: 'Slack bookmarks'."
        )
    if not token:
        raise SlackError(f"Slack token file '{path}' is empty.")
    return token


def channel_name_for_team(team_name: str) -> str:
    """'s26-01' -> 'team-s26-01'; 'Group 2' -> 'team-group-2' (Slack channel name rules)."""
    name = re.sub(r"\s+", "-", team_name.strip().lower())
    name = re.sub(r"[^a-z0-9_-]", "", name)
    return CHANNEL_PREFIX + name


class SlackClient:
    def __init__(self, token: str, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def call(self, method: str, **params) -> dict:
        """POST a Web API method; return the JSON on ok, raise SlackError otherwise."""
        for attempt in range(RETRIES + 1):
            response = self.session.post(f"{SLACK_API}/{method}", data=params, timeout=self.timeout)
            if response.status_code == 429 and attempt < RETRIES:
                wait = int(response.headers.get("Retry-After", "2"))
                log.info("Slack rate limit hit; waiting %ds", wait)
                time.sleep(wait)
                continue
            response.raise_for_status()
            data = response.json()
            if data.get("ok"):
                return data
            error = data.get("error", "unknown_error")
            if error == "ratelimited" and attempt < RETRIES:
                time.sleep(2)
                continue
            raise SlackError(self._explain(method, error, data), error)
        raise SlackError(f"Slack API {method}: still rate limited after {RETRIES} retries", "ratelimited")

    @staticmethod
    def _explain(method: str, error: str, data: dict) -> str:
        if error in AUTH_ERRORS:
            return (
                f"Slack rejected the token ({error}). Check the SLACK_TOKEN file, or reinstall "
                "the app to the workspace to get a new token."
            )
        if error == "missing_scope":
            return (
                f"The Slack token lacks the '{data.get('needed')}' scope needed by {method}. "
                "Add it under OAuth & Permissions in the Slack app settings and reinstall the app."
            )
        return f"Slack API {method} failed: {error}"

    def call_pages(self, method: str, key: str, **params) -> list:
        items: list = []
        cursor = None
        while True:
            data = self.call(method, **params, **({"cursor": cursor} if cursor else {}))
            items.extend(data.get(key, []))
            cursor = (data.get("response_metadata") or {}).get("next_cursor") or None
            if not cursor:
                return items

    # --- methods we use --------------------------------------------------

    def workspace_name(self) -> str:
        return self.call("auth.test").get("team", "?")

    def list_channels(self) -> dict[str, str]:
        """Map channel name -> id for all non-archived channels the token can see."""
        common = {"exclude_archived": "true", "limit": 200}
        try:
            channels = self.call_pages(
                "conversations.list", "channels", types="public_channel,private_channel", **common
            )
        except SlackError as e:
            if e.error != "missing_scope":
                raise
            log.info("Slack token cannot list private channels (no groups:read scope); using public channels only.")
            channels = self.call_pages("conversations.list", "channels", types="public_channel", **common)
        return {c["name"]: c["id"] for c in channels if c.get("name")}

    def list_bookmarks(self, channel_id: str) -> list[dict]:
        return self.call("bookmarks.list", channel_id=channel_id).get("bookmarks", [])

    def add_bookmark(self, channel_id: str, title: str, link: str) -> None:
        self.call("bookmarks.add", channel_id=channel_id, title=title, type="link", link=link)

    def edit_bookmark(self, channel_id: str, bookmark_id: str, link: str) -> None:
        self.call("bookmarks.edit", channel_id=channel_id, bookmark_id=bookmark_id, link=link)


def sync_bookmark(client: SlackClient, channel_id: str, link: str, dry_run: bool) -> str:
    """Ensure the channel has one BOOKMARK_TITLE bookmark pointing at ``link``.

    Returns what happened: 'up to date', 'added' or 'updated' (prefixed with
    'would ' in a dry run).
    """
    existing = [b for b in client.list_bookmarks(channel_id) if b.get("title") == BOOKMARK_TITLE]
    if existing:
        if existing[0].get("link") == link:
            return "up to date"
        if dry_run:
            return "would update"
        client.edit_bookmark(channel_id, existing[0]["id"], link)
        return "updated"
    if dry_run:
        return "would add"
    client.add_bookmark(channel_id, BOOKMARK_TITLE, link)
    return "added"


def update_slack_bookmarks(
    client: SlackClient, team_links: list[tuple[str, str]], dry_run: bool = False
) -> None:
    """For each (team name, folder url), bookmark the folder in #team-<name>."""
    log.info("")
    log.info("Slack workspace: %s", client.workspace_name())
    channels = client.list_channels()
    for team_name, link in team_links:
        channel_name = channel_name_for_team(team_name)
        channel_id = channels.get(channel_name)
        if not channel_id:
            log.warning("  %s: no Slack channel #%s; skipping", team_name, channel_name)
            continue
        try:
            outcome = sync_bookmark(client, channel_id, link, dry_run)
            log.info("  %s: bookmark in #%s %s", team_name, channel_name, outcome)
        except SlackError as e:
            if e.error in AUTH_ERRORS or e.error == "missing_scope":
                raise
            if e.error == "not_in_channel":
                log.warning(
                    "  %s: the Slack token's account is not a member of #%s; "
                    "invite it (/invite) and re-run", team_name, channel_name,
                )
            else:
                log.warning("  %s: #%s: %s", team_name, channel_name, e)
