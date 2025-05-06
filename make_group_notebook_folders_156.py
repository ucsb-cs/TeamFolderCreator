import os
import json
import csv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
import pickle
from pprint import pprint
import time
import sys

import canvas_roster_functions
import make_google_chat_conversations
import make_group_notebook_folders

if __name__ == "__main__":
    
    COURSE_ID = "25659"  # CS156 S25

    TEAMS_GROUP_SET_ID = "21872"  # You can get this from the URL in Canvas (for midterm groups)

    GROUP_CATEGORY_ID = TEAMS_GROUP_SET_ID

    GROUP_EXPORT_FILE = f"group_export_{GROUP_CATEGORY_ID}.csv"

    PROJECTS_FOLDER_NAME = "CS156-S25-Team-Folders"
    

    filter=None

    service = make_group_notebook_folders.authenticate()
    
    group_data = make_group_notebook_folders.csv_to_dict(GROUP_EXPORT_FILE)

    group_dict = make_group_notebook_folders.make_group_dictionary(group_data)

    # parent_folder_id = create_folder(service, PROJECTS_FOLDER_NAME)
    # (notebook_file_id, notebook_file_name) = get_notebook_file_id_and_name(
    #      service, PROJECTS_FOLDER_NAME
    #  )
    # make_group_folders(service, group_dict, notebook_file_id, notebook_file_name,  PROJECTS_FOLDER_NAME, filter=filter, GROUP_CATEGORY_ID=GROUP_CATEGORY_ID)
    parent_folder_id = make_group_notebook_folders.create_folder(service, PROJECTS_FOLDER_NAME)
    # (notebook_file_id, notebook_file_name) = get_notebook_file_id_and_name(
    #      service, PROJECTS_FOLDER_NAME
    #  )
    
    #make_group_folders_with_single_notebook(service, group_dict, notebook_file_id, notebook_file_name,  PROJECTS_FOLDER_NAME, filter=None, GROUP_CATEGORY_ID=GROUP_CATEGORY_ID)
    make_group_notebook_folders.make_group_folders(service, group_dict, PROJECTS_FOLDER_NAME, filter=None, GROUP_CATEGORY_ID=GROUP_CATEGORY_ID)


    make_group_notebook_folders.populate_group_dict_with_folder_urls(
        service,
        group_dict,
        PROJECTS_FOLDER_NAME,
        filter=filter,
        GROUP_CATEGORY_ID=GROUP_CATEGORY_ID,
    )

    