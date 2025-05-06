import requests
import csv
from pprint import pprint
import re
import sys
import inspect
import time
import pytz

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

HEADERS = {"Authorization": f"Bearer {ACCESS_TOKEN}"}


def function_name():
    return inspect.stack()[1].function

def press_return_to_continue():
    input("Press Return to continue...")

def get_groups(category_id, COURSE_ID=COURSE_ID):
    url = f"{API_URL}/group_categories/{category_id}/groups"
    all_groups = []
    while url:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        all_groups.extend(data)
        # Check for pagination
        url = response.links.get("next", {}).get("url")


    for group in all_groups:
        if "leader" in group and group["leader"] and "id" in group["leader"]:
          leader_id = group["leader"]["id"]
        else:
          leader_id = None
        group["leader_id"] = leader_id
        members = get_group_members(group["id"])
        for member in members:
            loginId = member.get("login_id")
            email = f"{loginId}@ucsb.edu"
            member["email"] = email
        group["members"] = members
    return all_groups


def add_roster_fields_to_group_members(group, roster):
    leader_id = group.get("leader_id")
    if leader_id:
        leader_on_roster = roster.get(leader_id)
        if leader_on_roster:
            group["leader_name"] = leader_on_roster.get("student_name")
            group["leader_email"] = leader_on_roster.get("email")
    else:
        group["leader_name"] = None
        group["leader_email"] = None
    for member in group["members"]:
        member_id = member.get("id")
        if member_id:
            member_on_roster = roster.get(member_id)
            if member_on_roster:
                member["section_id"] = member_on_roster.get("section_id")
                member["section_name"] = member_on_roster.get("section_name")
                member["section_time"] = member_on_roster.get("section_time")
                member["section_day"] = member_on_roster.get("section_day")
                member["section_ta"] = member_on_roster.get("section_ta")
                member["perm"] = member_on_roster.get("perm")
            else:
                member["section_id"] = None
                member["section_name"] = None
                member["section_time"] = None
                member["section_day"] = None
                member["section_ta"] = None
                member["perm"] = None
        else:
            print(f"WARNING: Member ID not found for group {group['name']}.")
    
    
def fix_singleton_set(group, field_name):
    field_set = group[field_name]
    if len(field_set) == 1:
        group[field_name] = list(field_set)[0]
    else:
        group[field_name] = field_set
def add_roster_fields_to_all_groups(groups, roster):
    for group in groups:
        add_roster_fields_to_group_members(group, roster)
    for group in groups:
        group["section_id"] = set()
        group["section_name"] = set()
        group["section_time"] = set()
        group["section_day"] = set()
        group["section_ta"] = set()
        for member in group["members"]:
            group["section_id"] =  group["section_id"].union({member["section_id"]})
            group["section_name"] = group["section_name"].union({member["section_name"]})
            group["section_time"] = group["section_time"].union({member["section_time"]})
            group["section_day"] = group["section_day"].union({member["section_day"]})
            group["section_ta"] = group["section_ta"].union({member["section_ta"]})
        fix_singleton_set(group, "section_id")
        fix_singleton_set(group, "section_name")
        fix_singleton_set(group, "section_time")
        fix_singleton_set(group, "section_day")
        fix_singleton_set(group, "section_ta")
    return groups

def rename_group(group, new_name):
    # Use the Canvas API to rename the group
    url = f"{API_URL}/groups/{group['id']}"
    data = {
        "name": new_name
    }
    response = requests.put(url, headers=HEADERS, json=data)
    response.raise_for_status()
    group["name"] = new_name
    return group

def get_group_members(group_id):
    url = f"{API_URL}/groups/{group_id}/users"
    all_members = []
    while url:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        all_members.extend(data)
        # Check for pagination
        url = response.links.get("next", {}).get("url")
    return all_members


def get_students(COURSE_ID=COURSE_ID):
    # use Canvas API to get all students in the course
    url = f"{API_URL}/courses/{COURSE_ID}/users?enrollment_type[]=student"
    all_students = []
    while url:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        all_students.extend(data)
        # Check for pagination
        url = response.links.get("next", {}).get("url")
    filtered_students = [
        student for student in all_students if student["name"] != "Test Student"
    ]
    fix_umails(filtered_students)
    return filtered_students

def fix_umails(students):
    # For each student, change @umail.ucsb.edu to @ucsb.edu
    for i in range(len(students)):
        student = students[i]
        if "email" in student:
            email = student["email"]
            if "@umail.ucsb.edu" in email:
                new_email = email.replace("@umail.ucsb.edu", "@ucsb.edu")
                students[i]["email"] = new_email
    return students
                
def get_user_id_to_student_dict(COURSE_ID=COURSE_ID):
    students = get_students(COURSE_ID)
    fix_umails(students)
    user_id_to_student = {}
    for student in students:
        user_id = student["id"]
        user_id_to_student[user_id] = student
    return user_id_to_student

def get_sections(COURSE_ID=COURSE_ID):
    # Use Canvas API to get all sections in the course
    url = f"{API_URL}/courses/{COURSE_ID}/sections"
    all_sections = []
    while url:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        all_sections.extend(data)
        # Check for pagination
        url = response.links.get("next", {}).get("url")

    for section in all_sections:
        # Get the section ID and name
        section_id = section["id"]
        section_name = section["name"]

        section_time = re.search(r"\d{1,2}:\d{2}\s*[AP]M", section_name)
        section["section_time"] = set_field_from_re_result(section_time)

        section_day = re.search(r"\b(M|T|W|T|F)\b", section_name)
        section["section_day"] = set_field_from_re_result(section_day)

        section_ta = re.search(r"\[.*\]", section_name)
        section["section_ta"] = (
            set_field_from_re_result(section_ta)
            .replace("[", "")
            .replace("]", "")
            .strip()
        )

        # Get the list of students in the section
        students = get_section_members(section_id)
        # Add the students to the section dictionary
        section["students"] = students

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
        url = response.links.get("next", {}).get("url")
    return all_members


def set_field_from_re_result(result):
    if result:
        return result.group(0)
    else:
        return "Unknown"


def warn_unless_test_student_or_TA(student):
    if student["role"] != "StudentEnrollment":
        return
    if (
        student["role"] == "StudentEnrollment"
        and "user" in student
        and "name" in student["user"]
        and student["user"]["name"] == "Test Student"
    ):
        return

    print(f"WARNING: Student not found in roster.")
    pprint(student)


def make_roster(all_students, all_sections):

    roster = {}
    for student in all_students:
        # Get the student ID and name
        student_id = student["id"]
        student_name = student["name"]
        login_id = student["login_id"]
        # Get the student's email address
        email = f"{student['login_id']}@ucsb.edu"

        user = student["user"] if "user" in student else None
        perm = user["integration_id"] if (user and "integration_id" in user) else None

        # Get the student's section ID

        # Add the student to the roster
        roster[student_id] = {
            "student_id": student_id,
            "student_name": student_name,
            "email": email,
            "login_id": login_id,
            "perm": perm,
        }

    for section in all_sections:
        # Get the section ID and name
        section_id = section["id"]
        section_name = section["name"]

        # Get the list of students in the section
        students = section["students"]

        # Add the section information to each student in the roster
        for student in students:
            student_id = student["user_id"]
            user = student["user"] if "user" in student else None
            perm = (
                user["integration_id"] if (user and "integration_id" in user) else None
            )
            if student_id in roster:
                roster_student = roster[student_id]
                roster_student["section_id"] = section_id
                roster_student["section_name"] = section_name
                roster_student["section_time"] = section["section_time"]
                roster_student["section_day"] = section["section_day"]
                roster_student["section_ta"] = section["section_ta"]
                roster_student["perm"] = perm
            else:
                warn_unless_test_student_or_TA(student)

    return roster


def make_roster_main(COURSE_ID=COURSE_ID):
    # main()
    all_students = get_students(COURSE_ID)
    print(f"Found {len(all_students)} students.")

    all_sections = get_sections(COURSE_ID)
    print(f"Found {len(all_sections)} sections.")

    total_students = 0
    for section in all_sections:
        section_id = section["id"]
        section_name = section["name"]
        students = section["students"]

        print(f"Section ID: {section_id}, Section Name: {section_name}")
        students_with_role_student = [
            student
            for student in students
            if student["role"] == "StudentEnrollment"
            and student["user"]["name"] != "Test Student"
        ]
        total_students += len(students_with_role_student)
        print(
            f"Number of students in section {section_id}: {len(students_with_role_student)}"
        )

    print(f"Total number of students in all sections: {total_students}")
    roster = make_roster(all_students, all_sections)
    students_with_no_perms = [
        student for student in roster.values() if student["perm"] is None
    ]
    print(f"Number of students with no perms: {len(students_with_no_perms)}")
    pprint(students_with_no_perms)
    return roster


def export_roster_to_csv(roster, filename="roster.csv"):
    with open(filename, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            [
                "Student ID",
                "Name",
                "Email",
                "Login ID",
                "Perm",
                "Section ID",
                "Section Name",
                "Section Time",
                "Section Day",
                "Section TA",
            ]
        )
        for student in roster.values():
            writer.writerow(
                [
                    student["student_id"],
                    student["student_name"],
                    student["email"],
                    student["login_id"],
                    student.get("perm", ""),
                    student.get("section_id", ""),
                    student.get("section_name", ""),
                    student.get("section_time", ""),
                    student.get("section_day", ""),
                    student.get("section_ta", ""),
                ]
            )
    print(f"Roster exported to {filename}")


def make_roster_csv(COURSE_ID=COURSE_ID):
    roster = make_roster_main(COURSE_ID)
    export_roster_to_csv(roster)



def locate_assignment_by_id(assignment_id):
    url = f"{API_URL}/courses/{COURSE_ID}/assignments/{assignment_id}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def locate_assignment(assignment_name, COURSE_ID=COURSE_ID):
    url = f"{API_URL}/courses/{COURSE_ID}/assignments"
    assignments = []
    while url:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        assignments.extend(data)
        # Check for pagination
        url = response.links.get("next", {}).get("url")
    for assignment in assignments:
        if assignment["name"] == assignment_name:
            return assignment
    return None

def get_assignment_submissions(assignment_id, COURSE_ID=COURSE_ID):
    url = f"{API_URL}/courses/{COURSE_ID}/assignments/{assignment_id}/submissions"
    all_submissions = []
    while url:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        all_submissions.extend(data)
        # Check for pagination
        url = response.links.get("next", {}).get("url")
    return all_submissions

def get_assignment_submissions_for_student(assignment_id, student_id):
    url = f"{API_URL}/courses/{COURSE_ID}/assignments/{assignment_id}/submissions/{student_id}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()

def add_feedback_to_submission(assignment_id, student_id, comment):
    url = f"{API_URL}/courses/{COURSE_ID}/assignments/{assignment_id}/submissions/{student_id}"
    data = {
        "comment": {
            "text_comment": comment
        }
    }
    response = requests.put(url, headers=HEADERS, json=data)
    response.raise_for_status()
    return response.json()

def add_feedback_to_submission_unless_duplicate(assignment_id, student_id, comment):
    assignment = locate_assignment_by_id(assignment_id)
    if not assignment:
        print(f"Assignment with id '{assignment_id}' not found.")
        return

    assignment_id = assignment["id"]
    comments = get_submission_comments_graphql(COURSE_ID, student_id, assignment_id)
    # Check if the comment already exists
        
    for existing_comment in comments:
        existing_html = existing_comment["htmlComment"]
    
        if existing_html.strip() == comment.strip():
            print(f"Comment already exists for student {student_id}.")
            return
 
 
    if comments == []:
        print(f"Graphql returned no coments for {student_id}.")
        comments_via_rest = get_submission_comments(COURSE_ID, student_id, assignment_id)
        if comments_via_rest == []:
            print(f"REST API returned no comments for {student_id}.")
        else:
            print(f"REST API returned comment for {student_id}:")
            for existing_comment in comments_via_rest:
                equal_to_existing = comment.strip() == existing_comment.strip()

                print(f"Existing comment, equal to new comment: {equal_to_existing}")
                print("***************")
                print(existing_comment)
                print("***************")
            press_return_to_continue()
 
    print(f"{function_name()} called with assignment_id: {assignment_id}, student_id: {student_id}:")
    print("***ABOUT TO ADD NEW COMMENT:***")
    print("****** Comment *****")
    print(comment)
    print("********************")
    
    print("***Existing comments:*****")
    pprint(comments)
    print("***********************")
    press_return_to_continue()

    print(f"Adding comment to submission for student {student_id}...")
    # Add the new comment
    add_feedback_to_submission(assignment_id, student_id, comment)


def get_submission_comments(COURSE_ID, assignment_id, student_id):
    url = f"{API_URL}/courses/{COURSE_ID}/assignments/{assignment_id}/submissions/{student_id}"
    params = {
        "include[]": "submission_comments"
    }
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    submission = response.json()
    pprint(submission)
    comments = []
    if 'submission_comments' in submission:
        for comment in submission['submission_comments']:
            comments.append(comment['comment'])  # or comment['text_comment'] depending on API version

    return comments


def get_submission_comments(course_id, user_id, assignment_id):
    url = f"{API_URL}/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}"
    params = {
        "include[]": "submission_comments"
    }
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    submission = response.json()
    
    comments = []
    if 'submission_comments' in submission:
        for comment in submission['submission_comments']:
            comments.append(comment['comment'])  # or comment['text_comment'] depending on API version

    return comments

def get_submission_comments_graphql(course_id, user_id, asssignment_id):
    url = f"""{API_URL.replace("v1","")}/graphql"""

    query = """
    query GetAssignmentHTMLComments($userId: ID!, $courseId: ID!) {
        course(id: $courseId) {
            id
            name
            assignmentsConnection(filter: {userId: $userId}) {
            edges {
                node {
                id
                _id
                name
                submissionsConnection(filter: { userId: $userId}) {
                    edges {
                    node {
                        id
                        commentsConnection {
                        edges {
                            node {
                                htmlComment
                                createdAt
                                author {
                                    name
                                    email
                                }
                            }
                        }
                        }
                    }
                    }
                }
                }
            }
            }
        }
    }
    """
    
    
    variables = {
        "userId": str(user_id),
        "courseId": str(course_id)
    }

    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "query": query,
        "variables": variables
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    
    print(f"GraphQL result status code: {response.status_code}")
    # Print all status information we can get back from a requests respose
    print(f"GraphQL result headers: {response.headers}")
    print(f"GraphQL result text: {response.text}")
    print(f"GraphQL result json: {data}")


    if 'errors' in data:
        print("GraphQL errors:", data['errors'])
        return []
    if 'data' not in data:
        print("No data found in response.")
        return []

    assignments = data['data']['course']['assignmentsConnection']['edges']    
    filtered_assignments = [
        assignment for assignment in assignments if assignment['node']['_id'] == str(asssignment_id)
    ]
    
    htmlComments = []
    for assignment in filtered_assignments:
        submissions = assignment['node']['submissionsConnection']['edges']
        for submission in submissions:
            comments = submission['node']['commentsConnection']['edges']
            for comment in comments:
                # if type(comment['node']['htmlComment']) == tuple:
                #     commentText = comment['node']['htmlComment'].join("")
                # else:
                commentText = comment['node']['htmlComment']
                    
                thisComment = { 
                   "htmlComment" : commentText,
                   "authorName" : comment['node']['author']['name'],
                   "authorEmail" : comment['node']['author']['email'],
                   "createdAt" : comment['node']['createdAt'],
                }
                htmlComments.append(thisComment) 
    
    return htmlComments

    # comments = []
    # try:
    #     enrollments = data["data"]["user"]["enrollments"]["nodes"]
    #     for enrollment in enrollments:
    #         course = enrollment.get("course")
    #         if course and course["id"] == str(course_id):
    #             submissions = course["submissionsConnection"]["nodes"]
    #             for submission in submissions:
    #                 assignment = submission["assignment"]
    #                 if assignment:
    #                     submission_id = assignment.get("id")
    #                     if submission_id:
    #                         comment_nodes = submission["submissionCommentsConnection"]["nodes"]
    #                         for comment in comment_nodes:
    #                             comments.append({
    #                                 "assignment_id": assignment["id"],
    #                                 "assignment_name": assignment["name"],
    #                                 "comment_id": comment["id"],
    #                                 "author_name": comment["author"]["displayName"],
    #                                 "comment_text": comment["comment"],
    #                                 "created_at": comment["createdAt"]
    #                             })
    # except (KeyError, TypeError) as e:
    #     print("Error parsing response:", e)

    # return comments


def get_user_details(user_id, COURSE_ID=COURSE_ID):
    # Use the Canvas API to get user details

    print(f"Getting user details for user ID: {user_id}")
    url = f"{API_URL}/users/{user_id}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    result = response.json()
    if "errors" in result:
        print("Error:", result["errors"])
        return None
    print(f"{function_name()} user details for {user_id}:")
    pprint(result)
    return response.json()

if __name__ == "__main__":
    pass

    MIDTERM_GROUP_SET_ID = "22640"  # You can get this from the URL in Canvas (for midterm groups)
    WEEK4_GROUP_SET_ID = "22633"  # You can get this from the URL in Canvas (for week4 groups)

    
    (PROJECTS_FOLDER_NAME, GROUP_CATEGORY_ID) = ('cs5a-s25-ic12', WEEK4_GROUP_SET_ID)
    # (PROJECTS_FOLDER_NAME, GROUP_CATEGORY_ID) = ('cs5a-s25-midterm', MIDTERM_GROUP_SET_ID)


    # roster = make_roster_main(COURSE_ID)
    groups = get_groups(GROUP_CATEGORY_ID)
    # add_roster_fields_to_all_groups(groups, roster)
    
    make_roster_csv(COURSE_ID)


    
