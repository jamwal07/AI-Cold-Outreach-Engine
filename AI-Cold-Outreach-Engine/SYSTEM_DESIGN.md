# System Overview: Plumber Outreach Workflow

This document aggregates the updated architecture, directives, and code for the Plumber Outreach System.

## 1. Architecture (`gemini.md`)
3-Layer Architecture:
- **Directive**: SOPs (Markdown) - Defines the "What" and "Why".
- **Orchestration**: Agent logic (n8n/LLM) - Coordinate tasks.
- **Execution**: Deterministic Python scripts - Performs the "How".
  - **Note**: Email content generation currently uses **static Python templates** (f-strings), not LLM generation, to ensure strict control and consistency.

## 2. Directives

### A. Prospecting (`directives/prospecting_sop.md`)
- **Goal**: Find plumbers in a target city using Google Maps (SerpApi).
- **Criteria**:
  - Rating: 3.5 - 4.5 stars.
  - Reviews: 30+ reviews.
  - Keywords: "didn't answer", "voicemail" (used for intent, though API limits may restrict deep review searching).
- **Execution**: `find_prospects_serpapi.py` -> outputs to `directives/prospects.md`.

### B. Daily Outreach (`directives/daily_outreach.md`)
- **Goal**: Manage the daily lifecycle of leads (Reply checks and Follow-ups).
- **Trigger**: Schedule (e.g., Daily at 9 AM).
- **Sequence**:
    1.  **Check Replies**: Scan inbox for responses to stop automation.
    2.  **Manage Follow-ups**: Check 'Sent' leads for inactivity.

### C. Follow-up Logic (`directives/followup_sop.md`)
- **Rule**: 3-day inactivity gap between steps.
- **Logic**:
    -   If Status='Sent' AND Step < 3 AND 3 days inactive -> **Draft Step+1** (Status: 'Draft Created').
    -   If Status='Sent' AND Step == 3 AND 3 days inactive -> **Revoke** (Status: 'Revoked').

## 3. Execution Scripts

### A. Scraper (`execution/find_prospects_serpapi.py`)
-   **Input**: City name, Limit.
-   **Action**: Fetches leads from Google Maps via SerpApi. Applies rating filters.
-   **Output**: Appends candidates to `directives/prospects.md`.

### B. Processor (`execution/clean_and_draft.py`)
-   **Input**: `directives/prospects.md`.
-   **Action**:
    -   Parses prospect data.
    -   Uses Selenium (Headless Chrome) to scrape email addresses from websites if missing.
    -   Generates **Initial Outreach** email using a static template.
    -   Creates Gmail Draft.
    -   Updates Google Sheet (Status: 'Draft Created', Step: 1).

### C. Reply Checker (`execution/check_replies.py`)
-   **Action**: Checks Gmail threads for incoming replies from leads marked as 'Sent' in Google Sheet.
-   **Updates**:
    -   If reply found: Status -> 'Replied', Step -> 'Stop'.
    -   If no reply: No change.

### D. Follow-up Manager (`execution/manage_followups.py`)
-   **Action**: Scans Google Sheet for independent follow-up logic.
-   **Logic**:
    -   Checks `Last_Date` and `Step`.
    -   If eligible: **Drafts** the next email (Step 2 or 3) using static templates.
    -   Updates Sheet: Status -> 'Draft Created', Step -> Increment, Last_Date -> Today.
    -   Handles 'Revoked' status for expired leads.

## 4. Automation (`plumber_secretary_v2.json`)
-   **Platform**: n8n.
-   **Trigger**: Webhook or Schedule.
-   **Flow**:
    1.  Execute `check_replies.py` to clear the board.
    2.  Execute `manage_followups.py` to advance remaining leads.
    3.  (Manual/Separate) User runs `find_prospects_serpapi.py` and `clean_and_draft.py` to fill the funnel.

## 5. Dependencies
```text
google-auth>=2.23.0
google-auth-oauthlib>=1.1.0
google-api-python-client>=2.100.0
selenium>=4.15.0
google-search-results>=2.4.2
python-dotenv>=1.0.0
```
