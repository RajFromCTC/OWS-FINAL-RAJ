#browseruse\vision_utils.py
import os
import base64
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def analyze_adx(image_path):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    base64_image = encode_image(image_path)

    print("Analyzing image with GPT Vision...")

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a technical analysis expert. Look at the provided TradingView chart screenshot and locate the ADX indicator."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
    "Analyze this TradingView chart screenshot (timeframe: 5 MIN) and provide technical analysis for the VERY LATEST (rightmost) part of the chart.\n\n"
    "HARD RULES (to avoid confusion):\n"
    "- Use ONLY what is visible in the screenshot.\n"
    "- Focus ONLY on the latest/rightmost price action and labels.\n"
    "- IGNORE all drawings/overlays/zones (supply-demand boxes, rectangles, order blocks, toolbars, lines, notes, watermark). Those are NOT the pattern.\n"
    "- For price patterns, use the candle bodies/wicks ONLY.\n\n"
    "INSTRUCTIONS:\n"
    "1) Detection Area:\n"
    "   - Focus on the rightmost ~30–120 candles visible (the most recent action on the chart).\n\n"
    "2) ADX Value:\n"
    "   - Locate the ADX indicator panel (lower panel).\n"
    "   - Read the current ADX numeric value shown at the most recent (right side / latest value label).\n"
    "   - If the exact value is not readable, set adx_val = null and is_adx_above_20 = null (do not guess).\n\n"
    "3) TCI Crossover (TWO BLUE LINES ONLY) — ROBUST SCAN:\n"
    "   - The TCI crossover is indicated by TWO thin blue lines (fast and slow) running along the candles.\n"
    "   - Do NOT use any other blue objects (tool drawings/markers/annotations).\n"
    "   - Scan for a crossover/crossunder EVENT across the latest/rightmost visible candles (up to the last ~200 candles; if fewer than 200 are visible, use ALL visible candles).\n"
    "   - Find the MOST RECENT crossover EVENT within that scan window:\n"
    "       * If fast crosses from BELOW slow to ABOVE slow => tci_cross = \"CROSSOVER\"\n"
    "       * If fast crosses from ABOVE slow to BELOW slow => tci_cross = \"CROSSUNDER\"\n"
    "       * If NO crossing event occurs anywhere in the scan window => tci_cross = \"NONE\"\n"
    "   - Do NOT only check the last 5–15 candles. The goal is to not miss crosses that happened earlier but still matter in the current context.\n\n"
    "4) Break Confirmation + SL/Target (RR MUST BE 1:2):\n"
    "   - Using ONLY candle price action, identify ONE key trigger level (support/resistance/neckline) in the latest/rightmost section.\n"
    "   - CONFIRMATION (CLOSE ONLY):\n"
    "       * CONFIRMED_BREAKOUT only if a 5-min candle CLOSES ABOVE the key level.\n"
    "       * CONFIRMED_BREAKDOWN only if a 5-min candle CLOSES BELOW the key level.\n"
    "       * Wick beyond level without close = NO_CONFIRMED_BREAK.\n"
    "   - If there is NO confirmed break, output trade_decision = \"NO_TRADE\" and set stop_loss/target = null.\n"
    "   - If CONFIRMED_BREAKOUT:\n"
    "       * entry_price = the close price of the breakout candle.\n"
    "       * stop_loss = below the most recent swing low (last lowest) in the rightmost area.\n"
    "       * risk = entry_price - stop_loss.\n"
    "       * target = entry_price + (2 * risk).\n"
    "       * If a clear nearby resistance exists BEFORE the target, then trade_decision = \"NO_TRADE\" (RR not achievable) and set stop_loss/target = null.\n"
    "   - If CONFIRMED_BREAKDOWN:\n"
    "       * entry_price = the close price of the breakdown candle.\n"
    "       * stop_loss = above the most recent swing high (last highest) in the rightmost area.\n"
    "       * risk = stop_loss - entry_price.\n"
    "       * target = entry_price - (2 * risk).\n"
    "       * If a clear nearby support exists BEFORE the target, then trade_decision = \"NO_TRADE\" (RR not achievable) and set stop_loss/target = null.\n"
    "   - Do NOT guess. If entry/SL/target cannot be read/estimated from the chart, set them to null and trade_decision = \"NO_TRADE\".\n\n"
    "5) Market Psychology (Supply/Demand):\n"
    "   - Briefly describe the current buyer vs seller psychology in the latest/rightmost area using supply/demand logic.\n"
    "   - Keep it tied to what is visible (impulsive candles, rejections, stalls, breakdown/breakout attempts).\n"
    "   - Do not add any new levels/drawings; just interpret price action.\n\n"
    "CONFIDENCE (HARD GATE + deterministic rule, 0–10 integer ONLY):\n"
    " - HARD GATE (ALL 3 conditions are REQUIRED):\n"
    "   * If (is_adx_above_20 is not True) OR (tci_cross == \"NONE\") OR\n"
    "     (close_confirmation is NOT \"CONFIRMED_BREAKOUT\" AND is NOT \"CONFIRMED_BREAKDOWN\")\n"
    "     => confidence MUST be 0 (do not score anything, do not clamp to 1..10).\n\n"
    " - If the HARD GATE passes (all 3 are satisfied):\n"
    "   - Start from confidence = 1.\n"
    "   - +3 if is_adx_above_20 is True.\n"
    "   - +2 if tci_cross is CROSSOVER or CROSSUNDER.\n"
    "   - +3 if close_confirmation is CONFIRMED_BREAKOUT or CONFIRMED_BREAKDOWN.\n"
    "   - +1 if rr_ratio is 1:2 AND entry_price/stop_loss/target are all not null.\n"
    "   - Clamp to 0..10.\n\n"
    "Return ONLY a JSON object with these keys:\n"
    "{\n"
    "  \"is_adx_above_20\": boolean | null,\n"
    "  \"adx_val\": number | null,\n"
    "  \"tci_cross\": \"CROSSOVER\" | \"CROSSUNDER\" | \"NONE\",\n"
    "  \"key_level\": number | null,\n"
    "  \"key_level_type\": \"RESISTANCE\" | \"SUPPORT\" | \"NECKLINE\" | \"UNKNOWN\",\n"
    "  \"close_confirmation\": \"CONFIRMED_BREAKOUT\" | \"CONFIRMED_BREAKDOWN\" | \"NO_CONFIRMED_BREAK\" | \"UNKNOWN\",\n"
    "  \"trade_decision\": \"TRADE\" | \"NO_TRADE\",\n"
    "  \"entry_price\": number | null,\n"
    "  \"stop_loss\": number | null,\n"
    "  \"target\": number | null,\n"
    "  \"rr_ratio\": \"1:2\" | \"NOT_1:2\" | \"UNKNOWN\",\n"
    "  \"evidence\": \"Brief: key level + which candle close confirmed break + which swing high/low used for SL + why RR is achievable or not.\",\n"
    "  \"confidence\": integer,\n"
    "  \"reasoning\": \"Step-by-step: (1) ADX value read and whether >20. (2) TCI cross direction. (3) Close-based break confirmation. (4) Entry/SL/Target computed with RR 1:2 only if achievable.\",\n"
    "  \"psychology\": \"Buyer vs seller psychology (supply/demand) for the latest/rightmost area.\"\n"
    "}\n\n"
    "IMPORTANT:\n"
    "- Output JSON only. No extra text.\n"
    "- confidence must be an integer from 0 to 10 ONLY (no decimals).\n"
    "- If anything is unreadable/unclear, use null/UNKNOWN and trade_decision = \"NO_TRADE\" rather than guessing."
),

                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    print(f"GPT Raw Content: {content}")

    if not content:
        raise ValueError("GPT returned empty content")

    content = content.replace("```json", "").replace("```", "").strip()

    return json.loads(content)

def analyze_alignment_context(image_path, primary_analysis, primary_tf="5m", secondary_tf="1h"):
    """
    Analyzes a higher timeframe chart to see if it aligns with the primary timeframe analysis.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    base64_image = encode_image(image_path)
    
    p_decision = primary_analysis.get("trade_decision")
    p_tci = primary_analysis.get("tci_cross")
    p_rsi = primary_analysis.get("rsi_momentum")
    
    print(f"Checking {secondary_tf} Alignment for {primary_tf} {p_decision} setup...")
    
    prompt_text = (
        f"You are a technical analysis expert. \n\n"
        f"CONTEXT (Primary Chart Analysis - {primary_tf}): \n"
        f"- Decision: {p_decision}\n"
        f"- RSI Momentum: {p_rsi}\n"
        f"- TCI: {p_tci}\n\n"
        f"TASK:\n"
        f"Look at this SECONDARY chart ({secondary_tf}). Does this higher timeframe trend/momentum SUPPORT the primary setup above?\n"
        f"1. Check {secondary_tf} RSI (Text labels 'Positive'/'Negative' or Ribbon Color).\n"
        f"2. Check {secondary_tf} Trend Structure (Higher Highs vs Lower Lows).\n"
        f"3. Decide if this timeframe ALIGNS with {primary_tf} (e.g. {primary_tf} Buy + {secondary_tf} Bullish = High Alignment).\n\n"
        f"Return JSON:\n"
        f"{{\n"
        f"  \"alignment_confidence\": integer (0-10),\n"
        f"  \"alignment_analysis\": \"Brief summary of whether {secondary_tf} supports or contradicts the {primary_tf} setup.\"\n"
        f"}}"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are a technical analysis expert. Verify multi-timeframe alignment.",
            },
            {
                "role": "user",
                "content": [
                     {"type": "text", "text": prompt_text},
                     {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                    }
                ]
            }
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    return json.loads(content.replace("```json", "").replace("```", "").strip())

if __name__ == "__main__":

    test_path = "step1_connected.png"
    if os.path.exists(test_path):
        result = analyze_adx(test_path)
        print(json.dumps(result, indent=2))
    else:
        print(f"File {test_path} not found for testing.")
