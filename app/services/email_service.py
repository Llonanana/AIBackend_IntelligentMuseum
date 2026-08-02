import base64
import os
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid

from dotenv import load_dotenv


class EmailService:
    # Gmail rejects plain account passwords for SMTP login — GMAIL_APP_PASSWORD
    # has to be a 16-character "App Password" generated in the Google Account's
    # security settings (requires 2-Step Verification to be turned on first),
    # not the normal login password.
    def __init__(self):
        load_dotenv()
        self.gmail_address = os.getenv("GMAIL_ADDRESS")
        self.gmail_app_password = os.getenv("GMAIL_APP_PASSWORD")

    def send_group_photo(self, to_email: str, photo_base64: str, file_name: str):
        if not self.gmail_address or not self.gmail_app_password:
            raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set in .env")

        photo_bytes = base64.b64decode(photo_base64)

        # Bare-bones messages (no Date/Message-ID, no display name, one-line body +
        # a lone attachment) are exactly the shape spam filters key off of for
        # script-sent mail — this is why the first test emails landed in Gmail's
        # spam folder. None of this guarantees the inbox, but it's the standard
        # baseline for anything sent through smtplib instead of a real mail client.
        message = MIMEMultipart()
        message["Subject"] = "重塑天青古窯復原MR體驗 - 大合照"
        message["From"] = formataddr(("重塑天青古窯復原MR體驗", self.gmail_address))
        message["To"] = to_email
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = make_msgid()
        message.attach(MIMEText(
            "謝謝您參與「重塑天青古窯復原MR體驗」！\n\n"
            "附件是您與乾隆帝、專屬蓮花碗的合照，歡迎下載留念。\n"
            "如果沒有在收件匣看到這封信，麻煩檢查一下垃圾郵件資料夾。",
            "plain",
        ))

        image = MIMEImage(photo_bytes, name=file_name)
        image.add_header("Content-Disposition", "attachment", filename=file_name)
        message.attach(image)

        # SMTP_SSL (port 465), not starttls — one less round trip, and Gmail supports
        # both; no reason to prefer starttls here since nothing else in this codebase
        # depends on that connection style.
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(self.gmail_address, self.gmail_app_password)
            server.sendmail(self.gmail_address, to_email, message.as_string())


email_service = EmailService()
