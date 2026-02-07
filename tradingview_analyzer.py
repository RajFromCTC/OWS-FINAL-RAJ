import logging 
import subprocess
import threading
import sys
from pathlib import Path

logger  = logging.getLogger("analyzer")


class TradingViewAnalyzer:
    def __init__(self):
        self.rsi_oversold = 30
        self.rsi_overbought = 70

        self.previous_rsi = None
        self.previous_macd_line = None
        self.previous_macd_signal = None

        self.buy_signal_pending = False
        self.in_position = False
    
    def analyze_gpt_vision(self, data):  
        ticker = data.get("ticker", "UNKNOWN")
        momentum = data.get("momentum", "NONE")

        thread = threading.Thread(
            target=self._run_vision_script, 
            args=(ticker, momentum), 
            daemon=True
        )
        thread.start()

        return {"message": f"Vision analysis started for {ticker}"}

    def _run_vision_script(self, ticker, momentum):
        try:    
            base_dir = Path(__file__).resolve().parent
         
            script_path = base_dir / "browseruse" / "gpt_vision_analyzer.py"
            
            subprocess.run([sys.executable, str(script_path), ticker, momentum], check=True)
            logger.info(f"✅ Vision script finished for {ticker}")
        except Exception as e:
            logger.error(f"❌ Error running vision script: {e}")
            

    def analyze(self,data:dict)-> dict:

        ticker = data.get("ticker",'UNKNOWN')
        rsi = data.get('rsi')
        macd_line = data.get('macd_line')
        macd_signal = data.get('macd_signal')

        decision = {
            'action':'hold',
            'side':None,
            'reason':'No signal'
        }
        macd_bullish = False

        if self.previous_rsi is not None and self.previous_rsi < 30 and rsi >= 30:
            self.buy_signal_pending = True
            logger.info("📈 RSI BUY SIGNAL: Crossed above 30")
        
        if self.previous_macd_line is not None and self.previous_macd_signal is not None and self.previous_macd_line < self.previous_macd_signal and macd_line > macd_signal:
            macd_bullish = True
            logger.info("✅ MACD BULLISH CROSSOVER!")
        
        if self.buy_signal_pending and macd_bullish and not self.in_position :
            decision = {
            'action': 'buy',
            'side': 'LONG',
            'reason': 'RSI + MACD bullish confirmation'
            }
            self.buy_signal_pending = False
            self.in_position = True
            logger.info("🚀 DECISION: BUY LONG")
        
        self.previous_rsi = rsi
        self.previous_macd_line = macd_line
        self.previous_macd_signal = macd_signal

        return decision
        
            

        

            