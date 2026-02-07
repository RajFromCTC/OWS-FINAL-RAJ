import os
import base64
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def analyze_1h_sr(image_path):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    base64_image = encode_image(image_path)

    prompt = (
        "You are a technical analysis expert. Analyze this 1H TradingView chart screenshot.\n\n"
        "TASK:\n"
        "1. Identify the most significant nearest Support and Resistance levels based on price action.\n"
        "2. Note the current price (rightmost value).\n"
        "3. Check for a BREAKOUT (candle BODY closing above resistance) or BREAKDOWN (candle BODY closing below support) on the 1H chart.\n"
        "   - Wicks above resistance or below support do NOT count as breaks.\n"
        "4. Calculate how far the current price is from the identified support and resistance levels.\n\n"
        "Return ONLY a JSON object with these keys:\n"
        "{\n"
        "  \"current_price\": number,\n"
        "  \"support_level\": number,\n"
        "  \"resistance_level\": number,\n"
        "  \"dist_to_support\": number,\n"
        "  \"dist_to_resistance\": number,\n"
        "  \"is_breakout_imminent\": boolean,\n"
        "  \"is_breakdown_imminent\": boolean,\n"
        "  \"status\": \"NORMAL\" | \"BREAKOUT_IMMINENT\" | \"BREAKDOWN_IMMINENT\" | \"BREAKOUT_CONFIRMED\" | \"BREAKDOWN_CONFIRMED\",\n"
        "  \"summary_1h\": \"Short technical summary of 1H price action, mentioning the levels and market context.\"\n"
        "}\n"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a professional trader specializing in Support and Resistance technical analysis."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"},
                    },
                ],
            },
        ],
        response_format={"type": "json_object"},
    )
    
    content = response.choices[0].message.content
    return json.loads(content.replace("```json", "").replace("```", "").strip())

def confirm_5m_break(image_path, sr_context):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    base64_image = encode_image(image_path)

    prompt = (
        f"You are a technical analysis expert. We found potential S/R activity on the 1H chart.\n"
        f"1H CONTEXT: Support={sr_context['support_level']}, Resistance={sr_context['resistance_level']}.\n\n"
        "TASK:\n"
        "Look at this 5-minute chart. Confirm if there is a REAL breakout or breakdown happening CURRENTLY.\n"
        "1. A breakout is confirmed ONLY if a 5m candle BODY closes significantly ABOVE the 1H resistance.\n"
        "2. A breakdown is confirmed ONLY if a 5m candle BODY closes significantly BELOW the 1H support.\n"
        "3. WICKS beyond the levels are FAKEOUTS and must be marked as 'UNCONFIRMED'.\n\n"
        "Return ONLY a JSON object with these keys:\n"
        "{\n"
        "  \"confirmed\": boolean,\n"
        "  \"event_type\": \"BREAKOUT\" | \"BREAKDOWN\" | \"NONE\",\n"
        "  \"reasoning\": \"Detailed explanation. EXPLICITLY state if it was a candle body close or just a wick.\",\n"
        "  \"likely_next_move\": \"What is likely to happen next?\",\n"
        "  \"summary_5m\": \"Short technical summary of 5m confirmation.\"\n"
        "}\n"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a professional trader specializing in multi-timeframe breakout confirmation."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"},
                    },
                ],
            },
        ],
        response_format={"type": "json_object"},
    )
    
    content = response.choices[0].message.content
    return json.loads(content.replace("```json", "").replace("```", "").strip())
