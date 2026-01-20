import os
import re
import requests
import html
import logging

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Backward compatible:
# - If TELEGRAM_CHAT_IDS exists, use it
# - Else fall back to TELEGRAM_CHAT_ID (single OR comma/space separated)
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_CHAT_IDS = os.getenv("TELEGRAM_CHAT_IDS")  # optional

MAX_FIELD_LEN = 900
backend_logger = logging.getLogger("backend")


def clip(text: str, n: int = MAX_FIELD_LEN) -> str:
    if not text:
        return "N/A"
    text = str(text)
    return text if len(text) <= n else text[:n] + "…"


def _parse_chat_ids(raw: str):
    """
    Accepts:
      "12345"
      "12345,67890"
      "-1001234567890 12345"
      "12345, 67890 | -1001234567890"
    Returns list[str] in stable order, de-duplicated.
    """
    if not raw:
        return []

    parts = re.split(r"[,\s|]+", raw.strip())
    out = []
    seen = set()
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        if re.fullmatch(r"-?\d+", p):
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


def send_telegram_alert(ticker, primary, hourly, daily, rsi_momentum, screenshot_path=None):
    # NOTE: function signature unchanged

    # Build chat id list without breaking old env usage
    chat_ids = _parse_chat_ids(TELEGRAM_CHAT_IDS or TELEGRAM_CHAT_ID)

    if not TELEGRAM_BOT_TOKEN or not chat_ids:
        backend_logger.info("[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID/TELEGRAM_CHAT_IDS in env")
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

    # if primary.get("trade_decision") != "TRADE":
    #     message += "⚠️ <b>No Trade Triggered</b> (Rules not met)\n\n"

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

    # 1) Send the TEXT message (same as before, now to multiple chat_ids)
    send_msg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for chat_id in chat_ids:
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            resp = requests.post(send_msg_url, json=payload, timeout=10)
            backend_logger.info(f"[Telegram] sendMessage chat_id={chat_id} status={resp.status_code} body={resp.text}")
            resp.raise_for_status()
        except Exception as e:
            backend_logger.error(f"[Telegram] Error sending message to chat_id={chat_id}: {e}")
            continue

        # 2) Send screenshot (same as before, now to multiple chat_ids)
        if screenshot_path and os.path.exists(screenshot_path):
            send_photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            caption = f"{title_emoji} {ticker} ({primary_conf}/10)"

            try:
                with open(screenshot_path, "rb") as f:
                    files = {"photo": f}
                    data = {
                        "chat_id": chat_id,
                        "caption": caption,
                        "parse_mode": "HTML"
                    }
                    resp2 = requests.post(send_photo_url, data=data, files=files, timeout=20)
                    backend_logger.info(f"[Telegram] sendPhoto chat_id={chat_id} status={resp2.status_code} body={resp2.text}")
                    resp2.raise_for_status()
            except Exception as e:
                backend_logger.error(f"[Telegram] Error sending screenshot to chat_id={chat_id}: {e}")
        else:
            backend_logger.info(f"[Telegram] screenshot_path missing or not found: {screenshot_path}")
        
        # 3) Cleanup: Delete the screenshot file after sending to all users
    if screenshot_path and os.path.exists(screenshot_path):
        try:
            os.remove(screenshot_path)
            backend_logger.info(f"[Telegram] Deleted screenshot: {screenshot_path}")
        except Exception as e:
            backend_logger.error(f"[Telegram] Failed to delete screenshot: {e}")


if __name__ == "__main__":

    test_ticker = "TEST"

    test_primary = {
        "confidence": 9,
        "psychology": "Test psychology message (testing only).",
        "reasoning": "Test reasoning message (testing only).",
        "entry_price": 100.0,
        "stop_loss": 95.0,
        "target": 110.0,
        "rr_ratio": "2.0",
        "trade_decision": "TRADE",
        "alignment_analysis": "Test alignment analysis (testing only).",
        "alignment_confidence": 8,
    }

    test_hourly = {}
    test_daily = {}

    test_rsi_momentum = "POSITIVE"

    send_telegram_alert(
        test_ticker,
        test_primary,
        test_hourly,
        test_daily,
        test_rsi_momentum,
        screenshot_path=None,
    )
