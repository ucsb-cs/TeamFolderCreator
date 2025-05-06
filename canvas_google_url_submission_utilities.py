import canvas_roster_functions
import make_group_notebook_folders

from pprint import pprint

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import re
import inspect

def function_name():
    return inspect.stack()[1].function

def add_readers_from_url(drive_service, file_url, email_list):
    """
    Adds a list of email addresses as readers to a Google Drive file.

    Parameters:
    - drive_service: Authorized Google Drive API service instance
    - file_url: URL to the Google Drive file
    - email_list: List of email addresses to be added as readers
    """
    # Extract file ID from URL
    if not "google.com" in file_url:
        print(f"{function_name()} Error: URL does note appear to be a google drive URL: {file_url}")
        return
    try:
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', file_url)
        if not match:
            match = re.search(r'id=([a-zA-Z0-9_-]+)', file_url)
        if not match:
            match = re.search(r'/drive/([a-zA-Z0-9_-]+)', file_url)
        if not match:
            raise ValueError("Could not extract file ID from URL")
    except Exception as e:
        print(f"{function_name()} Error extracting file id from url: {file_url}: Exception is: {e}")
        return

    file_id = match.group(1)

    users_added = []
    for email in email_list:
        try:
            permission = {
                'type': 'user',
                'role': 'writer',
                'emailAddress': email
            }
            drive_service.permissions().create(
                fileId=file_id,
                body=permission,
                sendNotificationEmail=False  # Set to True if you want to notify
            ).execute()
            users_added.append(email)
        except HttpError as error:
            print(f"An error occurred: {error}")
    print(f"Added users: {', '.join(users_added)}")

def summarize_submissions_by_url(submissions, user_id_to_student):
    result = {}
    for submission in submissions:
        if not 'url' in submission:
            continue
        url = submission['url']
        user_id = submission['user_id']
        if url not in result:
            result[url] = {'submission': submission, 'students': [], 'unknown_user_ids': []}
        try:
            student = user_id_to_student[user_id]
            result[url]['students'].append(student)
        except KeyError:
            result[url]['unknown_user_ids'].append(user_id)
    return result


if __name__ == "__main__":
    # This is a placeholder for the main function.
    # You can add code here to test the functions or run the script directly.
    
    COURSE_ID = "25658"  # You can get this from the URL in Canvas (this is CMPSC 5A, S25)
    
    STAFF_FILE = "staff.txt"

    # Read the staff file and create a list of staff members
    with open(STAFF_FILE, "r") as f:
        staff = [line.strip() for line in f.readlines()]
    # Print the staff members

    
    assignment = canvas_roster_functions.locate_assignment("ic16", COURSE_ID)
    assignment_id = assignment["id"]
    submissions = canvas_roster_functions.get_assignment_submissions(assignment_id, COURSE_ID)
    #pprint(submissions)
    
    user_id_to_student = canvas_roster_functions.get_user_id_to_student_dict(COURSE_ID)
    
    #pprint(user_id_to_student)
    
    service = make_group_notebook_folders.authenticate()
    
    url_dict = summarize_submissions_by_url(submissions, user_id_to_student)
    
    # pprint(url_dict)
    
    for url, data in url_dict.items():
        print(f"URL: {url}")
        student_names = [student['name'] for student in data['students']]
        print(f"Students: {', '.join(student_names)}")
        if len(data['unknown_user_ids']) > 0:
            print(f"Unknown user IDs: {', '.join(map(str, data['unknown_user_ids']))}")
        add_readers_from_url(service, url, staff)
        
        
    