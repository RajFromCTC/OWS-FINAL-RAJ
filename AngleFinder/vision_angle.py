import os
import base64
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def analyze_trend_angle(screenshot_path):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    base64_image = encode_image(screenshot_path)

    prompt = (
        "You are a technical analysis expert looking at a TradingView chart.\n\n"
        "1. Focus on the LATEST (rightmost) indicator on the chart.\n"
        "2. Find the current trend direction/angle following that indicator.\n"
        "3. Evaluate if the trend is positive or negative, and closely estimate its angle based on price action.\n"
        "4. Determine if the trend angle is STEEPER than 60 degrees:\n"
        "   - If it's an UPWARD trend, is the angle greater than +60 degrees?\n"
        "   - If it's a DOWNWARD trend, is the angle steeper/lower than -60 degrees?\n\n"
        "5. Locate the ATR (Average True Range) indicator at the bottom of the chart:\n"
        "   - Read the VERY LATEST (rightmost) numeric value for ATR.\n"
        "   - Determine if the current ATR line is visually ABOVE its recent average/moving average line in the indicator pane.\n\n"
        "Return ONLY a JSON object with:\n"
        "{\n"
        "  \"indicator_detected\": \"Brief description of the latest indicator you see\",\n"
        "  \"trend_direction\": \"UP\" | \"DOWN\" | \"FLAT\",\n"
        "  \"estimated_angle\": \"e.g. +45 degrees, -65 degrees, etc.\",\n"
        "  \"is_above_60\": true | false,\n"
        "  \"atr_value\": number | null,\n"
        "  \"is_atr_above_average\": true | false,\n"
        "  \"reasoning\": \"Step by step: (1) Angle estimation & 60-degree check. (2) ATR value read and average comparison.\",\n"
        "  \"confidence\": integer (0-10)\n"
        "}"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a technical analysis bot."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"}}
                ]
            }
        ],
        response_format={"type": "json_object"}
    )

    content = response.choices[0].message.content.replace("```json", "").replace("```", "").strip()
    return json.loads(content)



def analyze_pullback(screenshot_path):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    base64_image = encode_image(screenshot_path)
  
    prompt = (
        "You are a strict technical analysis expert looking at a TradingView chart with candlestick bodies and wicks explicitly enabled.\n\n"
        "1. Identify the current market sentiment (BULLISH or BEARISH) based on the latest trend.\n"
        "2. Look for a 'Pullback' towards the slow signal line (the EMA):\n"
        "   - **Bullish Pullback**: Look at the latest candles. Does the LOWER WICK dip down and touch (or nearly touch) the EMA line? The gap between the absolute Low of the wick and the EMA MUST be extremely small (visually within 0.1% of the price) or piercing it.\n"
        "   - **Bearish Pullback**: Look at the latest candles. Does the UPPER WICK retrace up and touch (or nearly touch) the EMA line? The gap between the absolute High of the wick and the EMA MUST be extremely small (visually within 0.1% of the price) or piercing it.\n"
        "3. A confident pullback ONLY exists if this strict 0.1% distance or physical physical wipe/touch rule is met.\n"
        "4. Note the approximate current price on the right-side axis.\n\n"
        "Return ONLY a JSON object with:\n"
        "{\n"
        "  \"pullback_detected\": true | false,\n"
        "  \"market_sentiment\": \"BULLISH\" | \"BEARISH\",\n"
        "  \"current_price\": \"numeric value as string\",\n"
        "  \"confidence\": integer (0-10),\n"
        "  \"pullback_reasoning\": \"Explain exactly how close the wick is to the EMA line and whether it strictly passes the 0.1% or physical touch rule.\"\n"
        "}"
    )


    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a technical analysis bot."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"}}
                    ]
                }
            ],
            response_format={"type": "json_object"}
        )
        
        raw_content = response.choices[0].message.content
        
        if raw_content is None:
            print(f"[GPT Error] OpenAI returned empty content! Reason: {response.choices[0].finish_reason}")
            return {"pullback_detected": False, "market_sentiment": "UNKNOWN", "current_price": "0", "confidence": 0, "pullback_reasoning": "OpenAI API returned an empty response."}

        clean_content = raw_content.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_content)

    except Exception as e:
        print(f"[GPT Error] Failed to analyze pullback image: {e}")
        return {"pullback_detected": False, "market_sentiment": "UNKNOWN", "current_price": "0", "confidence": 0, "pullback_reasoning": f"Local script exception: {e}"}
