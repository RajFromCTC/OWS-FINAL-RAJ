import asyncio
import sys
import json
import redis
import os
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from browser_use import Agent

load_dotenv()

r = redis.Redis(host='localhost', port=6379, db=0)
async def run_vision_analysis(ticker, momentum):
 
    llm = ChatOpenAI(model="gpt-4o")
   
    pattern_to_find = "W (Double Bottom)" if momentum == "POSITIVE" else "M (Double Top)"
    action = "BUY" if momentum == "POSITIVE" else "SELL"
    
    task_description = (
        f"1. Go to https://www.tradingview.com/chart/?symbol={ticker}\n"
        f"2. Wait 5 seconds for the candles to load completely.\n"
        f"3. Hide any toolbars or indicator panels that block the main price action if possible.\n"
        f"4. Analyze the most recent price action for a {pattern_to_find} pattern.\n"
        f"5. If a clear {pattern_to_find} is visible and completion/breakout is confirmed, return a 'YES'.\n"
        f"Return ONLY a JSON object: "
        '{"recommendation": "'+action+'", "confidence": 0.0, "reasoning": "text"}'
        f"If no clear pattern is found, return recommendation: 'HOLD'."
    )
    agent = Agent(
        task=task_description,
        llm=llm,
        use_vision=True
    )
 
    history = await agent.run()
    
    
    try:
      
        final_result_str = history.final_result()
       
        clean_json = final_result_str.replace("```json", "").replace("```", "").strip()
        analysis = json.loads(clean_json)
        
        # Decide if we take action
        if analysis.get("recommendation") in ["BUY", "SELL"] and analysis.get("confidence", 0) > 0.7:
            signal = {
                "ticker": ticker,
                "action": analysis["recommendation"],
                "source": "gpt_vision",
                "reason": analysis["reasoning"],
                "confidence": analysis["confidence"],
                "timestamp": sys.time() if hasattr(sys, 'time') else None # simplified
            }
            # Write to Redis for algo_strategy.py to execute
            r.set("strategy:gpt_signal", json.dumps(signal))
            print(f"🚀 SIGNAL GENERATED: {analysis['recommendation']} for {ticker}")
        else:
            print(f"⏸️ No high-confidence pattern found for {ticker}")
    except Exception as e:
        print(f"❌ Error parsing GPT response: {e}")
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python gpt_vision_analyzer.py <ticker> <momentum>")
        sys.exit(1)
    
    ticker_arg = sys.argv[1]
    momentum_arg = sys.argv[2]
    
    asyncio.run(run_vision_analysis(ticker_arg, momentum_arg))