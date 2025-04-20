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
