import os
import json
import base64
import logging
import re
from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify
from datetime import timedelta
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pymongo import MongoClient
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

# Write credentials.json from environment variable if it doesn't exist
if not os.path.exists('credentials.json'):
    creds_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_str:
        with open("credentials.json", "w") as f:
            f.write(creds_str)

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# MongoDB setup
client = MongoClient(os.getenv('MONGO_URI'))
db = client["gmail_auth"]
tokens_col = db["tokens"]

USER_FILE = "users.json"

def load_users():
    if os.path.exists(USER_FILE):
        with open(USER_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USER_FILE, 'w') as f:
        json.dump(users, f)

def is_valid_email(email):
    return re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email)

def save_user_credentials(email, credentials):
    tokens_col.update_one(
        {"email": email},
        {"$set": {"credentials": json.loads(credentials.to_json())}},
        upsert=True
    )

def load_user_credentials(email):
    user = tokens_col.find_one({"email": email})
    if user and "credentials" in user:
        return Credentials.from_authorized_user_info(user["credentials"], SCOPES)
    return None

def get_gmail_service():
    if 'user_email' not in session:
        return None
    creds = load_user_credentials(session['user_email'])
    if not creds:
        return None
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_user_credentials(session['user_email'], creds)
        else:
            return None
    return build('gmail', 'v1', credentials=creds)

def create_email(sender, to, reply_to, subject, body, files):
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = to
    if reply_to:
        msg['Reply-To'] = reply_to
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    for file in files:
        if file and file.filename:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(file.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{file.filename}"')
            msg.attach(part)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {'raw': raw}

@app.route('/')
def home():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', user_email=session['user_email'])

@app.route('/send', methods=['POST'])
def send():
    if 'user_email' not in session:
        return redirect(url_for('login'))

    to = request.form['to'].strip()
    subject = request.form['subject'].strip()
    body = request.form['body'].strip()
    reply_to = request.form.get('reply_to', '').strip()
    files = request.files.getlist('attachments')

    if not is_valid_email(to):
        flash("Invalid recipient email.")
        return redirect(url_for('home'))

    service = get_gmail_service()
    if not service:
        flash("Gmail not authorized.")
        return redirect(url_for('authorize'))

    try:
        email_msg = create_email(session['user_email'], to, reply_to, subject, body, files)
        service.users().messages().send(userId='me', body=email_msg).execute()
        flash("Email sent successfully!", "success")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        flash("Failed to send email.")

    return redirect(url_for('home'))

@app.route('/backend_service', methods=['POST'])
def backend_service():
    if not request.is_json:
        logging.error("Request must contain JSON data")
        return jsonify({'error': 'Request must contain JSON data'}), 400

    if 'user_email' not in session:
        logging.error("User not authenticated")
        return jsonify({'error': 'User not authenticated'}), 401

    data = request.get_json()
    if not isinstance(data, list):
        logging.error("Expected a list of email items")
        return jsonify({'error': 'Expected a list of email items'}), 400

    service = get_gmail_service()
    if not service:
        logging.error("Gmail service not authorized")
        return jsonify({'error': 'Gmail service not authorized'}), 401

    for item in data:
        to = item.get('recipient', '').strip()
        subject = item.get('subject', '').strip()
        body = item.get('body', '').strip()
        sender = item.get('sender_email', session['user_email']).strip()
        reply_to = item.get('reply_to', '').strip()

        if not is_valid_email(to):
            logging.error(f"Invalid recipient email: {to}")
            return jsonify({'error': f'Invalid recipient email: {to}'}), 400

        if not is_valid_email(sender):
            logging.error(f"Invalid sender email: {sender}")
            return jsonify({'error': f'Invalid sender email: {sender}'}), 400

        try:
            email_msg = create_email(sender, to, reply_to, subject, body, files=[])
            service.users().messages().send(userId='me', body=email_msg).execute()
            logging.info(f"Email sent to {to} with subject '{subject}'")
        except Exception as e:
            logging.error(f"Failed to send email to {to}: {str(e)}")
            return jsonify({'error': f'Failed to send email to {to}: {str(e)}'}), 500

    return jsonify({'message': 'Emails sent successfully'}), 200

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].strip()
        if not is_valid_email(email):
            flash("Invalid email.")
            return redirect(url_for('register'))

        users = load_users()
        if email in users:
            flash("Email already registered.")
        else:
            users[email] = {}
            save_users(users)
            flash("Registered! Now log in.")
            return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        users = load_users()
        if email in users:
            session['user_email'] = email
            return redirect(url_for('authorize'))
        else:
            flash("User not found. Register first.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/authorize')
def authorize():
    redirect_uri = url_for('oauth2callback', _external=True)
    client_config = {
        "web": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }
    flow = Flow.from_client_config(client_config, SCOPES)
    flow.redirect_uri = redirect_uri
    authorization_url, state = flow.authorization_url(
        access_type='offline', include_granted_scopes='true', prompt='consent'
    )
    session['state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = session.get('state')
    flow = Flow.from_client_secrets_file(
        'credentials.json', scopes=SCOPES, state=state
    )
    flow.redirect_uri = url_for('oauth2callback', _external=True)

    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    session['token'] = json.loads(credentials.to_json())
    save_user_credentials(session['user_email'], credentials)
    return redirect(url_for('home'))

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    print(f"[INFO] Starting Flask app on port {port}")
    app.run(debug=False, host='0.0.0.0', port=port)