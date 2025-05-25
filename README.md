
# 📬 Gmail API Flask Mailer

A Flask-based SMTP-like server that uses the **Gmail API** to send emails (including attachments) via OAuth2 authentication — without using a traditional SMTP server or external database.

---

## ✨ Features

- ✅ OAuth2 flow using Google APIs (secure authorization)
- 📎 Send emails with optional file attachments
- 📨 Compose and dispatch fully-formatted Gmail messages
- 💬 User-friendly web interface + programmatic endpoints
- 🔐 No external database needed (session-based handling)
- 🛠️ Configurable for local development or production

---

## 🧰 Tech Stack

- **Flask** – Python web framework
- **Google API Client** – Gmail API and OAuth
- **HTML + Bootstrap** – Simple web interface
- **Werkzeug** – Flask debugging and sessions

---

## 📁 Project Structure

```

SMTP-Server/
│
├── app.py                # Main Flask app
├── credentials.json      # Google OAuth credentials
├── templates/
│   └── index.html        # Frontend page for sending emails
├── static/               # (optional) CSS or images
├── venv/                 # Python virtual environment
├── requirements.txt      # Dependencies
└── README.md             # Project documentation

````

---

## 🔧 Setup Instructions

### 1. 🔑 Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project or select an existing one.
3. Enable the **Gmail API**.
4. Go to **OAuth consent screen**:
   - Add necessary scopes: `../auth/gmail.send`
   - Add test users (your Gmail address)
5. Go to **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**:
   - Application type: *Web Application*
   - Authorized redirect URI: `http://localhost:5000/oauth2callback`
6. Download `credentials.json` and place it in your project root.

---

### 2. 🐍 Python Environment Setup

```bash
git clone https://github.com/your-username/SMTP-Server.git
cd SMTP-Server
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
````

---

## 🚀 Running the App

### 🔄 Set up Local Environment Variable

```bash
export OAUTHLIB_INSECURE_TRANSPORT=1  # For Linux/macOS
# On Windows:
# set OAUTHLIB_INSECURE_TRANSPORT=1
```

### ▶️ Run the Flask Server

```bash
python app.py
```

Visit: `http://localhost:5000`

---

## 🔐 OAuth Flow (How It Works)

1. You click "Send Email"
2. Google login window opens
3. You authenticate, grant access
4. Google redirects to `/oauth2callback`
5. Access token is saved in session
6. App sends email via Gmail API using that token

---

## 🧪 API Endpoints

| Method | Endpoint          | Description                            |
| ------ | ----------------- | -------------------------------------- |
| GET    | `/`               | Home page with email form              |
| GET    | `/authorize`      | Starts the OAuth2 flow                 |
| GET    | `/oauth2callback` | Callback from Google, fetches token    |
| POST   | `/send_email`     | Sends the composed email via Gmail API |

### 📤 `/send_email` Parameters (form-data or HTML form):

* `to` (string): Recipient email
* `subject` (string): Email subject
* `message` (string): Email body (plain text)
* `file` (optional): File attachment (e.g., PDF, PNG, etc.)

---

## 📦 Requirements

Install dependencies via:

```bash
pip install -r requirements.txt
```

Sample `requirements.txt`:

```
Flask
google-auth
google-auth-oauthlib
google-api-python-client
requests
```

---

## ⚠️ Troubleshooting

### ❗ OAuth 2 MUST utilize HTTPS

If you see:

```
oauthlib.oauth2.rfc6749.errors.InsecureTransportError: OAuth 2 MUST utilize https.
```

✅ Set this in your environment (for local dev):

```bash
export OAUTHLIB_INSECURE_TRANSPORT=1
```

---

## ☁️ Deployment Notes

For production deployment:

* Use HTTPS (e.g., reverse proxy with Nginx or deploy to Render/Fly.io)
* Set up SSL certificates via Let's Encrypt
* Use environment secrets instead of hardcoding credentials
* Ensure authorized redirect URIs in Google match production domain

---

## 📄 License

MIT License. Use responsibly.


