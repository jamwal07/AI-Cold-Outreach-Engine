#!/usr/bin/env python3
"""
Script to check for email replies and update Google Sheet status.

This script:
1. Connects to Google Sheet and finds all leads with Status 'Sent'
2. Uses Gmail API to check if there are any incoming messages in those email threads
3. If a reply is found: Updates Sheet Status to 'Replied' and Step to 'Stop'
4. If no reply: Does nothing (leaves it for n8n timing)

Architecture: Layer 3 (Execution) - Deterministic script for checking Gmail replies.
Uses credentials.json for OAuth authentication and .env for GOOGLE_SHEET_ID.
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("Error: Google API libraries not installed. Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    sys.exit(1)

# Gmail API scopes - need read access for checking replies
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/spreadsheets'
]


def load_credentials():
    """Load or create OAuth credentials for Google APIs."""
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
                print("Error: credentials.json not found. Please set up OAuth credentials.")
                print("See: https://developers.google.com/gmail/api/quickstart/python")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    
    return creds


def get_sent_leads(sheets_service, spreadsheet_id: str) -> List[Dict]:
    """
    Get all leads from Google Sheet with Status 'Sent'.
    Returns list of dictionaries with row index and lead data.
    Expected columns: Business Name, Owner, Email, Website, Rating, Review Count, Status, Step
    
    Robust error handling: Handles missing columns, empty rows, and API errors.
    """
    try:
        # Read all data from Sheet1 - use a wide range to catch all columns
        range_name = 'Sheet1!A:Z'  # Wide range to handle varying column counts
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        
        values = result.get('values', [])
        
        if not values:
            print("No data found in sheet.")
            return []
        
        # Assume first row is header
        headers = values[0] if values else []
        
        if not headers:
            print("Error: No header row found in sheet.")
            return []
        
        # Find column indices with robust error handling
        try:
            status_col = headers.index('Status')
            email_col = headers.index('Email')
        except ValueError as e:
            print(f"Error: Required column not found in sheet. {e}")
            print(f"Available columns: {headers}")
            return []
        
        # Find step column if it exists (optional)
        step_col = headers.index('Step') if 'Step' in headers else None
        
        sent_leads = []
        
        # Start from row 2 (index 1) to skip header
        for row_idx, row in enumerate(values[1:], start=2):
            # Pad row with empty strings if needed to avoid index errors
            max_col_needed = max(status_col, email_col, step_col if step_col is not None else 0)
            while len(row) <= max_col_needed:
                row.append('')
            
            # Safely extract status and email
            status = row[status_col].strip() if status_col < len(row) and row[status_col] else ''
            email = row[email_col].strip() if email_col < len(row) and row[email_col] else ''
            
            # Only process rows with Status 'Sent' and a valid email
            if status == 'Sent' and email and '@' in email:
                lead = {
                    'row': row_idx,
                    'email': email,
                    'status_col': status_col + 1,  # Convert to 1-based for A1 notation
                    'step_col': step_col + 1 if step_col is not None else None,
                    'row_data': row
                }
                sent_leads.append(lead)
        
        return sent_leads
        
    except HttpError as error:
        print(f"Error reading Google Sheet: {error}")
        if error.resp.status == 404:
            print(f"  Sheet not found. Check that GOOGLE_SHEET_ID is correct.")
        elif error.resp.status == 403:
            print(f"  Permission denied. Check that credentials.json has Sheets API access.")
        return []
    except Exception as error:
        print(f"Unexpected error reading Google Sheet: {error}")
        return []


def get_user_email(gmail_service) -> str:
    """Get the authenticated user's email address."""
    try:
        profile = gmail_service.users().getProfile(userId='me').execute()
        return profile.get('emailAddress', '')
    except HttpError as error:
        print(f"Error getting user email: {error}")
        return ''


def find_sent_message_thread(gmail_service, to_email: str, user_email: str) -> Optional[str]:
    """
    Find the Gmail thread ID for a sent message to the given email address.
    Returns the thread ID if found, None otherwise.
    
    Uses Gmail search to find the most recent sent message to the recipient.
    """
    try:
        # Search for sent messages to this email (most recent first)
        query = f'to:{to_email} from:{user_email}'
        results = gmail_service.users().messages().list(
            userId='me',
            q=query,
            maxResults=1
        ).execute()
        
        messages = results.get('messages', [])
        if messages:
            # Get the most recent message
            message_id = messages[0]['id']
            message = gmail_service.users().messages().get(
                userId='me',
                id=message_id,
                format='metadata',
                metadataHeaders=['From', 'To', 'Subject']
            ).execute()
            
            thread_id = message.get('threadId')
            if thread_id:
                return thread_id
        
        return None
        
    except HttpError as error:
        print(f"  Error searching for sent message: {error}")
        if error.resp.status == 401:
            print(f"  Authentication error. Check credentials.json and token.json.")
        elif error.resp.status == 403:
            print(f"  Permission denied. Check Gmail API scopes in credentials.")
        return None
    except Exception as error:
        print(f"  Unexpected error finding thread: {error}")
        return None


def check_thread_for_reply(gmail_service, thread_id: str, user_email: str) -> bool:
    """
    Check if there are any incoming replies in the given thread.
    Returns True if a reply from the recipient is found, False otherwise.
    
    Robustly checks all messages in the thread to identify incoming replies.
    """
    try:
        thread = gmail_service.users().threads().get(
            userId='me',
            id=thread_id,
            format='full'
        ).execute()
        
        messages = thread.get('messages', [])
        
        if not messages:
            return False
        
        user_email_lower = user_email.lower()
        
        # Check each message in the thread
        for message in messages:
            payload = message.get('payload', {})
            headers = payload.get('headers', [])
            
            # Get sender email from headers
            sender = ''
            for header in headers:
                if header['name'].lower() == 'from':
                    sender = header['value']
                    break
            
            if not sender:
                continue
            
            # Extract email from "Name <email@example.com>" or "email@example.com" format
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', sender)
            if email_match:
                sender_email = email_match.group(0).lower()
            else:
                sender_email = sender.lower()
            
            # Check if this is a reply (not from us)
            if sender_email != user_email_lower:
                # Check if message is not in SENT label (meaning it's incoming)
                label_ids = message.get('labelIds', [])
                if 'SENT' not in label_ids:
                    return True
        
        return False
        
    except HttpError as error:
        print(f"  Error checking thread: {error}")
        if error.resp.status == 404:
            print(f"  Thread not found. It may have been deleted.")
        return False
    except Exception as error:
        print(f"  Unexpected error checking thread: {error}")
        return False


def column_number_to_letter(n: int) -> str:
    """Convert column number (1-based) to Excel column letter (A, B, ..., Z, AA, AB, ...)."""
    result = ""
    while n > 0:
        n -= 1
        result = chr(65 + (n % 26)) + result
        n //= 26
    return result


def update_sheet_status(sheets_service, spreadsheet_id: str, row: int, 
                        status_col: int, step_col: Optional[int], 
                        status: str, step: str = 'Stop') -> bool:
    """
    Update the Status and Step columns for a specific row in Google Sheet.
    
    Robustly handles updates with proper error handling and validation.
    """
    try:
        # Convert to A1 notation (e.g., Sheet1!G2)
        status_letter = column_number_to_letter(status_col)
        status_range = f'Sheet1!{status_letter}{row}'
        
        body = {
            'values': [[status]]
        }
        
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=status_range,
            valueInputOption='RAW',
            body=body
        ).execute()
        
        # Update Step column if it exists
        if step_col is not None:
            step_letter = column_number_to_letter(step_col)
            step_range = f'Sheet1!{step_letter}{row}'
            body = {
                'values': [[step]]
            }
            sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=step_range,
                valueInputOption='RAW',
                body=body
            ).execute()
        
        return True
        
    except HttpError as error:
        print(f"  Error updating sheet: {error}")
        if error.resp.status == 404:
            print(f"  Sheet or range not found. Check GOOGLE_SHEET_ID and sheet structure.")
        elif error.resp.status == 403:
            print(f"  Permission denied. Check Sheets API access in credentials.")
        return False
    except Exception as error:
        print(f"  Unexpected error updating sheet: {error}")
        return False


def main():
    """
    Main execution function.
    
    Follows Layer 3 (Execution) architecture: deterministic, reliable, handles errors.
    Uses credentials.json for OAuth and .env for GOOGLE_SHEET_ID.
    """
    # Load environment variables from .env
    spreadsheet_id = os.getenv('GOOGLE_SHEET_ID')
    if not spreadsheet_id:
        print("Error: GOOGLE_SHEET_ID environment variable not set.")
        print("Set it in your .env file: GOOGLE_SHEET_ID=your_sheet_id")
        sys.exit(1)
    
    # Load credentials from credentials.json
    print("Loading Google API credentials from credentials.json...")
    try:
        creds = load_credentials()
    except Exception as e:
        print(f"Error loading credentials: {e}")
        print("Ensure credentials.json exists in the project root.")
        sys.exit(1)
    
    # Build API services
    try:
        gmail_service = build('gmail', 'v1', credentials=creds)
        sheets_service = build('sheets', 'v4', credentials=creds)
    except Exception as e:
        print(f"Error building API services: {e}")
        sys.exit(1)
    
    # Get user's email address
    print("Getting user email address...")
    user_email = get_user_email(gmail_service)
    if not user_email:
        print("Error: Could not retrieve user email address.")
        sys.exit(1)
    
    print(f"User email: {user_email}\n")
    
    # Get all leads with Status 'Sent'
    print("Reading Google Sheet for leads with Status 'Sent'...")
    sent_leads = get_sent_leads(sheets_service, spreadsheet_id)
    
    if not sent_leads:
        print("No leads with Status 'Sent' found.")
        return
    
    print(f"Found {len(sent_leads)} lead(s) with Status 'Sent'.\n")
    
    # Check each lead for replies
    replied_count = 0
    error_count = 0
    
    for i, lead in enumerate(sent_leads, 1):
        email = lead['email']
        row = lead['row']
        
        print(f"[{i}/{len(sent_leads)}] Checking: {email}")
        
        try:
            # Find the Gmail thread for this email
            thread_id = find_sent_message_thread(gmail_service, email, user_email)
            
            if not thread_id:
                print(f"  ⚠ No sent message thread found. Skipping.")
                continue
            
            # Check if there's a reply in the thread
            has_reply = check_thread_for_reply(gmail_service, thread_id, user_email)
            
            if has_reply:
                print(f"  ✓ Reply found! Updating status...")
                
                # Update sheet
                success = update_sheet_status(
                    sheets_service,
                    spreadsheet_id,
                    row,
                    lead['status_col'],
                    lead['step_col'],
                    'Replied',
                    'Stop'
                )
                
                if success:
                    print(f"  ✓ Updated Status to 'Replied' and Step to 'Stop'")
                    replied_count += 1
                else:
                    print(f"  ✗ Failed to update sheet")
                    error_count += 1
            else:
                print(f"  - No reply yet. Doing nothing (n8n handles timing).")
        
        except Exception as e:
            print(f"  ✗ Unexpected error processing lead: {e}")
            error_count += 1
            continue
    
    # Summary
    print(f"\n✓ Check complete.")
    print(f"  - {replied_count} lead(s) updated to 'Replied' with Step 'Stop'")
    if error_count > 0:
        print(f"  - {error_count} error(s) encountered")


if __name__ == "__main__":
    main()
