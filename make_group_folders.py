import pandas as pd
import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Define the required scopes
SCOPES = ['https://www.googleapis.com/auth/drive']
PROJECTS_FOLDER_NAME = 'CS5A S25 ic10 test 5'
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
    if folders:
        return folders[0]['id']
    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id] if parent_id else []
    }
    folder = service.files().create(body=metadata, fields='id').execute()
    return folder['id']

# Share folder with email
def share_folder(service, file_id, email):
    permission = {
        'type': 'user',
        'role': 'writer',
        'emailAddress': email
    }
    service.permissions().create(
        fileId=file_id,
        body=permission,
        fields='id',
        sendNotificationEmail=False
    ).execute()

def make_folders():
    service = authenticate()

    df = pd.read_csv('canvas_group_export.csv')  # CSV with columns: email, group
    df['folder_link'] = ''

    # Step 1: Create the parent Projects folder
    parent_folder_id = create_folder_1(service, PROJECTS_FOLDER_NAME)

    # Step 2: Create group folders and assign permissions
    group_folders = {}

    for index, row in df.iterrows():
        email, group = row['Email'], row['Group Name']
        if group not in group_folders:
            group_id = create_folder_1(service, group, parent_folder_id)
            group_folders[group] = group_id
        else:
            group_id = group_folders[group]
        
        share_folder(service, group_id, email)

        folder_link = f"https://drive.google.com/drive/folders/{group_id}"
        df.at[index, 'folder_link'] = folder_link

    # Step 3: Export updated CSV
    df.to_csv('output_with_links.csv', index=False)
    print("Done. Output saved to 'output_with_links.csv'.")

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

    # Step 3: Get list of all group folders (excluding 'Initial Contents')
    folders = service.files().list(
        q=f"'{projects_id}' in parents and mimeType='application/vnd.google-apps.folder' and name != 'Initial Contents'",
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




if __name__ == '__main__':
    make_folders()
    copy_initial_contents_to_groups()
