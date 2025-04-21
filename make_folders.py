import pandas as pd
import os
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Define the required scopes
SCOPES = ['https://www.googleapis.com/auth/drive']
PROJECTS_FOLDER_NAME = 'CS5A S25 ic10 test 3'

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

def main():
    service = authenticate()

    df = pd.read_csv('input.csv')  # CSV with columns: email, group
    df['folder_link'] = ''

    # Step 1: Create the parent Projects folder
    parent_folder_id = create_folder(service, PROJECTS_FOLDER_NAME)

    # Step 2: Create group folders and assign permissions
    group_folders = {}

    for index, row in df.iterrows():
        email, group = row['email'], row['group']
        if group not in group_folders:
            group_id = create_folder(service, group, parent_folder_id)
            group_folders[group] = group_id
        else:
            group_id = group_folders[group]
        
        share_folder(service, group_id, email)

        folder_link = f"https://drive.google.com/drive/folders/{group_id}"
        df.at[index, 'folder_link'] = folder_link

    # Step 3: Export updated CSV
    df.to_csv('output_with_links.csv', index=False)
    print("Done. Output saved to 'output_with_links.csv'.")

if __name__ == '__main__':
    main()