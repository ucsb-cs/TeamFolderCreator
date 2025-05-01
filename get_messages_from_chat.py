import make_google_chat_conversations

import inspect
from pprint import pprint
import sys
import time
from datetime import datetime
import pytz

import canvas_roster_functions

def function_name():
    return inspect.stack()[1].function

def convert_to_local_time(time_str):
    utc_time = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    utc_time = utc_time.replace(tzinfo=pytz.utc)
    local_time = utc_time.astimezone(pytz.timezone("America/Los_Angeles"))
    return local_time.strftime("%m-%d %I:%M %p")

def summarize_chat_messages(chat_message_data):
    """
    Summarize chat messages by email.
    returns a dictionary where the keys are email addresses 
    and the values are dictionaries containing the messages and other information.
    
    Fields in the values are:
    - messages: a list of messages sent by the user
    - displayName: the display name of the user
    - email: the email address of the user
    - group_name: the name of the group the user is in
    """
    
    email_to_messages = {}
    for chat in chat_message_data:
        email = chat.get("email")
        if email in ["phtcon@ucsb.edu"]:
            continue
        if email not in email_to_messages:
            email_to_messages[email] = {}
            email_to_messages[email]['messages'] = []
        message = {
            'text': chat.get('message').get('text'),
            'createTime': chat.get('message').get('createTime'),
            'name': chat.get('message').get('name'),
        }
        email_to_messages[email]['messages'].append(message)
        if 'displayName' not in email_to_messages[email] and \
            'sender' in chat and 'names' in chat['sender'] and len(chat['sender']['names']) > 0 and 'displayName' in chat['sender']['names'][0]:
            email_to_messages[email]['displayName'] = chat['sender']['names'][0]['displayName']
        if 'email' not in email_to_messages[email] and 'sender' in chat:
            email_to_messages[email]['email'] = make_google_chat_conversations.person_to_ucsb_email(chat['sender'])
        if 'group_name' not in email_to_messages[email] and 'group_name' in chat:
            email_to_messages[email]['group_name'] = chat['group_name']
        if 'space_url' not in email_to_messages[email] and 'space_url' in chat:
            email_to_messages[email]['space_url'] = chat['space_url']
  
    return email_to_messages


def add_canvas_post_text(summarized_chat_message_data):
    """
    Add the canvas post text to the summarized chat message data.
    The canvas post text is a string that contains the group name and the messages.
    """
   
    for email, data in summarized_chat_message_data.items():
        space_url = data.get('space_url')
        group_name = data.get('group_name')
        displayName = data.get('displayName')
        email = data.get('email')
        formatted_messages = f"""
        <p>In the Google Chat space for <a href="{space_url}">{group_name}</a><br />
        the following messages were found for {displayName} ({email})</p>
        """
        
        formatted_messages += f"""
        <table border="1">
        <thead>
        <tr>
            <th>Time</th>
            <th>Message</th>
        </tr>
        </thead>
        <tbody>
        """
        for message in data['messages']:
            formatted_messages += f"""
            <tr>
                <td>{convert_to_local_time(message['createTime'])}</td>
                <td>{message['text']}</td>
            </tr>
            """
        formatted_messages += f"""
        </tbody>
        </table>
        """
        data['canvas_post_text'] = formatted_messages


def no_chat_message_found(student, group_name, message, url):
    return f"""
    <p>In the Google Chat space for <a href="{url}">{group_name}</a><br />
    no messages were found for {student['name']} ({student['email']})</p>
    <p>{message}</p>
    """
    


if __name__ == "__main__":
    
    COURSE_ID = "25658"  # You can get this from the URL in Canvas
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


    all_students = canvas_roster_functions.get_students(COURSE_ID)
    groups = canvas_roster_functions.get_groups(GROUP_CATEGORY_ID, COURSE_ID=COURSE_ID)
    student_email_to_group = {}
    for group in groups:
        for student in group['members']:
            student_email = student['email'].replace("@umail.ucsb.edu","@ucsb.edu")
            student_email_to_group[student['email']] = group['name']

    canvas_assignment_name = "ic13"    
    assignment = canvas_roster_functions.locate_assignment(canvas_assignment_name, COURSE_ID=COURSE_ID)
    if not assignment:
        raise Exception(f"Assignment {canvas_assignment_name} not found.")
    assignment_id = assignment["id"]

    session = make_google_chat_conversations.get_session()
    group_folders = make_google_chat_conversations.get_group_folders(GROUP_CATEGORY_ID)
    

    group_folders = make_google_chat_conversations.get_group_folders_with_chat(GROUP_CATEGORY_ID)


    chat_message_data =  make_google_chat_conversations.read_chat_messages(session, group_folders)

    summarized_chat_message_data = summarize_chat_messages(chat_message_data)

   
    add_canvas_post_text(summarized_chat_message_data)
    
    print(f"len(students): {len(all_students)}")
    for student in all_students:
        print(f"Adding feedback for student: {student['name']}")
        email = student['email'].replace("@umail.ucsb.edu","@ucsb.edu")
        group_name = student_email_to_group.get(email)
        if group_name is None:
            print(f"WARNING: No group found for student {student['name']} with email {email}")
            continue
        print(f"Group: {group_name}")
        if email in summarized_chat_message_data:
            canvas_roster_functions.add_feedback_to_submission_unless_duplicate(
                assignment_id,
                student['id'],
                summarized_chat_message_data[email]['canvas_post_text'],
            )
        else:
            if group_name not in group_folders:
                print("Skippping stuudnt {student['name']} because no group folder found")
                print(f"WARNING: No group folder found for group {group_name}")
                continue
            space_url = group_folders.get(group_name).get("space_url")
            message = no_chat_message_found(student, group_name, "No messages found in Google Chat", space_url)
            print(f"No chat messages found for {student['name']}")
            print("message: ", message)
            canvas_roster_functions.add_feedback_to_submission_unless_duplicate(
                assignment_id,
                student['id'],
                message,
            )
            