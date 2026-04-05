import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configure logger for this tool
logger = logging.getLogger(__name__)

def send_email(to_email: str, subject: str, body: str) -> dict:
    """
    Sends an email using the SMTP protocol.
    Reads credentials from the MS7 environment (.env file).
    """
    # Read from environment variables (populated from .env in MS7)
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    try:
        SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    except (ValueError, TypeError):
        SMTP_PORT = 587
        
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)

    if not all([SMTP_USER, SMTP_PASSWORD, FROM_EMAIL]):
        logger.warning("Email tool is called but SMTP credentials are not fully configured.")
        return {"error": "Email configuration is incomplete. Please set SMTP_USER, SMTP_PASSWORD, and FROM_EMAIL in the .env file."}

    # Cast for type safety
    smtp_user: str = str(SMTP_USER)
    smtp_password: str = str(SMTP_PASSWORD)
    from_email: str = str(FROM_EMAIL)

    try:
        # Create the message
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # Connect and send
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info(f"SUCCESS: Email sent to {to_email}")
        return {
            "status": "success",
            "message": f"Email successfully sent to {to_email}",
            "recipient": to_email
        }

    except smtplib.SMTPAuthenticationError:
        logger.error("Email API Error: Authentication failed. Check your SMTP credentials.")
        return {"error": "Authentication failed. Please verify your SMTP_USER and SMTP_PASSWORD."}
    except Exception as e:
        logger.error(f"Unexpected error in Email tool: {e}")
        return {"error": f"An unexpected error occurred: {str(e)}"}
