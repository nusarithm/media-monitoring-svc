import ssl
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List
from app.core.config import settings


class EmailService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        plain_content: str = None
    ) -> bool:
        """Send email using aiosmtplib (async). Returns True on success."""
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to_email

            # Add plain text and HTML parts
            if plain_content:
                part1 = MIMEText(plain_content, "plain")
                message.attach(part1)

            part2 = MIMEText(html_content, "html")
            message.attach(part2)

            # TLS / SSL context
            tls_context = ssl.create_default_context()
            if not settings.SMTP_VERIFY_SSL:
                tls_context.check_hostname = False
                tls_context.verify_mode = ssl.CERT_NONE

            # Use SSL for port 465, else use STARTTLS
            use_tls = True if self.smtp_port == 465 else False

            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_username,
                password=self.smtp_password,
                use_tls=use_tls,
                tls_context=tls_context,
                sender=self.from_email,
                recipients=[to_email],
            )

            return True
        except Exception as e:
            # Log full error for debugging
            print(f"Error sending email via SMTP: {e}")
            return False
    
    async def send_otp_email(self, to_email: str, otp_code: str, name: str = None) -> bool:
        """Send OTP verification email"""
        recipient_name = name or to_email.split("@")[0]
        
        subject = f"Kode OTP Anda - {settings.APP_NAME}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #4F46E5;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 5px 5px 0 0;
                }}
                .content {{
                    background-color: #f9fafb;
                    padding: 30px;
                    border-radius: 0 0 5px 5px;
                }}
                .otp-code {{
                    font-size: 32px;
                    font-weight: bold;
                    color: #4F46E5;
                    text-align: center;
                    padding: 20px;
                    background-color: white;
                    border-radius: 5px;
                    letter-spacing: 8px;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 20px;
                    color: #666;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{settings.APP_NAME}</h1>
                </div>
                <div class="content">
                    <h2>Halo {recipient_name},</h2>
                    <p>Anda telah meminta kode OTP untuk verifikasi akun Anda.</p>
                    <p>Gunakan kode OTP berikut untuk melanjutkan:</p>
                    <div class="otp-code">{otp_code}</div>
                    <p><strong>Kode ini akan kedaluwarsa dalam {settings.OTP_EXPIRE_MINUTES} menit.</strong></p>
                    <p>Jika Anda tidak meminta kode ini, abaikan email ini.</p>
                    <div class="footer">
                        <p>Email ini dikirim secara otomatis, mohon jangan membalas.</p>
                        <p>&copy; 2026 {settings.APP_NAME}. All rights reserved.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_content = f"""
        Halo {recipient_name},
        
        Kode OTP Anda adalah: {otp_code}
        
        Kode ini akan kedaluwarsa dalam {settings.OTP_EXPIRE_MINUTES} menit.
        
        Jika Anda tidak meminta kode ini, abaikan email ini.
        
        {settings.APP_NAME}
        """
        
        return await self.send_email(to_email, subject, html_content, plain_content)
    
    async def send_password_reset_email(self, to_email: str, otp_code: str, name: str = None) -> bool:
        """Send password reset email"""
        recipient_name = name or to_email.split("@")[0]
        
        subject = f"Reset Password - {settings.APP_NAME}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #EF4444;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 5px 5px 0 0;
                }}
                .content {{
                    background-color: #f9fafb;
                    padding: 30px;
                    border-radius: 0 0 5px 5px;
                }}
                .otp-code {{
                    font-size: 32px;
                    font-weight: bold;
                    color: #EF4444;
                    text-align: center;
                    padding: 20px;
                    background-color: white;
                    border-radius: 5px;
                    letter-spacing: 8px;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 20px;
                    color: #666;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Reset Password</h1>
                </div>
                <div class="content">
                    <h2>Halo {recipient_name},</h2>
                    <p>Kami menerima permintaan untuk mereset password akun Anda.</p>
                    <p>Gunakan kode OTP berikut untuk mereset password:</p>
                    <div class="otp-code">{otp_code}</div>
                    <p><strong>Kode ini akan kedaluwarsa dalam {settings.OTP_EXPIRE_MINUTES} menit.</strong></p>
                    <p>Jika Anda tidak meminta reset password, abaikan email ini dan pastikan akun Anda aman.</p>
                    <div class="footer">
                        <p>Email ini dikirim secara otomatis, mohon jangan membalas.</p>
                        <p>&copy; 2026 {settings.APP_NAME}. All rights reserved.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_content = f"""
        Halo {recipient_name},
        
        Kode OTP untuk reset password Anda adalah: {otp_code}
        
        Kode ini akan kedaluwarsa dalam {settings.OTP_EXPIRE_MINUTES} menit.
        
        Jika Anda tidak meminta reset password, abaikan email ini.
        
        {settings.APP_NAME}
        """
        
        return await self.send_email(to_email, subject, html_content, plain_content)


email_service = EmailService()
