import os
import smtplib
import logging
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv
load_dotenv() 
# --- LOGGING SETUP (added) ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
smtp_logger = logging.getLogger("backend")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT", "587")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")

def _mask(s: str):
    if not s:
        return "MISSING"
    if len(s) <= 4:
        return "***"
    return s[:2] + "***" + s[-2:]

def send_email_alert(ticker, primary, rsi_momentum, screenshot_path):
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_RECEIVER]):
        smtp_logger.info("[Email] Missing SMTP configuration in env. Skipping email alert.")
        return

    signal_side = "BUY" if rsi_momentum == "POSITIVE" else "SELL"
    confidence = primary.get("confidence", 0)

    subject = f"🚀 HIGH CONFIDENCE {signal_side} SETUP: {ticker} ({confidence}/10)"

    # Compose text body
    psych = primary.get("psychology", "N/A")
    reasoning = primary.get("reasoning", "N/A")
    entry = primary.get("entry_price", "N/A")
    sl = primary.get("stop_loss", "N/A")
    target = primary.get("target", "N/A")
    rr = primary.get("rr_ratio", "N/A")
    align_summary = primary.get("alignment_analysis", "No alignment data available.")
    align_conf = primary.get("alignment_confidence", "N/A")

    body = f"""
    This is testing mail kindly ignore
    HIGH CONFIDENCE {signal_side} SETUP
    ---------------------------------
    Ticker: {ticker}
    Confidence: {confidence}/10

    🧠 Psychology:
    {psych}

    📝 Reasoning:
    {reasoning}

    🎯 ACTION PLAN:
    • Price: {entry}
    • Stop Loss: {sl}
    • Target: {target}
    • R/R Ratio: {rr}

    📊 Hourly Alignment:
    • Alignment Conf: {align_conf}/10
    • Analysis: {align_summary}
    """

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    # Attach Screenshot
    if screenshot_path and os.path.exists(screenshot_path):
        smtp_logger.info(f"[Email] screenshot_path={screenshot_path} exists=True")
        try:
            with open(screenshot_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())

            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={os.path.basename(screenshot_path)}",
            )
            msg.attach(part)
            smtp_logger.info("[Email] Screenshot attached successfully.")
        except Exception as e:
            smtp_logger.error(f"[Email] Failed to attach screenshot: {e}", exc_info=True)
    else:
        smtp_logger.info(f"[Email] screenshot_path={screenshot_path} exists=False (no attachment)")

    # Send Email (supports 587 STARTTLS or 465 SSL)
    try:
        port = int(SMTP_PORT)
        smtp_logger.info(f"[Email] Connecting to SMTP {SMTP_HOST}:{port} ...")

        if port == 465:
            smtp_logger.info("[Email] Using SMTP_SSL (465)...")
            server = smtplib.SMTP_SSL(SMTP_HOST, port, timeout=20)
        else:
            server = smtplib.SMTP(SMTP_HOST, port, timeout=20)
            server.set_debuglevel(1)  # prints SMTP conversation
            smtp_logger.info("[Email] EHLO...")
            server.ehlo()
            smtp_logger.info("[Email] Starting TLS...")
            server.starttls()
            server.ehlo()

        server.set_debuglevel(1)  # keep logs in both modes
        smtp_logger.info("[Email] Logging in...")
        server.login(SMTP_USER, SMTP_PASS)

        smtp_logger.info("[Email] Sending message...")
        server.send_message(msg)

        server.quit()
        smtp_logger.info(f"[Email] Alert sent successfully for {ticker}!")
    except Exception as e:
        smtp_logger.error(f"[Email] Error sending email: {e}", exc_info=True)


if __name__ == "__main__":
    demo_primary = {
        "confidence": 9,
        "psychology": "Demo psychology text",
        "reasoning": "Demo reasoning text",
        "entry_price": 100,
        "stop_loss": 95,
        "target": 110,
        "rr_ratio": "1:2",
        "alignment_analysis": "Demo alignment analysis",
        "alignment_confidence": 8,
    }

    demo_screenshot_path = "chart_primary.png"

    send_email_alert(
        ticker="DEMO:TICKER",
        primary=demo_primary,
        rsi_momentum="POSITIVE",
        screenshot_path=demo_screenshot_path,
    )

    print("Done. Check terminal logs above.")
