import os
import requests
import html

TELEGRAM_BOT_TOKEN = "8405034100:AAFWrKVb2f8le_VtLFZbl6G2TJApF-Hq838"
TELEGRAM_CHAT_ID = "1806343942"

MAX_FIELD_LEN = 900 


def clip(text: str, n: int = MAX_FIELD_LEN) -> str:
    if not text:
        return "N/A"
    text = str(text)
    return text if len(text) <= n else text[:n] + "…"


def send_telegram_alert(ticker, primary, hourly, daily, rsi_momentum):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in env")
        return

    primary_conf = int(primary.get("confidence", 0) or 0)
    if primary_conf < 8:
        print(f"[Telegram] Skipped: Confidence {primary_conf} is below 8")
        return

    signal_side = "BUY" if rsi_momentum == "POSITIVE" else "SELL"
    title_emoji = "🟢" if signal_side == "BUY" else "🔴"

    psych = clip(primary.get("psychology"))
    reasoning = clip(primary.get("reasoning"))

    # Escape everything that might break formatting
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

    if primary.get("trade_decision") == "TRADE":
        entry = primary.get("entry_price")
        sl = primary.get("stop_loss")
        target = primary.get("target")
        rr = primary.get("rr_ratio", "N/A")

        message += (
            f"🎯 <b>ACTION PLAN</b>\n"
            f"• Price: <code>{html.escape(str(entry))}</code>\n"
            f"• Stop Loss: <code>{html.escape(str(sl))}</code>\n"
            f"• Target: <code>{html.escape(str(target))}</code>\n"
            f"• R/R Ratio: <code>{html.escape(str(rr))}</code>\n\n"
        )
    else:
        message += "⚠️ <b>No Trade Triggered</b> (Rules not met)\n\n"

    # Hourly alignment summary (your real alignment is stored in primary)
    align_summary = primary.get("hourly_alignment")
    align_conf = primary.get("alignment_confidence")

    if align_summary:
        message += (
            "📊 <b>Hourly Alignment</b>\n"
            f"• Alignment Conf: <b>{html.escape(str(align_conf))}/10</b>\n"
            f"• Analysis: <i>{html.escape(clip(align_summary, 700))}</i>\n"
        )
    else:
        message += "📊 <b>Hourly Alignment</b>\n• No alignment data available.\n"

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("[Telegram] Alert sent successfully!")
    except requests.exceptions.HTTPError as e:
        print(f"[Telegram] HTTP Error: {e}")
        print(f"[Telegram] Response: {response.text}")
    except Exception as e:
        print(f"[Telegram] Error sending alert: {e}")
