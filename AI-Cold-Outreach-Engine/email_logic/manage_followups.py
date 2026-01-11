#!/usr/bin/env python3
"""
Script to manage follow-up emails for plumbers.
Reads Google Sheet, checks 'Last_Date' and 'Step', and creates drafts for follow-ups.
"""

import os
import sys
import datetime
import base64
from pathlib import Path
from email.mime.text import MIMEText
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

# Configuration
SCOPES = [
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/spreadsheets'
]
SPREADSHEET_ID = os.getenv('GOOGLE_SHEET_ID')

# Column Indices (Assuming standard layout, 0-indexed)
# Users might move columns, but we'll assume a schema for now based on typical usage.
# If header row exists, we could map names. Let's assume schema:
# Name(0), Owner(1), Email(2), Website(3), Rating(4), Reviews(5), Status(6), Step(7), Last_Date(8)
# If Step/Last_Date don't exist, we might need to handle that.
# For robustness, we'll try to find headers.

def load_credentials():
    """Load OAuth credentials."""
    creds = None
    token_path = Path('token.json')
    credentials_path = Path('credentials.json')
    
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                print("Error: credentials.json not found.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    return creds

def create_draft(service, to_email, subject, body):
    """Create a Gmail draft."""
    try:
        message = MIMEText(body)
        message['To'] = to_email
        message['Subject'] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        draft = service.users().drafts().create(
            userId='me', 
            body={'message': {'raw': raw}}
        ).execute()
        return draft['id']
    except Exception as e:
        print(f"Error creating draft: {e}")
        return None

def get_days_diff(date_str):
    """Calculate days passed since date_str (YYYY-MM-DD)."""
    try:
        # Try multiple formats
        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y'):
            try:
                dt = datetime.datetime.strptime(date_str, fmt).date()
                return (datetime.date.today() - dt).days
            except ValueError:
                continue
        return 0 # Default if parse fail
    except Exception:
        return 0

def get_template(step, owner):
    """Return subject and body for follow-up step."""
    name = owner if owner and owner.lower() != 'not found' else 'there'
    
    if step == 2:
        subj = "Following up: AI Receptionist"
        body = f"""Hi {name},

Just checking if you saw my previous email. I know things get buried!

Are you still dealing with missed calls during busy hours?

Best,
YourPlumberAI Team"""
    elif step == 3:
        subj = "Last try: AI Receptionist"
        body = f"""Hi {name},

I haven't heard back, so I assume you're all set with your current phone handling.

I'll stop reaching out now. If you ever need to automate your lead capture, feel free to reply.

Best,
YourPlumberAI Team"""
    else:
        return None, None
    
    return subj, body

def main():
    if not SPREADSHEET_ID:
        print("Error: GOOGLE_SHEET_ID not set.")
        sys.exit(1)

    creds = load_credentials()
    sheets_service = build('sheets', 'v4', credentials=creds)
    gmail_service = build('gmail', 'v1', credentials=creds)

    # Read Sheet
    sheet = sheets_service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range='Sheet1!A:Z').execute()
    rows = result.get('values', [])

    if not rows:
        print("No data found.")
        return

    # Map Headers
    headers = [h.lower() for h in rows[0]]
    try:
        col_status = headers.index('status')
        col_email = headers.index('email')
        col_owner = headers.index('owner')
        
        # Try to find Step/Last_Date, if not create logic to handle them via fixed indices or appending?
        # User prompt implies they exist.
        col_step = headers.index('step')
        col_date = headers.index('last_date')
    except ValueError as e:
        print(f"Error: Missing required column: {e}")
        print(f"Available columns: {headers}")
        print("Please add 'Step' and 'Last_Date' columns to your sheet.")
        return

    print("Analyzing rows for follow-ups...")
    
    updates = []

    for i, row in enumerate(rows[1:], start=2): # 1-based index, skip header
        # Pad row if incomplete
        if len(row) <= max(col_status, col_step, col_date):
            continue

        status = row[col_status]
        step = row[col_step]
        last_date = row[col_date]
        email = row[col_email]
        owner = row[col_owner]

        if status.lower() != 'sent':
            continue

        try:
            step_num = int(step)
        except ValueError:
            continue

        days_passed = get_days_diff(last_date)
        
        if days_passed < 3:
            continue

        # Logic
        if step_num < 3:
            new_step = step_num + 1
            subj, body = get_template(new_step, owner)
            
            if subj:
                print(f"Creating Draft Step {new_step} for {email} (Days passed: {days_passed})")
                draft_id = create_draft(gmail_service, email, subj, body)
                
                if draft_id:
                    # Queue Update
                    # Update Status -> 'Draft Created', Step -> new_step, Last_Date -> Today
                    # Batch updates are better but for simplicity/safety we'll do one by one or print
                    # Actually we need to write back using ranges.
                    
                    # Update Step
                    sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=f'Sheet1!{chr(65+col_step)}{i}', 
                                          valueInputOption='RAW', body={'values': [[new_step]]}).execute()
                    # Update Status
                    sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=f'Sheet1!{chr(65+col_status)}{i}', 
                                          valueInputOption='RAW', body={'values': [['Draft Created']]}).execute()
                    # Update Date
                    today = datetime.date.today().strftime('%Y-%m-%d')
                    sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=f'Sheet1!{chr(65+col_date)}{i}', 
                                          valueInputOption='RAW', body={'values': [[today]]}).execute()

        elif step_num == 3:
            # Revoke
            print(f"Revoking lead {email} (Step 3 complete, {days_passed} days stale)")
            sheet.values().update(spreadsheetId=SPREADSHEET_ID, range=f'Sheet1!{chr(65+col_status)}{i}', 
                                  valueInputOption='RAW', body={'values': [['Revoked']]}).execute()

if __name__ == "__main__":
    main()
