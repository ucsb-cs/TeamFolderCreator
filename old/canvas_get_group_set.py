import requests
import csv
from pprint import pprint

# === CONFIGURATION ===
API_URL = "https://ucsb.instructure.com/api/v1"

with open("CANVAS_API_TOKEN", "r") as token_file:
    ACCESS_TOKEN = token_file.read().strip()

# Go to the People tab in Canvas and click on tab for the Group Set you want.
# The URL will look something like this:
# https://ucsb.instructure.com/courses/16870/groups#tab-22613
# The number at the end is the group category ID.
# e.g. in this case, 22613.  Put that nummber as the definitino for GROUP_CATEGORY_ID

GROUP_CATEGORY_ID = "22633"  # You can get this from the URL in Canvas

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

def get_groups(category_id):
    url = f"{API_URL}/group_categories/{category_id}/groups"
    all_groups = []
    while url:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        all_groups.extend(data)
        # Check for pagination
        url = response.links.get('next', {}).get('url')
    return all_groups

def get_group_members(group_id):
    url = f"{API_URL}/groups/{group_id}/users"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    # pprint(response.json())  # For debugging/exploration of data
    return response.json()

def export_group_data_to_csv(groups):
    with open("canvas_group_export.csv", "w", newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["id", "Group Name", "Name", "Perm", "Email", "LoginId", "Leader Id", "Leader Name", "Leader Email"])

        # First pass; get all groups and their members
        
        students = {}

        for group in groups:
            group_name = group['name']
            group_id = group['id']
            if group['leader'] and group['leader']['id']:
                # If the group has a leader, get their display name
                leader_id = group['leader']['id']
            else:
                # If the group does not have a leader, set leader to None
                leader_id = None
            users = get_group_members(group_id)
            for user in users:
                # pprint(user) # for debugging/exploration of data
                loginId = user.get("login_id")
                email = f"{loginId}@ucsb.edu"
                students[user.get("id")] = {
                    'id': user.get("id"),
                    'group_name': group_name,
                    'name': user.get("name"),
                    'integration_id': user.get("integration_id"),
                    'email': email,
                    'loginId': loginId,
                    'leader_id': leader_id,
                    'leader_name': None, # Placeholder for leader name
                    'leader_email': None # Placeholder for leader email
                }
                
        # Fill in leader names and emails
        for student in students.values():
            try:
                leader_id = student['leader_id']
                if leader_id:
                    # If the leader exists in the students dictionary, get their details
                    student['leader_name'] = students[leader_id]['name']
                    student['leader_email'] = students[leader_id]['email']
            except KeyError:
                pprint(f"WARNING: Leader ID {leader_id} for student {student} not found in students dictionary.")
       
        for student in students.values():
            writer.writerow([
                student['id'],
                student['group_name'],
                student['name'],
                student['integration_id'],
                student['email'],
                student['leader_id'],
                student['leader_name'],
                student['leader_email']
            ])

def main():
    print("Fetching groups...")
    groups = get_groups(GROUP_CATEGORY_ID)
    print(f"Found {len(groups)} groups.")
    print("Exporting to CSV...")
    export_group_data_to_csv(groups)
    print("Done! Saved as 'canvas_group_export.csv'")

if __name__ == "__main__":
    main()