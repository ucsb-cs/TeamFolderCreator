# TeamFolderCreator

One script, one job: given a Canvas group set, create a Google Drive folder
for each group, shared with that group's members, plus a spreadsheet that
links to all of them.

Run it again whenever the groups change in Canvas. It never creates
duplicates and never deletes anything; it only adds what is missing and
updates what is out of date.

Optionally, it can also bookmark each team's folder in that team's Slack
channel (see [Slack bookmarks](#slack-bookmarks-optional)).

A second script, `distribute_file.py`, copies a template Google Doc (e.g. a
team agreement) into every team's folder once `create_team_folders.py` has
created them (see [Distributing a file to every team](#distributing-a-file-to-every-team-optional)).


## Running it (after setup)

If you have already set up the tokens, etc., here's how you run the script.  Note that it will not work if you haven't set up the tokens yet to authenticate and authorize the actions in Canvas and Google Drive (see below), and optionally in Slack.

```bash
source venv/bin/activate
python create_team_folders.py \
    --course "CMPSC 156" --term "Fall 2026" \
    --group-set "Project Groups" \
    --folder-name "20264-CS156-F26" \
    --group-folder-name "CS156-F26-GroupFolders"
```

Preview first if you like:

```bash
python create_team_folders.py --course "CMPSC 156" --term "Fall 2026" \
    --group-set "Project Groups" --folder-name "20264-CS156-F26" \
    --group-folder-name "CS156-F26-GroupFolders" --dry-run
```

The same with Canvas ids instead of names:

```bash
python create_team_folders.py --course-id 32781 --group-set-id 28352 \
    --folder-name "20264-CS156-F26" --group-folder-name "CS156-F26-GroupFolders"
```

Once the team folders exist, `distribute_file.py` can copy a template Google
Doc into every team's folder (see [Distributing a file to every team](#distributing-a-file-to-every-team-optional)
for setup: it needs a `Templates` folder with exactly one Google Doc in it).
It needs the same tokens set up as above:

```bash
python distribute_file.py --course "CMPSC 156" --term "Fall 2026" \
    --group-set "Project Groups" --folder-name "20264-CS156-F26" \
    --group-folder-name "CS156-F26-GroupFolders" \
    --file-name "Team Agreement, {team}"
```

## What it creates

Given the name of an existing Google Drive folder (say
`20264-CS156-F26`), the script produces:

```
20264-CS156-F26/                 <- the parent folder; you create this
└── GroupFolders/                       <- created by the script; readable by anyone with the link
    ├── GroupFolders Index              <- spreadsheet: Group | Folder (link)
    ├── s26-01/                         <- one folder per Canvas group, named after it
    │   └── s26-01 Members              <- spreadsheet: Member | Email
    ├── s26-02/
    │   └── s26-02 Members
    └── ...
```

* Each group folder is shared (writer) with every member of that group.
* Because Drive folders inherit permissions, every group folder and
  spreadsheet is also readable by anyone with the link, so the links in
  `GroupFolders Index` work for anyone you give the index to.
* `<group> Members` lists the group's members with a header row
  `Member | Email`.

## What happens on later runs

| Change in Canvas                        | What the script does                                                 |
| --------------------------------------- | -------------------------------------------------------------------- |
| Nothing                                 | Reports everything is up to date; changes nothing                    |
| Student added to a group                | Shares that group's folder with them; updates the Members sheet      |
| Student removed from / moved to a group | Removes their access to the old folder; updates the Members sheet(s) |
| New group                               | Creates its folder and Members sheet; adds a row to the index        |
| Group deleted or renamed                | Leaves the old folder alone and prints a warning listing it          |

Rules that keep re-runs safe:

* Folders and spreadsheets are found **by name**. If two items with the same
  name exist in the same place, the script stops and asks you to fix it
  rather than guess. The parent folder must already exist; the script never
  creates it, so a misspelled name is an error rather than a stray folder.
* Access is only ever removed from people who are (or were) **students in
  the course**. Anyone else you share a folder with by hand, such as a TA,
  is left alone (the script prints who they are).
* The script never deletes or trashes folders or files, and never removes
  the owner.
* Use `--dry-run` to see exactly what a run would do without changing
  anything.
* **Don't rename the `GroupFolders` folder.** The script finds it by name
  (`GroupFolders` by default), so renaming it makes the next run think it's
  missing and create a brand new one, leaving your old folders as an
  orphaned duplicate. If you must rename it, pass the same new name via
  `--group-folder-name` on every future run (see the options table below).

## Setup

### 1. Python environment

Python 3.10 or newer.

```bash
git clone https://github.com/ucsb-cs/TeamFolderCreator.git
cd TeamFolderCreator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set up the Canvas token

1. In Canvas, go to **Account > Settings**.
2. Scroll to **Approved Integrations** and click **+ New Access Token**.
3. Give it a purpose (e.g. `TeamFolderCreator`) and an expiration date, then
   click **Generate Token**.
4. Copy the token now. Canvas will not show it again.
5. Save it in a file named `CANVAS_API_TOKEN` in this directory (one line,
   nothing else), or export it as an environment variable of the same name:

   ```bash
   echo 'PASTE-TOKEN-HERE' > CANVAS_API_TOKEN
   chmod 600 CANVAS_API_TOKEN
   ```

The token only needs the permissions your own Canvas account has. The script
only **reads** from Canvas (the group set, its groups and members, and the
student roster); it never writes to Canvas.

### 3. Set up Google credentials

The script acts as *you* in Google Drive through OAuth. You need an OAuth
client from Google Cloud once; after that, a browser login on first run.

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and
   create a project (or reuse one). Instructions:
   [creating a project](https://ucsb-cs156.github.io/topics/oauth/google_create_developer_project.html).
2. **Enable two APIs**: in **APIs & Services > Library**, search for and
   enable **Google Drive API** and **Google Sheets API**.
3. **Configure the OAuth consent screen** (**APIs & Services > OAuth consent
   screen**). Instructions:
   [OAuth consent screen](https://ucsb-cs156.github.io/topics/oauth/google_oauth_consent_screen.html).
   Add your own Google account as a test user.
4. **Create the OAuth client**: **APIs & Services > Credentials > Create
   Credentials > OAuth client ID**, application type **Desktop app**.
   Download the JSON file and save it as `credentials.json` in this
   directory.
5. The first time you run the script, a browser window opens asking you to
   sign in to Google and approve access to Drive. The resulting token is
   cached in `token.json` so you are not asked again.

Note on consent-screen "Testing" status: while the consent screen is in
Testing mode, Google expires the cached login after 7 days, and you will be
asked to sign in again. That is harmless. To avoid it, publish the consent
screen (Publishing status > **Publish app**); for an internal UCSB project
choose user type **Internal** instead, which needs no publishing.

### 4. Protect the tokens

`CANVAS_API_TOKEN`, `credentials.json`, `token.json` (and `SLACK_TOKEN` if
you use it) grant access to your Canvas courses, your Google Drive and your
Slack workspace. Treat them like passwords:

* They are listed in `.gitignore`. **Never commit them.** Check with
  `git status --ignored` if in doubt.
* Keep them readable only by you (`chmod 600 CANVAS_API_TOKEN credentials.json token.json`).
* Don't paste them into chat, issues or email.
* If one leaks: delete the Canvas token under **Account > Settings >
  Approved Integrations**; revoke the Google token at
  [myaccount.google.com/permissions](https://myaccount.google.com/permissions)
  and delete `token.json`; delete the OAuth client in the Cloud Console if
  `credentials.json` leaked.

## Naming the course and group set

You normally identify the course and group set by name:

* `--course "CMPSC 156"` is a phrase from the Canvas course name or course
  code, matched as whole words, ignoring case and extra spaces. Canvas names
  UCSB courses like `CMPSC 156 - ADV APP PROGRAM - Spring 2026` with course
  code `CMPSC 156 S26`, so `CMPSC 156` matches both (but `CS156` matches
  nothing). It must match exactly one of your courses.
* `--term "Spring 2026"` narrows the match when you have taught the course
  more than once. It is matched against the Canvas term name and also
  against the course name and code, so `S26` works too.
* `--group-set "Project Groups"` is the exact name of the group set (case
  and spacing don't matter). The group set names in the course are shown on
  the tabs of the **People** page.

If a lookup finds nothing, or more than one course, the script stops and
lists the candidates with their ids so you can refine the phrase, add
`--term`, or fall back to ids.

### Using ids instead

`--course-id` and `--group-set-id` take the Canvas ids directly:

1. In Canvas open the course, then **People**, then the tab for the group
   set you want (e.g. "Project Groups").
2. Look at the URL. It looks like
   `https://ucsb.instructure.com/courses/32781/groups#tab-28352`.
3. The number after `courses/` is the **course id** (`32781`); the number
   after `#tab-` is the **group set id** (`28352`).



Before the first run, create the parent folder (`20264-CS156-F26`
above) anywhere in your Drive. The script looks it up by name; if there is
no folder with that name, or more than one, it stops with a message saying
so. Everything the script creates goes inside `GroupFolders` under that
parent, so anything else you keep in the parent folder is unaffected and
stays private.

At the end the script prints the links to the `GroupFolders` folder and the
`GroupFolders Index` spreadsheet.

All options (`python create_team_folders.py --help`):

| Option                 | Default                         | Meaning                                                                 |
| ---------------------- | ------------------------------- | ----------------------------------------------------------------------- |
| `--course`             | one of these two is required    | Phrase from the Canvas course name or code, e.g. `"CMPSC 156"`         |
| `--course-id`          |                                 | Canvas course id                                                        |
| `--term`               | none                            | With `--course`: narrow to a term, e.g. `"Spring 2026"` or `"S26"`      |
| `--group-set`          | one of these two is required    | Name of the group set, e.g. `"Project Groups"`                          |
| `--group-set-id`       |                                 | Canvas group set (group category) id                                    |
| `--folder-name`        | required                        | Existing Google Drive folder that `GroupFolders` goes under             |
| `--group-folder-name`  | `GroupFolders`                  | Name of the folder (under `--folder-name`) that holds the team folders. Change this only if you renamed `GroupFolders` after a previous run — use the *same* new name every time, or you will get a second, duplicate set of folders |
| `--canvas-url`         | `https://ucsb.instructure.com`  | Your Canvas instance                                                    |
| `--email-domain`       | `ucsb.edu`                      | Appended to each Canvas login id to get the student's Google account    |
| `--canvas-token-file`  | `CANVAS_API_TOKEN`              | File holding the Canvas token (env var `CANVAS_API_TOKEN` overrides it) |
| `--credentials`        | `credentials.json`              | Google OAuth client file                                                |
| `--token`              | `token.json`                    | Where the Google login is cached                                        |
| `--update-slack-bookmarks` | off                         | Also bookmark each folder in its team's Slack channel (see below)       |
| `--slack-token-file`   | `SLACK_TOKEN`                   | File holding the Slack token (env var `SLACK_TOKEN` overrides it)       |
| `--dry-run`            | off                             | Report what would change; change nothing                                |
| `-v`, `--verbose`      | off                             | Debug output                                                            |

## Distributing a file to every team (optional)

Once `create_team_folders.py` has created the team folders, `distribute_file.py`
can copy a template Google Doc (e.g. a team agreement) into every team's
folder:

```bash
python distribute_file.py --course "CMPSC 156" --term "Fall 2026" \
    --group-set "Project Groups" --folder-name "20264-CS156-F26" \
    --group-folder-name "CS156-F26-GroupFolders" \
    --file-name "Team Agreement, {team}"
```

It takes the same `--course`/`--course-id`, `--term`, `--group-set`/
`--group-set-id` and `--folder-name` options as `create_team_folders.py`
(see above), plus:

* `--file-name` (required): the name to give the copy in each team's folder.
  `{team}` is replaced by the team's name, e.g. `"Team Agreement, {team}"`
  becomes `"Team Agreement, s26-01"`.
* `--group-folder-name` (default `GroupFolders`): must match whatever
  `--group-folder-name` you used (if any) with `create_team_folders.py`, so
  it looks inside the right folder.

Before running it:

1. Run `create_team_folders.py` so that `GroupFolders` and each team's folder
   already exist.
2. Inside `GroupFolders`, create a folder named `Templates` and put the
   Google Doc to distribute in it. There must be exactly one Google Doc in
   `Templates`.

For each team, the script looks for a file with the target name already in
that team's folder; if one is there, it is left alone (never overwritten,
never duplicated). Otherwise it copies the template doc in. Teams with no
folder yet (i.e. `create_team_folders.py` hasn't been run for them) are
reported as warnings and skipped. `--dry-run` and `-v`/`--verbose` work the
same way as for `create_team_folders.py`.

## Slack bookmarks (optional)

If each team has a Slack channel named `team-<group name>` (for a Canvas
group `s26-01`, the channel `#team-s26-01`), the script can add a bookmark
called **Google Drive Folder** to each channel that links to the team's
folder:

```bash
python create_team_folders.py --course "CMPSC 156" --term "Fall 2026" \
    --group-set "Project Groups" --folder-name "20264-CS156-F26" \
    --group-folder-name "CS156-F26-GroupFolders" \
    --update-slack-bookmarks
```

This runs after the Drive folders are created or updated. For each group it
looks for the channel; if there is none it prints a warning and moves on.
Re-running is safe: an existing **Google Drive Folder** bookmark is left
alone if its link is unchanged, or edited if the folder link changed, so
you never get duplicates. Other bookmarks in the channel are not touched.

Channel names are derived from group names by lower-casing, turning spaces
into `-`, and dropping characters Slack doesn't allow, so `Group 2` maps
to `#team-group-2`.

### Set up the Slack token

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click
   **Create New App > From scratch**. Name it (e.g. `TeamFolderCreator`) and
   pick your course workspace.
2. Under **OAuth & Permissions > Scopes**, add these **Bot Token Scopes**:
   * `channels:read` to find the `#team-...` channels
   * `bookmarks:read` to see whether the bookmark already exists
   * `bookmarks:write` to add or update it
   * `groups:read` only if some team channels are private
3. Click **Install to Workspace** and approve. Copy the **Bot User OAuth
   Token** (it starts with `xoxb-`).
4. Save it in a file named `SLACK_TOKEN` in this directory (one line), or
   export it as the `SLACK_TOKEN` environment variable:

   ```bash
   echo 'xoxb-PASTE-TOKEN-HERE' > SLACK_TOKEN
   chmod 600 SLACK_TOKEN
   ```

5. The app must be a member of each team channel to add bookmarks. Invite it
   in each channel with `/invite @TeamFolderCreator` (or whatever you named
   the app). Channels where it is not a member are reported as warnings.

`SLACK_TOKEN` is in `.gitignore`; protect it like the other tokens. If it
leaks, go to the app's **OAuth & Permissions** page and click **Revoke**
(or reinstall the app to rotate the token).

You can use a user token (`xoxp-`) instead, with the same scopes added
under **User Token Scopes**; then the bookmarks are added as you, and *you*
must be a member of each team channel.

## How it works

`create_team_folders.py` is the command line entry point. It uses three modules:

* `canvas_api.py` looks up the course and group set by name, then reads the
  group set, each group's members and the course roster from Canvas. Canvas only exposes each member's login id, so the
  Google account email is `login_id@ucsb.edu` (change `--email-domain` for
  another campus).
* `google_drive.py` wraps the few Drive and Sheets API calls needed:
  find-or-create by name, list/add/remove permissions, read/write the first
  two columns of a sheet. Every write honours `--dry-run`. Transient API
  errors (rate limits, 5xx) are retried automatically.
* `slack_bookmarks.py` (only with `--update-slack-bookmarks`) lists the
  workspace's channels once, then for each team checks the channel's
  bookmarks and adds or edits the **Google Drive Folder** one.
* `team_folders.py` does the work in this order: find the parent folder,
  `GroupFolders` (plus "anyone with the link" access), then for each group
  its folder, its member permissions, and its Members sheet; finally the
  index sheet. Spreadsheets are only rewritten when their contents differ
  from what Canvas says.
* `file_distribution.py` is used by `distribute_file.py`. It finds the
  single Google Doc in `GroupFolders/Templates`, then for each team copies
  it into that team's (already existing) folder under the requested name,
  skipping teams that already have a file with that name.

Group folders are sorted naturally in the index (`Group 2` before
`Group 10`).

## Troubleshooting

* **`Canvas rejected the API token (HTTP 401)`**: the token has expired or
  been deleted. Create a new one (Setup step 2).
* **`2 courses match 'CMPSC 156'`**: you have taught it more than once. Add
  `--term`, or use `--course-id` with one of the ids listed.
* **`No course matching ...`**: use a phrase as Canvas spells it (e.g.
  `CMPSC 156`, not `CS156`), or check the term spelling.
* **`Course ... has no group set named ...`**: the message lists the group
  sets that exist; copy the name exactly.
* **`Group set ... belongs to course X, not course Y`**: the group set id and
  course id don't match; re-check the URL.
* **`No folder named '...' found in your Google Drive`**: create the parent
  folder first, or fix the spelling of `--folder-name`.
* **`Found 2 folders named '...'`** (or items): there are two folders or
  sheets with the same name (perhaps from an earlier manual attempt). Trash
  or rename one and re-run.
* **`could not share with <email>`**: that address is not a Google account
  (Drive refuses to share silently with unknown addresses). Check the login
  id / email domain, or share by hand.
* **`could not enable 'anyone with the link'`**: your Google Workspace
  forbids link sharing. Share `GroupFolders` manually with the audience you
  want.
* **`--update-slack-bookmarks needs a Slack token`**: create the `SLACK_TOKEN`
  file (see "Slack bookmarks").
* **`The Slack token lacks the '...' scope`**: add the named scope in the
  app's OAuth & Permissions page and reinstall the app to the workspace.
* **`no Slack channel #team-...`**: the channel doesn't exist or isn't
  visible to the token (private channels need `groups:read`). The script
  continues with the other teams.
* **`the Slack token's account is not a member of #team-...`**: invite the
  app (or yourself, for a user token) to that channel and re-run.
* **Browser login keeps reappearing every week**: see the note on consent
  screen Testing status in Setup step 3.
* **Folders for old groups are listed as unmatched**: expected after groups
  are deleted or renamed in Canvas. The script leaves them alone; trash them
  yourself if you want.
* **A second `GroupFolders`-like folder appeared after renaming it**: you
  renamed `GroupFolders` without passing `--group-folder-name`; the script
  didn't find the renamed folder and created a new `GroupFolders`. Trash the
  new (empty, or nearly so) one, then always pass
  `--group-folder-name "<your renamed name>"` on future runs of both
  scripts.
* **`No Google Doc found in the 'Templates' folder`** (`distribute_file.py`):
  create a `Templates` folder inside `GroupFolders` and put the document to
  distribute in it.
* **`Found 2 Google Docs in the 'Templates' folder`**: trash or move the
  extra doc so exactly one remains.
* **`no team folder found` for a team** (`distribute_file.py`): that team has
  no folder yet; run `create_team_folders.py` first.

## Development

Run the unit tests (no network access needed):

```bash
python -m unittest discover -s tests -v
```

The tests exercise the Canvas parsing, the permission add/remove planning,
the idempotent sync logic (against an in-memory fake Drive), file
distribution, and dry-run mode.

## History

This is a clean rewrite of the group-folder parts of
[TeamFolderScripts](https://github.com/ucsb-cs/TeamFolderScripts), which had
accumulated code for several other tasks (notebooks, retros, Google Chat).
