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
    pprint(all_groups)  # For debugging/exploration of data
    return all_groups

def get_group_members(group_id):
    url = f"{API_URL}/groups/{group_id}/users"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()

def export_group_data_to_csv(groups):
    with open("canvas_group_export.csv", "w", newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Group Name", "Name", "Perm", "Email"])

        for group in groups:
            group_name = group['name']
            group_id = group['id']
            users = get_group_members(group_id)
            for user in users:
                # pprint(user) # for debugging/exploration of data
                loginId = user.get("login_id")
                email = f"{loginId}@ucsb.edu"
                writer.writerow([
                    group_name,
                    user.get("name"),
                    user.get("integration_id"),
                    email
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