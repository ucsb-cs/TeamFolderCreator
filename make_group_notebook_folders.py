import os
import json
import csv
import string
from xmlrpc.client import boolean
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
import pickle
from pprint import pprint
import time
import sys


import canvas_roster_functions
import make_google_chat_conversations

SLEEP_TIME = 1

# Define the required scopes
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.activity.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/chat.spaces",
    "https://www.googleapis.com/auth/documents.currentonly",
    "https://www.googleapis.com/auth/documents",
]
INITIAL_PROJECTS_FOLDER_NAME = "Initial Contents"


# Authenticate and build the Drive API service
def authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


# Create a folder and return its ID
def create_folder(service, name, parent_id=None, create_if_not_exists=True):
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    folders = results.get("files", [])
    # If the folder already exists, return its ID
    if folders:
        return folders[0]["id"]

    if not create_if_not_exists:
        print(
            f"Folder '{name}' not found and create_if_not_exists is False. Returning None."
        )
        return None

    # Otherwise, create a new folder and return it's ID
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id] if parent_id else [],
    }
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


# Share folder with email
def share_folder(service, file_id, email):
    # Give the user with the email address `email` write access to the folder
    # file_id is the ID of the folder
    # email is the email address of the user to share with

    # Create a permission object
    permission = {"type": "user", "role": "writer", "emailAddress": email}
    # Create the permission using the Drive API
    service.permissions().create(
        fileId=file_id, body=permission, fields="id", sendNotificationEmail=False
    ).execute()


def get_values_from_spreadsheet(service, sheet_id):
    # Find a tab in the spreadsheet called "Members"
    sheets_service = build("sheets", "v4", credentials=service._http.credentials)
    result = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheets = result.get("sheets", [])
    members_tab = None
    for sheet in sheets:
        if sheet["properties"]["title"] == "Members":
            members_tab = sheet
            break
    if not members_tab:
        members_tab = sheets[0]

    # Get the values from the "Members" tab
    range_name = f"'{members_tab['properties']['title']}'!A1:B"
    result = (
        sheets_service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=range_name)
        .execute()
    )
    values = result.get("values", [])
    return values


def create_new_retro_file_google_doc(
    service, group_drive_folder_id, group_name, members, retro_file_name="Retro1"
):
    print(
        f"Google Doc {retro_file_name} does not exist in {group_name}. Creating new Google Doc..."
    )

    # Create a new Google Doc
    doc_metadata = {
        "name": retro_file_name,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [group_drive_folder_id],
    }
    doc = service.files().create(body=doc_metadata, fields="id").execute()
    return doc


def get_all_tab_titles(tabs):
    """Recursively extracts all tab titles from the document tree."""
    titles = []
    for tab in tabs:
        # Get title from tabProperties
        titles.append(tab.get("tabProperties", {}).get("title"))
        # Check for nested child tabs
        if "childTabs" in tab:
            titles.extend(get_all_tab_titles(tab["childTabs"]))
    return titles


def get_document_from_document_id(service, document_id):
    docs_service = build("docs", "v1", credentials=service._http.credentials)
    document = (
        docs_service.documents()
        .get(documentId=document_id, includeTabsContent=True)
        .execute()
    )
    return document


def rename_tabs_for_each_member(service, doc, group_name, members):
    """
    Add a new tab to the Google Doc for each member.
    """

    requests = []

    orig_tab_name_to_new_tab_name = {}
    for i, member in enumerate(members):
        member_name = member["student_name"]
        orig_tab_name = f"Member{i+1}"
        orig_tab_name_to_new_tab_name[orig_tab_name] = member_name

    # Initialize the Docs API service
    docs_service = build("docs", "v1", credentials=service._http.credentials)
    document = get_document_from_document_id(service, doc["id"])

    # 2. Get flat list of existing tab names
    existing_tabs = document.get("tabs", [])
    existing_titles = get_all_tab_titles(existing_tabs)

    print(f"Existing tabs in document '{group_name}': {existing_titles}")

    for tab in existing_tabs:
        tab_title = get_tab_name(tab)
        if tab_title in orig_tab_name_to_new_tab_name:
            new_tab_name = orig_tab_name_to_new_tab_name[tab_title]
            print(f"Renaming tab '{tab_title}' to '{new_tab_name}'...")
            tabId = tab["tabProperties"]["tabId"]
            print("Tab ID: ", tabId)
            requests.append(
                {
                    "updateDocumentTabProperties": {
                        "tabProperties": {"tabId": tabId, "title": new_tab_name},
                        "fields": "title",
                    }
                }
            )

    # 4. Execute the update if there are new tabs to add
    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc["id"], body={"requests": requests}
        ).execute()
        print(f"Successfully added {len(requests)} tabs to the document.")
    else:
        print("All member tabs already exist.")


def locate_retro_file_template(service, parent_folder_id, retro_file_name="Retro1"):
    # Locate a folder called "TEMPLATES" in the group folder
    templates_folder = find_folder(service, "TEMPLATES", parent_id=parent_folder_id)
    if not templates_folder:
        raise Exception(
            f"TEMPLATES folder not found in parent folder {parent_folder_id}."
        )
    print(f"Located TEMPLATES folder in parent folder {parent_folder_id}.")
    # Locate a file with the name retro_file_name in the TEMPLATES folder
    query = f"name='{retro_file_name}' and mimeType='application/vnd.google-apps.document' and '{templates_folder['id']}' in parents"
    results = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    templates = results.get("files", [])
    if not templates:
        raise Exception(
            f"Template file '{retro_file_name}' not found in TEMPLATES folder."
        )
    return templates[0]


def get_tab_name(tab):
    return tab.get("tabProperties", {}).get("title")


def create_or_update_member_file_google_sheet(
    service, group_drive_folder_id, group_name, members
):
    # Check if a Google Sheet with the target name already exists
    query = f"name='{group_name}_members' and mimeType='application/vnd.google-apps.spreadsheet' and '{group_drive_folder_id}' in parents"
    results = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    sheets = results.get("files", [])

    if sheets:
        valuesFromSheet = get_values_from_spreadsheet(service, sheets[0]["id"])
        valuesToSheet = get_values_for_spreadsheet(members)
        if valuesFromSheet != valuesToSheet:
            create_new_tab_member_file_google_sheet(
                service, group_drive_folder_id, group_name, members, sheets
            )
        else:
            print(f"Spreadsheet {group_name}_members already exists and is up to date.")
    else:
        create_new_member_file_google_sheet(
            service, group_drive_folder_id, group_name, members
        )


def create_new_member_file_google_sheet(
    service, group_drive_folder_id, group_name, members
):
    # If the spreadsheet does not exist, create a new one
    sheet_metadata = {
        "name": f"{group_name}_members",
        "mimeType": "application/vnd.google-apps.spreadsheet",
        "parents": [group_drive_folder_id],
    }
    sheet = service.files().create(body=sheet_metadata, fields="id").execute()
    sheet_id = sheet["id"]

    # Rename the default tab to "Members"
    sheets_service = build("sheets", "v4", credentials=service._http.credentials)
    rename_tab_body = {
        "requests": [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": 0,  # Default sheet ID is 0
                        "title": "Members",
                    },
                    "fields": "title",
                }
            }
        ]
    }
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id, body=rename_tab_body
    ).execute()

    # Prepare data for the Google Sheet
    values = get_values_for_spreadsheet(members)

    # Update the Google Sheet with the member data
    body = {"values": values}
    range_name = "Members!A1"
    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id, range=range_name, valueInputOption="RAW", body=body
    ).execute()

    print(
        f"Created new spreadsheet: {group_name}_members in group folder: {group_name}"
    )


def get_values_for_spreadsheet(members):
    # Prepare data for the Google Sheet
    values = [["Name", "Email"]]
    for member in members:
        values.append([member["student_name"], member["email"]])
    return values


def create_new_tab_member_file_google_sheet(
    service, group_drive_folder_id, group_name, members, sheets
):
    # If the spreadsheet exists, add a new tab with the member data
    sheet_id = sheets[0]["id"]
    sheets_service = build("sheets", "v4", credentials=service._http.credentials)

    new_tab_name = "Members"

    # Determine number of existing tabs
    existing_tabs = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing_tabs = existing_tabs.get("sheets", [])
    existing_tab_names = [tab["properties"]["title"] for tab in existing_tabs]

    # Ensure the new tab name is unique
    version = 1
    new_tab_name = f"Members_{version}"
    while new_tab_name in existing_tab_names:
        version += 1
        new_tab_name = f"Members_{version}"

    # Create a new tab with a unique name
    add_sheet_body = {
        "requests": [{"addSheet": {"properties": {"title": new_tab_name}}}]
    }
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id, body=add_sheet_body
    ).execute()

    # Prepare data for the new tab
    values = get_values_for_spreadsheet(members)

    # Update the new tab with the member data
    body = {"values": values}
    range_name = f"'{new_tab_name}'!A1"
    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id, range=range_name, valueInputOption="RAW", body=body
    ).execute()

    print(
        f"Updated existing spreadsheet: {group_name}_members with new tab: {new_tab_name}"
    )


def update_retro_file_google_doc(
    service, group_drive_folder_id, group, members, retro_file_name
):
    # Get the file ID of the retro file in the group folder
    query = f"name='{retro_file_name}' and mimeType='application/vnd.google-apps.document' and '{group_drive_folder_id}' in parents"
    results = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    docs = results.get("files", [])
    if not docs:
        raise Exception(
            f"Retro file '{retro_file_name}' not found in group folder '{group}'."
        )
    doc = docs[0]

    # Get the tabs, and ensure we have a 'Main' and 'Members' tab
    document = get_document_from_document_id(service, doc["id"])
    existing_tabs = document.get("tabs", [])
    existing_titles = get_all_tab_titles(existing_tabs)

    if "Main" not in existing_titles:
        raise Exception(f"Retro file '{retro_file_name}' does not have a 'Main' tab.")

    rename_tabs_for_each_member(service, doc, group, members)
    search_and_replace_group_and_member_names(service, doc["id"], group, members)


def search_and_replace_group_and_member_names(
    service, document_id, group_name, members
):

    substitutions = {
        "%TEAM%": group_name,
        "%MEMBERS%": ", ".join([member["student_name"] for member in members]),
        "%MEMBER1%": members[0]["student_name"] if len(members) > 0 else "",
        "%MEMBER2%": members[1]["student_name"] if len(members) > 1 else "",
        "%MEMBER3%": members[2]["student_name"] if len(members) > 2 else "",
        "%MEMBER4%": members[3]["student_name"] if len(members) > 3 else "",
        "%MEMBER5%": members[4]["student_name"] if len(members) > 4 else "",
        "%MEMBER6%": members[5]["student_name"] if len(members) > 5 else "",
    }

    requests = []

    for key, value in substitutions.items():
        requests.append(search_and_replace_in_doc_request(key, value))

    docs_service = build("docs", "v1", credentials=service._http.credentials)
    docs_service.documents().batchUpdate(
        documentId=document_id, body={"requests": requests}
    ).execute()


def search_and_replace_in_doc_request(search_text, replace_text):
    return {
        "replaceAllText": {
            "replaceText": replace_text,
            "containsText": {
               "text": search_text,
                 "matchCase": True,
                 "searchByRegex": False
            }
        }
    }

def delete_existing_files(service, file_name, folder_id):
    query = f"name='{file_name}' and '{folder_id}' in parents"
    results = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    files = results.get("files", [])
    for file in files:
        print(f"Deleting existing file '{file['name']}' with ID {file['id']} in folder {folder_id}...")
        service.files().delete(fileId=file["id"]).execute()


def make_group_folders(
    service,
    group_dict,
    PROJECTS_FOLDER_NAME,
    filter=None,
    GROUP_CATEGORY_ID=None,
):

    # Step 1: Create the parent Projects folder
    parent_folder_id = create_folder(service, PROJECTS_FOLDER_NAME)

    retroFileName = f"Retro1"
    template = locate_retro_file_template(service, parent_folder_id, retroFileName)
    print(
        f"Located retro file template: id: {template['id']}, name: {template['name']}"
    )

    # Step 1a: Get the template document and extract existing tab names for later comparison

    template_document = get_document_from_document_id(service, template["id"])

    existing_tabs = template_document.get("tabs", [])
    existing_titles = get_all_tab_titles(existing_tabs)
    print(f"Existing tab names in Template: {existing_titles}")

    # Step 2: Create group folders and assign permissions
    group_folders = {}

    print(f"Filter: {filter}")
    groups = list(group_dict.keys())
    groups.sort(key=folder_name_sort_key)
    for group in groups:
        value = group_dict[group]

        if group == "":
            print(f"Skipping group {group} as it has no name.")
            names = [member["student_name"] for member in value["members"]]
            print(f"This group has the following members: {names}")
            continue

        if filter and group not in filter:
            print(f"Skipping group {group} as it is not in the filter list.")
            continue

        print(f"Creating folder for group: {group}...")

        group_drive_folder_id = create_folder(service, group, parent_folder_id)
        group_dict[group][
            "folder_url"
        ] = f"https://drive.google.com/drive/folders/{group_drive_folder_id}"
        group_dict[group]["group_drive_folder_id"] = group_drive_folder_id

        # Give this user write access to the group folder
        for student in value["members"]:
            email = student["email"]
            share_folder(service, group_drive_folder_id, email)

        create_or_update_member_file_google_sheet(
            service, group_drive_folder_id, group, value["members"]
        )

        new_name = f"{retroFileName}-{group}"

        delete_existing_files(service, new_name, group_drive_folder_id)

        copy_file(
            service, template["id"], new_name, group_drive_folder_id
        )

        update_retro_file_google_doc(
            service,
            group_drive_folder_id,
            group,
            value["members"],
            retro_file_name=f"{retroFileName}-{group}",
        )

    # Output the group dictionary to a CSV file
    output_file = f"group_folders_{GROUP_CATEGORY_ID}.csv"
    with open(output_file, "w", newline="") as csvfile:
        fieldnames = ["Group Name", "Folder URL"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for group_name, group_info in group_dict.items():
            writer.writerow(
                {"Group Name": group_name, "Folder URL": group_info["folder_url"]}
            )

    print(f"Done. Output saved to {output_file}.")


def populate_group_dict_with_folder_urls(
    service, group_dict, PROJECTS_FOLDER_NAME, filter=None, GROUP_CATEGORY_ID=None
):

    # Step 1: Get the parent Projects folder id
    parent_folder_id = create_folder(
        service, PROJECTS_FOLDER_NAME, create_if_not_exists=False
    )

    # Step 2: Create group folders and assign permissions
    group_folders = {}

    print(f"Filter: {filter}")
    groups = list(group_dict.keys())
    groups.sort(key=folder_name_sort_key)

    for group in groups:
        value = group_dict[group]

        if group == "":
            print(f"Skipping group {group} as it has no name.")
            names = [member["student_name"] for member in value["members"]]
            print(f"This group has the following members: {names}")
            continue

        if filter and group not in filter:
            print(f"Skipping group {group} as it is not in the filter list.")
            continue

        print(f"Get folder id for {group}...")

        group_drive_folder_id = create_folder(service, group, parent_folder_id)
        group_dict[group][
            "folder_url"
        ] = f"https://drive.google.com/drive/folders/{group_drive_folder_id}"
        group_dict[group]["group_drive_folder_id"] = group_drive_folder_id

    # Output the group dictionary to a CSV file
    output_file = f"group_folders_{GROUP_CATEGORY_ID}.csv"
    with open(output_file, "w", newline="") as csvfile:
        fieldnames = ["Group Name", "Folder URL"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for group_name, group_info in group_dict.items():
            writer.writerow(
                {"Group Name": group_name, "Folder URL": group_info["folder_url"]}
            )

    print(f"Done. Output saved to {output_file}.")


def find_folder_id(service, name, parent_id=None):
    folder = find_folder(service, name, parent_id)
    return folder["id"] if folder else None


def find_folder(service, name, parent_id=None):
    """Find a folder by name and optionally parent folder ID."""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    folders = results.get("files", [])
    return folders[0] if folders else None


def list_files_in_folder(service, folder_id):
    """List files and folders in a folder."""
    results = (
        service.files()
        .list(
            q=f"'{folder_id}' in parents and trashed = false",
            spaces="drive",
            fields="files(id, name, mimeType, createdTime, modifiedTime)",
        )
        .execute()
    )
    return results.get("files", [])


def copy_file_if_not_exists(service, file_id, new_name, parent_id):
    """Copy a file into a folder if a file with the same name does not already exist."""
    existing_files = list_files_in_folder(service, parent_id)
    for file in existing_files:
        if file["name"] == new_name:
            print(
                f"File with name '{new_name}' already exists in folder {parent_id}. Skipping copy."
            )
            return file
    return copy_file(service, file_id, new_name, parent_id)


def copy_file(service, file_id, new_name, parent_id):
    """Copy a file into a folder."""
    copied_file = {"name": new_name, "parents": [parent_id]}
    return service.files().copy(fileId=file_id, body=copied_file).execute()


def get_notebook_file_id_and_name(service, PROJECTS_FOLDER_NAME):
    # Step 1: Find the Projects folder
    projects_id = find_folder_id(service, PROJECTS_FOLDER_NAME)
    if not projects_id:
        raise Exception("Projects folder not found.")

    # Step 2: Find the 'Initial Contents' folder inside Projects
    initial_id = find_folder_id(service, "Initial Contents", parent_id=projects_id)
    if not initial_id:
        raise Exception(
            f"'Initial Contents' folder not found inside {PROJECTS_FOLDER_NAME}."
        )

    # Step 3: Get the list of all files inside the 'Initial Contents' folder
    files = list_files_in_folder(service, initial_id)
    if not files:
        raise Exception(f"No files found inside 'Initial Contents' folder.")

    # Step 4: Find the name of the first file inside the 'Initial Contents' folder
    # and check if it is a notebook file
    # If it is not a notebook file, raise an exception
    # If it is a notebook file, get its ID
    notebook_file_name = None
    notebook_file_id = None
    for file in files:
        # If the filename ends in .ipynb, it is a notebook file
        if file["name"].endswith(".ipynb"):
            notebook_file_name = file["name"]
            notebook_file_id = file["id"]
            print(
                f"Found notebook file: {notebook_file_name} in Initial Contents folder."
            )

    if not notebook_file_name:
        raise Exception(
            f"No notebook file (.ipynb) found inside 'Initial Contents' folder."
        )

    return (notebook_file_id, notebook_file_name)


def csv_to_dict(filename):
    data_dict = {}
    with open(filename, "r") as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            key = row[csv_reader.fieldnames[0]]
            data_dict[key] = row
    return data_dict


def make_group_dictionary(group_data):
    group_dict = {}
    for row in group_data.values():
        group_name = row["group_name"]
        if group_name not in group_dict:
            group_dict[group_name] = {"folder_url": "", "members": []}
        group_dict[group_name]["members"].append(row)
    return group_dict


def folder_sort_key(folder):
    return folder_name_sort_key(folder["name"])


def folder_name_sort_key(folder_name):
    # Extract the number from the folder name
    # Assuming the folder name is in the format "Group X"

    try:
        return int(folder_name.split(" ")[1])
    except (IndexError, ValueError):
        return float("inf")  # If it doesn't match, sort it to the end


def move_all_files_in_folder(service, src=None, dest=None):
    if not src or not dest:
        raise Exception("Source and destination folder IDs must be provided.")
    print(f"Moving files from {src['name']} to {dest['name']}...")
    iterate_files = list_files_in_folder(service, src["id"])
    for file in iterate_files:
        file_id = file["id"]
        file_name = file["name"]
        print(f"Moving {file_name} from {src['name']} to {dest['name']}...")
        service.files().update(
            fileId=file_id,
            addParents=dest["id"],
            removeParents=src["id"],
            fields="id, parents",
        ).execute()
        print(f"Moved {file_name} to {dest['name']}.")


def folder_id_to_name(service, folder_id):
    """Get the name of a folder by its ID."""
    try:
        file = service.files().get(fileId=folder_id, fields="name").execute()
        return file.get("name")
    except HttpError as error:
        print(f"An error occurred: {error}")
        return None


def fix_filenames(service, name, folder_name, files):
    files_for_name = [file for file in files if name in file["name"]]
    print(f"  Found {len(files_for_name)} files for {name} in {folder_name}.")
    suffix_num = 0
    for file in files_for_name:
        file_id = file["id"]
        file_name = file["name"]

        if file_name.endswith("UNTOUCHED.ipynb") or file_name.endswith(f"{name}.ipynb"):
            new_file_name = file_name.replace("_UNTOUCHED", "")

            new_file_name = new_file_name.replace(".ipynb", f"_{suffix_num}.ipynb")
            print(f"  Renaming {file_name} to {new_file_name} in {folder_name}.")
            rename_file = (
                service.files()
                .update(fileId=file_id, body={"name": new_file_name})
                .execute()
            )
            print(f"  Renamed {file_name} to {new_file_name} in {folder_name}.")

        suffix_num += 1


def scan_group_folders(
    service, drive_activity_service, PROJECTS_FOLDER_NAME, group_dict
):

    # Step 1: Find the Projects folder

    projects_folder = find_folder(service, PROJECTS_FOLDER_NAME)
    if not projects_folder:
        raise Exception("Projects folder not found.")

    # Step 2: Iterate over all folders in the Projects folder
    results = (
        service.files()
        .list(
            q=f"'{projects_folder['id']}' in parents and mimeType='application/vnd.google-apps.folder'",
            spaces="drive",
            fields="files(id, name)",
        )
        .execute()
    )
    folders = results.get("files", [])

    # Sort the folders by name
    folders.sort(key=folder_sort_key)

    for folder in folders:
        print("*" * 40)
        print(f"Folder: {folder['name']} (ID: {folder['id']})")

        if folder["name"] in [INITIAL_PROJECTS_FOLDER_NAME, "data"]:
            continue

        if folder["name"].startswith("Midterm"):
            continue

        # Look for a folder inside each folder called "OLD"

        old_folder = find_folder(service, "OLD", parent_id=folder["id"])
        extra_folder = find_folder(service, "EXTRA", parent_id=folder["id"])

        folder_id = folder["id"]
        folder_name = folder["name"]

        if old_folder:
            print(f"  Found OLD folder:")
            move_all_files_in_folder(service, src=old_folder, dest=folder)
        if extra_folder:
            print(f"  Found EXTRA folder:")
            move_all_files_in_folder(service, src=extra_folder, dest=folder)

        # Get new list of all files in the folder
        files = list_files_in_folder(service, folder_id)
        # Sort the files by name and then by created time
        files.sort(key=lambda x: (x["name"], x["createdTime"]))

        print(f"  Found {len(files)} files in {folder_name}.")

        # Find group members

        group_name = folder["name"]
        group_info = group_dict.get(group_name)
        if not group_info:
            print(f"  No group info found for {group_name}. Skipping.")
            continue
        group_members = group_info["members"]
        group_member_names_with_underscores = [
            member["student_name"].replace(" ", "_") for member in group_members
        ]
        print(f"  Group members: {group_member_names_with_underscores}")

        for member_name in group_member_names_with_underscores:
            fix_filenames(service, member_name, folder_name, files)

        fix_filenames(service, "FINAL", folder_name, files)

        # # Step 3: List all files in the folder
        # files = list_files_in_folder(service, folder_id)
        # for file in files:
        #     file_id = file['id']
        #     file_name = file['name']
        #     if file_name.endswith('UNTOUCHED.ipynb'):
        #         # If the file name ends with _UNTOUCHED.ipynb, move it into the OLD folder
        #         # Move the file into the OLD folder
        #         service.files().update(
        #             fileId=file_id,
        #             addParents=old_folder_id,
        #             removeParents=folder_id,
        #             fields='id, parents'
        #         ).execute()
        #         print(f"  Moved {file_name} to EXTRA folder in {folder_name}.")

        #     else:
        #          # Get history of the file

        #         file_editors = list_editors( drive_activity_service, file_id, file_name)
        #         pprint(file_editors)
        #         if (len(file_editors) == 1) and file_editors[0]['display_name'] == 'Phill Conrad':
        #             # rename file by appending _UNTOUCHED before .ipynb
        #             new_file_name = file_name.replace('.ipynb', '_UNTOUCHED.ipynb')
        #             service.files().update(fileId=file_id, body={'name': new_file_name}).execute()
        #             print(f"  Renamed {file_name} to {new_file_name} in {folder_name}.")

        # print("\n")


def authorize_drive_activity_api():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("driveactivity", "v2", credentials=creds)


def get_credentials():
    creds = None
    if os.path.exists("token.pkl"):
        with open("token.pkl", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.pkl", "wb") as token:
            pickle.dump(creds, token)
    return creds


def resolve_person_name(people_service, person_resource_name):
    try:
        person = (
            people_service.people()
            .get(resourceName=person_resource_name, personFields="names,emailAddresses")
            .execute()
        )

        names = person.get("names", [])
        emails = person.get("emailAddresses", [])

        display_name = names[0]["displayName"] if names else "Unknown"
        email = emails[0]["value"] if emails else "No email"
        return {
            "display_name": display_name,
            "email": email,
            "person_resource_name": person_resource_name,
        }

    except Exception as e:
        return {
            "display_name": None,
            "email": None,
            "person_resource_name": person_resource_name,
            "error": str(e),
        }


def list_editors(activity_service, file_id, file_name):
    creds = get_credentials()
    print(f"Getting history for file: {file_name} ({file_id})")
    time.sleep(SLEEP_TIME)
    # Create the correct services
    people_service = build("people", "v1", credentials=creds)

    response = (
        activity_service.activity()
        .query(
            body={
                "itemName": f"items/{file_id}",
                "filter": "detail.action_detail_case:EDIT",
            }
        )
        .execute()
    )

    if response.get("error"):
        print(f"Error: {response['error']}")
        sys.exit(1)

    editors = set()
    for activity in response.get("activities", []):
        for actor in activity.get("actors", []):
            known_user = actor.get("user", {}).get("knownUser", {})
            if known_user:
                editors.add(known_user.get("personName"))

    names = list(
        map(lambda person_id: resolve_person_name(people_service, person_id), editors)
    )
    return names


def add_google_drive_folder_links(
    canvas_assignment_name,
    group_dict,
    service,
    drive_activity_service,
    PROJECTS_FOLDER_NAME,
    addFeedback=False,
):

    # Step 0: locate the canvas assignment

    assignment = canvas_roster_functions.locate_assignment(canvas_assignment_name)
    if not assignment:
        raise Exception(f"Assignment {canvas_assignment_name} not found.")

    assignment_id = assignment["id"]

    # Step 1: Find the Projects folder

    projects_id = find_folder_id(service, PROJECTS_FOLDER_NAME)
    if not projects_id:
        raise Exception("Projects folder not found.")

    # Step 2: Iterate over groups

    for group_name, group_info in group_dict.items():
        if group_name == "":
            print(f"Skipping group {group_name} as it has no name.")
            names = [member["student_name"] for member in group_info["members"]]
            print(f"This group has the following members: {names}")
            continue
        for student in group_info["members"]:
            student_id = student["student_id"]
            url = group_info["folder_url"]

            text = f"""
            <p>Group Folder on Google Drive is at:</p>
            <p><a href="{url}">{url}></p>
            """

            if addFeedback:
                canvas_roster_functions.add_feedback_to_submission_unless_duplicate(
                    assignment_id, student_id, text
                )
                print(
                    f"Added feedback for {student['student_name']} in group {group_name} with ID {student_id}."
                )


if __name__ == "__main__":

    MIDTERM_GROUP_SET_ID = (
        "22640"  # You can get this from the URL in Canvas (for midterm groups)
    )
    WEEK4_GROUP_SET_ID = (
        "22633"  # You can get this from the URL in Canvas (for week4 groups)
    )

    # (PROJECTS_FOLDER_NAME, GROUP_CATEGORY_ID) = ("cs5a-s25-ic12", WEEK4_GROUP_SET_ID)
    PROJECTS_FOLDER_NAME, GROUP_CATEGORY_ID = (
        "cs5a-s25-midterm-folders",
        MIDTERM_GROUP_SET_ID,
    )

    # filter = [
    #     "Week-4-Lecture-Group 23",
    #     "Week-4-Lecture-Group 25",
    #     "Week-4-Lecture-Group-33"]

    filter = None

    service = authenticate()
    drive_activity_service = authorize_drive_activity_api()

    group_data = csv_to_dict(f"group_export_{GROUP_CATEGORY_ID}.csv")

    group_dict = make_group_dictionary(group_data)

    # parent_folder_id = create_folder(service, PROJECTS_FOLDER_NAME)
    # (notebook_file_id, notebook_file_name) = get_notebook_file_id_and_name(
    #      service, PROJECTS_FOLDER_NAME
    #  )
    # make_group_folders(service, group_dict, notebook_file_id, notebook_file_name,  PROJECTS_FOLDER_NAME, filter=filter, GROUP_CATEGORY_ID=GROUP_CATEGORY_ID)
    parent_folder_id = create_folder(service, PROJECTS_FOLDER_NAME)
    # (notebook_file_id, notebook_file_name) = get_notebook_file_id_and_name(
    #      service, PROJECTS_FOLDER_NAME
    #  )

    # make_group_folders_with_single_notebook(service, group_dict, notebook_file_id, notebook_file_name,  PROJECTS_FOLDER_NAME, filter=None, GROUP_CATEGORY_ID=GROUP_CATEGORY_ID)
    make_group_folders(
        service,
        group_dict,
        PROJECTS_FOLDER_NAME,
        filter=None,
        GROUP_CATEGORY_ID=GROUP_CATEGORY_ID,
    )

    populate_group_dict_with_folder_urls(
        service,
        group_dict,
        PROJECTS_FOLDER_NAME,
        filter=filter,
        GROUP_CATEGORY_ID=GROUP_CATEGORY_ID,
    )

    # scan_group_folders(service, drive_activity_service, PROJECTS_FOLDER_NAME, group_dict)

    # add_google_drive_folder_links("ic12", group_dict, service, drive_activity_service, PROJECTS_FOLDER_NAME )

    # session = make_google_chat_conversations.get_session()

    # add_chat_folder_link(group_dict, session)

    # generate_links_to_jupyter_notebooks(
    #     service,
    #     group_dict,
    #     notebook_file_id,
    #     notebook_file_name,
    #     PROJECTS_FOLDER_NAME,
    #     filter=filter,
    #     GROUP_CATEGORY_ID=GROUP_CATEGORY_ID,
    #     drive_activity_service=drive_activity_service,
    #     canvas_assignment_name="ic12",
    # )

    # generate_links_to_ic10_folders(
    #     service,
    #     group_dict,
    #     "CS5A S25 ic10",
    #     filter=[],
    #     drive_activity_service=drive_activity_service,
    #     canvas_assignment_name="ic12",
    # )
