AUTOMATED TRADING SYSTEM OVERVIEW

SYSTEM SETUP

1. Start Chrome (Debugging Mode) - Must be running before analysis can start.

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\chrome-debug"

Wait for Chrome to open, then load your TradingView chart with indicators visible.

2. Start Backend & Tunnel

Terminal 1 (Backend):
python backend/app.py

Terminal 2 (Public Access):
ngrok http 8009

Copy the https URL from ngrok (e.g., https://7f1947499c0e.ngrok-free.app).


WORKFLOW

- TradingView Alert: RSI Momentum Trend changes (Positive/Negative).
- Webhook Trigger: Sends POST request to .../api/webhook/tradingview.
- Backend: Receives alert, triggers Browser_use_screenshot.py.
- Automation: Script connects to debug Chrome, captures chart screenshot.
- Analysis: GPT Vision reads indicators (ADX, TCI) and Price Action.
- Decision: Python logic combines Webhook RSI + GPT Analysis to decide Buy/Sell.


TRADINGVIEW SETUP

Webhook URL:
https://YOUR-NGROK-URL.ngrok-free.app/api/webhook/tradingview

Required Indicators (must be visible):
- RSI Momentum Trend
- ADX (Average Directional Index)
- TCI (Trend Cycle Indicator)

Alert Config:
- Condition: RSI Momentum Trend crossing UP (Positive) or DOWN (Negative).
- Trigger: Once Per Bar Close (Critical).

JSON Payload:
{ "rsi_momentum": "POSITIVE", "ticker": "{{ticker}}" }

(Use "NEGATIVE" for the bearish alert)


TRADING LOGIC

The system applies strict rules to generate a signal.

BUY SIGNAL RULES (all conditions must be TRUE):
- RSI Alert: "POSITIVE" (from Webhook)
- ADX: Value > 20 (Trending Market)
- TCI: "CROSSOVER" (Fast line crosses above Slow)
- Conf: "CONFIRMED_BREAKOUT" (Candle CLOSED above key resistance)
- RR: 1:2 Risk-Reward ratio is achievable
- Output: TRADE + BUY + Entry + SL + Target

SELL SIGNAL RULES (all conditions must be TRUE):
- RSI Alert: "NEGATIVE" (from Webhook)
- ADX: Value > 20 (Trending Market)
- TCI: "CROSSUNDER" (Fast line crosses below Slow)
- Conf: "CONFIRMED_BREAKDOWN" (Candle CLOSED below key support)
- RR: 1:2 Risk-Reward ratio is achievable
- Output: TRADE + SELL + Entry + SL + Target

If ANY condition fails, the result is NO_TRADE.


