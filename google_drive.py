"""Google Drive / Sheets access: OAuth login plus the handful of calls we need.

Every write method honours ``dry_run``: it does nothing and, where an id is
expected, returns a placeholder id instead of touching Drive.
"""

from __future__ import annotations

import logging
import os

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

log = logging.getLogger(__name__)

# One scope covers both the Drive API and the Sheets API.
SCOPES = ["https://www.googleapis.com/auth/drive"]

FOLDER_MIME = "application/vnd.google-apps.folder"
SPREADSHEET_MIME = "application/vnd.google-apps.spreadsheet"
DOCUMENT_MIME = "application/vnd.google-apps.document"

# googleapiclient retries HTTP 5xx, 429 and rate-limit 403s with backoff.
RETRIES = 5

DRY_RUN_PREFIX = "dry-run:"


class DriveError(Exception):
    """Raised for Drive problems we can explain to the user."""


def load_credentials(credentials_path: str, token_path: str) -> Credentials:
    """Return valid OAuth credentials, running the browser login flow if needed.

    ``credentials_path`` is the OAuth client file downloaded from Google Cloud.
    ``token_path`` caches the user's access/refresh token between runs.
    """
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if creds and not creds.valid and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            log.warning("Stored Google token could not be refreshed (%s); logging in again.", e)
            creds = None

    if not creds or not creds.valid:
        if not os.path.exists(credentials_path):
            raise DriveError(
                f"Google OAuth client file '{credentials_path}' not found. "
                "See README: 'Set up Google credentials'."
            )
        flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)

    with open(token_path, "w") as f:
        f.write(creds.to_json())
    os.chmod(token_path, 0o600)
    return creds


def folder_url(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"


def spreadsheet_url(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"


def http_error_reason(error: HttpError) -> str:
    try:
        return error.error_details[0].get("message") or str(error)  # type: ignore[index]
    except Exception:  # noqa: BLE001 - best effort formatting only
        return str(error)


class Drive:
    def __init__(self, creds: Credentials, dry_run: bool = False):
        self.drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self.dry_run = dry_run

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _quote(value: str) -> str:
        """Escape a string for use inside a Drive search query."""
        return value.replace("\\", "\\\\").replace("'", "\\'")

    @staticmethod
    def is_placeholder(file_id: str) -> bool:
        return file_id.startswith(DRY_RUN_PREFIX)

    def _list_files(self, query: str) -> list[dict]:
        files: list[dict] = []
        page_token = None
        while True:
            response = (
                self.drive.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType)",
                    pageSize=100,
                    pageToken=page_token,
                )
                .execute(num_retries=RETRIES)
            )
            files.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return files

    # --- files and folders ----------------------------------------------

    def find_by_name(self, name: str, parent_id: str | None, mime_type: str | None = None) -> list[dict]:
        """Non-trashed items with exactly this name (and parent and type, if given)."""
        if parent_id and self.is_placeholder(parent_id):
            return []
        query = f"name = '{self._quote(name)}' and trashed = false"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        return self._list_files(query)

    def list_children(self, parent_id: str, mime_type: str | None = None) -> list[dict]:
        if self.is_placeholder(parent_id):
            return []
        query = f"'{parent_id}' in parents and trashed = false"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"
        return self._list_files(query)

    def find_or_create(self, name: str, parent_id: str | None, mime_type: str) -> tuple[str, bool]:
        """Return (id, created).  Never creates a second item with the same name."""
        matches = self.find_by_name(name, parent_id, mime_type)
        if len(matches) > 1:
            where = f"inside folder {parent_id}" if parent_id else "in your Drive"
            raise DriveError(
                f"Found {len(matches)} items named '{name}' {where}; expected at most one. "
                "Rename or trash the extras so exactly one remains, then re-run."
            )
        if matches:
            return matches[0]["id"], False
        kind = "folder" if mime_type == FOLDER_MIME else "spreadsheet"
        if self.dry_run:
            log.debug("[dry-run] not creating %s '%s'", kind, name)
            return f"{DRY_RUN_PREFIX}{kind}:{name}", True
        body: dict = {"name": name, "mimeType": mime_type}
        if parent_id:
            body["parents"] = [parent_id]
        created = self.drive.files().create(body=body, fields="id").execute(num_retries=RETRIES)
        return created["id"], True

    def find_or_create_folder(self, name: str, parent_id: str | None = None) -> tuple[str, bool]:
        return self.find_or_create(name, parent_id, FOLDER_MIME)

    def find_existing_folder(self, name: str, parent_id: str | None = None) -> str:
        """Return the id of the one folder with this name; error if there are none or several."""
        matches = self.find_by_name(name, parent_id, FOLDER_MIME)
        where = f"inside folder {parent_id}" if parent_id else "in your Google Drive"
        if not matches:
            raise DriveError(
                f"No folder named '{name}' found {where}. "
                "Create it first (anywhere in My Drive), or check the spelling."
            )
        if len(matches) > 1:
            raise DriveError(
                f"Found {len(matches)} folders named '{name}' {where}; expected exactly one. "
                "Rename or trash the extras so exactly one remains, then re-run."
            )
        return matches[0]["id"]

    def find_or_create_spreadsheet(self, name: str, parent_id: str) -> tuple[str, bool]:
        return self.find_or_create(name, parent_id, SPREADSHEET_MIME)

    def copy_file(self, file_id: str, name: str, parent_id: str) -> str:
        """Copy an existing file, giving the copy a new name and parent."""
        if self.dry_run:
            log.debug("[dry-run] not copying %s to '%s'", file_id, name)
            return f"{DRY_RUN_PREFIX}copy:{name}"
        copied = (
            self.drive.files()
            .copy(fileId=file_id, body={"name": name, "parents": [parent_id]}, fields="id")
            .execute(num_retries=RETRIES)
        )
        return copied["id"]

    def trash_file(self, file_id: str) -> None:
        """Move a file to the Drive trash (recoverable for 30 days)."""
        if self.dry_run or self.is_placeholder(file_id):
            log.debug("[dry-run] not trashing %s", file_id)
            return
        self.drive.files().update(fileId=file_id, body={"trashed": True}, fields="id").execute(
            num_retries=RETRIES
        )

    # --- permissions -----------------------------------------------------

    def list_permissions(self, file_id: str) -> list[dict]:
        if self.is_placeholder(file_id):
            return []
        permissions: list[dict] = []
        page_token = None
        while True:
            response = (
                self.drive.permissions()
                .list(
                    fileId=file_id,
                    fields="nextPageToken, permissions(id, type, role, emailAddress)",
                    pageSize=100,
                    pageToken=page_token,
                )
                .execute(num_retries=RETRIES)
            )
            permissions.extend(response.get("permissions", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return permissions

    def add_anyone_reader(self, file_id: str) -> None:
        if self.dry_run:
            log.debug("[dry-run] not changing %s", file_id)
            return
        self.drive.permissions().create(
            fileId=file_id, body={"type": "anyone", "role": "reader"}, fields="id"
        ).execute(num_retries=RETRIES)

    def add_writer(self, file_id: str, email: str) -> None:
        if self.dry_run:
            log.debug("[dry-run] not sharing %s with %s", file_id, email)
            return
        self.drive.permissions().create(
            fileId=file_id,
            body={"type": "user", "role": "writer", "emailAddress": email},
            sendNotificationEmail=False,
            fields="id",
        ).execute(num_retries=RETRIES)

    def set_role(self, file_id: str, permission_id: str, role: str) -> None:
        if self.dry_run:
            log.debug("[dry-run] not changing permission %s on %s", permission_id, file_id)
            return
        self.drive.permissions().update(
            fileId=file_id, permissionId=permission_id, body={"role": role}, fields="id"
        ).execute(num_retries=RETRIES)

    def remove_permission(self, file_id: str, permission_id: str) -> None:
        if self.dry_run:
            log.debug("[dry-run] not removing permission %s from %s", permission_id, file_id)
            return
        self.drive.permissions().delete(fileId=file_id, permissionId=permission_id).execute(
            num_retries=RETRIES
        )

    # --- spreadsheet values ---------------------------------------------

    def read_values(self, spreadsheet_id: str, cell_range: str = "A:B") -> list[list[str]]:
        """Values on the first sheet (a range with no sheet name means the first sheet)."""
        if self.is_placeholder(spreadsheet_id):
            return []
        response = (
            self.sheets.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=cell_range)
            .execute(num_retries=RETRIES)
        )
        return response.get("values", [])

    def write_values(
        self, spreadsheet_id: str, values: list[list[str]], value_input_option: str = "RAW"
    ) -> None:
        """Replace columns A:B of the first sheet with ``values``."""
        if self.dry_run:
            log.debug("[dry-run] not writing to spreadsheet %s", spreadsheet_id)
            return
        sheet_values = self.sheets.spreadsheets().values()
        sheet_values.clear(spreadsheetId=spreadsheet_id, range="A:B", body={}).execute(
            num_retries=RETRIES
        )
        sheet_values.update(
            spreadsheetId=spreadsheet_id,
            range="A1",
            valueInputOption=value_input_option,
            body={"values": values},
        ).execute(num_retries=RETRIES)
