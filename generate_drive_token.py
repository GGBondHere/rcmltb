# Source: https://github.com/anasty17/mirror-leech-telegram-bot/blob/master/generate_drive_token.py

import os
from drive_credentials import read_drive_credentials, write_drive_credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

credentials = None
__G_DRIVE_TOKEN_FILE = "token.pickle"
__OAUTH_SCOPE = ["https://www.googleapis.com/auth/drive"]
if os.path.exists(__G_DRIVE_TOKEN_FILE):
    credentials = read_drive_credentials(__G_DRIVE_TOKEN_FILE)
    if not credentials.valid and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
else:
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", __OAUTH_SCOPE)
    credentials = flow.run_local_server(port=0, open_browser=False)

# Save the credentials for the next run
write_drive_credentials(credentials, __G_DRIVE_TOKEN_FILE)
