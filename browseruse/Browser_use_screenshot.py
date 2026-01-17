#browseruse\Browser_use_screenshot.py
import asyncio
import json
import os
import sys
from playwright.async_api import async_playwright
from vision_utils import analyze_adx, analyze_alignment_context
from telegram_utils import send_telegram_alert

CDP_URL = "http://127.0.0.1:9222"
BASE_CHART_URL = "https://in.tradingview.com/chart/s3TnltIC/"

# ... (apply_trading_rules stays same) ...

async def analyze_single_timeframe(page, ticker, interval, label, rsi_momentum=None):
   
    pass 



async def goto_chart(page, ticker, interval):
    # Helper to navigate
    tv_interval = interval
    if interval.lower() == "1h": tv_interval = "60"
    elif interval.lower() == "4h": tv_interval = "240"
    elif "m" in interval.lower(): tv_interval = interval.lower().replace("m", "")
    
    separator = "&" if "?" in BASE_CHART_URL else "?"
    target_url = f"{BASE_CHART_URL}{separator}symbol={ticker}&interval={tv_interval}"
    
    try:
        await page.goto(target_url)
        await page.wait_for_timeout(5000)
        try:
            await page.mouse.move(50, 50)
            await page.wait_for_timeout(500)
            legends = await page.locator("[class*='legend-'] button[class*='toggler-']").all()
            if legends: await legends[0].click()
        except: pass
    except Exception as e:
        print(f"Nav error: {e}")

async def run_analysis_flow(rsi_momentum, ticker, interval, intent):
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
        except:
            return {"error": "Chrome not connected"}

        context = browser.contexts[0]
        page = await context.new_page() if not context.pages else context.pages[0]

        # 1. Primary (Minute) Analysis
        await goto_chart(page, ticker, interval)
        screenshot_path = "chart_primary.png"
        await page.bring_to_front()
        await page.screenshot(path=screenshot_path, full_page=False)
        
        primary_res = analyze_adx(screenshot_path)
        primary_res['rsi_momentum'] = rsi_momentum
        
        # Apply Logic First so we know the 'decision' to verify against
        if intent == "live_trade":
            decision, sig_type = apply_trading_rules(primary_res, rsi_momentum)
            primary_res["trade_decision"] = decision
            primary_res["signal_type"] = sig_type
        else:
            primary_res["trade_decision"] = "EVALUATION_ONLY"
            primary_res["signal_type"] = "NONE"

        # 2. Alignment Analysis (Hourly)
        short_intervals = ["1", "3", "5", "15", "30", "1m", "3m", "5m", "15m" , "30m"]
        
        if str(interval) in short_intervals:
            print("Fetching Hourly Alignment...")
            await goto_chart(page, ticker, "1h")
            hourly_path = "chart_hourly.png"
            await page.bring_to_front()
            await page.screenshot(path=hourly_path, full_page=False)
            
            # Use NEW Alignment Function
            # Passes the Hourly Image + The already-calculated Minute Analysis
            alignment = analyze_alignment_context(hourly_path, primary_res)
            
            # Merge Alignment Data
            primary_res["hourly_alignment"] = alignment.get("alignment_analysis")
            primary_res["alignment_confidence"] = alignment.get("alignment_confidence")

        # 3. Telegram
        print("Checking Telegram alert criteria...")
        send_telegram_alert(
            ticker=ticker,
            primary=primary_res,
            hourly={}, # No longer independent hourly data
            daily={}, 
            rsi_momentum=rsi_momentum 
        )

        return primary_res

if __name__ == "__main__":
    if len(sys.argv) > 1:
        rsi_momentum = sys.argv[1]
        ticker = sys.argv[2] if len(sys.argv) > 2 else "NIFTY"
        interval = sys.argv[3] if len(sys.argv) > 3 else "5"
        intent = sys.argv[4] if len(sys.argv) > 4 else "live_trade"
        
        result = asyncio.run(run_analysis_flow(rsi_momentum, ticker, interval, intent))
        print("\n[JSON OUTPUT]")
        print(json.dumps(result, indent=2))
    else:
        print("Arguments required")
