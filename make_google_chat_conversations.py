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


SLEEP = 1.1  # seconds

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
import inspect


# --- Config ---
OAUTH_CLIENT_FILE = "credentials.json"
TOKEN_FILE = "token_chat.json"
SCOPES = [
    "https://www.googleapis.com/auth/chat.memberships",
    "https://www.googleapis.com/auth/chat.spaces",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/chat.messages",
]

STAFF_FILE = "staff.txt"
ACTIVITY_NAME = "CS5A S25 Wk4"


def function_name():
    return inspect.stack()[1].function


def called_by():
    return inspect.stack()[2].function


def group_name_filter(group_name):
    if "Week-4-Lecture-Group " in group_name:
        # Remove "Week-4-Lecture-Group " from the group name
        return group_name.replace("Week-4-Lecture-Group ", "Group ")
    if "MidtermProject" in group_name:
        # Remove "MidtermProject" from the group name
        return group_name.replace("MidtermProject", "")
    return group_name


def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        print(f"Token file {TOKEN_FILE} exists. Loading...")
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
            TOKEN_FILE, SCOPES
        )
        if not set(SCOPES).issubset(set(creds.scopes)):
            print("⚠️ Token does not have the required scopes. Re-authenticating...")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
            print(f"Token saved to {TOKEN_FILE}")

    return creds


def get_welcome_text_week4(space_display_name, group_folders, group_name):
    group_folder_url = group_folders[group_name]["folder_url"]

    return f"""
           This chat channel is for your group: {space_display_name}
           
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


def get_group_number_from_group_name(group_name):
    # Extract the group number using an regulat expressions,
    # assuming the group name is in the format: "CS5A S25 Midterm -  3 (W noon)"
    # The group number comes after the first hyphen and before the space.
    # Example: "CS5A S25 Midterm - 3 (W noon)" -> "3"
    import re

    match = re.search(r"\s*(\d+)\s*", group_name)
    if match:
        return int(match.group(1))
    return None


def get_welcome_text_midterm(space_display_name, group_folders, group_name):
    group_folder_url = group_folders[group_name]["folder_url"]

    return f"""
           This chat channel is for your group: {group_name}
           
           Your group folder is at this link: {group_folder_url}
           
           More instructions for using this chat channel will be posted shortly.
           """


def send_message(
    session, space_name, group_display_name, group_folders, group_name, text
):
    group_folder_url = group_folders[group_name]["folder_url"]

    print(f"Group folder URL: {group_folder_url}")
    print(f"Group display name: {group_display_name}")

    message_url = f"https://chat.googleapis.com/v1/{space_name}/messages"

    text_payload = {"text": text}

    resp = session.post(message_url, json=text_payload)
    if resp.status_code != 200:
        print(f"⚠️ Failed to send welcome message to {group_display_name}: {resp.text}")
    else:
        print(f"✅ Sent welcome message to {group_display_name}")


def get_existing_space(session, display_name):
    print(f"Display name: {display_name}")
    existing_spaces = get_existing_spaces(session)
    for space in existing_spaces:
        if space.get("displayName") == display_name:
            return space
    return None


def list_all_spaces_with_display_names(session: requests.Session):
    list_url = "https://chat.googleapis.com/v1/spaces"
    params = {"pageSize": 100}

    all_spaces = []

    while True:
        response = session.get(list_url, params=params)
        if response.status_code != 200:
            print(f"⚠️ Failed to list spaces: {response.status_code} {response.text}")
            break

        data = response.json()
        all_spaces.extend(data.get("spaces", []))

        if "nextPageToken" in data:
            params["pageToken"] = data["nextPageToken"]
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
    time.sleep(SLEEP)  # Respect rate limits
    create_space_payload = {"spaceType": "SPACE", "displayName": space_display_name}
    resp = session.post(
        "https://chat.googleapis.com/v1/spaces", json=create_space_payload
    )
    if resp.status_code != 200:
        print(f"❌ Failed to create space {space_display_name}: {resp.text}")
        return None

    space = resp.json()
    space_name = space["name"]
    print(f"🚀 Created space {space_display_name}: {space_name}")
    return space


def get_person(session, user_id):
    # print(f"{function_name()}, called by {called_by()} Getting person {user_id}")
    people_url = f"https://people.googleapis.com/v1/people/{user_id}?personFields=emailAddresses,names"
    resp = session.get(people_url)
    time.sleep(SLEEP)  # Respect rate limits
    if resp.status_code != 200:
        print(f"⚠️ Failed to get person {user_id}: {resp.text}")
        sys.exit(1)
        return None
    person = resp.json()
    return person


def person_to_name(person):
    if not person:
        return None
    names = person.get("names", [])
    pprint(names)
    sys.exit(0)
    return None


def person_to_ucsb_email(person):
    if not person:
        return None
    email_addresses = person.get("emailAddresses", [])
    for email_entry in email_addresses:
        email_entry = email_entry.get("value")
        if email_entry and email_entry.endswith("@ucsb.edu"):
            return email_entry
    return None


def person_id_to_ucsb_email(session, person_id):
    person = get_person(session, person_id)
    if not person:
        return None
    return person_to_ucsb_email(person)


def person_id_to_name(session, person_id):
    person = get_person(session, person_id)
    if not person:
        return None
    return person_to_name(person)


def get_existing_members_emails(session, space):
    members_url = f"https://chat.googleapis.com/v1/{space['name']}/members"
    members_resp = session.get(members_url)
    if members_resp.status_code != 200:
        print(
            f"⚠️ Failed to get members for {space['displayName']}: {members_resp.text}"
        )
        return None
    existing_members = members_resp.json().get("memberships", [])

    # Extract user IDs from the member data
    user_ids = []
    for member in existing_members:
        member_info = member.get("member", {})
        user_id = member_info.get("name", "").split("/")[-1]
        if user_id:
            user_ids.append(user_id)

    # Use People API to fetch emails for the user IDs
    emails = []
    for user_id in user_ids:
        email_entry = person_id_to_ucsb_email(session, user_id)
        if email_entry:
            emails.append(email_entry)

        # people_url = f"https://people.googleapis.com/v1/people/{user_id}?personFields=emailAddresses"
        # people_resp = session.get(people_url)
        # if people_resp.status_code != 200:
        #     print(f"⚠️ Failed to get email for user {user_id}: {people_resp.text}")
        #     continue
        # person_data = people_resp.json()
        # email_addresses = person_data.get('emailAddresses', [])
        # for email_entry in email_addresses:
        #     email_entry = email_entry.get('value')
        #     if email_entry and email_entry.endswith('@ucsb.edu'):
        #         emails.append(email_entry)

    return emails


def get_group_folders(GROUP_CATEGORY_ID):

    input_file = f"group_folders_{GROUP_CATEGORY_ID}.csv"

    group_folders = {}
    with open(input_file, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            group_name = row["Group Name"]
            folder_url = row["Folder URL"]
            group_folders[group_name] = {"folder_url": folder_url}
    return group_folders


def get_group_folders_with_chat(GROUP_CATEGORY_ID):

    input_file = f"group_folders_with_chat_groups_{GROUP_CATEGORY_ID}.csv"

    group_folders = {}
    with open(input_file, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            group_name = row["Group Name"]
            folder_url = row["Folder URL"]
            group_folders[group_name] = {"folder_url": folder_url}
            group_folders[group_name]["space_name"] = row["Space Name"]
            group_folders[group_name]["space_display_name"] = row["Space Display Name"]
            group_folders[group_name]["space_url"] = row["Space URL"]
    return group_folders


def add_group_chat_urls_to_group_folder(session, group_folders, ACTIVITY_NAME):
    """Add group chat URLs to the group folders."""
    for group_name in group_folders.keys():
        space_display_name = get_space_name_from_group_name(group_name, ACTIVITY_NAME)
        space = get_existing_space(session, space_display_name)
        if not space:
            print(f"❌ Space {space_display_name} not found.")
            continue
        space_url = "https://chat.google.com/room/" + space["name"].split("/")[1]
        group_folders[group_name]["space_name"] = space["name"]
        group_folders[group_name]["space_display_name"] = space["displayName"]
        group_folders[group_name]["space_url"] = space_url
    return group_folders


def get_recent_messages(session, space):
    messages_url = f"https://chat.googleapis.com/v1/{space['name']}/messages"
    params = {"pageSize": 50, "orderBy": "createTime asc"}
    resp = session.get(messages_url, params=params)
    if resp.status_code != 200:
        print(
            f"⚠️ Failed to get recent messages for {space['displayName']}: {resp.text}"
        )
        return None
    messages = resp.json().get("messages", [])

    # Add the URL of each message to the message data
    for message in messages:
        message_id = message.get("name", "").split("/")[-1]
        if message_id:
            message["url"] = (
                f"https://chat.google.com/room/{space['name'].split('/')[1]}/{message_id}"
            )

    return messages


def folder_name_sort_key(folder_name):
    # Extract the number from the folder name
    # Assuming the folder name is iquin the format "Group X"

    try:
        return int(folder_name.split(" ")[1])
    except (IndexError, ValueError):
        return float("inf")  # If it doesn't match, sort it to the end


def get_space_name_from_group_name(group_name, ACTIVITY_NAME):
    space_display_name = f"{ACTIVITY_NAME} - {group_name}"
    space_display_name = group_name_filter(space_display_name)
    return space_display_name


def get_session():
    creds = authenticate()
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {creds.token}"})
    return session


def get_group_to_list_of_emails_dict(STUDENT_CSV):
    group_to_list_of_emails = {}
    with open(STUDENT_CSV, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            group_name = row["group_name"]
            if group_name not in group_to_list_of_emails:
                group_to_list_of_emails[group_name] = []
            group_to_list_of_emails[group_name].append(row["email"])
    return group_to_list_of_emails


def send_message_unless_sent_recently(session, space, group_folders, group_name, text):

    recent_messages = get_recent_messages(session, space)

    sent = False
    for message in recent_messages:
        if message.get("text") == text:
            print(f"✅ Message already sent to {space['displayName']}.")
            sent = True
            break

        if not sent:
            print(f"🔄 Sending welcome message to {space['displayName']}...")
            send_message(
                session,
                space["name"],
                space["displayName"],
                group_folders,
                group_name,
                text,
            )
            time.sleep(SLEEP)  # Respect rate limits


def welcome_text_function_week4(session, space, group_folders, group_name):
    welcome_text = get_welcome_text_week4(
        space["displayName"], group_folders, group_name
    )
    send_message_unless_sent_recently(
        session, space, group_folders, group_name, welcome_text
    )


def welcome_text_function_midterm(session, space, group_folders, group_name):
    welcome_text = get_welcome_text_midterm(
        space["displayName"], group_folders, group_name
    )
    send_message_unless_sent_recently(
        session, space, group_folders, group_name, welcome_text
    )


# --- Main Script ---
def create_group_chats(
    session, group_folders, STUDENT_CSV, ACTIVITY_NAME, welcome_text_function=None
):

    # Reads group_export_nnnnn.csv
    # Creates a dictionary `groups` with key as group_name, and values as a list of student emails

    # Read students
    group_to_list_of_emails = get_group_to_list_of_emails_dict(STUDENT_CSV)

    # Read staff
    with open(STAFF_FILE) as f:
        staff_emails = [line.strip() for line in f if line.strip()]

    group_names = list(group_to_list_of_emails.keys())

    group_names.sort(key=folder_name_sort_key)

    # Process each group
    for group_name in group_names:
        if group_name == "":
            continue

        group_number = get_group_number_from_group_name(group_name)
        if group_number is None:
            print(f"⚠️ Invalid group name format: {group_name}")
            continue

        if group_number < 30:
            continue

        try:
            group_number = int(group_name.split(" ")[1])
        except (IndexError, ValueError):
            print(f"⚠️ Invalid group name format: {group_name}")
            continue

        student_emails = group_to_list_of_emails[group_name]
        space_display_name = get_space_name_from_group_name(group_name, ACTIVITY_NAME)
        print(f"🔄 {function_name()} Processing group: {space_display_name}")

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
        # all_emails = student_emails + staff_emails
        all_emails = student_emails

        for email in all_emails:
            if email in existing_members_list:
                print(f"✅ {email} already in {space_display_name}.")
                continue
            print(f"🔄 Inviting {email} to {space_display_name}...")
            member_payload = {"member": {"name": f"users/{email}", "type": "HUMAN"}}
            invite_url = f"https://chat.googleapis.com/v1/{space['name']}/members"
            r = session.post(invite_url, json=member_payload)

            if r.status_code != 200:
                print(f"⚠️ Failed to add {email} to {space['displayName']}: {r.text}")
            else:
                print(f"➕ Added {email} to {space['displayName']}")

            time.sleep(SLEEP)  # Respect rate limits

        # Send a welcome card unless we've already sent one

        if welcome_text_function:
            welcome_text_function(session, space, group_folders, group_name)

    print("✅ All groups processed successfully.")


def get_space_from_space_name(session, space_name):
    """Fetch space details from space name."""
    space_url = f"https://chat.googleapis.com/v1/{space_name}"
    resp = session.get(space_url)
    if resp.status_code != 200:
        print(f"⚠️ Failed to get space {space_name}: {resp.text}")
        return None
    space = resp.json()
    return space


def read_chat_messages(session, group_folders, process_messages_for_this_group=None):
    result = []

    group_names = list(group_folders.keys())
    group_names.sort(key=folder_name_sort_key)

    for group_name in group_names:
        this_groups_messages = []
        if group_name == "":
            continue
        data = group_folders[group_name]
        pprint(data)
        space_name = data["space_name"]

        space = get_space_from_space_name(session, space_name)
        print(f"Reading messages from {space_name}...")
        messages = get_recent_messages(session, space)
        if messages:
            for message in messages:
                user_id = message["sender"]["name"].split("/")[-1]
                person = get_person(session, user_id)
                if not person:
                    print(f"⚠️ Failed to get person {user_id}: {person}")
                    sys.exit(1)
                space_id = message["name"].split("/")[1]
                this_message = {
                    "group_name": group_name,
                    "message": message,
                    "sender": person,
                    "email": person_to_ucsb_email(person),
                    "space_name": space_name,
                    "space_display_name": space["displayName"],
                    "space_url": f"https://chat.google.com/room/{space_id}",
                }
                result.append(this_message)
                this_groups_messages.append(this_message)
        if process_messages_for_this_group:
            process_messages_for_this_group(group_name, this_groups_messsages)
        time.sleep(SLEEP)  # Respect rate limits
    return result


def print_chat_message_data(chat_message_data):
    for data in chat_message_data:
        if data["email"] == "phtcon@ucsb.edu":
            continue
        sender = None
        displayName = None
        email = None
        text = None
        if "sender" in data:
            sender = data["sender"]
        if sender and "names" in sender and len(sender["names"]) > 0:
            displayName = sender["names"][0].get("displayName")
        if "email" in data:
            email = data["email"]
        if "message" in data and "text" in data["message"]:
            text = data["message"]["text"]

        print(
            f"group: {data['group_name']} Sender: {displayName} email: {data['email']} text: {repr(text[0:30])}"
        )


def write_group_folders_with_chat_groups(group_folders, GROUP_CATEGORY_ID):

    # Output the group dictionary to a CSV file
    output_file = f"group_folders_with_chat_groups_{GROUP_CATEGORY_ID}.csv"

    with open(output_file, "w", newline="") as csvfile:
        fieldnames = [
            "Group Name",
            "Folder URL",
            "Space Name",
            "Space Display Name",
            "Space URL",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for group_name, data in group_folders.items():
            writer.writerow(
                {
                    "Group Name": group_name,
                    "Folder URL": data["folder_url"],
                    "Space Name": data.get("space_name", ""),
                    "Space Display Name": data.get("space_display_name", ""),
                    "Space URL": data.get("space_url", ""),
                }
            )
    print(f"✅ Group folders written to {output_file}")


def invite_staff_to_group_chats(session, group_folders, SECTION_TO_STAFF_EMAILS):

    group_names = list(group_folders.keys())
    group_names.sort(key=folder_name_sort_key)

    print(f"Groups names: {group_names}")

    for group_name in group_names:
        if group_name == "":
            continue
        print(f"{function_name()}: Group name: {group_name}")
        data = group_folders[group_name]
        space_name = data["space_name"]
        space_display_name = data["space_display_name"]
        print(f"🔄 Processing staff for group: {space_display_name}")
        print(f"Space name: {space_name}")

        parts = space_display_name.replace("(", "").replace(")", "").split(" ")
        section = parts[-1]
        print(f"Section: {section}")
        space = get_existing_space(session, space_display_name)

        # Invite staff members
        staff_emails = SECTION_TO_STAFF_EMAILS[section]

        # Get existing members
        existing_members_list = get_existing_members_emails(session, space)

        for email in staff_emails:
            print(f"About to invite {email} to {space_display_name}...")
            if email in existing_members_list:
                print(f"✅ {email} already in {space_display_name}.")
                continue
            print(f"🔄 Inviting {email} to {space_display_name}...")
            member_payload = {"member": {"name": f"users/{email}", "type": "HUMAN"}}
            invite_url = f"https://chat.googleapis.com/v1/{space_name}/members"
            r = session.post(invite_url, json=member_payload)

            if r.status_code != 200:
                print(f"⚠️ Failed to add {email} to {space_display_name}: {r.text}")
            else:
                print(f"➕ Added {email} to {space_display_name}")

            time.sleep(SLEEP)  # Respect rate limits

    print("✅ All staff processed successfully.")


if __name__ == "__main__":

    SECTION_TO_STAFF_EMAILS = {
        "noon": [
            "danish_ebadulla@ucsb.edu",
            "li_an@ucsb.edu",
            "schattoraj@ucsb.edu",
            "ktivinjack@ucsb.edu",
            "stacycallahan@ucsb.edu",
        ],
        "1pm": [
            "christoszangos@ucsb.edu",
            "danish_ebadulla@ucsb.edu",
            "calais@ucsb.edu",
            "jejansen@ucsb.edu",
        ],
        "2pm": ["xchen774@ucsb.edu", "christoszangos@ucsb.edu", "rachitgupta@ucsb.edu"],
        "3pm": [
            "sanjaychandrasekaran@ucsb.edu",
            "xchen774@ucsb.edu",
            "ktivinjack@ucsb.edu",
            "calais@ucsb.edu",
        ],
        "4pm": [
            "li_an@ucsb.edu",
            "sanjaychandrasekaran@ucsb.edu",
            "schattoraj@ucsb.edu",
            "stacycallahan@ucsb.edu",
            "jejansen@ucsb.edu",
        ],
    }

    MIDTERM_GROUP_SET_ID = (
        "22640"  # You can get this from the URL in Canvas (for midterm groups)
    )
    WEEK4_GROUP_SET_ID = (
        "22633"  # You can get this from the URL in Canvas (for week4 groups)
    )

    (PROJECTS_FOLDER_NAME, GROUP_CATEGORY_ID, ACTIVITY_NAME) = (
        "cs5a-s25-ic12",
        WEEK4_GROUP_SET_ID,
        "CS5A S25 Wk4",
    )
    # (PROJECTS_FOLDER_NAME, GROUP_CATEGORY_ID, ACTIVITY_NAME) = (
    #     "cs5a-s25-midterm",
    #     MIDTERM_GROUP_SET_ID,
    #     "CS5A S25 Midterm",
    # )

    STUDENT_CSV = f"group_export_{GROUP_CATEGORY_ID}.csv"

    session = get_session()
    group_folders = get_group_folders(GROUP_CATEGORY_ID)
    print(f"Function: {function_name()} Group folders: {group_folders}")
    create_group_chats(
        session, group_folders, STUDENT_CSV=STUDENT_CSV, ACTIVITY_NAME=ACTIVITY_NAME
    )

    add_group_chat_urls_to_group_folder(session, group_folders, ACTIVITY_NAME)
    write_group_folders_with_chat_groups(group_folders, GROUP_CATEGORY_ID)

    # group_folders = get_group_folders_with_chat(GROUP_CATEGORY_ID)
    # print("reading chat messages...")
    # chat_message_data = read_chat_messages(session, group_folders)
    # print_chat_message_data(chat_message_data)

    #invite_staff_to_group_chats(session, group_folders, SECTION_TO_STAFF_EMAILS)
