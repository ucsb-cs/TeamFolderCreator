
import os
import json
import csv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
import pickle
from pprint import pprint
import time

# Define the required scopes
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.activity.readonly',    
    'https://www.googleapis.com/auth/contacts.readonly' 
]
INITIAL_PROJECTS_FOLDER_NAME = 'Initial Contents'

# Authenticate and build the Drive API service
def authenticate():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

# Create a folder and return its ID
def create_folder(service, name, parent_id=None):
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    folders = results.get('files', [])
    # If the folder already exists, return its ID
    if folders:
        return folders[0]['id']
    
    # Otherwise, create a new folder and return it's ID
    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id] if parent_id else []
    }
    folder = service.files().create(body=metadata, fields='id').execute()
    return folder['id']

# Share folder with email
def share_folder(service, file_id, email):
    # Give the user with the email address `email` write access to the folder
    # file_id is the ID of the folder
    # email is the email address of the user to share with
    
    # Create a permission object
    permission = {
        'type': 'user',
        'role': 'writer',
        'emailAddress': email
    }
    # Create the permission using the Drive API
    service.permissions().create(
        fileId=file_id,
        body=permission,
        fields='id',
        sendNotificationEmail=False
    ).execute()

def get_values_from_spreadsheet(service, sheet_id):
    # Find a tab in the spreadsheet called "Members"
    sheets_service = build('sheets', 'v4', credentials=service._http.credentials)
    result = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheets = result.get('sheets', [])
    members_tab = None
    for sheet in sheets:
        if sheet['properties']['title'] == 'Members':
            members_tab = sheet
            break
    if not members_tab:
        members_tab = sheets[0]        
      
    # Get the values from the "Members" tab
    range_name = f"'{members_tab['properties']['title']}'!A1:B"
    result = sheets_service.spreadsheets().values().get(spreadsheetId=sheet_id, range=range_name).execute()
    values = result.get('values', [])
    return values

def create_or_update_member_file_google_sheet(service, group_id, group_name, members):
    # Check if a Google Sheet with the target name already exists
    query = f"name='{group_name}_members' and mimeType='application/vnd.google-apps.spreadsheet' and '{group_id}' in parents"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    sheets = results.get('files', [])

    if sheets:
        valuesFromSheet = get_values_from_spreadsheet(service, sheets[0]['id'])
        valuesToSheet = get_values_for_spreadsheet(members)
        if (valuesFromSheet != valuesToSheet):
          create_new_tab_member_file_google_sheet(service, group_id, group_name, members, sheets)
        else:
          print(f"Spreadsheet {group_name}_members already exists and is up to date.")
    else:
        create_new_member_file_google_sheet(service, group_id, group_name, members)
                
def create_new_member_file_google_sheet(service, group_id, group_name, members):
    # If the spreadsheet does not exist, create a new one
    sheet_metadata = {
        'name': f"{group_name}_members",
        'mimeType': 'application/vnd.google-apps.spreadsheet',
        'parents': [group_id]
    }
    sheet = service.files().create(body=sheet_metadata, fields='id').execute()
    sheet_id = sheet['id']
    
    # Rename the default tab to "Members"
    sheets_service = build('sheets', 'v4', credentials=service._http.credentials)
    rename_tab_body = {
        "requests": [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": 0,  # Default sheet ID is 0
                        "title": "Members"
                    },
                    "fields": "title"
                }
            }
        ]
    }
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body=rename_tab_body
    ).execute()
    
    # Prepare data for the Google Sheet
    values = get_values_for_spreadsheet(members)

    # Update the Google Sheet with the member data
    body = {
        'values': values
    }
    range_name = 'Members!A1'
    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption='RAW',
        body=body
    ).execute()
    
    print(f"Created new spreadsheet: {group_name}_members in group folder: {group_name}")


def get_values_for_spreadsheet(members):
    # Prepare data for the Google Sheet
    values = [['Name', 'Email']]
    for member in members:
        values.append([member['student_name'], member['email']])
    return values

def create_new_tab_member_file_google_sheet(service, group_id, group_name, members, sheets):
    # If the spreadsheet exists, add a new tab with the member data
    sheet_id = sheets[0]['id']
    sheets_service = build('sheets', 'v4', credentials=service._http.credentials)
    
    new_tab_name = "Members"

    # Determine number of existing tabs
    existing_tabs = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing_tabs = existing_tabs.get('sheets', [])
    existing_tab_names = [tab['properties']['title'] for tab in existing_tabs]
    
    # Ensure the new tab name is unique
    version = 1;
    new_tab_name = f"Members_{version}"
    while new_tab_name in existing_tab_names:
        version += 1
        new_tab_name = f"Members_{version}"
    
    # Create a new tab with a unique name
    add_sheet_body = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": new_tab_name
                    }
                }
            }
        ]
    }
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body=add_sheet_body
    ).execute()
    
    # Prepare data for the new tab
    values = get_values_for_spreadsheet(members)

    
    # Update the new tab with the member data
    body = {
        'values': values
    }
    range_name = f"'{new_tab_name}'!A1"
    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption='RAW',
        body=body
    ).execute()
    
    print(f"Updated existing spreadsheet: {group_name}_members with new tab: {new_tab_name}")


def copy_notebook_file(service, notebook_file_id, new_name, group_id, group_name):
    # Check if a file with the target name already exists in the group folder
    existing_files = list_files_in_folder(service, group_id)
    file_exists = any(file['name'] == new_name for file in existing_files)
    if file_exists:
        print(f"  File {new_name} already exists in {group_name}. Skipping copy.")
        return
    try:
        copy_file(service, notebook_file_id, new_name, group_id)   
        print(f"  Copied {notebook_file_name} to {group_name} as {new_name}")    
    except HttpError as e:
        print(f"  Failed to copy into {group_name}: {e}")  
        
def copy_initial_notebook_file_to_group(service, group_id, group_name, members, notebook_file_id, notebook_file_name):
  print(f"\nCopying notebook file into {group_name}...")

  final_notebook_file_name = notebook_file_name.replace('.ipynb', f'_FINAL.ipynb')
  copy_notebook_file(service, notebook_file_id, final_notebook_file_name, group_id, group_name)
  for member in members:
    name_with_underscores = member['student_name'].replace(' ', '_')
    new_name = notebook_file_name.replace('.ipynb', f'_{name_with_underscores}.ipynb')
    copy_notebook_file(service, notebook_file_id, new_name, group_id, group_name)
 
def make_group_folders(service, group_dict, notebook_file_id, notebook_file_name, PROJECTS_FOLDER_NAME, filter=None, GROUP_CATEGORY_ID=None):

    # Step 1: Create the parent Projects folder
    parent_folder_id = create_folder(service, PROJECTS_FOLDER_NAME)

    # Step 2: Create group folders and assign permissions
    group_folders = {}

    print(f"Filter: {filter}")
    groups = list(group_dict.keys())
    groups.sort()
    for group in groups:
        value = group_dict[group]

        if group == "":
            print(f"Skipping group {group} as it has no name.")
            names = [member['student_name'] for member in value['members']]
            print(f"This group has the following members: {names}")
            continue

        if filter and group not in filter:
            print(f"Skipping group {group} as it is not in the filter list.")
            continue
        
        print(f"Creating folder for group: {group}...")

        group_id = create_folder(service, group, parent_folder_id)
        group_dict[group]['folder_url'] = f"https://drive.google.com/drive/folders/{group_id}"

        # Give this user write access to the group folder
        for student in value['members']:
            email = student['email']
            share_folder(service, group_id, email)
            
        create_or_update_member_file_google_sheet(service, group_id, group, value['members'])
        copy_initial_notebook_file_to_group(service, group_id, group, value['members'], notebook_file_id, notebook_file_name)
        

    # Output the group dictionary to a CSV file
    output_file = f'group_folders_{GROUP_CATEGORY_ID}.csv'
    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ['Group Name', 'Folder URL']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for group_name, group_info in group_dict.items():
            writer.writerow({'Group Name': group_name, 'Folder URL': group_info['folder_url']})

    print(f"Done. Output saved to {output_file}.")


def find_folder_id(service, name, parent_id=None):
    """Find a folder by name and optionally parent folder ID."""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    folders = results.get('files', [])
    return folders[0]['id'] if folders else None

def list_files_in_folder(service, folder_id):
    """List files and folders in a folder."""
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        spaces='drive',
        fields='files(id, name, mimeType)'
    ).execute()
    return results.get('files', [])

def copy_file(service, file_id, new_name, parent_id):
    """Copy a file into a folder."""
    copied_file = {
        'name': new_name,
        'parents': [parent_id]
    }
    return service.files().copy(fileId=file_id, body=copied_file).execute()


def get_notebook_file_id_and_name(service, PROJECTS_FOLDER_NAME):
  # Step 1: Find the Projects folder
    projects_id = find_folder_id(service, PROJECTS_FOLDER_NAME)
    if not projects_id:
        raise Exception("Projects folder not found.")

    # Step 2: Find the 'Initial Contents' folder inside Projects
    initial_id = find_folder_id(service, 'Initial Contents', parent_id=projects_id)
    if not initial_id:
        raise Exception(f"'Initial Contents' folder not found inside {PROJECTS_FOLDER_NAME}.")

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
        if file['name'].endswith('.ipynb'):
            notebook_file_name = file['name']
            notebook_file_id = file['id']
            print(f"Found notebook file: {notebook_file_name} in Initial Contents folder.")
            
        
    if not notebook_file_name:
        raise Exception(f"No notebook file (.ipynb) found inside 'Initial Contents' folder.")
    
    return (notebook_file_id, notebook_file_name)
 

def csv_to_dict(filename):
    data_dict = {}
    with open(filename, 'r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            key = row[csv_reader.fieldnames[0]]
            data_dict[key] = row
    return data_dict

def make_group_dictionary(group_data):
    group_dict = {}
    for row in group_data.values():
        group_name = row['group_name']
        if group_name not in group_dict:
            group_dict[group_name] = { 'folder_url': '', 'members': [] }
        group_dict[group_name]['members'].append(row)
    return group_dict

def sort_key(folder):
    # Extract the number from the folder name
    # Assuming the folder name is in the format "Group X"
    try:
        return int(folder['name'].split(' ')[1])
    except (IndexError, ValueError):
        return float('inf')  # If it doesn't match, sort it to the end

def scan_group_folders(service, drive_activity_service, PROJECTS_FOLDER_NAME):
    
    # Step 1: Find the Projects folder
    
    projects_id = find_folder_id(service, PROJECTS_FOLDER_NAME)
    if not projects_id:
        raise Exception("Projects folder not found.")

    # Step 2: Iterate over all folders in the Projects folder
    results = service.files().list(
        q=f"'{projects_id}' in parents and mimeType='application/vnd.google-apps.folder'",
        spaces='drive',
        fields='files(id, name)'
    ).execute()
    folders = results.get('files', [])

    pprint(folders)
    
    

    # Sort the folders by name
    folders.sort(key=sort_key)
    
    for folder in folders:
        if folder['name'] in [INITIAL_PROJECTS_FOLDER_NAME, "data"]:
            continue
        
        if folder['name'].startswith('Midterm'):
            continue
        
    
        # Look for a folder inside each folder called "OLD"
        # If it does not exist, create it
        old_folder_id = find_folder_id(service, 'EXTRA', parent_id=folder['id'])
        if not old_folder_id:
            old_folder_id = create_folder(service, 'EXTRA', parent_id=folder['id'])
            print(f"Created EXTRA folder in {folder['name']}")
        else:
            print(f"EXTRA folder already exists in {folder['name']}")
    
        folder_id = folder['id']
        folder_name = folder['name']
        print(f"Folder: {folder_name} (ID: {folder_id})")
        # Step 3: List all files in the folder
        files = list_files_in_folder(service, folder_id)
        for file in files:
            file_id = file['id']
            file_name = file['name']
            print(f"  File: {file_name} (ID: {file_id})")
            if file_name.endswith('UNTOUCHED.ipynb'):   
                # If the file name ends with _UNTOUCHED.ipynb, move it into the OLD folder
                # Move the file into the OLD folder
                service.files().update(
                    fileId=file_id,
                    addParents=old_folder_id,
                    removeParents=folder_id,
                    fields='id, parents'
                ).execute()
                print(f"  Moved {file_name} to EXTRA folder in {folder_name}.")
                time.sleep(1)
            else:
                 # Get history of the file
                time.sleep(3)
                file_editors = list_editors( drive_activity_service, file_id)
                pprint(file_editors)
                if (len(file_editors) == 1) and file_editors[0]['display_name'] == 'Phill Conrad':
                    # rename file by appending _UNTOUCHED before .ipynb
                    new_file_name = file_name.replace('.ipynb', '_UNTOUCHED.ipynb')
                    service.files().update(fileId=file_id, body={'name': new_file_name}).execute()
                    print(f"  Renamed {file_name} to {new_file_name} in {folder_name}.")
                    time.sleep(1)
                    
        print("\n")
        
def authorize_drive_activity_api():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('driveactivity', 'v2', credentials=creds)


def get_credentials():
    creds = None
    if os.path.exists('token.pkl'):
        with open('token.pkl', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.pkl', 'wb') as token:
            pickle.dump(creds, token)
    return creds

def resolve_person_name(people_service, person_resource_name):
    try:
        person = people_service.people().get(
            resourceName=person_resource_name,
            personFields='names,emailAddresses'
        ).execute()
        
        names = person.get('names', [])
        emails = person.get('emailAddresses', [])

        display_name = names[0]['displayName'] if names else 'Unknown'
        email = emails[0]['value'] if emails else 'No email'
        return { 'display_name': display_name, 'email': email, 'person_resource_name': person_resource_name }

    except Exception as e:
        return { 'display_name': None, 'email': None , 'person_resource_name': person_resource_name, 'error': str(e) }

def list_editors(activity_service, file_id):
    creds = get_credentials()
    
    # Create the correct services
    people_service = build('people', 'v1', credentials=creds)

    response = activity_service.activity().query(body={
        "itemName": f"items/{file_id}",
        "filter": "detail.action_detail_case:EDIT"
    }).execute()

    editors = set()
    for activity in response.get('activities', []):
        for actor in activity.get('actors', []):
            known_user = actor.get('user', {}).get('knownUser', {})
            if known_user:
                editors.add(known_user.get('personName'))

    
    names = list(map(lambda person_id: resolve_person_name(people_service, person_id), editors))
    return names


if __name__ == '__main__':
    
    MIDTERM_GROUP_SET_ID = "22640"  # You can get this from the URL in Canvas (for midterm groups)
    WEEK4_GROUP_SET_ID = "22633"  # You can get this from the URL in Canvas (for week4 groups)

    
    (PROJECTS_FOLDER_NAME, GROUP_CATEGORY_ID) = ('cs5a-s25-ic12', WEEK4_GROUP_SET_ID)
    # (PROJECTS_FOLDER_NAME, GROUP_CATEGORY_ID) = ('cs5a-s25-midterm', MIDTERM_GROUP_SET_ID)
    
    
    service = authenticate()
    drive_activity_service = authorize_drive_activity_api()
    
    # group_data = csv_to_dict(f"group_export_{GROUP_CATEGORY_ID}.csv")
    
    # group_dict = make_group_dictionary(group_data)
    
    # parent_folder_id = create_folder(service, PROJECTS_FOLDER_NAME)
    # (notebook_file_id, notebook_file_name) = get_notebook_file_id_and_name(service, PROJECTS_FOLDER_NAME)
    # make_group_folders(service, group_dict, notebook_file_id, notebook_file_name,  PROJECTS_FOLDER_NAME, filter=None, GROUP_CATEGORY_ID=GROUP_CATEGORY_ID)
    

    scan_group_folders(service, drive_activity_service, PROJECTS_FOLDER_NAME)
    
    
