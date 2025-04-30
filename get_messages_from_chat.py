import make_google_chat_conversations

import inspect
from pprint import pprint
import sys

def function_name():
    return inspect.stack()[1].function


def get_messages_from_chat():
    print(f"Running {function_name()}()")


if __name__ == "__main__":
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

    session = make_google_chat_conversations.get_session()
    group_folders = make_google_chat_conversations.get_group_folders(GROUP_CATEGORY_ID)
    

    group_folders = make_google_chat_conversations.get_group_folders_with_chat(GROUP_CATEGORY_ID)

    chat_message_data =  make_google_chat_conversations.read_chat_messages(session, group_folders)

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
        }
        email_to_messages[email]['messages'].append(message)
        if 'displayName' not in email_to_messages[email] and \
            'sender' in chat and 'names' in chat['sender'] and len(chat['sender']['names']) > 0 and 'displayName' in chat['sender']['names'][0]:
            email_to_messages[email]['displayName'] = chat['sender']['names'][0]['displayName']
        if 'email' not in email_to_messages[email] and 'sender' in chat:
            email_to_messages[email]['email'] = make_google_chat_conversations.person_to_ucsb_email(chat['sender'])
        if 'group_name' not in email_to_messages[email] and 'group' in chat:
            email_to_messages[email]['group_name'] = chat['group']['name']


