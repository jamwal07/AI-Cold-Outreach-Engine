# AI Cold Outreach Engine

A completely autonomous system for finding, qualifying, and contacting plumbing leads. This project demonstrates a 3-layer architecture (Directive -> Orchestration -> Execution) to handle business growth on autopilot.

## 🏗 System Architecture

The system is split into three distinct layers to ensure reliability and scalability:

1.  **Prospecting Layer (`prospecting/`)**:
    *   Example: `find_leads.py`
    *   **Function**: Uses SerpApi to find local plumbers in a specific city.
    *   **Logic**: Filters for plumbers with 3.5-4.5 stars (the "Sweet Spot" for AI receptionist sales) and 30+ reviews.
    *   **Intelligent Filtering**: Scans fragments for keywords like "didn't answer" or "bad service" to identify high-intent prospects.

2.  **Logic Layer (`email_logic/`)**:
    *   Example: `check_replies.py` & `manage_followups.py`
    *   **Function**: Acts as the brain of the email campaign.
    *   **Features**:
        *   Connects to Gmail via OAuth2 (Secure).
        *   Reads tracking status from a central Google Sheet.
        *   Detects replies *intelligently* (ignores auto-responders or your own sends).
        *   Auto-drafts follow-up emails based on how many days have passed (e.g., "Bump" email after 3 days).

3.  **Orchestration Layer (`workflows/`)**:
    *   Example: `n8n_orchestration.json`
    *   **Function**: The heartbeat of the operation.
    *   **Role**: An n8n workflow that schedules the Python scripts to run at specific intervals (e.g., Check replies every hour, Send follow-ups at 9 AM).

## 🚀 Setup & Installation

### 1. Requirements
*   Python 3.10+
*   Google Cloud Project (Gmail API & Sheets API enabled)
*   SerpApi Account

### 2. Environment Variables
Create a `.env` file in the root directory:
```bash
SERPAPI_KEY=your_serpapi_key_here
GOOGLE_SHEET_ID=your_sheet_id_here
```

### 3. Google Auth
Place your `credentials.json` from Google Cloud Console in the root folder.
*Note: The system will generate a `token.json` after the first successful login.*

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

## 🛡 Security & Privacy
This repository contains **NO** scraped data or private keys.
*   `.env` files are gitignored.
*   `credentials.json` and `token.json` are gitignored.
*   Prospect lists (PII) are gitignored.

## 📄 License
MIT License. Free to use for your own automation projects.
