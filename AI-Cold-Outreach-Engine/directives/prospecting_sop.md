# Directive: Prospect for Plumbers

**Goal**: Identify potential plumbing leads in a specific city who are likely to be unresponsive (based on reviews) and thus good candidates for our AI receptionist service.

## Inputs
- **City**: The target city and state (e.g., "Las Vegas, NV").
- **Limit**: Number of leads to find (default: 10).

## Search Criteria
1.  **Query**: "Plumbers near [City]"
2.  **Platform**: Google Maps (via SerpApi)
3.  **Rating**: 3.5 to 4.5 stars (inclusive).
4.  **Minimum Reviews**: 30+
5.  **Keywords**:
    - "didn't answer"
    - "did not answer"
    - "voicemail"
    - "no call back"
    - "took too long"
    - "waited all day"

## Execution Process
1.  Run `python3 execution/find_prospects_serpapi.py --city "[City]" --limit [Limit]`
2.  The script will:
    -   Fetch results from SerpApi.
    -   Filter candidates based on rating and review count.
    -   Scan reviews for keywords.
    -   Extract: Business Name, Website, Owner (if found), and the specific "frustrated" review snippet.
3.  **Output**: Results will be appended to `directives/prospects.md`.

## Output Format
Each entry in `directives/prospects.md` should look like:
```markdown
## [Business Name]
- **Rating**: [Rating] ([Review Count] reviews)
- **Website**: [URL]
- **Snippet**: "[Review text containing keyword]"
- **Owner**: [Name or 'Not found']
```

## Edges Cases
-   **No leads found**: Try broadening the city range or reducing the minimum review count.
-   **API Limit**: If SerpApi credits are low, the script will exit early.
