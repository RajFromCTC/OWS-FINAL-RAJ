import os
import requests
import html
import logging

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MAX_FIELD_LEN = 900
backend_logger = logging.getLogger("backend")

def clip(text: str, n: int = MAX_FIELD_LEN) -> str:
    if not text:
        return "N/A"
    text = str(text)
    return text if len(text) <= n else text[:n] + "…"


def send_telegram_alert(ticker, primary, hourly, daily, rsi_momentum, screenshot_path=None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        backend_logger.info("[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in env")
        return

    primary_conf = int(primary.get("confidence", 0) or 0)
    if primary_conf < 8:
        backend_logger.info(f"[Telegram] Skipped: Confidence {primary_conf} is below 8")
        return

    signal_side = "BUY" if rsi_momentum == "POSITIVE" else "SELL"
    title_emoji = "🟢" if signal_side == "BUY" else "🔴"

    psych = clip(primary.get("psychology"))
    reasoning = clip(primary.get("reasoning"))

    ticker_e = html.escape(str(ticker))
    psych_e = html.escape(psych)
    reasoning_e = html.escape(reasoning)

    message = (
        f"{title_emoji} <b>HIGH CONFIDENCE {signal_side} SETUP</b>\n"
        f"Ticker: <code>{ticker_e}</code>\n"
        f"Confidence: <b>{primary_conf}/10</b>\n\n"
        f"🧠 <b>Psychology</b>:\n<i>{psych_e}</i>\n\n"
        f"📝 <b>Reasoning</b>:\n<i>{reasoning_e}</i>\n\n"
    )

    entry = primary.get("entry_price")
    sl = primary.get("stop_loss")
    target = primary.get("target")
    rr = primary.get("rr_ratio", "N/A")

    if any([entry, sl, target]):
        message += (
            f"🎯 <b>ACTION PLAN</b>\n"
            f"• Price: <code>{html.escape(str(entry or 'N/A'))}</code>\n"
            f"• Stop Loss: <code>{html.escape(str(sl or 'N/A'))}</code>\n"
            f"• Target: <code>{html.escape(str(target or 'N/A'))}</code>\n"
            f"• R/R Ratio: <code>{html.escape(str(rr))}</code>\n\n"
        )

    if primary.get("trade_decision") != "TRADE":
        message += "⚠️ <b>No Trade Triggered</b> (Rules not met)\n\n"

    align_summary = primary.get("alignment_analysis")
    align_conf = primary.get("alignment_confidence")

    if align_summary:
        message += (
            "📊 <b>Hourly Alignment</b>\n"
            f"• Alignment Conf: <b>{html.escape(str(align_conf))}/10</b>\n"
            f"• Analysis: <i>{html.escape(clip(align_summary, 700))}</i>\n"
        )
    else:
        message += "📊 <b>Hourly Alignment</b>\n• No alignment data available.\n"

    # 1) Send the TEXT message (same as before)
    send_msg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        resp = requests.post(send_msg_url, json=payload, timeout=10)
        backend_logger.info(f"[Telegram] sendMessage status={resp.status_code} body={resp.text}")
        resp.raise_for_status()
    except Exception as e:
        backend_logger.error(f"[Telegram] Error sending message: {e}")
        return  

    # 2) Send the screenshot as PHOTO (optional)
    if screenshot_path and os.path.exists(screenshot_path):
        send_photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        caption = f"{title_emoji} {ticker} ({primary_conf}/10)"  # keep caption short

        try:
            with open(screenshot_path, "rb") as f:
                files = {"photo": f}
                data = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": caption,
                    "parse_mode": "HTML"
                }
                resp2 = requests.post(send_photo_url, data=data, files=files, timeout=20)
                backend_logger.info(f"[Telegram] sendPhoto status={resp2.status_code} body={resp2.text}")
                resp2.raise_for_status()
        except Exception as e:
            backend_logger.error(f"[Telegram] Error sending screenshot: {e}")
    else:
        backend_logger.info(f"[Telegram] screenshot_path missing or not found: {screenshot_path}")
