## Duolingo


I made this so I don't lose my 1000 day streak for 3 days I can't use my phone coming up, I'm not a terrible person D:

### 1) Install

```powershell
cd C:\Users\Alex\Desktop\DuoAuto
py -3 -m venv .venv
. .venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

### 2) Run once to verify

```powershell
python .\duo_story_bot.py --chrome-user-data-dir "$env:LOCALAPPDATA\Google\Chrome\User Data" --chrome-profile-name "Default"
```

If you are not already logged into Duolingo with that Chrome profile, provide your credentials once via CLI flags and the script
will prompt for them in future runs if they are not saved:

```powershell
python .\duo_story_bot.py --username "name@example.com" --password "yourPassword"
```

Leaving out the `--password` flag will cause the script to prompt securely when login is required, so you do not have to store it
in plain text.

Notes:

- If you use another Chrome profile, change `--chrome-profile-name` (e.g. `Profile 1`).
- Optional: pick a specific story via `--story-path`, e.g. `--story-path "/en/intro-1"` or full URL.
- Add `--headless` if you prefer. If it fails in headless, run visible.

### 3) Schedule daily on Windows (Task Scheduler)

1. Open Task Scheduler → Create Task.
2. General: Name it "Duolingo Streak Bot". Run whether user logged on or not.
3. Triggers: New → Daily → set time.
4. Actions: New → Start a program.
   - Program/script: `powershell.exe`
   - Add arguments:
     ```
     -NoProfile -ExecutionPolicy Bypass -Command "cd 'C:\Users\Alex\Desktop\DuoAuto'; if (-not (Test-Path .venv)) { py -3 -m venv .venv }; . .venv\Scripts\Activate.ps1; if (-not (Get-Command pip -ErrorAction SilentlyContinue)) { python -m ensurepip }; pip install -r requirements.txt | Out-Null; python .\duo_story_bot.py --chrome-user-data-dir '$env:LOCALAPPDATA\Google\Chrome\User Data' --chrome-profile-name 'Default'"
     ```
5. Conditions: Uncheck "Start the task only if the computer is on AC power" if needed.
6. Settings: Enable "Run task as soon as possible after a scheduled start is missed".

### Config file (optional)

Create `config.json` like:

```json
{
  "chrome_user_data_dir": "C:/Users/Alex/AppData/Local/Google/Chrome/User Data",
  "chrome_profile_name": "Default",
  "story_path": null,
  "headless": false,
  "max_steps": 200,
  "wait_secs": 20,
  "username": "name@example.com",
  "password": "yourPassword"
}
```

Run with:

```powershell
python .\duo_story_bot.py --config .\config.json
```

### Tips

- Make sure Chrome is closed when the bot starts, so the profile isn't locked.
- If the site UI changes, update selectors in `duo_story_bot.py` (search for `stories-player-continue`, `challenge` selectors, etc.).
- This script is intentionally dumb on answers; it clicks through and guesses. If you want higher accuracy, add logic to scrape prompts and compute answers, but it's usually unnecessary to keep a streak.
