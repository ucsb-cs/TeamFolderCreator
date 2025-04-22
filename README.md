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

Here's how to set those up:

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


