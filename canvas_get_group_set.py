import requests
import csv
from pprint import pprint
import re
import sys

# === CONFIGURATION ===
API_URL = "https://ucsb.instructure.com/api/v1"

import canvas_roster_functions

with open("CANVAS_API_TOKEN", "r") as token_file:
    ACCESS_TOKEN = token_file.read().strip()

# Go to the People tab in Canvas and click on tab for the Group Set you want.
# The URL will look something like this:
# https://ucsb.instructure.com/courses/16870/groups#tab-22613
# The number at the end is the group category ID.
# e.g. in this case, 22613.  Put that nummber as the definitino for GROUP_CATEGORY_ID

COURSE_ID = "25658"  # You can get this from the URL in Canvas

MIDTERM_GROUP_SET_ID = "22640"  # You can get this from the URL in Canvas (for midterm groups)
WEEK4_GROUP_SET_ID = "22633"  # You can get this from the URL in Canvas (for week4 groups)

GROUP_CATEGORY_ID = MIDTERM_GROUP_SET_ID
# GROUP_CATEGORY_ID = WEEK4_GROUP_SET_ID

OUTPUT_FILE = f"group_export_{GROUP_CATEGORY_ID}.csv"


HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}


def make_students_dict(groups):
          
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
            users = canvas_roster_functions.get_group_members(group_id)
            for user in users:
                # print("user data: ",end="")
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

        return students
    
    
def set_field_from_group_info(group_info, field_name):
    if group_info and field_name in group_info:
        return group_info[field_name]
    else:
        return None
    
    
    
def add_group_info_to_roster(students, roster):
    for student_id,student in roster.items():
        group_info = students.get(student_id)
        student['group_name'] = set_field_from_group_info(group_info, 'group_name')
        student['group_id'] = set_field_from_group_info(group_info, 'id')
        student['leader_id'] = set_field_from_group_info(group_info, 'leader_id')
        student['leader_name'] = set_field_from_group_info(group_info, 'leader_name')
        student['leader_email'] = set_field_from_group_info(group_info, 'leader_email')
        
    
        
def export_roster_as_csv(roster, filename="midterm_group_export.csv"):
    with open(filename, "w", newline='') as csvfile:
        writer = csv.writer(csvfile)
        # Write the header row
        writer.writerow([
            "student_id", "student_name", "email", "login_id", "group_id", 
            "group_name", "leader_id", "leader_name", "leader_email", 
            "section_id", "section_name", "section_ta", "section_time", "section_day"
        ])
        # Write each student's data
        for student_id, student in roster.items():
            writer.writerow([
                student_id,
                student.get("student_name"),
                student.get("email"),
                student.get("login_id"),
                student.get("group_id"),
                student.get("group_name"),
                student.get("leader_id"),
                student.get("leader_name"),
                student.get("leader_email"),
                student.get("section_id"),
                student.get("section_name"),
                student.get("section_ta"),
                student.get("section_time"),
                student.get("section_day")
            ])
        print(f"Exported roster to {filename}")
        
def roster_of_students_with_no_group(roster):
    students_with_no_group = [student for student in roster.values() if student['group_id'] is None]
    print(f"Number of students with no group: {len(students_with_no_group)}")
    roster_with_no_group = {}
    for student in students_with_no_group:
        student_id = student['student_id']
        roster_with_no_group[student_id] = student
    return roster_with_no_group
           
           
def map_groups_to_section(groups):
    groups_to_section = {}
    for group in groups:
       pprint(group)
    return groups_to_section      


def get_nice_day_time_from_section(group):
    if type(group["section_time"]) != str or type(group["section_day"]) != str:
        return ""
    section_time = convertSectionTimeToNiceTime(group["section_time"])
    return f"{group['section_day']} {section_time}"

def convertSectionTimeToNiceTime(section_time,):
    if type(section_time) != str:
        return section_time
    # If section time matches the pattern "([0-9]{1,2}):([0-9]{2})([AP]M)", convert it to 12-hour format
    match = re.match(r"([0-9]{1,2}):([0-9]{2})([AP]M)", section_time.strip())
    if match:
        hour, minute, period = match.groups()
        hour = int(hour)
        minute = int(minute)
        if (hour == 12 and minute == 0 and period == "PM"):
            return "noon"
        if minute == 0:
            return f"{hour}{period.lower()}"
        return section_time
    else:
        # If it doesn't match the pattern, return it as is
        return section_time     
             
             
def renameGroupForSectionInfo(group):    
    section_time = get_nice_day_time_from_section(group)

    match = re.match(r"^MidtermProject (\d+)$", group['name'])
    if match:
        group_number = match.group(1)
        if section_time == "":
          return
        new_name = f"MidtermProject {group_number} ({section_time})"
        canvas_roster_functions.rename_group(group, new_name)
        return
    match = re.match(r"^MidtermProject (\d+) \(\)$", group['name'])
    if match:
        group_number = match.group(1)
        section_time = get_nice_day_time_from_section(group)
        if section_time == "":
            new_name = f"MidtermProject {group_number}"
        else:
            new_name = f"MidtermProject {group_number} ({section_time})"        
        canvas_roster_functions.rename_group(group, new_name)
        return
    match = re.match(r"^MidtermProject (\d+) (\([MTWRF] [^)*]]\))$", group['name'])
    if match:
        group_number = match.group(1)
        old_section_time = match.group(2)
        section_time = get_nice_day_time_from_section(group)
        if old_section_time != section_time:
            print(f"WARNING: for group {group['name']}, old section time '{old_section_time}' does not match new section time '{section_time}'")
                
                
def main():
    print("Fetching groups...")
    groups = canvas_roster_functions.get_groups(GROUP_CATEGORY_ID)
    print(f"Found {len(groups)} groups.")
    
    
    roster = canvas_roster_functions.make_roster_main(COURSE_ID)
    print(f"Found {len(roster)} students in the roster.")
    
    groups = canvas_roster_functions.add_roster_fields_to_all_groups(groups, roster)
    #pprint(groups)

    for group in groups:
        section_time = get_nice_day_time_from_section(group)
        print(f"Group Name: {group['name']}  Members: {len(group['members'])} Section Time: {section_time} ")
        renameGroupForSectionInfo(group)
       
        
    students = make_students_dict(groups)
    add_group_info_to_roster(students,roster)
    
    export_roster_as_csv(roster, OUTPUT_FILE)
    print(f"Done! Saved as '{OUTPUT_FILE}'")
    
    students_with_no_group = roster_of_students_with_no_group(roster)
    print(f"Number of students with no group: {len(students_with_no_group)}")
    export_roster_as_csv(students_with_no_group, f"students_with_no_group_{GROUP_CATEGORY_ID}.csv")


if __name__ == "__main__":
    main()


