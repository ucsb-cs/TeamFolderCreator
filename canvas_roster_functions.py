import requests
import csv
from pprint import pprint
import re
# === CONFIGURATION ===
API_URL = "https://ucsb.instructure.com/api/v1"

with open("CANVAS_API_TOKEN", "r") as token_file:
    ACCESS_TOKEN = token_file.read().strip()

# Go to the People tab in Canvas and click on tab for the Group Set you want.
# The URL will look something like this:
# https://ucsb.instructure.com/courses/16870/groups#tab-22613
# The number at the end is the group category ID.
# e.g. in this case, 22613.  Put that nummber as the definitino for GROUP_CATEGORY_ID

COURSE_ID = "25658"  # You can get this from the URL in Canvas

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

def get_students():
    # use Canvas API to get all students in the course
    url = f"{API_URL}/courses/{COURSE_ID}/users?enrollment_type[]=student"
    all_students = []
    while url:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        all_students.extend(data)
        # Check for pagination
        url = response.links.get('next', {}).get('url')
    filtered_students = [student for student in all_students if student['name'] != 'Test Student']
    return filtered_students

def get_sections():
    # Use Canvas API to get all sections in the course
    url = f"{API_URL}/courses/{COURSE_ID}/sections"
    all_sections = []
    while url:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        all_sections.extend(data)
        # Check for pagination
        url = response.links.get('next', {}).get('url')
        
    for section in all_sections:
        # Get the section ID and name
        section_id = section['id']
        section_name = section['name']
          
        section_time = re.search(r"\d{1,2}:\d{2}\s*[AP]M", section_name)
        section["section_time"] = set_field_from_re_result(section_time)
    
        section_day = re.search(r"\b(M|T|W|T|F)\b", section_name)
        section["section_day"] = set_field_from_re_result(section_day)

        section_ta = re.search(r"\[.*\]", section_name)
        section["section_ta"] = set_field_from_re_result(section_ta).replace("[", "").replace("]", "").strip()        
        
        # Get the list of students in the section
        students = get_section_members(section_id)
        # Add the students to the section dictionary
        section['students'] = students
        
    
    return all_sections

def get_section_members(section_id):
    url = f"{API_URL}/sections/{section_id}/enrollments"
    all_members = []
    while url:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        all_members.extend(data)
        # Check for pagination
        url = response.links.get('next', {}).get('url')
    return all_members


def set_field_from_re_result(result):
    if result:
        return result.group(0)
    else:
        return "Unknown"
   
def warn_unless_test_student_or_TA(student):
    if student['role']!='StudentEnrollment':
        return
    if student['role']=='StudentEnrollment' and \
        'user' in student and \
        'name' in student['user'] and \
        student['user']['name'] == 'Test Student':
        return
        
    print(f"WARNING: Student not found in roster.")
    pprint(student)

def make_roster(all_students, all_sections):

    roster = {}
    for student in all_students:
        # Get the student ID and name
        student_id = student['id']
        student_name = student['name']
        login_id = student['login_id']
        # Get the student's email address
        email = f"{student['login_id']}@ucsb.edu"
        
        user = student['user'] if 'user' in student else None
        perm = user['integration_id'] if (user and 'integration_id' in user) else None
                
        # Get the student's section ID
       
        # Add the student to the roster
        roster[student_id] = {
            'student_id': student_id,
            'student_name': student_name,
            'email': email,
            'login_id': login_id,
            'perm': perm
        }
        
    for section in all_sections:
        # Get the section ID and name
        section_id = section['id']
        section_name = section['name']
        
        # Get the list of students in the section
        students = section['students']
        
        # Add the section information to each student in the roster
        for student in students:
            student_id = student['user_id']
            user = student['user'] if 'user' in student else None
            perm = user['integration_id'] if (user and 'integration_id' in user) else None     
            if student_id in roster:
                roster_student = roster[student_id]
                roster_student['section_id'] = section_id
                roster_student['section_name'] = section_name
                roster_student['section_time'] = section['section_time']
                roster_student['section_day'] = section['section_day']
                roster_student['section_ta'] = section['section_ta']
                roster_student['perm'] = perm
            else:
                warn_unless_test_student_or_TA(student)
               
                
                
    return roster
  

def make_roster_csv():
      # main()
    all_students = get_students()
    print(f"Found {len(all_students)} students.")
    
    all_sections = get_sections()
    print(f"Found {len(all_sections)} sections.")
    
    total_students = 0
    for section in all_sections:
        section_id = section['id']
        section_name = section['name']
        students = section['students']

        print(f"Section ID: {section_id}, Section Name: {section_name}")
        students_with_role_student = [student for student in students if student['role'] == 'StudentEnrollment' and student['user']['name'] != 'Test Student']
        total_students += len(students_with_role_student)
        print(f"Number of students in section {section_id}: {len(students_with_role_student)}")

    print(f"Total number of students in all sections: {total_students}")
    roster = make_roster(all_students, all_sections)    
    students_with_no_perms = [student for student in roster.values() if student['perm'] is None]
    print(f"Number of students with no perms: {len(students_with_no_perms)}")
    pprint(students_with_no_perms)
    export_roster_to_csv(roster)

def export_roster_to_csv(roster, filename="roster.csv"):
    with open(filename, "w", newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Student ID", "Name", "Email", "Login ID", "Perm", "Section ID", "Section Name", "Section Time", "Section Day", "Section TA"])
        for student in roster.values():
            writer.writerow([
                student['student_id'],
                student['student_name'],
                student['email'],
                student['login_id'],
                student.get('perm', ''),
                student.get('section_id', ''),
                student.get('section_name', ''),
                student.get('section_time', ''),
                student.get('section_day', ''),
                student.get('section_ta', '')
            ])
    print(f"Roster exported to {filename}")

if __name__ == "__main__":
    make_roster_csv()
  
