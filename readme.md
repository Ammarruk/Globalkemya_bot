## AI Bot

## Overview

This project is a web-based application built with Flask that automates supplier verification and trade data analysis on the Volza platform. It uses Selenium for browser automation to handle login, search, and data extraction, integrates an IMAP email client to automatically read and input OTPs for authentication, and leverages the Groq AI API for intelligent analysis of extracted trade data. The frontend is a responsive HTML interface for user interaction, including login, analysis initiation, progress tracking, and AI-powered querying.

The core workflow involves:
- User input for a product name.
- Automated navigation to Volza, login via OTP from email, and prompt for company name entry.
- Data capture from search results.
- AI-driven extraction and assessment of trade metrics (e.g., shipments, consignees, countries).
- Interactive chat for querying the analyzed data.

## Features

- **Automated Browser Login**: Uses undetected-chromedriver to launch Chrome with persistent profiles, handling Volza's login flow including OTP retrieval.
- **Email OTP Integration**: Connects to Gmail IMAP server to fetch the latest unseen OTP email from Volza and inputs it automatically.
- **Search Automation**: Configures global searches on Volza for companies trading the specified product, with custom date ranges (2019 onwards).
- **Data Extraction**: Captures full page text after zooming and scrolling for complete content retrieval.
- **AI Analysis**: Uses Groq's Llama model to extract key trade insights (consignees, countries, shipments) and assess supplier legitimacy.
- **Interactive Chat**: Post-analysis query interface powered by direct AI prompts on extracted data.
- **Session Management**: Maintains browser state for subsequent analyses without re-login.
- **History Tracking**: Stores past analyses in JSON for quick access.
- **Progress Monitoring**: Real-time status updates via WebSocket-like polling.
- **Secure Configuration**: Credentials loaded from .env, with validation for required keys.

## Prerequisites

- Python 3.8+
- Chrome browser installed (auto-detects version for chromedriver compatibility).
- Gmail account with App Password enabled for IMAP access.
- Volza account credentials.

## Installation

1. Clone or download the project files.
2. Install dependencies:
   ```
   pip install flask selenium undetected-chromedriver groq python-dotenv imaplib2 email
   ```
3. Place `index.html` in a `templates/` folder.
4. Place favicon.ico and logo.png in a `static/` folder.
5. Create a `.env` file in the root directory (see Configuration section).

## Configuration

Create `.env` with the following keys (replace with your values):

```
VALID_USERNAME=your_app_username
VALID_PASSWORD=your_app_password
LOGIN_EMAIL=your_volza_email
APP_PASSWORD=your_gmail_app_password
EMAIL=your_gmail_address
IMAP_SERVER=Your_IMAP_SERVER
IMAP_PORT=Your_IMAP_PORT
OTP_SENDER_EMAIL=.....@gmail.com
OTP_SUBJECT_KEYWORD=Your OTP for Secure Login
GROQ_API_KEY=your_groq_api_key
```

- `VALID_USERNAME` and `VALID_PASSWORD`: For app-level authentication.
- `LOGIN_EMAIL` and `APP_PASSWORD`: For Volza login and Gmail IMAP.
- `GROQ_API_KEY`: For AI analysis.

The app validates these on startup and raises errors if missing.

## Usage

1. Run the Flask app:
   ```
   python app.py
   ```
   The server starts on http://127.0.0.1:5000.

2. Access the web interface in a browser.

3. Login with credentials from `.env`.

4. In the dashboard:
   - Enter a product name (e.g., "chemicals") and click "Analyze".
   - The app launches a browser, logs into Volza using the integrated email OTP reader, and prompts you to enter the company name in the browser.
   - Click "Search" in the browser to proceed.
   - Monitor progress in the UI (includes status and progress bar).

5. Once complete:
   - View the AI-generated report (legitimacy assessment, key facts, red flags).
   - Use the chat interface or quick questions to query details (e.g., "Top consignees?").

6. For new analyses: Click "Start New Analysis" to reset.

7. Close browser session via sidebar if needed.

## How It Works

- **Initialization**: Flask app loads .env, initializes Groq client, and sets up global state for sessions.
- **Login Flow**:
  - Navigates to Volza search page.
  - Inputs email and requests OTP.
  - Uses IMAP to search inbox for latest OTP email (from sender, matching subject), extracts 6-digit code via regex, and inputs it.
  - Completes sign-in and selects company profile.
- **Search Setup**:
  - Configures global search, custom date (01/01/2019), and company field.
  - Pauses for manual company name entry and "Search" click.
- **Data Capture**:
  - Waits for results with smart checks (table presence, row count).
  - Zooms out, scrolls full page, extracts body text.
  - Auto-detects company name via multiple strategies (XPath, URL params, text regex).
- **AI Processing**:
  - Sends page text to Groq for focused extraction (consignees, countries, shipments, dates).
  - Follow-up prompt for legitimacy assessment (YES/NO on multi-country/multi-buyer, status: LEGITIMATE/SUSPICIOUS).
  - Saves raw and analyzed data to files and JSON history.
- **Query Handling**: Direct Groq prompts on extracted data for chat responses, limited to company-specific info.
- **Error Handling**: Retries on timeouts/stale elements, cache clearing for driver issues, voice alerts for manual steps.
- **Frontend**: Polls backend for status, renders Markdown reports via Showdown, handles chat history.

## Benefits

- Streamlines supplier due diligence by automating 80% of manual Volza workflows.
- Reduces login friction with automatic OTP handling, saving 2-5 minutes per session.
- Provides instant AI insights on trade patterns, cutting analysis time from hours to minutes.
- Enables risk assessment (e.g., single-buyer flags) to avoid unreliable partners.
- Maintains session persistence for batch analyses, improving efficiency for multiple products.
- Stores historical data for trend tracking and quick re-queries.
- Secure and local: No third-party data sharing beyond Volza/Groq APIs.

## Technologies

- **Backend**: Flask, Selenium (with undetected-chromedriver), Groq API, IMAPlib, python-dotenv.
- **Frontend**: HTML/CSS/JS, Showdown for Markdown rendering.
- **Data**: JSON for history, TXT for raw extracts.
- **Browser**: Chrome with options for speed (no images, persistent profile).

## Troubleshooting

- **Driver Errors**: Auto-clears cache and retries; ensure Chrome is updated.
- **OTP Failures**: Verify Gmail App Password and unseen email search.
- **AI Limits**: Check Groq quota; model is Moonshot Kimi for fast responses.
- **CORS Issues**: Enabled in app for potential API extensions.

## License

Internal use only. For questions, contact the developer.