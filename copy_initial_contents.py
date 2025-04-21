from googleapiclient.errors import HttpError

from make_folders import authenticate

INITIAL_PROJECTS_FOLDER_NAME = 'Initial Contents'
from make_folders import PROJECTS_FOLDER_NAME

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
    copy_initial_contents_to_groups()