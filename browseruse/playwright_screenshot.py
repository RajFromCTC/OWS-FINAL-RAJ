#browseruse\Browser_use_screenshot.py
import asyncio
import json
import os
import sys
from playwright.async_api import async_playwright
from vision_utils import analyze_adx, analyze_alignment_context
from telegram_utils import send_telegram_alert
from playwrightUtils import set_timeframe_by_typing

CDP_URL = "http://127.0.0.1:9222"
BASE_CHART_URL = "https://in.tradingview.com/chart/s3TnltIC/"


async def analyze_single_timeframe(page, ticker, interval, label, rsi_momentum=None):
   
    pass 

def _interval_to_tv_typing(interval: str) -> str:
    """
    What we will TYPE on the TradingView chart.
    TradingView accepts:
      - minutes: 1, 3, 5, 15, 30
      - daily: 1D (or D), weekly: 1W (or W), monthly: 1M (or M)
      - hours: TradingView often accepts minutes (60 for 1h, 240 for 4h)
    """
    iv = str(interval).strip()
    iv_l = iv.lower()

    if iv_l == "1h":
        return "60"
    if iv_l == "4h":
        return "240"
    if iv_l in ["1d", "d"]:
        return "1D"
    if iv_l in ["1w", "w"]:
        return "1W"
    if iv_l in ["1m", "m"]:
        return "1M"

    # if "5m" -> "5"
    if iv_l.endswith("m") and iv_l[:-1].isdigit():
        return iv_l[:-1]

    # if "5" -> "5"
    return iv

async def goto_chart(page, ticker, interval):

    separator = "&" if "?" in BASE_CHART_URL else "?"
    symbol_url = f"{BASE_CHART_URL}{separator}symbol={ticker}"

    try:
        await page.goto(symbol_url)
        await page.wait_for_timeout(5000)

        try:
            await page.mouse.move(50, 50)
            await page.wait_for_timeout(500)
            legends = await page.locator("[class*='legend-'] button[class*='toggler-']").all()
            if legends:
                await legends[0].click()
        except:
            pass


        try:
            await set_timeframe_by_typing(page, interval)
        except Exception as e:
            print(f"[WARN] UI timeframe typing failed: {e}")
            raise

    except Exception as e:
        print(f"[WARN] UI navigation/timeframe set failed. Falling back to URL method. Error: {e}")

      
        tv_interval = interval
        if interval.lower() == "1h":
            tv_interval = "60"
        elif interval.lower() == "4h":
            tv_interval = "240"
        elif interval.lower() == "1d":
            tv_interval = "1D"
        elif "m" in interval.lower():
            tv_interval = interval.lower().replace("m", "")

        target_url = f"{BASE_CHART_URL}{separator}symbol={ticker}&interval={tv_interval}"

        try:
            await page.goto(target_url)
            await page.wait_for_timeout(5000)

            try:
                await page.mouse.move(50, 50)
                await page.wait_for_timeout(500)
                legends = await page.locator("[class*='legend-'] button[class*='toggler-']").all()
                if legends:
                    await legends[0].click()
            except:
                pass
        except Exception as e2:
            print(f"Nav error (fallback also failed): {e2}")

async def run_analysis_flow(rsi_momentum, ticker, interval, intent):
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
        except:
            return {"error": "Chrome not connected"}

        context = browser.contexts[0]
        page = await context.new_page() if not context.pages else context.pages[0]

       
        await goto_chart(page, ticker, interval)
        screenshot_path = "chart_primary.png"
        await page.bring_to_front()
        await page.screenshot(path=screenshot_path, full_page=False)
        
        primary_res = analyze_adx(screenshot_path)
        primary_res['rsi_momentum'] = rsi_momentum
        
    
        if intent == "live_trade":
            decision, sig_type = apply_trading_rules(primary_res, rsi_momentum)
            primary_res["trade_decision"] = decision
            primary_res["signal_type"] = sig_type
        else:
            primary_res["trade_decision"] = "EVALUATION_ONLY"
            primary_res["signal_type"] = "NONE"

        tf_map = {
            "1":  "5m",   "1m":  "5m",
            "2":  "10m",  "2m":  "10m",
            "3":  "15m",  "3m":  "15m",
            "5":  "1h",   "5m":  "1h",
            "15": "1h",   "15m": "1h",
            "30": "2h",   "30m": "2h",
            "60": "4h",   "1h":  "4h",
        }

        interval_key = str(interval).strip().lower()
        higher_tf = tf_map.get(interval_key)

        if higher_tf:
            print(f"Fetching Alignment: {interval_key} vs {higher_tf} ...")
            await goto_chart(page, ticker, higher_tf)

            align_path = "chart_secondary.png"
            await page.bring_to_front()
            await page.screenshot(path=align_path, full_page=False)

            alignment = analyze_alignment_context(align_path, primary_res)

            primary_res[f"alignment_analysis_{interval_key}"] = alignment.get("alignment_analysis")
            primary_res[f"alignment_confidence_{interval_key}"] = alignment.get("alignment_confidence")
            primary_res["alignment_tf"] = higher_tf
        else:
            print(f"No alignment mapping for interval={interval}. Skipping alignment.")
     
        print("Checking Telegram alert criteria...")
        send_telegram_alert(
            ticker=ticker,
            primary=primary_res,
            hourly={}, 
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
