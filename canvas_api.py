"""Read a group set (and its members) from Canvas.

Only read-only Canvas endpoints are used:

* GET /api/v1/courses                         (your courses, to look one up by name)
* GET /api/v1/courses/:id/group_categories    (a course's group sets, to look one up by name)
* GET /api/v1/group_categories/:id            (the group set)
* GET /api/v1/group_categories/:id/groups     (the groups in the set)
* GET /api/v1/groups/:id/users                (the members of one group)
* GET /api/v1/courses/:id/users               (the student roster)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

TEST_STUDENT_NAME = "Test Student"


class CanvasError(Exception):
    """Raised when Canvas returns an error we can explain to the user."""


@dataclass(frozen=True)
class Member:
    name: str
    email: str


@dataclass
class Team:
    name: str
    canvas_id: int
    members: list[Member] = field(default_factory=list)

    @property
    def emails(self) -> set[str]:
        return {m.email for m in self.members}


class CanvasClient:
    """Thin wrapper over the Canvas REST API that handles auth and pagination."""

    def __init__(self, base_url: str, token: str, timeout: int = 60):
        self.api = base_url.rstrip("/") + "/api/v1"
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def get(self, path: str, params: dict | None = None):
        """GET a single (non-paginated) resource and return its JSON."""
        response = self.session.get(
            f"{self.api}/{path.lstrip('/')}", params=params, timeout=self.timeout
        )
        self._check(response)
        return response.json()

    def get_all(self, path: str, params: dict | None = None) -> list:
        """GET every page of a paginated list resource."""
        params = dict(params or {})
        params.setdefault("per_page", 100)
        url = f"{self.api}/{path.lstrip('/')}"
        items: list = []
        while url:
            response = self.session.get(url, params=params, timeout=self.timeout)
            self._check(response)
            items.extend(response.json())
            url = response.links.get("next", {}).get("url")
            params = None  # the "next" URL already carries the query string
        return items

    @staticmethod
    def _check(response: requests.Response) -> None:
        if response.status_code == 401:
            raise CanvasError(
                "Canvas rejected the API token (HTTP 401). "
                "The token may be expired or revoked; see README for how to create a new one. "
                f"Canvas said: {response.text[:200]}"
            )
        if response.status_code == 404:
            raise CanvasError(
                f"Canvas returned 404 Not Found for {response.url}. "
                "Check the course id and group set id."
            )
        response.raise_for_status()

    # --- endpoints -------------------------------------------------------

    def get_courses(self) -> list[dict]:
        """Every course the token's owner is enrolled in, with term info."""
        return self.get_all("courses", {"include[]": "term"})

    def get_group_sets(self, course_id: str | int) -> list[dict]:
        return self.get_all(f"courses/{course_id}/group_categories")

    def get_group_set(self, group_set_id: str | int) -> dict:
        return self.get(f"group_categories/{group_set_id}")

    def get_groups(self, group_set_id: str | int) -> list[dict]:
        return self.get_all(f"group_categories/{group_set_id}/groups")

    def get_group_members(self, group_id: str | int) -> list[dict]:
        return self.get_all(f"groups/{group_id}/users")

    def get_course_students(self, course_id: str | int) -> list[dict]:
        """Everyone with a student enrollment, including concluded/inactive ones.

        Used to decide whose folder access it is safe to remove.
        """
        params = {
            "enrollment_type[]": "student",
            "enrollment_state[]": ["active", "invited", "completed", "inactive"],
        }
        return self.get_all(f"courses/{course_id}/users", params)


# --- looking things up by name -----------------------------------------------


def _squash(text: str | None) -> str:
    """Lower-case and collapse runs of whitespace, for forgiving comparisons."""
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _contains_phrase(haystack: str | None, phrase: str) -> bool:
    """True if ``phrase`` appears in ``haystack`` as whole words (case/space insensitive).

    'CMPSC 156' matches 'CMPSC 156 (section 1100) - ...' but not 'CMPSC 1560',
    and 'CMPSC 8' does not match 'CMPSCW 8'.
    """
    pattern = r"(?<!\w)" + re.escape(_squash(phrase)) + r"(?!\w)"
    return re.search(pattern, _squash(haystack)) is not None


def describe_course(course: dict) -> str:
    term = (course.get("term") or {}).get("name") or "no term"
    return f"{course.get('id')}: {course.get('name')}  [{course.get('course_code')}; {term}]"


def find_course(client: CanvasClient, course_text: str, term_text: str | None = None) -> dict:
    """Find exactly one of the user's courses by a phrase from its name or course code.

    ``term_text`` (e.g. "Spring 2026" or "S26") narrows the match; it is
    compared against the term name, the course name and the course code.
    Raises CanvasError, listing the candidates, unless exactly one course matches.
    """
    courses = client.get_courses()
    matches = [
        c for c in courses
        if _contains_phrase(c.get("name"), course_text) or _contains_phrase(c.get("course_code"), course_text)
    ]
    if term_text:
        matches = [
            c for c in matches
            if any(
                _contains_phrase(field_value, term_text)
                for field_value in ((c.get("term") or {}).get("name"), c.get("name"), c.get("course_code"))
            )
        ]
    if len(matches) == 1:
        return matches[0]
    wanted = f"'{course_text}'" + (f" in term '{term_text}'" if term_text else "")
    if not matches:
        raise CanvasError(
            f"No course matching {wanted} among the {len(courses)} course(s) this token can see. "
            "Try a phrase from the course name or code as Canvas shows it (e.g. 'CMPSC 156'), "
            "or pass --course-id."
        )
    listing = "\n  ".join(describe_course(c) for c in matches)
    raise CanvasError(
        f"{len(matches)} courses match {wanted}; add --term or use --course-id to pick one:\n  {listing}"
    )


def find_group_set(client: CanvasClient, course_id: str | int, name: str) -> dict:
    """Find the group set in the course whose name equals ``name`` (case/space insensitive)."""
    group_sets = client.get_group_sets(course_id)
    matches = [g for g in group_sets if _squash(g.get("name")) == _squash(name)]
    if len(matches) == 1:
        return matches[0]
    available = ", ".join(f"'{g.get('name')}' (id {g.get('id')})" for g in group_sets) or "none"
    if not matches:
        raise CanvasError(
            f"Course {course_id} has no group set named '{name}'. Group sets in this course: {available}."
        )
    raise CanvasError(
        f"Course {course_id} has {len(matches)} group sets named '{name}'; "
        f"use --group-set-id to pick one. Group sets: {available}."
    )


# --- turning Canvas data into teams ------------------------------------------


def user_email(user: dict, email_domain: str) -> str | None:
    """Best-effort Google account email for a Canvas user.

    Canvas only returns ``login_id`` for group members, so the email is
    ``login_id@<email_domain>`` (unless the login id is already an address).
    Falls back to the ``email`` field when present.  Returns None if neither
    is available (e.g. the Canvas "Test Student").
    """
    login_id = (user.get("login_id") or "").strip()
    if login_id:
        email = login_id if "@" in login_id else f"{login_id}@{email_domain}"
        return email.lower()
    email = (user.get("email") or "").strip()
    return email.lower() or None


def fetch_teams(
    client: CanvasClient, course_id: str | int, group_set_id: str | int, email_domain: str
) -> list[Team]:
    """Return every group in the group set, with its members, sorted by name."""
    group_set = client.get_group_set(group_set_id)
    if str(group_set.get("course_id")) != str(course_id):
        raise CanvasError(
            f"Group set {group_set_id} ('{group_set.get('name')}') belongs to course "
            f"{group_set.get('course_id')}, not course {course_id}."
        )
    log.info("Group set %s: '%s' (course %s)", group_set_id, group_set.get("name"), course_id)

    teams: list[Team] = []
    for group in client.get_groups(group_set_id):
        name = (group.get("name") or "").strip()
        if not name:
            log.warning("Skipping Canvas group id %s because it has no name.", group.get("id"))
            continue
        members: list[Member] = []
        for user in client.get_group_members(group["id"]):
            email = user_email(user, email_domain)
            if not email or user.get("name") == TEST_STUDENT_NAME:
                log.warning("  %s: no email for member %r; skipping.", name, user.get("name"))
                continue
            display_name = user.get("name") or user.get("sortable_name") or email
            members.append(Member(name=display_name.strip(), email=email))
        members.sort(key=lambda m: (m.name.lower(), m.email))
        teams.append(Team(name=name, canvas_id=group["id"], members=members))
        log.info("  %s: %d member(s)", name, len(members))
    teams.sort(key=lambda t: t.name.lower())
    return teams


def fetch_student_emails(client: CanvasClient, course_id: str | int, email_domain: str) -> set[str]:
    """Emails of everyone who has (or had) a student enrollment in the course."""
    emails: set[str] = set()
    for user in client.get_course_students(course_id):
        if user.get("name") == TEST_STUDENT_NAME:
            continue
        email = user_email(user, email_domain)
        if email:
            emails.add(email)
    return emails
