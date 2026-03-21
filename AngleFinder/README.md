# AngleFinder Vision AI Bot

## Overview
AngleFinder is an automated, webhook-driven technical analysis bot designed to interface with TradingView and OpenAI's GPT-4o Vision API. The bot evaluates live chart indicators to capture high-probability trade setups based on a strict two-stage visual filtering system. 

It handles multiple concurrent symbols simultaneously while gracefully orchestrating Playwright browser tabs, evaluating chart angles, and measuring precise wick pullbacks before sending structured alerts directly to Telegram.

---

## 1. Prerequisites and Setup

Before starting the Flask server, ensure the following are installed and configured:
- Python 3.10+
- `pip install -r requirements.txt` (including `playwright`, `openai`, `flask`)
- Run `python -m playwright install chromium` to ensure the automation drivers are installed.
- Configure your `.env` file with `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID`.

### Starting Chrome in Debugging Mode
This bot requires access to an active, authenticated instance of Google Chrome so it can read your customized TradingView layouts without getting blocked by login screens.

You **Must** launch Chrome using the remote debugging port before starting the bot:
**Windows CMD:**
```cmd
chrome.exe --remote-debugging-port=9222
```
*Note: Ensure no other instances of Chrome are running before executing this command, or specify a custom `--user-data-dir` so it runs in isolation.*

---

## 2. Webhook Architecture and TradingView Setup

To connect TradingView to the AngleFinder server, you will need a service like **Ngrok** to expose your local Flask server (`port 8000`) to the public internet.

**Example Ngrok Command:**
```cmd
ngrok http 8000
```

### TradingView Alert Setup
Create an alert in TradingView and set the **Webhook URL** to your generated Ngrok address (e.g., `https://your-ngrok.app/webhook`).

In the **Message Body** of the TradingView alert, paste the following JSON payload template. The bot parses this payload to know exactly what chart to open:
```json
{
  "ticker": "{{exchange}}:{{ticker}}",
  "interval": "{{interval}}",
  "rsi_momentum": "{{plot_0}}"
}
```
*For example, if NIFTY triggers, TradingView replaces `{{ticker}}` so the payload mathematically evaluates to `{"ticker": "NSE:NIFTY"}`.*

---

## 3. The Queuing System (Scalable Multi-Ticker Support)

AngleFinder is designed for **Scalable Concurrency** and can track an unlimited number of assets simultaneously on a single machine.

- **Isolated Queues**: When the server receives a webhook for `BTCUSDT`, it assigns a unique Task ID specifically to Bitcoin and starts a background evaluation thread. 
- **Conflict Resolution**: If the bot receives *another* alert for `BTCUSDT` while the first one is still evaluating, the new alert automatically upgrades the Task ID and kills the old/stale evaluation.
- **Parallel Processing**: An alert for `NSE:NIFTY` operates on a completely isolated track. A new `NIFTY` alert will never interrupt a `BTCUSDT` evaluation.
- **Browser Traffic Light (Lock)**: Even though 5 coins might be evaluating at once, a system-level asyncio "Lock" ensures the mouse physically clicks only one TradingView tab at a time when capturing screenshots.

---

## 4. The Dual-Stage AI Vision Logic

The bot does not blindly trust every alert. It pushes the chart through two strict visual checkpoints utilizing the GPT-4o Vision API.

### Stage 1: The Minimum Trend Angle (60-Degree Rule)
*When the webhook triggers, the bot waits for the trend to mature before taking action.*
1. **Wait Timer**: The bot sleeps for a predefined time (e.g., waiting for the current 1-minute or 2-minute candle to close).
2. **Clean Screenshot**: The bot locates the correct browser tab, aggressively **clears all candlestick bodies, borders, and wicks** from the screen (via native right-click UI manipulation), and snaps a screenshot of the pure indicator lines.
3. **Vision Processing**: GPT-4o is asked to estimate the angle of the main signal line. Is it rising strictly above +60 degrees? Is it dropping aggressively below -60 degrees?
4. **Resolution**: If the angle is too flat (e.g., +45 degrees), the bot throws away the alert or continues a sleeping retry-loop. If it passes >60 degrees, it advances to Stage 2.

### Stage 2: The Pullback Validation (0.1% / Touch Rule)
*If the trend is strong enough, the bot looks for a safe entry point (a pullback) rather than chasing an over-extended move.*
1. **Detailed Screenshot**: The bot re-opens the charting menu, forces the candlestick bodies, borders, and wicks back **ON**, and takes a highly-detailed second screenshot (`pullback_TICKER.png`).
2. **Vision Processing**: GPT-4o acts as a strict caliper to judge wick proximity to the EMA line.
3. **The Logical Rule**: 
   - *Bullish*: The bot looks for a 'buy' candle where the LOWER WICK dips down. The absolute lowest needle-point of that wick must visibly be within **0.1%** of the EMA price line, or physically pierce it.
   - *Bearish*: The bot looks for a 'sell' candle where the UPPER WICK spikes up to physically touch or come within 0.1% of the upper EMA boundary.
4. **Resolution**: If the pullback is not clean or doesn't explicitly touch the line, the task is dropped. If it passes this final gauntlet, the JSON responses from both stages are combined into a detailed psychology report.

---

## 5. Output

Once an alert survives both the Angle Test and the Pullback Test, it compiles the JSON and fires it directly to your customized Telegram group using `telegram_utils.py`! The attached image will be your clean, initial Chart layout. 

```json
{
  "confidence": 9,
  "psychology": "Trend: UP (Angle: +65 degrees)\nSentiment: BULLISH @ 70,123.45\nPullback Logic: The lower wick of the latest candle cleanly pierced the EMA line, confirming a physical touch per the 0.1% rule.",
  "reasoning": "Angle estimation > 60-degree check passed. Pullback wick touch explicitly verified.",
  "trade_decision": "TRADE CONFIRMED"
}
```
