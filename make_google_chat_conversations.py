# This script creates Google Chat spaces for each group of students, invites them, and sends a welcome message.
# It uses the Google Chat API and requires OAuth2 authentication.
# Make sure to have the required libraries installed:
# pip install google-auth google-auth-oauthlib requests
# Ensure you have the OAuth2 client file (oauth2_client.json) and token file (token.json) in the same directory.
# The script reads a CSV file with student emails and a text file with staff emails.
# The CSV file should have a header with 'group_name' and 'email' columns.
# The staff file should have one email per line.
# The script creates a space for each group, invites the students and staff, and sends a welcome card.
# The welcome card includes a message and an image.
# The script handles errors and prints messages to indicate the status of each operation.
# The script is designed to be run in a Python environment with access to the internet.
# The script is intended for educational purposes and should be used responsibly.
# Note: The Google Chat API has usage limits and quotas. Make sure to check the documentation for details.
# The script is provided as-is and the author is not responsible for any issues that may arise from its use.
# The script is intended for educational purposes and should be used responsibly.


SLEEP=2.0  # seconds

import csv
import json
import os
import time
import sys
from pprint import pprint

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import google.auth
import requests

# --- Config ---
OAUTH_CLIENT_FILE = 'credentials.json'
TOKEN_FILE = 'token_chat.json'
SCOPES = [
    'https://www.googleapis.com/auth/chat.memberships',
    'https://www.googleapis.com/auth/chat.spaces',
    'https://www.googleapis.com/auth/contacts.readonly',
    'https://www.googleapis.com/auth/chat.messages'
]

STAFF_FILE = 'staff.txt'
ACTIVITY_NAME = 'CS5A S25 Wk4'


def group_name_filter(group_name):
    return group_name.replace("Week-4-Lecture-Group ", "Group ")

def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        print(f"Token file {TOKEN_FILE} exists. Loading...")
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if not set(SCOPES).issubset(set(creds.scopes)):
            print("⚠️ Token does not have the required scopes. Re-authenticating...")
            creds = None
            
        
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            print("Token saved to %s\n", TOKEN_FILE)
    
    
    return creds


def get_welcome_card_text(session, space_name, group_display_name, group_folders, group_name):
    group_folder_url = group_folders[group_name]['folder_url']
    
    return f"""
           This chat channel is for your group: {group_display_name}
           
           Your group folder is at this link: {group_folder_url}
           
           You should find files with your own name in that folder,
           as well as a FINAL file.
           
           Do your own work in the file with your name. 
            
           (If there is more than one file with your name, any of them is fine; 
           we suggest the "_0.ipynb" version is probably the best if you haven't
           started on one yet.)
            
           There should also be a FINAL file.  You need to 
           coordinate with your fellow team members to update that 
           file.  You can use this chat (or any other way of communicating,
           such as "being in the same room") to make sure only one person
           edits that at a time.
           """




def send_welcome_card(session, space_name, group_display_name, group_folders, group_name, text):
    group_folder_url = group_folders[group_name]['folder_url']

    print(f"Group folder URL: {group_folder_url}")
    print(f"Group display name: {group_display_name}")
    
    message_url = f"https://chat.googleapis.com/v1/{space_name}/messages"
    
    text_payload = {
        "text": text
    }

    resp = session.post(message_url, json=text_payload)
    if resp.status_code != 200:
        print(f"⚠️ Failed to send welcome message to {group_display_name}: {resp.text}")
    else:
        print(f"✅ Sent welcome message to {group_display_name}")

def get_existing_space(session, display_name):
    print(f"Display name: {display_name}")
    existing_spaces = get_existing_spaces(session)
    for space in existing_spaces:
        if space.get('displayName') == display_name:
            return space
    return None
    

def list_all_spaces_with_display_names(session: requests.Session):
    list_url = 'https://chat.googleapis.com/v1/spaces'
    params = {
        'pageSize': 100
    }

    all_spaces = []

    while True:
        response = session.get(list_url, params=params)
        if response.status_code != 200:
            print(f"⚠️ Failed to list spaces: {response.status_code} {response.text}")
            break

        data = response.json()
        all_spaces.extend(data.get('spaces', []))

        if 'nextPageToken' in data:
            params['pageToken'] = data['nextPageToken']
        else:
            break

    return all_spaces


def get_existing_spaces(session):
    """Fetch and cache all existing spaces."""
    if not hasattr(get_existing_spaces, "_cache"):
        get_existing_spaces._cache = None

    if get_existing_spaces._cache is not None:
        return get_existing_spaces._cache
    
    all_spaces = list_all_spaces_with_display_names(session)
    
    get_existing_spaces._cache = all_spaces
    return all_spaces

def create_new_space(session, space_display_name):
    create_space_payload = {
        "spaceType": "SPACE",
        "displayName": space_display_name
    }
    resp = session.post('https://chat.googleapis.com/v1/spaces', json=create_space_payload)
    if resp.status_code != 200:
        print(f"❌ Failed to create space {space_display_name}: {resp.text}")
        return None

    space = resp.json()
    space_name = space['name']
    print(f"🚀 Created space {space_display_name}: {space_name}")
    return space

def get_existing_members_emails(session, space):
    members_url = f"https://chat.googleapis.com/v1/{space['name']}/members"
    members_resp = session.get(members_url)
    if members_resp.status_code != 200:
        print(f"⚠️ Failed to get members for {space['displayName']}: {members_resp.text}")
        return None
    existing_members = members_resp.json().get('memberships', [])
    
    pprint(existing_members)
    # Extract user IDs from the member data
    user_ids = []
    for member in existing_members:
        member_info = member.get('member', {})
        user_id = member_info.get('name', '').split('/')[-1]
        if user_id:
            user_ids.append(user_id)
    
    pprint(user_ids)
    # Use People API to fetch emails for the user IDs
    emails = []
    for user_id in user_ids:
        people_url = f"https://people.googleapis.com/v1/people/{user_id}?personFields=emailAddresses"
        people_resp = session.get(people_url)
        if people_resp.status_code != 200:
            print(f"⚠️ Failed to get email for user {user_id}: {people_resp.text}")
            continue
        person_data = people_resp.json()
        email_addresses = person_data.get('emailAddresses', [])
        for email_entry in email_addresses:
            email_entry = email_entry.get('value')
            if email_entry and email_entry.endswith('@ucsb.edu'):
                emails.append(email_entry)
    pprint(emails)
    return emails

def get_group_folders(GROUP_CATEGORY_ID):
    
    
    input_file = f'group_folders_{GROUP_CATEGORY_ID}.csv'

    group_folders = {}
    with open(input_file, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            group_name = row['Group Name']
            folder_url = row['Folder URL']
            group_folders[group_name] = { "folder_url": folder_url }
    return group_folders

def add_group_chat_urls_to_group_folder(session, group_folders):
    """Add group chat URLs to the group folders."""
    for group_name in group_folders.keys():
        space_display_name = get_space_name_from_group_name(group_name)
        space = get_existing_space(session, space_display_name)
        if not space:
            print(f"❌ Space {space_display_name} not found.")
            continue
        space_url = "https://chat.google.com/room/" + space['name'].split('/')[1]
        group_folders[group_name]['space_name'] = space['name']
        group_folders[group_name]['space_display_name'] = space['displayName']
        group_folders[group_name]['space_url'] = space_url
    return group_folders
        
       
    
def get_recent_messages(session, space):
    messages_url = f"https://chat.googleapis.com/v1/{space['name']}/messages"
    params = {
        'pageSize': 10,
        'orderBy': 'createTime desc'
    }
    resp = session.get(messages_url, params=params)
    if resp.status_code != 200:
        print(f"⚠️ Failed to get recent messages for {space['displayName']}: {resp.text}")
        return None
    messages = resp.json().get('messages', [])
    return messages

def folder_name_sort_key(folder_name):
    # Extract the number from the folder name
    # Assuming the folder name is in the format "Group X"
    
    try:
        return int(folder_name.split(' ')[1])
    except (IndexError, ValueError):
        return float('inf')  # If it doesn't match, sort it to the end


def get_space_name_from_group_name(group_name):
    space_display_name = f"{ACTIVITY_NAME} - {group_name}"
    space_display_name = group_name_filter(space_display_name)
    return space_display_name


def get_session():
    creds = authenticate()
    session = requests.Session()
    session.headers.update({'Authorization': f'Bearer {creds.token}'})
    return session
    
# --- Main Script ---
def main(session, group_folders, STUDENT_CSV):
      
    
    # Read students
    groups = {}
    with open(STUDENT_CSV, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            group_name = row['group_name']
            if group_name not in groups:
                groups[group_name] = []
            groups[group_name].append(row['email'])
    
    # Read staff
    with open(STAFF_FILE) as f:
        staff_emails = [line.strip() for line in f if line.strip()]
    
    group_names = list(groups.keys())
    print(f"Groups: {group_names}")
    
    
    group_names.sort(key=folder_name_sort_key)
    print(f"Sorted groups: {group_names}")
    
    # Process each group
    for group_name in group_names:
        if group_name == "":
            continue

        try:
            group_number = int(group_name.split(' ')[1])
        except (IndexError, ValueError):
            print(f"⚠️ Invalid group name format: {group_name}")
            continue
   

        student_emails = groups[group_name]
        space_display_name = get_space_name_from_group_name(group_name)
        print(f"🔄 Processing group: {space_display_name}")
        
        # Check if space already exists
        search_url = "https://chat.googleapis.com/v1/spaces"
        
        space = get_existing_space(session, space_display_name)

        if space:
            print(f"✅ Space {space_display_name} already exists.")
        else:
            # Create space
            space = create_new_space(session, space_display_name)
            if not space:
                print(f"❌ Failed to create space {space_display_name}.")
                sys.exit(0)

        
      
        
        # Get existing members
        existing_members_list = get_existing_members_emails(session, space)   
        print(f"Existing members: {existing_members_list}")
   
      
        # Invite members
        all_emails = student_emails + staff_emails
        for email in all_emails:
            if email in existing_members_list:
                print(f"✅ {email} already in {space_display_name}.")
                continue
            print(f"🔄 Inviting {email} to {space_display_name}...")
            member_payload = {
                "member": {
                    "name": f"users/{email}",
                    "type": "HUMAN"
                }
            }
            invite_url = f"https://chat.googleapis.com/v1/{space['name']}/members"
            r = session.post(invite_url, json=member_payload)
            
            if r.status_code != 200:
                print(f"⚠️ Failed to add {email} to {space['displayName']}: {r.text}")
            else:
                print(f"➕ Added {email} to {space['displayName']}")
 
            time.sleep(SLEEP)  # Respect rate limits


        welcome_card_text = get_welcome_card_text(session, space['name'], space['displayName'], group_folders, group_name)


       
        # Send a welcome card unless we've already sent one
        
        welcome_text = get_welcome_card_text(session, space['name'], space['displayName'], group_folders, group_name)

        
        recent_messages = get_recent_messages(session, space)
        
        sent = False
        for message in recent_messages:
            if message.get('text') == welcome_text:
                print(f"✅ Welcome message already sent to {space['displayName']}.")
                sent = True
                break
        
        if not sent:
            print(f"🔄 Sending welcome message to {space['displayName']}...")
            send_welcome_card(session, space['name'], space['displayName'], group_folders, group_name, welcome_text)
            time.sleep(SLEEP)  # Respect rate limits

    print("✅ All groups processed successfully.")


def write_group_folders(group_folders, GROUP_CATEGORY_ID):
    
        # Output the group dictionary to a CSV file
    output_file = f'group_folders_with_chat_groups_{GROUP_CATEGORY_ID}.csv'
        
    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ['Group Name', 'Folder URL', 'Space Name', 'Space Display Name', 'Space URL']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for group_name, data in group_folders.items():
            writer.writerow({
                'Group Name': group_name,
                'Folder URL': data['folder_url'],
                'Space Name': data.get('space_name', ''),
                'Space Display Name': data.get('space_display_name', ''),
                'Space URL': data.get('space_url', '')
            })
    print(f"✅ Group folders written to {output_file}")

if __name__ == "__main__":
    
    MIDTERM_GROUP_SET_ID = "22640"  # You can get this from the URL in Canvas (for midterm groups)
    WEEK4_GROUP_SET_ID = "22633"  # You can get this from the URL in Canvas (for week4 groups)

    
    (PROJECTS_FOLDER_NAME, GROUP_CATEGORY_ID) = ('cs5a-s25-ic12', WEEK4_GROUP_SET_ID)
    # (PROJECTS_FOLDER_NAME, GROUP_CATEGORY_ID) = ('cs5a-s25-midterm', MIDTERM_GROUP_SET_ID)
  
    
    STUDENT_CSV =f'group_export_{GROUP_CATEGORY_ID}.csv'

    
    session = get_session()
    group_folders = get_group_folders(GROUP_CATEGORY_ID)
    print(f"Group folders: {group_folders}")
    #main(session, group_folders, STUDENT_CSV=STUDENT_CSV)
    add_group_chat_urls_to_group_folder(session, group_folders)
    
    write_group_folders(group_folders, GROUP_CATEGORY_ID)