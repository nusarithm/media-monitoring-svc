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
    
    async def send_checkout_email(
        self, 
        to_email: str, 
        name: str, 
        plan_name: str,
        amount: int,
        billing_period: str
    ) -> bool:
        """Send checkout confirmation email"""
        
        subject = f"Checkout Confirmation - {settings.APP_NAME}"
        
        # Format amount with thousand separator
        formatted_amount = f"Rp {amount:,}".replace(",", ".")
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    margin: 0;
                    padding: 0;
                    background-color: #f4f4f4;
                }}
                .container {{
                    max-width: 600px;
                    margin: 20px auto;
                    background-color: white;
                    border-radius: 10px;
                    overflow: hidden;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #84cc16 0%, #65a30d 100%);
                    color: white;
                    padding: 40px 20px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                    font-weight: bold;
                }}
                .content {{
                    padding: 40px 30px;
                }}
                .greeting {{
                    font-size: 18px;
                    color: #1f2937;
                    margin-bottom: 20px;
                }}
                .plan-box {{
                    background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
                    border-left: 4px solid #84cc16;
                    padding: 20px;
                    margin: 25px 0;
                    border-radius: 8px;
                }}
                .plan-name {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #15803d;
                    margin-bottom: 10px;
                }}
                .plan-details {{
                    display: flex;
                    justify-content: space-between;
                    margin-top: 15px;
                    padding-top: 15px;
                    border-top: 2px solid #84cc16;
                }}
                .detail-item {{
                    text-align: center;
                }}
                .detail-label {{
                    font-size: 12px;
                    color: #6b7280;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }}
                .detail-value {{
                    font-size: 18px;
                    font-weight: bold;
                    color: #15803d;
                    margin-top: 5px;
                }}
                .info-section {{
                    background-color: #f9fafb;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 25px 0;
                }}
                .info-title {{
                    font-weight: bold;
                    color: #1f2937;
                    margin-bottom: 10px;
                }}
                .steps {{
                    list-style: none;
                    padding: 0;
                    margin: 15px 0;
                }}
                .steps li {{
                    padding: 10px 0 10px 30px;
                    position: relative;
                    color: #4b5563;
                }}
                .steps li:before {{
                    content: "✓";
                    position: absolute;
                    left: 0;
                    color: #84cc16;
                    font-weight: bold;
                    font-size: 18px;
                }}
                .button {{
                    display: inline-block;
                    padding: 14px 32px;
                    background: linear-gradient(135deg, #84cc16 0%, #65a30d 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: bold;
                    margin: 20px 0;
                    text-align: center;
                }}
                .footer {{
                    background-color: #1f2937;
                    color: #9ca3af;
                    padding: 30px;
                    text-align: center;
                    font-size: 14px;
                }}
                .footer-link {{
                    color: #84cc16;
                    text-decoration: none;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 Checkout Berhasil!</h1>
                    <p style="margin: 10px 0 0; opacity: 0.95;">Terima kasih atas pembelian Anda</p>
                </div>
                
                <div class="content">
                    <p class="greeting">Halo <strong>{name}</strong>,</p>
                    
                    <p>Terima kasih telah memilih <strong>{settings.APP_NAME}</strong>! Anda telah berhasil memulai proses checkout untuk:</p>
                    
                    <div class="plan-box">
                        <div class="plan-name">{plan_name}</div>
                        <div class="plan-details">
                            <div class="detail-item">
                                <div class="detail-label">Billing Period</div>
                                <div class="detail-value">{billing_period.capitalize()}</div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Total Amount</div>
                                <div class="detail-value">{formatted_amount}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="info-section">
                        <div class="info-title">📋 Langkah Selanjutnya:</div>
                        <ul class="steps">
                            <li>Scan QR code yang ditampilkan di halaman checkout</li>
                            <li>Lakukan pembayaran melalui aplikasi e-wallet Anda</li>
                            <li>Tunggu konfirmasi pembayaran (biasanya instan)</li>
                            <li>Akses fitur premium segera setelah pembayaran berhasil</li>
                        </ul>
                    </div>
                    
                    <p style="color: #6b7280; font-size: 14px; margin-top: 25px;">
                        Jika Anda mengalami kesulitan atau memiliki pertanyaan, jangan ragu untuk menghubungi tim support kami.
                    </p>
                </div>
                
                <div class="footer">
                    <p style="margin: 0 0 10px;">Email ini dikirim secara otomatis, mohon jangan membalas.</p>
                    <p style="margin: 0;">&copy; 2026 {settings.APP_NAME}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_content = f"""
        Halo {name},
        
        Terima kasih telah memilih {settings.APP_NAME}!
        
        Anda telah berhasil memulai proses checkout untuk:
        Plan: {plan_name}
        Billing Period: {billing_period}
        Total Amount: {formatted_amount}
        
        Langkah Selanjutnya:
        1. Scan QR code yang ditampilkan di halaman checkout
        2. Lakukan pembayaran melalui aplikasi e-wallet Anda
        3. Tunggu konfirmasi pembayaran (biasanya instan)
        4. Akses fitur premium segera setelah pembayaran berhasil
        
        Jika Anda mengalami kesulitan, silakan hubungi tim support kami.
        
        {settings.APP_NAME}
        """
        
        return await self.send_email(to_email, subject, html_content, plain_content)
    
    async def send_payment_success_email(
        self, 
        to_email: str, 
        name: str, 
        plan_name: str,
        amount: int,
        billing_period: str,
        expires_at: str
    ) -> bool:
        """Send payment success email"""
        
        subject = f"Pembayaran Berhasil - {settings.APP_NAME}"
        
        # Format amount with thousand separator
        formatted_amount = f"Rp {amount:,}".replace(",", ".")
        
        # Format expiration date
        from datetime import datetime
        try:
            exp_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            formatted_exp = exp_date.strftime("%d %B %Y")
        except:
            formatted_exp = expires_at
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    margin: 0;
                    padding: 0;
                    background-color: #f4f4f4;
                }}
                .container {{
                    max-width: 600px;
                    margin: 20px auto;
                    background-color: white;
                    border-radius: 10px;
                    overflow: hidden;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
                    color: white;
                    padding: 40px 20px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 32px;
                    font-weight: bold;
                }}
                .success-icon {{
                    font-size: 60px;
                    margin-bottom: 10px;
                }}
                .content {{
                    padding: 40px 30px;
                }}
                .greeting {{
                    font-size: 18px;
                    color: #1f2937;
                    margin-bottom: 20px;
                }}
                .success-box {{
                    background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%);
                    border: 2px solid #10b981;
                    padding: 25px;
                    margin: 25px 0;
                    border-radius: 10px;
                    text-align: center;
                }}
                .success-message {{
                    font-size: 20px;
                    font-weight: bold;
                    color: #065f46;
                    margin-bottom: 15px;
                }}
                .transaction-details {{
                    background-color: #f9fafb;
                    border-radius: 8px;
                    padding: 20px;
                    margin: 25px 0;
                }}
                .detail-row {{
                    display: flex;
                    justify-content: space-between;
                    padding: 12px 0;
                    border-bottom: 1px solid #e5e7eb;
                }}
                .detail-row:last-child {{
                    border-bottom: none;
                }}
                .detail-label {{
                    color: #6b7280;
                    font-weight: 500;
                }}
                .detail-value {{
                    color: #1f2937;
                    font-weight: bold;
                }}
                .features-box {{
                    background-color: #f0fdf4;
                    border-left: 4px solid #84cc16;
                    padding: 20px;
                    margin: 25px 0;
                    border-radius: 8px;
                }}
                .features-title {{
                    font-weight: bold;
                    color: #15803d;
                    margin-bottom: 15px;
                    font-size: 16px;
                }}
                .features-list {{
                    list-style: none;
                    padding: 0;
                    margin: 0;
                }}
                .features-list li {{
                    padding: 8px 0 8px 30px;
                    position: relative;
                    color: #374151;
                }}
                .features-list li:before {{
                    content: "✨";
                    position: absolute;
                    left: 0;
                    font-size: 16px;
                }}
                .button {{
                    display: inline-block;
                    padding: 14px 32px;
                    background: linear-gradient(135deg, #84cc16 0%, #65a30d 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 8px;
                    font-weight: bold;
                    margin: 20px 0;
                    text-align: center;
                }}
                .footer {{
                    background-color: #1f2937;
                    color: #9ca3af;
                    padding: 30px;
                    text-align: center;
                    font-size: 14px;
                }}
                .footer-link {{
                    color: #84cc16;
                    text-decoration: none;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="success-icon">✅</div>
                    <h1>Pembayaran Berhasil!</h1>
                    <p style="margin: 10px 0 0; opacity: 0.95;">Langganan Anda telah aktif</p>
                </div>
                
                <div class="content">
                    <p class="greeting">Selamat, <strong>{name}</strong>!</p>
                    
                    <div class="success-box">
                        <div class="success-message">🎊 Pembayaran Anda Telah Dikonfirmasi</div>
                        <p style="margin: 0; color: #047857;">Anda sekarang dapat menikmati semua fitur premium!</p>
                    </div>
                    
                    <div class="transaction-details">
                        <div class="detail-row">
                            <span class="detail-label">Paket Langganan</span>
                            <span class="detail-value">{plan_name}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Periode Billing</span>
                            <span class="detail-value">{billing_period.capitalize()}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Jumlah Dibayar</span>
                            <span class="detail-value">{formatted_amount}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Berlaku Sampai</span>
                            <span class="detail-value">{formatted_exp}</span>
                        </div>
                    </div>
                    
                    <div class="features-box">
                        <div class="features-title">🚀 Apa yang Bisa Anda Lakukan Sekarang:</div>
                        <ul class="features-list">
                            <li>Akses penuh ke semua fitur premium</li>
                            <li>Monitoring media tanpa batas</li>
                            <li>Dashboard analytics yang lengkap</li>
                            <li>Export laporan dalam berbagai format</li>
                            <li>Priority customer support</li>
                        </ul>
                    </div>
                    
                    <p style="margin-top: 30px; color: #374151;">
                        Terima kasih telah mempercayai <strong>{settings.APP_NAME}</strong> untuk kebutuhan media monitoring Anda. 
                        Kami berkomitmen untuk memberikan layanan terbaik!
                    </p>
                    
                    <p style="color: #6b7280; font-size: 14px; margin-top: 20px;">
                        Ada pertanyaan? Tim support kami siap membantu Anda 24/7.
                    </p>
                </div>
                
                <div class="footer">
                    <p style="margin: 0 0 10px;">Email ini dikirim secara otomatis, mohon jangan membalas.</p>
                    <p style="margin: 0;">&copy; 2026 {settings.APP_NAME}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_content = f"""
        Selamat, {name}!
        
        Pembayaran Anda telah dikonfirmasi dan langganan Anda sekarang aktif!
        
        Detail Transaksi:
        Paket: {plan_name}
        Billing Period: {billing_period}
        Jumlah Dibayar: {formatted_amount}
        Berlaku Sampai: {formatted_exp}
        
        Anda sekarang dapat menikmati semua fitur premium:
        - Akses penuh ke semua fitur premium
        - Monitoring media tanpa batas
        - Dashboard analytics yang lengkap
        - Export laporan dalam berbagai format
        - Priority customer support
        
        Terima kasih telah mempercayai {settings.APP_NAME}!
        
        Ada pertanyaan? Hubungi kami kapan saja.
        
        {settings.APP_NAME}
        """
        
        return await self.send_email(to_email, subject, html_content, plain_content)


email_service = EmailService()
