import asyncio
import os
import sys
import json
import time
import threading
from flask import Flask, request, jsonify
from playwright.async_api import async_playwright
from vision_angle import analyze_trend_angle, analyze_pullback
import urllib.parse
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(parent_dir, "browseruse"))
from telegram_utils import send_telegram_alert

app = Flask(__name__)

CDP_URL = "http://127.0.0.1:9222"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_TICKER = "BTCUSDT"


active_tasks = {} # Queue for each chart  { "BTCUSDT": 2, "NSE:NIFTY": 5 }
task_lock = threading.Lock()
screenshot_lock = asyncio.Lock() # Avoid Race condition in Screenshot


async def set_candle_visibility(page, visible: bool):
    print(f"[Bot] Setting chart Body/Borders/Wick to {visible} via Right-Click...")
    
    vp = page.viewport_size or {"width": 1280, "height": 720}
    cx, cy = vp["width"] // 2, vp["height"] // 2
    await page.mouse.click(cx, cy, button="right")
    await page.wait_for_timeout(800)
    

    try:
        settings_option = page.locator("tr").filter(has_text="Settings").last
        await settings_option.click(force=True, timeout=3000)
        await page.wait_for_timeout(1500) 
    except Exception as e:
        print(f"[Bot] Failed to click Settings in context menu: {e}")
    

    for label_text in ["Body", "Borders", "Wick"]:
        try: 
            checkbox = page.locator("label").filter(has_text=label_text).locator("input[type='checkbox']").first
            if await checkbox.count() > 0:
                is_checked = await checkbox.is_checked()
                if is_checked != visible:        
                    await checkbox.click(force=True)
                    await page.wait_for_timeout(300)
        except:
            pass 
            
    await page.keyboard.press("Enter")
    try:
        ok_btn = page.locator("button[data-name='submit-button']").first
        if await ok_btn.is_visible():
            await ok_btn.click(force=True)
    except:
        pass
        
    await page.wait_for_timeout(1000)



async def take_chart_screenshot(ticker):
    ticker = ticker.strip().upper()
    safe_name = ticker.replace(':', '_').replace('/', '_')
    screenshot_path = os.path.join(SCRIPT_DIR, f"angle_final_{safe_name}.png")
    
    async with screenshot_lock:
        print(f"[Bot] Locating chart for {ticker}...")
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(CDP_URL)
            except Exception as e:
                print(f"[Bot] Chrome connect error: {e}")
                return False, ""

            context = browser.contexts[0]
            chart_url = f"https://in.tradingview.com/chart/s3TnltIC/?symbol={ticker}"

         
            target_page = None
            for page in context.pages:
                decoded_url = urllib.parse.unquote(page.url).upper()
                if ticker in decoded_url:
                    target_page = page
                    break
            
            if not target_page:
                print(f"[Bot] No tab found for {ticker}. Opening fresh tab...")
                target_page = await context.new_page()
                await target_page.goto(chart_url)
                await target_page.wait_for_timeout(10000)
            else:
                print(f"[Bot] Recycling existing tab for {ticker}.")
                await target_page.bring_to_front()
                await target_page.wait_for_timeout(1000)
            
            await set_candle_visibility(target_page, False)
            await target_page.screenshot(path=screenshot_path, full_page=False)
            print(f"[Bot] Captured {ticker} -> {screenshot_path}")
            return True, screenshot_path


async def take_pullback_screenshot(ticker):
    ticker = ticker.strip().upper()
    safe_name = ticker.replace(':', '_').replace('/', '_')
    pullback_path = os.path.join(SCRIPT_DIR, f"pullback_{safe_name}.png")
    
    async with screenshot_lock: 
        print(f"[Bot] Locating chart for {ticker} PULLBACK analysis...")
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
    
            target_page = None
            for page in context.pages:
                decoded_url = urllib.parse.unquote(page.url).upper()
                if ticker in decoded_url:
                    target_page = page
                    break
                    
            if not target_page:
                return False, "" 
            await target_page.bring_to_front()
            await target_page.wait_for_timeout(1000)
            
            try:
                await set_candle_visibility(target_page, True)  
                await target_page.screenshot(path=pullback_path, full_page=False)
                print(f"[Bot] PULLBACK Screenshot captured -> {pullback_path}")
                
            finally:
                await set_candle_visibility(target_page, False)

            return True, pullback_path


def process_alert(payload, task_id):
    ticker = payload.get("ticker", DEFAULT_TICKER).strip().upper()
    trend = payload.get("trend", "UNKNOWN").upper()
    
    print(f"[Bot][{ticker} - Task {task_id}] Signal: {trend} | Waiting 2 minutes for trend...")
    
    for _ in range(60):#wait 1 min before taking ss and also do check if id is relevant or not 
        if task_id != active_tasks.get(ticker): return
        time.sleep(1)

    while True:
        if task_id != active_tasks.get(ticker): return

        success, final_img_path = asyncio.run(take_chart_screenshot(ticker))
        if task_id != active_tasks.get(ticker): return

        if not success:
            time.sleep(5)
            continue
            
        analysis = analyze_trend_angle(final_img_path, trend)
        if task_id != active_tasks.get(ticker): return
        
        print(f"[Bot][{ticker} - Task {task_id}] Analysis: {analysis.get('estimated_angle')}")

        if analysis.get("is_above_60"):
            print(f"[Bot][{ticker} - Task {task_id}] Stage 1 (Angle > 60) Passed! Starting Stage 2 (Pullback)...")
            
            pb_success, pb_path = asyncio.run(take_pullback_screenshot(ticker))
            if task_id != active_tasks.get(ticker): return
            
            if not pb_success:
                print(f"[Bot][{ticker} - Task {task_id}] Error taking Pullback screenshot. Retrying...")
                time.sleep(5)
                continue
                
            pb_analysis = analyze_pullback(pb_path, trend)
            print(f"\n--- GPT PULLBACK ANALYSIS ---")
            print(json.dumps(pb_analysis, indent=2))
            
            if pb_analysis.get("pullback_detected"):
                print(f"[Bot][{ticker} - Task {task_id}] STAGE 2 PASSED! Pullback confirmed. Sending Telegram...")
                
                rich_psychology = (
                    f"Trend: {analysis.get('trend_direction')} (Angle: {analysis.get('estimated_angle')})\n"
                    f"Sentiment: {pb_analysis.get('market_sentiment')} @ {pb_analysis.get('current_price')}\n"
                    f"Pullback Logic: {pb_analysis.get('pullback_reasoning')}"
                )
                
                primary_data = {
                    "confidence": pb_analysis.get("confidence", analysis.get("confidence", 0)),
                    "psychology": rich_psychology,
                    "reasoning": analysis.get("reasoning", ""),
                    "trade_decision": "TRADE CONFIRMED",
                }
                
                try:
                    send_telegram_alert(ticker, primary_data, {}, {}, "N/A", final_img_path)
                    print(f"[Bot][{ticker} - Task {task_id}] Telegram sent successfully! Exiting task.")
                except Exception as e:
                    print(f"[Bot] Telegram send error: {e}")
                    
                break # Both stages passed and alert sent, task complete!
                
            else:
                print(f"[Bot][{ticker} - Task {task_id}] Wait: No pullback detected yet. Re-evaluating next minute...")
                for _ in range(60):
                    if task_id != active_tasks.get(ticker): return
                    time.sleep(1)
        else:
            print(f"[Bot][{ticker} - Task {task_id}] Condition not met. Sleeping 1 min...")
            for _ in range(60):
                if task_id != active_tasks.get(ticker): return
                time.sleep(1)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json or {}
    except:
        data = {}
        
    ticker = data.get("ticker", DEFAULT_TICKER).strip().upper()
    
    with task_lock:
        new_id = active_tasks.get(ticker, 0) + 1
        active_tasks[ticker] = new_id

    threading.Thread(target=process_alert, args=(data, new_id)).start()
    return jsonify({"status": "received", "ticker": ticker, "task_id": new_id}), 200

if __name__ == "__main__":
    print("[Server] Starting Scalable Multi-Ticker Webhook Server...")
    app.run(host="0.0.0.0", port=8000)
