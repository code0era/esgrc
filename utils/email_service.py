import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import streamlit as st

def send_otp_email(recipient_email: str, otp_code: str, context: str = "signup") -> bool:
    """
    Sends a 6-digit OTP to the user's email via Gmail SMTP.
    Returns True if successful, False otherwise.
    """
    try:
        smtp_config = st.secrets.get("smtp", {})
        sender_email = smtp_config.get("email_sender")
        sender_password = smtp_config.get("email_password")
        
        if not sender_email or not sender_password:
            print("SMTP credentials missing in secrets.toml")
            return False
            
        msg = MIMEMultipart()
        msg['From'] = f"METEOERAIT SOFTWARE <{sender_email}>"
        msg['To'] = recipient_email
        
        if context == "signup":
            msg['Subject'] = "Your Registration Verification Code"
            html = f"""
            <html>
                <body>
                    <h2>METEOERAIT SOFTWARE Registration</h2>
                    <p>Thank you for signing up! Your verification code is:</p>
                    <h1 style="color: #0369A1; letter-spacing: 5px;">{otp_code}</h1>
                    <p>This code will expire in 10 minutes.</p>
                </body>
            </html>
            """
        else:
            msg['Subject'] = "Password Reset Verification Code"
            html = f"""
            <html>
                <body>
                    <h2>Password Reset Request</h2>
                    <p>We received a request to reset your password. Your verification code is:</p>
                    <h1 style="color: #0369A1; letter-spacing: 5px;">{otp_code}</h1>
                    <p>This code will expire in 10 minutes. If you did not request this, please ignore this email.</p>
                </body>
            </html>
            """
            
        msg.attach(MIMEText(html, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False
