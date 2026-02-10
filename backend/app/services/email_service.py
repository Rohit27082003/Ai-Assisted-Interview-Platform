"""Email service using SMTP for sending notifications."""

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

class EmailService:
    def __init__(self):
        self.smtp_server = settings.SMTP_SERVER
        self.smtp_port = settings.SMTP_PORT
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.EMAILS_FROM_EMAIL

    async def send_email(self, to_email: str, subject: str, body: str):
        """Send an email using configured SMTP server."""
        message = MIMEMultipart()
        message["From"] = self.from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.attach(MIMEText(body, "html"))

        try:
            # Connect to SMTP server
            if self.username and self.password:
                await aiosmtplib.send(
                    message,
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    username=self.username,
                    password=self.password,
                    use_tls=False, # MailHog doesn't support TLS by default
                )
            else:
                 await aiosmtplib.send(
                    message,
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    use_tls=False,
                )
            logger.info(f"Email sent successfully to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            logger.error(f"Email Content: Subject: {subject}, Body: {body}") # Fallback logging
            return False

def get_email_service() -> EmailService:
    return EmailService()
