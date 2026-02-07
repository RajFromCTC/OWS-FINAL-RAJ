import asyncio
import os
import sys
import time
import uuid
import logging
from playwright.async_api import async_playwright

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "browseruse")))

from vision_sr import analyze_1h_sr, confirm_5m_break
from config import SYMBOLS, POLL_INTERVAL, PRIMARY_TF, CONFIRM_TF, CDP_URL, BASE_CHART_URL
from telegram_utils import send_telegram_alert, _parse_chat_ids, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_CHAT_IDS
from playwrightUtils import set_timeframe_by_typing, ensure_single_layout
import requests
import html
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def goto_chart(page, ticker, interval):
    separator = "&" if "?" in BASE_CHART_URL else "?"
    symbol_url = f"{BASE_CHART_URL}{separator}symbol={ticker}"
    
    logger.info(f"Navigating to {ticker} on {interval} chart...")
    
    try:
        await page.goto(symbol_url)
        await page.wait_for_timeout(5000)
        
        try:
            await page.mouse.move(50, 50)
            await page.wait_for_timeout(500)
            toggler = page.locator("[class*='legend-'] button[class*='toggler-']").first
            if await toggler.is_visible():
                needs_click = await toggler.evaluate("""(btn) => {
                    const title = (btn.getAttribute('title') || '').toLowerCase();
                    const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                    const text = (btn.innerText || '').toLowerCase();
                    return !(title.includes('hide') || label.includes('hide') || text.includes('hide'));
                }""")
                if needs_click:
                    await toggler.click()
        except Exception as e:
            logger.debug(f"Legend toggle error: {e}")

        await set_timeframe_by_typing(page, interval)
        await page.wait_for_timeout(3000) 

        await ensure_single_layout(page)

    except Exception as e:
        logger.error(f"Failed to navigate to {ticker}: {e}")

def send_normal_status(ticker, analysis, screenshot_path=None):
    chat_ids = _parse_chat_ids(TELEGRAM_CHAT_IDS or TELEGRAM_CHAT_ID)
    if not TELEGRAM_BOT_TOKEN or not chat_ids:
        logger.warning("Telegram config missing")
        return

    message = (
        f"🔹 <b>{ticker} Status (1H)</b>\n"
        f"Price: <code>{analysis['current_price']}</code>\n"
        f"Support: <code>{analysis['support_level']}</code> (Dist: {analysis['dist_to_support']})\n"
        f"Resistance: <code>{analysis['resistance_level']}</code> (Dist: {analysis['dist_to_resistance']})\n"
        f"Status: <i>{analysis['status']}</i>"
    )

    msg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    for chat_id in chat_ids:
        try:
            requests.post(msg_url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
            if screenshot_path and os.path.exists(screenshot_path):
                with open(screenshot_path, "rb") as f:
                    requests.post(photo_url, data={"chat_id": chat_id, "caption": f"{ticker} Status"}, files={"photo": f}, timeout=20)
        except Exception as e:
            logger.error(f"Error sending normal status: {e}")

def send_alert_status(ticker, analysis_1h, analysis_5m, screenshot_path=None):
    chat_ids = _parse_chat_ids(TELEGRAM_CHAT_IDS or TELEGRAM_CHAT_ID)
    if not TELEGRAM_BOT_TOKEN or not chat_ids:
        return

    emoji = "🚀" if analysis_5m['event_type'] == "BREAKOUT" else "⚠️"
    
    message = (
        f"{emoji} <b>{analysis_5m['event_type']} CONFIRMED: {ticker}</b>\n"
        f"Price: <code>{analysis_1h['current_price']}</code>\n\n"
        f"🧐 <b>AI Analysis (5m)</b>:\n<i>{html.escape(analysis_5m['reasoning'])}</i>\n\n"
        f"📈 <b>Next Move</b>:\n<i>{html.escape(analysis_5m['likely_next_move'])}</i>\n\n"
        f"📑 <b>1H Context</b>: {html.escape(analysis_1h['summary_1h'])}"
    )

    msg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    photo_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    
    for chat_id in chat_ids:
        try:
            requests.post(msg_url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
            
            if screenshot_path and os.path.exists(screenshot_path):
                with open(screenshot_path, "rb") as f:
                    requests.post(photo_url, data={"chat_id": chat_id, "caption": f"{ticker} {analysis_5m['event_type']}"}, files={"photo": f}, timeout=20)
        except Exception as e:
            logger.error(f"Error sending alert status: {e}")

async def run_server():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            logger.error(f"Could not connect to Chrome on {CDP_URL}: {e}")
            return

        context = browser.contexts[0]
        page = await context.new_page() if not context.pages else context.pages[0]

        while True:
            current_time = time.strftime("%H:%M")
            start_msg = f"🔄 <b>System is starting its 5 min session at {current_time}</b> 📊"
            chat_ids = _parse_chat_ids(TELEGRAM_CHAT_IDS or TELEGRAM_CHAT_ID)
            if TELEGRAM_BOT_TOKEN and chat_ids:
                msg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                for chat_id in chat_ids:
                    try:
                        requests.post(msg_url, json={"chat_id": chat_id, "text": start_msg, "parse_mode": "HTML"}, timeout=10)
                    except Exception as e:
                        logger.error(f"Error sending cycle start message: {e}")

            logger.info("Starting analysis cycle...")
            for ticker_name, ticker_symbol in SYMBOLS.items():
                try:
                    await goto_chart(page, ticker_symbol, PRIMARY_TF)
                    screenshot_1h = f"sr_1h_{uuid.uuid4().hex[:8]}.png"
                    await page.bring_to_front()
                    await page.screenshot(path=screenshot_1h)
                    
                    analysis_1h = analyze_1h_sr(screenshot_1h)
                    logger.info(f"{ticker_name} (1H): {analysis_1h['status']}")

                    should_check_5m = analysis_1h['status'] in ["BREAKOUT_IMMINENT", "BREAKDOWN_IMMINENT", "BREAKOUT_CONFIRMED", "BREAKDOWN_CONFIRMED"]
                    
                    if should_check_5m:
                        logger.info(f"Potential activity on {ticker_name}, checking 5m chart...")
                        await goto_chart(page, ticker_symbol, CONFIRM_TF)
                        screenshot_5m = f"sr_5m_{uuid.uuid4().hex[:8]}.png"
                        await page.bring_to_front()
                        await page.screenshot(path=screenshot_5m)
                        
                        analysis_5m = confirm_5m_break(screenshot_5m, analysis_1h)
                        
                        if analysis_5m['confirmed']:
                            send_alert_status(ticker_name, analysis_1h, analysis_5m, screenshot_path=screenshot_5m)
                        else:
                            logger.info(f"Potential break on {ticker_name} NOT confirmed by 5m body close.")
                            analysis_1h['status'] = f"1H_{analysis_1h['status']}_NOT_CONFIRMED_BY_5M"
                            send_normal_status(ticker_name, analysis_1h, screenshot_path=screenshot_1h)
                        
                        if os.path.exists(screenshot_5m):
                            os.remove(screenshot_5m)
                    else:
                        send_normal_status(ticker_name, analysis_1h, screenshot_path=screenshot_1h)

                    if os.path.exists(screenshot_1h):
                        os.remove(screenshot_1h)

                except Exception as e:
                    logger.error(f"Error analyzing {ticker_name}: {e}")
            
            logger.info(f"Cycle complete. Waiting {POLL_INTERVAL} seconds...")
            
            await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    asyncio.run(run_server())
