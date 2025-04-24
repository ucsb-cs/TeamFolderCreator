# TeamFolderCreator

Scripts to:
* Enable instructors to create Google Drive folders for student teams to collaborate
* Extract Group Sets from Canvas as CSV files


# Getting Started

## Set up Python venv

```
python3 -m venv venv
source ./venv/bin/activate
pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib pandas requests
```

Then set up credentials.  You need two kinds:
* Google OAuth Credentials, stored in `credentials.json`
* Canvas API Token, stored in `CANVAS_API_TOKEN`

Instruction on setting those up appear below under "Set up Google Credentials"

## Getting CSV of students/groups

To get a CSV of the groups that students belong to:

1. Navigate to the page where the groups are set up in Canvas, e.g. <https://ucsb.instructure.com/courses/25658/groups#tab-22633>
2. Get the group number from the URL in Canvas, e.g. for the url above, it's `22633`
3. Set this variable in the line of code in the script `canvas_get_group_set.py`

   ```
   GROUP_CATEGORY_ID = "22633"  # You can get this from the URL ```
4. Run the script via: `python canvas_get_group_set.py`
5. Your groups are now in the file `canvas_group_export.csv`

To then create Google Drive folders:

1. Create a top level Google Drive folder with a unique name, e.g. `CS5A-S25-ic10`.  
2. Create `Initial Contents` inside that folder and put the Jupyter notebook you want students to work with inside that folder.  The script assumes that `Initial Contents` will contain a single file with the extension `.ipynb`
3. Also inside the top level folder, create a `data` folder, if desired, that will have the data files you want students to be able to access.
4. Set the permissions on the data file to these:
   <img width="469" alt="image" src="https://github.com/user-attachments/assets/aa662e12-6495-43a6-8524-8b4b6fa9ce3f" />
5. Get the URL of the `data` *folder* and paste it into the Notebook inside the cells that have the `!gdata` line that mounts the data folder.
6. Run the script `python make_group_notebook_folders.py`
7. The URLs will now be in `output_with_links.py`


## Set up Google credentials

### Google Developer Console

Preliminaries:

1. Go to the Google Developer Console (<https://console.cloud.google.com/>)
1. If you do not already have a "project", set up one  ([details here](https://ucsb-cs156.github.io/topics/oauth/google_create_developer_project.html)) 
1. If you do not already have an OAuth consent screen set one up([details here](https://ucsb-cs156.github.io/topics/oauth/google_oauth_consent_screen.html))

Getting credentials:

1. Enable the Google Drive API:
    * In the left menu, go to APIs & Services > Library.
    * Search for Google Drive API and enable it.
2. Create OAuth 2.0 Credentials:
    * Go to APIs & Services > Credentials.
    * Click Create Credentials > OAuth client ID.
    * Choose Desktop App or Web Application (for local scripts, Desktop is fine).
    * Download the JSON credentials file and rename it to `credentials.json`.
    * Note that `credentials.json` is in the `.gitignore` and should *not* be stored in the repo

## Set up Canvas credentials

You’ll need to:
* Log into your Canvas account.
* Go to Account > Settings.
* Scroll down to "Approved Integrations" and click + New Access Token.
* Give it a name, set an expiration, and create it.
* Copy the access token (you won’t be able to see it again!).
* Store the access token in a file called `CANVAS_API_TOKEN`
* Note that `CANVAS_API_TOKEN` is in the `.gitignore` and should *not* be stored in the Github repo.


