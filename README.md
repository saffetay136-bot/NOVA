# NOVA Chat

NOVA is a small Flask chat app with Google Sign-In, persistent SQLite chat history, an optional OpenAI-compatible chat API, and a separate host dashboard.

## Requirements

- Python 3.10+
- A Google OAuth 2.0 Client ID (Web application)
- An OpenAI-compatible API endpoint and key for live AI responses

## Run locally (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:GOOGLE_CLIENT_ID = "your-client-id.apps.googleusercontent.com"
$env:AI_API_URL = "https://api.openai.com/v1/chat/completions"
$env:AI_API_KEY = "your-api-key"
$env:AI_MODEL = "gpt-4o-mini"
$env:HOST_NAME = "s"
$env:HOST_PASSWORD = "use-a-long-random-password"
$env:FLASK_SECRET = "use-a-long-random-secret"
python app.py
```

Open `http://localhost:5000`. In Google Cloud Console, add that exact origin to the OAuth client's authorized JavaScript origins. For local testing, `http://127.0.0.1:5000` is a different origin and must be added separately if used.

Without AI API settings, the app stores messages but responds in demo mode. Without a host password, host sign-in is disabled.

## Host dashboard

- Sign-in: `http://localhost:5000/host-login`
- Dashboard: `http://localhost:5000/host`

The host name defaults to `s`; configure the password and Flask session secret through environment variables. Do not commit credentials, API keys, `.env` files, or the SQLite database. Use HTTPS and set `COOKIE_SECURE=true` when deployed.

## Location and network records

Location is saved only after the signed-in user explicitly grants browser location permission. The host dashboard can view location entries and request IP records. Tell users what is collected and why before deployment, and apply an appropriate retention policy.

## Deployment

Use a production WSGI server behind HTTPS rather than Flask's development server. Set all secrets in the hosting provider's secret/environment settings, and configure the public HTTPS origin with Google OAuth.
