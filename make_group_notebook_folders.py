
import os
import json
import csv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from pprint import pprint

# Define the required scopes
SCOPES = ['https://www.googleapis.com/auth/drive']
PROJECTS_FOLDER_NAME = 'CS5A S25 ic12 test 4 PLEASE IGNORE'
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
def create_folder_1(service, name, parent_id=None):
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

def create_member_file(service, group_id, group_name, members):
    # Create a CSV file with group members
    output_file = f"{group_name}_members.csv"
    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ['Name', 'Email']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for member in members:
            writer.writerow({'Name': member['Name'], 'Email': member['Email']})
    # Upload the CSV file to the group folder
    file_metadata = {
        'name': output_file,
        'parents': [group_id]
    }
    media = MediaFileUpload(output_file, mimetype='text/csv')
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print(f"Created member file: {output_file} in group folder: {group_name}")

def create_or_update_member_file_google_sheet(service, group_id, group_name, members):
    # Check if a Google Sheet with the target name already exists
    query = f"name='{group_name}_members' and mimeType='application/vnd.google-apps.spreadsheet' and '{group_id}' in parents"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    sheets = results.get('files', [])

    if sheets:
        create_new_tab_member_file_google_sheet(service, group_id, group_name, members, sheets)
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
    
    # Prepare data for the Google Sheet
    values = [['Name', 'Email']]
    for member in members:
        values.append([member['Name'], member['Email']])
    
    # Update the Google Sheet with the member data
    body = {
        'values': values
    }
    range_name = 'Sheet1!A1'
    sheets_service = build('sheets', 'v4', credentials=service._http.credentials)
    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_name,
        valueInputOption='RAW',
        body=body
    ).execute()
    
    print(f"Created new spreadsheet: {group_name}_members in group folder: {group_name}")

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
    values = [['Name', 'Email']]
    for member in members:
        values.append([member['Name'], member['Email']])
    
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
    name_with_underscores = member['Name'].replace(' ', '_')
    new_name = notebook_file_name.replace('.ipynb', f'_{name_with_underscores}.ipynb')
    copy_notebook_file(service, notebook_file_id, new_name, group_id, group_name)
 
def make_group_folders(service, group_dict, notebook_file_id, notebook_file_name):

    # Step 1: Create the parent Projects folder
    parent_folder_id = create_folder_1(service, PROJECTS_FOLDER_NAME)

    # Step 2: Create group folders and assign permissions
    group_folders = {}


    for group, value in group_dict.items():
        print(f"\nCreating folder for group: {group}...")
        group_id = create_folder_1(service, group, parent_folder_id)
        group_dict[group]['folder_url'] = f"https://drive.google.com/drive/folders/{group_id}"

        # Give this user write access to the group folder
        for student in value['members']:
            email = student['Email']
            share_folder(service, group_id, email)
            
        create_or_update_member_file_google_sheet(service, group_id, group, value['members'])
        copy_initial_notebook_file_to_group(service, group_id, group, value['members'], notebook_file_id, notebook_file_name)
        

    # Output the group dictionary to a CSV file
    output_file = 'group_folders.csv'
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

def create_folder_2(service, name, parent_id):
    """Create a folder and return its ID."""
    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    folder = service.files().create(body=metadata, fields='id').execute()
    return folder['id']

def copy_file(service, file_id, new_name, parent_id):
    """Copy a file into a folder."""
    copied_file = {
        'name': new_name,
        'parents': [parent_id]
    }
    return service.files().copy(fileId=file_id, body=copied_file).execute()

def copy_folder_recursive(service, source_folder_id, dest_parent_id):
    """Recursively copy the contents of a folder."""
    items = list_files_in_folder(service, source_folder_id)
    for item in items:
        name = item['name']
        if item['mimeType'] == 'application/vnd.google-apps.folder':
            # Create subfolder in destination
            new_folder_id = create_folder_2(service, name, dest_parent_id)
            # Recurse into subfolder
            copy_folder_recursive(service, item['id'], new_folder_id)
        else:
            # Copy file
            copy_file(service, item['id'], name, dest_parent_id)


def copy_initial_contents_to_groups():
    service = authenticate()

    # Step 1: Find the Projects folder
    projects_id = find_folder_id(service, PROJECTS_FOLDER_NAME)
    if not projects_id:
        raise Exception("Projects folder not found.")

    # Step 2: Find the 'Initial Contents' folder inside Projects
    initial_id = find_folder_id(service, 'Initial Contents', parent_id=projects_id)
    if not initial_id:
        raise Exception(f"'Initial Contents' folder not found inside {PROJECTS_FOLDER_NAME}.")

    # Step 3: Get list of all group folders (excluding 'Initial Contents', 'data)
    folders = service.files().list(
        q=f"'{projects_id}' in parents and mimeType='application/vnd.google-apps.folder' and name != 'Initial Contents' and name != 'data'",
        fields='files(id, name)'
    ).execute().get('files', [])

    # Step 4: Copy recursively into each group folder
    
    for folder in folders:
        if folder['name'] == 'Initial Contents':
            continue
        if folder['name'] == 'data':
            continue
        group_name = folder['name']
        group_id = folder['id']
        print(f"\nCopying contents into {group_name}...")
        try:
            copy_folder_recursive(service, initial_id, group_id)
        except HttpError as e:
            print(f"  Failed to copy into {group_name}: {e}")

    print("\n✅ All files and folders copied to group folders.")
 
 
def get_notebook_file_id_and_name(service):
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
            break
        
    if not notebook_file_name:
        raise Exception(f"No notebook file (.ipynb) found inside 'Initial Contents' folder.")
    
    return (notebook_file_id, notebook_file_name)


def copy_notebook_file_to_groups(service, group_dict):

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
            notebook_file_id - file['id']
            print(f"Found notebook file: {notebook_file_name} in Initial Contents folder.")
            break
        
    if not notebook_file_name:
        raise Exception(f"No notebook file (.ipynb) found inside 'Initial Contents' folder.")
    
    # Step 3: Find the notebook file in the 'Initial Contents' folder
    notebook_file_id = find_folder_id(service, notebook_file_name, parent_id=initial_id)
    if not notebook_file_id:
        raise Exception(f"Notebook file '{notebook_file_name}' not found inside 'Initial Contents' folder.")
    # Step 4: Get list of all group folders (excluding 'Initial Contents', 'data)
    folders = service.files().list(
        q=f"'{projects_id}' in parents and mimeType='application/vnd.google-apps.folder' and name != 'Initial Contents' and name != 'data'",
        fields='files(id, name)'
    ).execute().get('files', [])
    
    # Step 5: Iterate over the group members in the group.
    # For each group member, copy the notebook file into their group folder
    #  renaming it by replacing `.ipynb` with `_{loginId}.ipynb`

    for folder in folders:
        if folder['name'] == 'Initial Contents':
            continue
        if folder['name'] == 'data':
            continue
        group_name = folder['name']
        group_id = folder['id']
        print(f"\nCopying notebook file into {group_name}...")
        for member in group_dict[group_name]['members']:
            # Get the loginId of the group member
            loginId = member['loginId']
            new_name = notebook_file_name.replace('.ipynb', f'_{loginId}.ipynb')
            try:
                copy_file(service, notebook_file_id, new_name, group_id)   
                print(f"  Copied {notebook_file_name} to {group_name} as {new_name}")    
            except HttpError as e:
                print(f"  Failed to copy into {group_name}: {e}")    

    print("\n✅ All files and folders copied to group folders.")
 

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
        group_name = row['Group Name']
        if group_name not in group_dict:
            group_dict[group_name] = { 'folder_url': '', 'members': [] }
        group_dict[group_name]['members'].append(row)
    return group_dict


if __name__ == '__main__':
    service = authenticate()
    group_data = csv_to_dict('canvas_group_export.csv')
    group_dict = make_group_dictionary(group_data)
    parent_folder_id = create_folder_1(service, PROJECTS_FOLDER_NAME)
    (notebook_file_id, notebook_file_name) = get_notebook_file_id_and_name(service)
    make_group_folders(service, group_dict, notebook_file_id, notebook_file_name)
    # copy_notebook_file_to_groups(service, group_dict)
    
    
