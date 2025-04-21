# ChatGpt session

## Prompt


I have a CSV file of  email addresses, each of which is associated with a Google Drive account, and a group name (e.g. group01, group02, etc.).

I want to write some Python code that will create a folder on Google Drive for each of these groups, inside a base folder called "Projects".   I want the code to then give each email addresses read/write access to each folder that was created.

I then want a CSV that has a list of each students email address in column 1, their group name in column 2, and a link to their Google Drive folder in column three.

Please help me to set up the necessary Google API credentials and write the necessary python code.


## Results

### ✅ Step 1: Set up Google Drive API Access

* Go to the Google Cloud Console:
    * Create a new project or use an existing one.
* Enable the Google Drive API:
    * In the left menu, go to APIs & Services > Library.
    * Search for Google Drive API and enable it.
* Create OAuth 2.0 Credentials:
    * Go to APIs & Services > Credentials.
    * Click Create Credentials > OAuth client ID.
    * Choose Desktop App or Web Application (for local scripts, Desktop is fine).
    * Download the JSON credentials file and rename it to something like credentials.json.
* Install the required Python libraries:

```
pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib pandas
```

## ✅ Step 2: Python Script

This script does the following:

* Reads a CSV with columns: email, group
* Creates a folder for each group (if it doesn't already exist) inside a parent folder ("Projects")
* Shares each folder with the relevant students
* Exports a new CSV with folder links

```python
import pandas as pd
import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Define the required scopes
SCOPES = ['https://www.googleapis.com/auth/drive']

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

    # Step 1: Create the parent "Projects" folder
    parent_folder_id = create_folder(service, 'Projects')

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
```


### ✅ Step 3: Folder Structure on Drive

The script will create:

```
Projects/
│
├── group01/
├── group02/
└── group03/
```

Each folder is shared with the respective students based on their group membership.

## Additiionl Prompt

Can you add a second script that works with the same framework, but will copy all of the files from a folder called "Initial Contents" that is inside the "Projects" folder into each of the other folders?

### Response

Absolutely! Here’s a second script that uses the same authentication framework and builds on the existing Drive folder structure. This script will:

1. Look for a folder named "Initial Contents" inside the "Projects" folder.
2. Copy all files from "Initial Contents" into each group folder inside "Projects".

```python
from googleapiclient.errors import HttpError

def find_folder_id(service, name, parent_id=None):
    """Find a folder by name and optionally parent folder ID."""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    folders = results.get('files', [])
    return folders[0]['id'] if folders else None

def list_files_in_folder(service, folder_id):
    """List files in a folder."""
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        spaces='drive',
        fields='files(id, name)'
    ).execute()
    return results.get('files', [])

def copy_file(service, file_id, new_name, parent_id):
    """Copy a file into a new folder."""
    copied_file = {
        'name': new_name,
        'parents': [parent_id]
    }
    return service.files().copy(fileId=file_id, body=copied_file).execute()

def copy_initial_contents_to_groups():
    service = authenticate()

    # Step 1: Find the Projects folder
    projects_id = find_folder_id(service, 'Projects')
    if not projects_id:
        raise Exception("Projects folder not found.")

    # Step 2: Find the 'Initial Contents' folder inside Projects
    initial_id = find_folder_id(service, 'Initial Contents', parent_id=projects_id)
    if not initial_id:
        raise Exception("'Initial Contents' folder not found inside 'Projects'.")

    # Step 3: Get list of all group folders (excluding 'Initial Contents')
    folders = service.files().list(
        q=f"'{projects_id}' in parents and mimeType='application/vnd.google-apps.folder' and name != 'Initial Contents'",
        fields='files(id, name)'
    ).execute().get('files', [])

    # Step 4: Get files to copy
    files_to_copy = list_files_in_folder(service, initial_id)

    if not files_to_copy:
        print("No files found in 'Initial Contents' to copy.")
        return

    # Step 5: Copy files to each group folder
    for folder in folders:
        group_name = folder['name']
        group_id = folder['id']
        print(f"\nCopying files to {group_name}...")

        for file in files_to_copy:
            try:
                copy_file(service, file['id'], file['name'], group_id)
                print(f"  Copied: {file['name']}")
            except HttpError as e:
                print(f"  Failed to copy {file['name']}: {e}")

    print("\n✅ All files copied to group folders.")

if __name__ == '__main__':
    copy_initial_contents_to_groups()
```

📝 Notes

This script skips the "Initial Contents" folder when copying to groups.

If you re-run this script, it will re-copy files without overwriting unless names collide.

You can add logic to check for duplicate filenames before copying if needed.

Let me know if you'd like a version that logs what it copied, avoids duplicates, or handles subfolders recursively too.

## Follow up prompt

Please update the script so that it will copy subfolders "Initial Contents" recursively

### Response

Great — here's the updated script that recursively copies the entire contents of the "Initial Contents" folder (including all subfolders and files) into each group folder inside the "Projects" folder.

This involves:

* Detecting if a file is a folder or not.
* Creating subfolders recursively in the target group folder.
* Copying files into their respective subfolder structure.

```python
from googleapiclient.errors import HttpError

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

def create_folder(service, name, parent_id):
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
            new_folder_id = create_folder(service, name, dest_parent_id)
            # Recurse into subfolder
            copy_folder_recursive(service, item['id'], new_folder_id)
        else:
            # Copy file
            copy_file(service, item['id'], name, dest_parent_id)

def copy_initial_contents_to_groups():
    service = authenticate()

    # Step 1: Find the Projects folder
    projects_id = find_folder_id(service, 'Projects')
    if not projects_id:
        raise Exception("Projects folder not found.")

    # Step 2: Find the 'Initial Contents' folder inside Projects
    initial_id = find_folder_id(service, 'Initial Contents', parent_id=projects_id)
    if not initial_id:
        raise Exception("'Initial Contents' folder not found inside 'Projects'.")

    # Step 3: Get list of all group folders (excluding 'Initial Contents')
    folders = service.files().list(
        q=f"'{projects_id}' in parents and mimeType='application/vnd.google-apps.folder' and name != 'Initial Contents'",
        fields='files(id, name)'
    ).execute().get('files', [])

    # Step 4: Copy recursively into each group folder
    for folder in folders:
        group_name = folder['name']
        group_id = folder['id']
        print(f"\nCopying contents into {group_name}...")
        try:
            copy_folder_recursive(service, initial_id, group_id)
        except HttpError as e:
            print(f"  Failed to copy into {group_name}: {e}")

    print("\n✅ All files and folders copied to group folders.")

if __name__ == '__main__':
    copy_initial_contents_to_groups()
```

🚀 Features

* Recursive folder creation and file copying.
* Keeps the original folder structure from Initial Contents.
* Safe to re-run; it creates new copies every time (it does not check for duplicates).

Let me know if you'd like to add:

* Duplicate detection,
* Email notifications,
* Or logging to a file.

Ready to test this out?