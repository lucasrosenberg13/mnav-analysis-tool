import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import time  # ✅ for timezone abbreviation

# ✅ Mailjet SMTP settings
SMTP_SERVER = "in-v3.mailjet.com"
SMTP_PORT = 587
MAILJET_USER = "ad6944548828bc7ffc0582ffbb09fcb6"
MAILJET_PASS = "10a20df16440c695fbd8108d958dba80"
SENDER_EMAIL = "Jsorkin123@gmail.com"
RECEIVER_EMAIL = "Jsorkin123@gmail.com"

def send_email_report(data):
    # ✅ Generate LOCAL timestamp with timezone
    local_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tz_name = time.tzname[time.daylight]  # e.g. EDT/EST
    run_timestamp = f"{local_time} {tz_name}"

    eth_price = data["eth_price"]
    eth_held = data["eth_held"]
    sbet_price = data["sbet_price"]
    shares_out = data["shares_out"]
    treasury_value = data["treasury_value"]
    mnav_per_share = data["mnav_per_share"]
    market_cap = data["market_cap"]

    subject = "SBET MNAV Report"
    body = f"""
✅ SBET MNAV REPORT
Generated at: {run_timestamp}

ETH Price: ${eth_price:,.2f}
SBET Stock Price: ${sbet_price:,.2f}

Aggregate ETH Holdings: {eth_held:,} ETH
Diluted Shares Outstanding: {shares_out:,}

Treasury Value: ${treasury_value:,.2f}
MNAV per Share: ${mnav_per_share:,.2f}
Market Cap: ${market_cap:,.2f}
MNAV Multiple (MarketCap / Treasury): {market_cap / treasury_value:.2f}x

Generated automatically by your MNAV script.
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(MAILJET_USER, MAILJET_PASS)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print(f"[INFO] ✅ Email sent successfully to {RECEIVER_EMAIL}")
    except Exception as e:
        print(f"[WARN] Failed to send email: {e}")

if __name__ == "__main__":
    # ✅ Read output from MNAV calc
    with open("mnav_output.json", "r") as f:
        data = json.load(f)

    send_email_report(data)
