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
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")
app.config["SESSION_PERMANENT"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

# Constants
USER_FILE = "users.json"
SCOPES = ['https://www.googleapis.com/auth/gmail.send']
MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024  # 25MB limit

# User management functions
def load_users():
    if os.path.exists(USER_FILE):
        try:
            with open(USER_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error("Corrupted users file")
            return {}
    return {}

def save_users(users):
    try:
        with open(USER_FILE, 'w') as f:
            json.dump(users, f)
        return True
    except Exception as e:
        logger.error(f"Failed to save users: {e}")
        return False

# Validation functions
def is_valid_email(email):
    return re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email) is not None

def validate_email_data(to, subject, body):
    errors = []
    if not to:
        errors.append("Recipient email is required")
    elif not is_valid_email(to):
        errors.append("Invalid recipient email format")
    
    if not subject:
        errors.append("Subject is required")
    elif len(subject) > 100:
        errors.append("Subject too long (max 100 characters)")
    
    if not body:
        errors.append("Email body is required")
    
    return errors

# Gmail service functions
def get_gmail_service():
    if 'token' not in session:
        return None
    try:
        creds = Credentials.from_authorized_user_info(session['token'], SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                session['token'] = json.loads(creds.to_json())
            else:
                logger.warning("Credentials expired and no refresh token")
                return None
        return build('gmail', 'v1', credentials=creds)
    except Exception as e:
        logger.error(f"Failed to create Gmail service: {e}")
        return None

def create_email(sender, to, reply_to, subject, body, files):
    try:
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = to
        if reply_to and is_valid_email(reply_to):
            msg['Reply-To'] = reply_to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        total_size = 0
        for file in files:
            if file and file.filename:
                file_content = file.read()
                total_size += len(file_content)
                
                if total_size > MAX_ATTACHMENT_SIZE:
                    raise ValueError(f"Total attachment size exceeds the limit of {MAX_ATTACHMENT_SIZE/1024/1024}MB")
                
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(file_content)
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{file.filename}"')
                msg.attach(part)
                file.close()
        
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        return {'raw': raw}
    except Exception as e:
        logger.error(f"Error creating email: {e}")
        raise

# Routes
@app.route('/')
def home():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    theme = session.get('theme', 'light')
    return render_template('index.html', user_email=session['user_email'], theme=theme)

@app.route('/send', methods=['POST'])
def send():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    to = request.form['to'].strip()
    subject = request.form['subject'].strip()
    body = request.form['body'].strip()
    reply_to = request.form.get('reply_to', '').strip()
    files = request.files.getlist('attachments')
    
    # Validate input
    errors = validate_email_data(to, subject, body)
    if reply_to and not is_valid_email(reply_to):
        errors.append("Invalid reply-to email format")
    
    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for('home'))
    
    # Check Gmail service
    service = get_gmail_service()
    if not service:
        flash("Gmail authorization required. Please authorize again.", "error")
        return redirect(url_for('authorize'))
    
    # Send email
    try:
        email_msg = create_email(session['user_email'], to, reply_to, subject, body, files)
        service.users().messages().send(userId='me', body=email_msg).execute()
        flash("Email sent successfully!", "success")
        logger.info(f"Email sent from {session['user_email']} to {to}")
    except ValueError as ve:
        flash(str(ve), "error")
        logger.warning(f"Email validation error: {ve}")
    except Exception as e:
        error_msg = f"Failed to send email: {str(e)}"
        flash(error_msg, "error")
        logger.error(error_msg)
    
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email'].strip()
        
        if not is_valid_email(email):
            flash("Invalid email format.", "error")
            return render_template('register.html')
        
        users = load_users()
        if email in users:
            flash("Email already registered.", "error")
        else:
            users[email] = {"created_at": str(datetime.now())}
            if save_users(users):
                flash("Registration successful! Please log in.", "success")
                return redirect(url_for('login'))
            else:
                flash("Failed to register. Please try again.", "error")
    
    return render_template('register.html', theme=session.get('theme', 'light'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        
        if not is_valid_email(email):
            flash("Invalid email format.", "error")
            return render_template('login.html')
        
        users = load_users()
        if email in users:
            session['user_email'] = email
            session.permanent = True
            return redirect(url_for('authorize'))
        else:
            flash("User not found. Please register first.", "error")
    
    return render_template('login.html', theme=session.get('theme', 'light'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/authorize')
def authorize():
    if 'user_email' not in session:
        flash("Please log in first.", "error")
        return redirect(url_for('login'))
    
    try:
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
    except Exception as e:
        logger.error(f"Authorization error: {e}")
        flash("Failed to start Google authorization. Check client configuration.", "error")
        return redirect(url_for('login'))

@app.route('/oauth2callback')
def oauth2callback():
    if 'state' not in session:
        flash("Invalid authorization request.", "error")
        return redirect(url_for('login'))
    
    try:
        state = session['state']
        flow = Flow.from_client_secrets_file(
            'credentials.json', scopes=SCOPES, state=state
        )
        flow.redirect_uri = url_for('oauth2callback', _external=True)
        flow.fetch_token(authorization_response=request.url)
        credentials = flow.credentials
        session['token'] = json.loads(credentials.to_json())
        flash("Google authorization successful!", "success")
        return redirect(url_for('home'))
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        flash("Google authorization failed. Please try again.", "error")
        return redirect(url_for('login'))

@app.route('/set-theme', methods=['POST'])
def set_theme():
    data = request.json
    if 'theme' in data and data['theme'] in ['light', 'dark']:
        session['theme'] = data['theme']
        return jsonify({"status": "success"})
    return jsonify({"status": "error"})

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html', theme=session.get('theme', 'light')), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return render_template('500.html', theme=session.get('theme', 'light')), 500

# Missing import at the top
from datetime import datetime

if __name__ == "__main__":
    app.run(debug=True)