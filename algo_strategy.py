import threading
import logging
import sys
import time
import redis
import json
from pprint import pprint
from datetime import datetime, timedelta
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from kite_bms import KiteTrader
from utils.redis_config import RedisConfigReader
from utils.redis_utils import update_strategy_status, update_trading_status , update_strategy_action

logger = logging.getLogger("root")
r = redis.Redis(host='localhost', port=6379, db=0)
class StraddleVWAPUpdater:

    last_straddle_price = None
    last_vwap_straddle  = None
    ready_to_execute = False
    index_history    = deque()
    straddle_history = deque()

    def __init__(self, kite_client=None, symbol=None, expiry_date=None, strike_step=None, redis_config=None):
        self.kite = kite_client
        self.symbol = symbol
        self.index_token = '256265' if self.symbol == "NIFTY" else '265'
        self.exchange_options = "NFO" if self.symbol == "NIFTY" else "BFO"
        self.expiry_str = expiry_date
        self.strike_interval = strike_step
        
        logger.info(f"[{self.symbol}] Initializing StraddleVWAPUpdater with Redis config...")
        logger.info(f"Config: Symbol={self.symbol}, Expiry={self.expiry_str}, Strike Interval={self.strike_interval}")

        self.cum_pv = 0.0
        self.cum_vol = 0.0
        self.last_ts = None

    def _get_option_minute_data(self, ts: datetime, strike: int, opt_type: str):
            trading_symbol = f"{self.symbol}{self.expiry_str}{strike}{opt_type}"
            full_symbol = f"{self.exchange_options}:{trading_symbol}"

            from_dt = ts
            to_dt = ts + timedelta(minutes=1)

            logger.info(f"Fetching {opt_type} minute data for {full_symbol} @ {ts}")
            try:
                candles = self.kite.historical_data(
                    instrument_token=self.kite.ltp(full_symbol)[full_symbol]["instrument_token"],
                    interval="minute",
                    from_date=from_dt,
                    to_date=to_dt
                )
                logger.info(f"Fetched {len(candles)} candles for {full_symbol}")
            except Exception as e:
                logger.error(f"Could not fetch historical for {full_symbol} @ {ts}: {e}")
                raise KeyError(f"Could not fetch historical for {full_symbol} @ {ts}: {e}")

            if not candles:
                logger.error(f"No 1-minute candle for {full_symbol} at {ts}")
                raise KeyError(f"No 1-minute candle for {full_symbol} at {ts}")

            bar = candles[0]
            close_price = float(bar["close"])
            volume = float(bar["volume"])

            return close_price, volume

    def _round_to_atm(self, price: float) -> int:
        """Round 'price' to nearest multiple of strike_interval."""
        return int(round(price / self.strike_interval) * self.strike_interval)

    def run_forever(self, stop_event):
        today = datetime.now().date()
        market_open = datetime.combine(today, datetime.min.time()).replace(hour=9, minute=15)
        while not stop_event.is_set():
            now = datetime.now().replace(second=0, microsecond=0)
            if self.last_ts is None:
                if now < market_open:
                    print(f"[{now.strftime('%H:%M')}] Market not open until 09:15. Sleeping…")
                    self.last_ts = now 
                else:
                    try:
                        logger.info(f"[DEBUG] Fetching historical candles from {market_open} to {now}")
                        candles = self.kite.historical_data(
                            instrument_token=self.index_token,
                            interval="minute",
                            from_date=market_open,
                            to_date=now
                        )
                        logger.info(candles)
                    except Exception as e:
                        logger.error(f"[ERROR] Could not fetch historical candles: {e}")
                        candles = []

                    for bar in candles:
                        if stop_event.is_set():
                            break
                        ts = bar["date"].replace(tzinfo=None, second=0, microsecond=0)
                        idx_close = float(bar['close'])
                        logger.info(f"[DEBUG] Processing bar: {ts} Close: {idx_close}")
                        StraddleVWAPUpdater.index_history.append((ts, idx_close))
                        atm_strike = self._round_to_atm(idx_close)
                        print('[DEBUG] Processing bar:', ts, 'Close:', idx_close, 'ATM Strike:', atm_strike)
                        try:
                            with ThreadPoolExecutor(max_workers=2) as executor:
                                future_call = executor.submit(
                                    self._get_option_minute_data, ts, atm_strike, "CE"
                                )
                                future_put = executor.submit(
                                    self._get_option_minute_data, ts, atm_strike, "PE"
                                )

                                try:
                                    call_ltp, call_vol = future_call.result()
                                    put_ltp, put_vol   = future_put.result()
                                except Exception:
                                    logger.error(f"Could not fetch option data for {ts} at strike {atm_strike}")
                                    continue

                                logger.info(f'Call LTP: {call_ltp}, Volume: {call_vol}')
                                logger.info(f'Put LTP: {put_ltp}, Volume: {put_vol}')
                        except Exception:
                            continue

                        straddle_price  = call_ltp + put_ltp
                        StraddleVWAPUpdater.straddle_history.append((ts, straddle_price))
                        straddle_volume = call_vol + put_vol
                        print('[DEBUG] Straddle Price:', straddle_price, 'Volume:', straddle_volume)
                        self.cum_pv  += straddle_price * straddle_volume
                        self.cum_vol += straddle_volume

                        StraddleVWAPUpdater.last_straddle_price = straddle_price

                    if self.cum_vol > 0:
                        vwap_straddle = self.cum_pv / self.cum_vol
                    else:
                        vwap_straddle = float('nan')

                    if StraddleVWAPUpdater.last_straddle_price is not None:
                        print(
                            f"[{now.strftime('%H:%M')}] "
                            f"StraddlePrice={StraddleVWAPUpdater.last_straddle_price:.2f} | "
                            f"VWAP_straddle={vwap_straddle:.2f}"
                        )

                    StraddleVWAPUpdater.last_vwap_straddle  = vwap_straddle
                    self.last_ts = now
                    print(f"[DEBUG] Last timestamp updated to {self.last_ts}")
                    StraddleVWAPUpdater.ready_to_execute = True

            else:
                logger.info(f"[DEBUG] Last TS: {self.last_ts}")
                if now <= self.last_ts or now <= market_open:
                    logger.info(f"[DEBUG] Current time {now} is less than or equal to last timestamp or market open {self.last_ts}.")
                    self.last_ts = now
                    pass
                else:
                    try:
                        print("[DEBUG] Fetching incremental candles from", self.last_ts, "to", now)
                        new_candles = self.kite.historical_data(
                            instrument_token=self.index_token,
                            interval="minute",
                            from_date=self.last_ts,
                            to_date=now
                        )
                    except Exception as e:
                        print(f"[ERROR] Could not fetch incremental candles: {e}")
                        new_candles = []

                    for bar in new_candles:
                        print(f"[DEBUG] Processing new bar: {bar['date']}")
                        pprint(bar)
                        ts = bar["date"].replace(tzinfo=None, second=0, microsecond=0)
                        idx_close = float(bar['close'])

                        atm_strike = self._round_to_atm(idx_close)
                        try:
                            call_ltp, call_vol = self._get_option_minute_data(ts, atm_strike, 'CE')
                            put_ltp, put_vol   = self._get_option_minute_data(ts, atm_strike, 'PE')
                        except Exception:
                            continue

                        straddle_price  = call_ltp + put_ltp
                        straddle_volume = call_vol + put_vol

                        self.cum_pv  += straddle_price * straddle_volume
                        self.cum_vol += straddle_volume

                        StraddleVWAPUpdater.last_straddle_price = straddle_price
                        self.last_ts             = ts + timedelta(minutes=1)

                    if self.cum_vol > 0:
                        vwap_straddle = self.cum_pv / self.cum_vol
                    else:
                        vwap_straddle = float('nan')

                    if StraddleVWAPUpdater.last_straddle_price is not None:
                        print(
                            f"[{self.last_ts.strftime('%H:%M')}] "
                            f"StraddlePrice={StraddleVWAPUpdater.last_straddle_price:.2f} | "
                            f"VWAP_straddle={vwap_straddle:.2f}"
                        )
                        StraddleVWAPUpdater.index_history.append((ts, idx_close))
                        StraddleVWAPUpdater.straddle_history.append((ts, straddle_price))
                        StraddleVWAPUpdater.last_straddle_price = StraddleVWAPUpdater.last_straddle_price
                        StraddleVWAPUpdater.last_vwap_straddle  = vwap_straddle
                        StraddleVWAPUpdater.ready_to_execute = True

            sleep_target = (datetime.now() + timedelta(minutes=1)).replace(second=0, microsecond=0)
            sleep_secs   = (sleep_target - datetime.now()).total_seconds()
            if sleep_secs > 0:
                time.sleep(sleep_secs)
            else:
                time.sleep(1)
                continue
class AlgoStrategy(KiteTrader):

    def __init__(self):
        super().__init__()
        self.day_pnl = 0.0

    def start_algo_class(self,kite_client, symbol, redis_config=None):
        self.exit_signal     = threading.Event()
        self.exit_in_progress = False

        logger.info(f"[{symbol}] Initializing AlgoStrategy...")
        self.kite = kite_client
        self.symbol = symbol
        self.lot_size = 75 if symbol == "NIFTY" else 20
        self.redis_config = redis_config or RedisConfigReader()
        config = self.redis_config.get_all_config()

        self.batman_active   = False
        self.debit_spread_active = False
        self.highest_mtm     = 0
        self.batman_positions = {}  # { tradingsymbol: {'quantity': int, 'avg_price': float} }
        self.batman_closed_pnls = []  # List to store closed PnLs for batman trades
        self.debit_spread_positions = {}  # { tradingsymbol: {'quantity': int, 'avg_price': float} }
        self.debit_spread_closed_pnls = []  # List to store closed PnLs for debit spread trades

        self.redis_client = r
        self.last_action = "Initialized"
        self.action_count = 0
        
        self.exchange = "NSE" if symbol == "NIFTY" else "BSE"
        self.exchange_options = "NFO" if self.symbol == "NIFTY" else "BFO"
        self.expiry_date = config.get('expiry')
        self.open_range_min = int(config.get('PivotRangeMinutes', 15))
        self.shift_threshold = int(config.get('ShiftThresholdPts', 50))
        self.straddle_gap_pct = float(config.get('StraddleGapPct', 1)) / 100.0
        self.hedge_gap_pct = float(config.get('HedgeGapPct', 2.5)) / 100.0
        self.strike_step = 50 if symbol == "NIFTY" else 100
        self.order_buffer_pct = float(config.get('OrderBufferPct', 0.3)) / 100.0
        self.fill_timeout_sec = int(config.get('FillTimeoutSec', 5))
        self.rms_cap = float(config.get('RmsCap', -100000))
        self.quantity = int(config.get('Quantity', 75))
        self.qty_hedge_ratio = float(config.get('QtyHedgeRatio', 1.0))
        self.sl_buffer_pct = float(config.get('StopLossBufferPct', 1.0)) / 100.0
        self.target_pnl = float(config.get('TargetPnl', 1000.0))
        self.exit_pnl = float(config.get('ExitPnl', -500.0))
        self.rolling_value = float(config.get('RollingValue', 100.0))
        self.trail_stop_loss = config.get('TrailStopLossToggle', True)
        self.product_type = config.get('ProductType', 'MIS')

        logger.info(f"AlgoStrategy initialized with Redis config: {config}")
        logger.info(f"Key Parameters - Quantity: {self.quantity}, QtyHedgeRatio: {self.qty_hedge_ratio}, Target PnL: {self.target_pnl}, Exit PnL: {self.exit_pnl}")

        update_strategy_action(self.redis_client, "Initialized AlgoStrategy", {"config": config})
        update_strategy_status(self.redis_client, "starting", "Initializing straddle VWAP updater...")
        self._generate_straddle_vwap()
        self.start_mtm_monitor()

        update_strategy_status(self.redis_client, "running", "Waiting for StraddleVWAPUpdater to be ready...")
        while True:
            logger.info(f"[{self.symbol}] Waiting for StraddleVWAPUpdater to be ready...")
            if StraddleVWAPUpdater.ready_to_execute:
                break
            if self.exit_signal.is_set():
                logger.info(f"[{self.symbol}] Exit signal received while waiting for StraddleVWAPUpdater. Exiting...")
                return
            time.sleep(1)

        logger.info(f"[{self.symbol}] StraddleVWAPUpdater is ready. Proceeding with strategy initialization...")
        logger.info(f"[{self.symbol}] Straddle Price: {StraddleVWAPUpdater.last_straddle_price:.2f} | "
                    f"VWAP: {StraddleVWAPUpdater.last_vwap_straddle:.2f}")
        
        update_strategy_status(self.redis_client, "running", 
                             f"Strategy ready - Straddle: {StraddleVWAPUpdater.last_straddle_price:.2f}, VWAP: {StraddleVWAPUpdater.last_vwap_straddle:.2f}")

        self.strategy_main() 

    def _generate_straddle_vwap(self):
        logger.info(f"[{self.symbol}] Starting straddle VWAP generation thread...")
        update_strategy_action(self.redis_client, "Starting straddle VWAP generation", 
                             {"expiry": self.expiry_date, "strike_step": self.strike_step})
        
        self.straddle_updater = StraddleVWAPUpdater(self.kite, self.symbol, self.expiry_date,self.strike_step,self.redis_config)
        t = threading.Thread(target=self.straddle_updater.run_forever, args=(self.exit_signal,), daemon=True )
        t.start()
        
        logger.info(f"[{self.symbol}] Straddle VWAP thread started successfully")

    def _round_to_atm(self, price: float) -> int:
        """Round 'price' to nearest multiple of strike_interval."""
        return int(round(price / self.strike_step) * self.strike_step)

    def strategy_main(self):
        logger.info(f"[{self.symbol}] Starting main strategy loop (rolling OR={self.open_range_min}m)...")
        update_strategy_action(self.redis_client, "Starting main strategy loop")

        self.pivot_base = None
        # now = datetime.now()
        # time.sleep(60 - now.second)

        while not self.exit_signal.is_set():
            now = datetime.now()
            if now.second != 0:
                time.sleep(1)
                continue
            time.sleep(2)
            now = datetime.now().replace(second=0, microsecond=0)

            hist = StraddleVWAPUpdater.straddle_history
            logger.info(f"[{now:%H:%M}] Checking straddle history (len={len(hist)})...")
            
            if len(hist) < self.open_range_min:
                logger.info(f"Need {self.open_range_min} straddle data points (have {len(hist)})")
                update_strategy_action(self.redis_client, f"Waiting for data - have {len(hist)}/{self.open_range_min} points")
            else:
                last_straddle = hist[-1][1]
                last_vwap     = StraddleVWAPUpdater.last_vwap_straddle
                last_idx      = StraddleVWAPUpdater.index_history[-1][1]

                logger.info(
                    f"[{now:%H:%M}] Straddle={last_straddle:.2f} | VWAP={last_vwap:.2f} | Index={last_idx:.2f}"
                )
                
                update_trading_status(self.redis_client, self.symbol, straddle_price=last_straddle, vwap=last_vwap)
                update_strategy_action(self.redis_client, f"Monitoring: Straddle={last_straddle:.2f}, VWAP={last_vwap:.2f}")

                hist_list = list(hist)
                open_range_straddles = [s[1] for s in hist_list[-self.open_range_min:]]
                hh = max(open_range_straddles)
                ll = min(open_range_straddles)

                update_strategy_action(self.redis_client, f"Range analysis: High={hh:.2f}, Low={ll:.2f}")

                logger.info(f"Straddle Range High={hh:.2f} | Low={ll:.2f}")

                if ((last_straddle > last_vwap ) and (not self.debit_spread_active) and (not self.batman_active) and (not self.exit_in_progress)): 
                    update_strategy_action(self.redis_client, f"Straddle > Vwap")
                    logger.info(" Straddle > VWAP → checking for OR break")
                    cutoff = now - timedelta(minutes=self.open_range_min)
                    logger.info(
                        f" Rolling OR cutoff: {cutoff:%H:%M} (last {self.open_range_min}m)"
                    )
                    
                    recent_index = [
                            price for ts, price in StraddleVWAPUpdater.index_history
                            if ts >= cutoff
                        ]
               
                    if len(recent_index) < 2:
                        logger.info(
                            f" Not enough index data points in the last {self.open_range_min}m"
                        )
                        continue
                    indexHH = max(recent_index)
                    indexLL = min(recent_index)
                    logger.info(
                        f" RollingOR( last {self.open_range_min}m ) → HH={indexHH:.2f}, LL={indexLL:.2f}"
                    )
                    update_strategy_action(self.redis_client, f"Rolling Index : HH={indexHH:.2f}, LL={indexLL:.2f}")

                    # Debit CE if index breaks above high of index
                    if last_idx >= indexHH :
                        logger.info(" OR break above & Straddle>VWAP → CE debit")
                        update_strategy_action(self.redis_client, "OR Break Above & Straddle > VWAP → CE Debit")
                        self._execute_debit_spread("LONG")
                        self.debit_spread_active = True
                        self.swing_sl = ll    #Straddle Lower Low
                        logger.info(f" Swing SL set to {self.swing_sl:.2f} (Straddle LL)")
                        update_strategy_action(self.redis_client, "Debit Spread Active", 
                                             {"side": "LONG", "swing_sl": self.swing_sl, "straddle": last_straddle, "index": last_idx})

                    # Debit PE if index breaks below low of index
                    elif last_idx <= indexLL:
                        logger.info(" OR break below & Straddle>VWAP → PE debit")
                        update_strategy_action(self.redis_client, "OR Break Below & Straddle > VWAP → PE Debit")
                        self._execute_debit_spread("SHORT")
                        self.debit_spread_active = True
                        self.swing_sl = ll   #Straddle Lower Low
                        logger.info(f" Swing SL set to {self.swing_sl:.2f} (Straddle LL)")
                        update_strategy_action(self.redis_client, "Debit Spread Active", 
                                             {"side": "SHORT", "swing_sl": self.swing_sl, "straddle": last_straddle, "index": last_idx})

                # # 4) Stop-loss for Debit Spread
                if (self.debit_spread_active and (self.swing_sl is not None) and (not self.exit_in_progress)):
                    logger.info(
                        f" Checking Debit Spread SL: {self.swing_sl:.2f} (last straddle: {last_straddle:.2f})"
                    )
                    update_strategy_action(self.redis_client, "Checking Debit Spread SL", 
                                         {"swing_sl": self.swing_sl, "last_straddle": last_straddle})
                    if last_straddle <= self.swing_sl:
                        logger.info(
                            f" Straddle {last_straddle:.2f} ≤ swing_sl {self.swing_sl:.2f} → exiting debit"
                        )
                        update_strategy_status(self.redis_client, "running", 
                                             f"DEBIT SPREAD STOP LOSS HIT: Straddle {last_straddle:.2f} ≤ SL {self.swing_sl:.2f}")
                        self._exit_debit_spread_positions()
                        self.debit_spread_active = False

                # # 5) Trailing SL on new HH in straddle
                if self.debit_spread_active:
                    if not hasattr(self, "_hh_peak"):
                        self._hh_peak = last_straddle
                    if last_straddle > self._hh_peak:
                        self._hh_peak = last_straddle
                        old_sl = self.swing_sl
                        self.swing_sl = self._hh_peak * (1 - self.sl_buffer_pct)
                        logger.info(
                            f" New HH {self._hh_peak:.2f} → trailed SL {old_sl:.2f}→{self.swing_sl:.2f}"
                        )
                        update_strategy_action(self.redis_client, "Debit spread Trailing SL Updated", 
                                             {"old_sl": old_sl, "new_sl": self.swing_sl, "hh_peak": self._hh_peak})

                # 6) Batman Spread entry/shift
                if ((last_straddle <= ll) and (not self.batman_active) and (not self.debit_spread_active) and (not self.exit_in_progress)):
                    logger.info(" Straddle<LL → entering Batman Spread")
                    update_strategy_status(self.redis_client, "running", 
                                         f"BATMAN ENTRY: Straddle {last_straddle:.2f} <= LL {ll:.2f}")
                    update_strategy_action(self.redis_client, "Executing Batman Spread Entry", 
                                         {"straddle": last_straddle, "lower_limit": ll, "index": last_idx})
                    
                    self._execute_batman_spread()
                    self.batman_active = True
                    self.pivot_base = last_idx
                    self.batman_sl = hh
                    
                    update_strategy_status(self.redis_client, "running", 
                                         f"BATMAN ACTIVE: Pivot={self.pivot_base:.2f}, SL={self.batman_sl:.2f}")

                # If Batman active, check for SL
                if self.batman_active and self.batman_sl is not None and (not self.exit_in_progress):
                    logger.info(
                        f" Checking Batman SL: {self.batman_sl:.2f} (last straddle: {last_straddle:.2f})"
                    )
                    if last_straddle >= self.batman_sl:
                        logger.warning(
                            f" Straddle {last_straddle:.2f} ≥ SL {self.batman_sl:.2f} → exiting Batman"
                        )
                        update_strategy_status(self.redis_client, "running", 
                                             f"BATMAN STOP LOSS: Straddle {last_straddle:.2f} >= SL {self.batman_sl:.2f}")
                        update_strategy_action(self.redis_client, "Batman Stop Loss Triggered", 
                                             {"straddle": last_straddle, "stop_loss": self.batman_sl})
                        
                        self._exit_batman_positions()
                        self.batman_active = False
                        self.pivot_base = None
                        
                        update_strategy_status(self.redis_client, "running", "Batman positions exited due to stop loss")

                # Shift existing Batman if index moves N pts away from pivot_base
                if self.batman_active and self.pivot_base is not None and (not self.exit_in_progress):
                    index_move = abs(last_idx - self.pivot_base)
                    if index_move >= self.shift_threshold :
                        logger.info(
                            f" Index moved {last_idx-self.pivot_base:.0f} pts ≥ "
                            f"{self.shift_threshold} → shifting Batman legs"
                        )
                        update_strategy_status(self.redis_client, "running", 
                                             f"BATMAN SHIFT: Index moved {index_move:.0f} pts from pivot {self.pivot_base:.2f}")
                        update_strategy_action(self.redis_client, "Shifting Batman Positions", 
                                             {"index_move": index_move, "old_pivot": self.pivot_base, "new_pivot": last_idx})
                        
                        self._exit_batman_positions()
                        self._execute_batman_spread()
                        self.pivot_base = last_idx
                        
                        update_strategy_status(self.redis_client, "running", 
                                             f"Batman positions shifted to new pivot: {self.pivot_base:.2f}")

            time.sleep(1)

    def _execute_debit_spread(self, side):
        underlying = StraddleVWAPUpdater.index_history[-1][1]  # Last index price
        atm_strike = self._round_to_atm(underlying)
        q = self.quantity

        logger.info(f"[{self.symbol}] Executing DEBIT SPREAD - {side}")
        update_strategy_status(self.redis_client, "running", f"Executing {side} debit spread")
        
        if side == "LONG":
            option_type = "CE"
            otm_strike = atm_strike + self.strike_step
        elif side == "SHORT":
            option_type = "PE"
            otm_strike = atm_strike - self.strike_step
        else:
            logger.error(f"Invalid side specified for debit spread: {side}")
            update_strategy_status(self.redis_client, "error", f"Invalid debit spread side: {side}")
            return

        atm_option = f"{self.symbol}{self.expiry_date}{atm_strike}{option_type}"
        otm_option = f"{self.symbol}{self.expiry_date}{otm_strike}{option_type}"

        logger.info(f"[{self.symbol}] DEBIT SPREAD ORDERS: BUY {atm_option} qty={q}, SELL {otm_option} qty={q}")
        update_strategy_action(self.redis_client, f"Debit Spread Orders - {side}", 
                             {"buy_leg": atm_option, "sell_leg": otm_option, "quantity": q, "underlying": underlying})

        buy_id = self._place_order_with_fallback(atm_option, self.kite.TRANSACTION_TYPE_BUY, q, "DEBIT_SPREAD")
        sell_id = self._place_order_with_fallback(otm_option, self.kite.TRANSACTION_TYPE_SELL, q, "DEBIT_SPREAD")
        
        if buy_id and sell_id:
            update_strategy_status(self.redis_client, "running", f"{side} debit spread orders placed successfully")
        else:
            update_strategy_status(self.redis_client, "error", f"Failed to place {side} debit spread orders")
  
    def _exit_debit_spread_positions(self):
        logger.info(f"[{self.symbol}] Exiting all Debit Spread positions...")
        update_strategy_status(self.redis_client, "running", "Exiting all Debit Spread positions")
        
        positions_to_exit = len(self.debit_spread_positions)
        update_strategy_action(self.redis_client, "Debit Spread Position Exit Started", 
                             {"positions_count": positions_to_exit})
        
        exit_count = 0
        logger.info(f"[{self.symbol}] Total Debit Spread positions to exit: {positions_to_exit}")
        for symbol, pos in self.debit_spread_positions.copy().items():
            if pos['quantity'] < 0:
                logger.info(f"[{self.symbol}] Closing Debit Spread SELL position: {symbol} quantity={pos['quantity']}")
                close_id = self._place_order_with_fallback(
                    symbol, self.kite.TRANSACTION_TYPE_BUY, abs(pos['quantity']), "DEBIT_SPREAD"
                )
                if close_id:
                    exit_count += 1
                    update_strategy_action(self.redis_client, "Debit Spread Sell Position Closed", 
                                {"symbol": symbol, "quantity": pos['quantity'], "order_id": close_id})
            elif pos['quantity'] > 0:
                logger.info(f"[{self.symbol}] Closing Debit Spread BUY position: {symbol} quantity={pos['quantity']}")
                close_id = self._place_order_with_fallback(
                    symbol, self.kite.TRANSACTION_TYPE_SELL, pos['quantity'], "DEBIT_SPREAD"
                )
                if close_id:
                    exit_count += 1
                    update_strategy_action(self.redis_client, "Debit Spread Buy Position Closed", 
                                {"symbol": symbol, "quantity": pos['quantity'], "order_id": close_id})

        current_mtm = self._calculate_current_mtm()
        self.day_pnl = self.day_pnl + current_mtm         
        self.debit_spread_positions.clear()
        self.debit_spread_closed_pnls.clear()
        self.highest_mtm = 0     
        logger.info(f"[{self.symbol}] All Debit Spread positions exited successfully.")
        update_strategy_status(self.redis_client, "running", f"Debit Spread positions exited: {exit_count}/{positions_to_exit} orders placed")


    def _execute_batman_spread(self):
        """
        1. Sell CE & PE at ±StraddleGapPct
        2. Buy hedge‐legs at ±HedgeGapPct
        3. Record all legs in self.positions
        4. Set initial SL = previous swing high (± buffer if trailing)
        """
        underlying = StraddleVWAPUpdater.index_history[-1][1]  # Last index price
        ce_strike = round(underlying * (1 + self.straddle_gap_pct) / self.strike_step) * self.strike_step
        pe_strike = round(underlying * (1 - self.straddle_gap_pct) / self.strike_step) * self.strike_step
        ce_hedge  = round(underlying * (1 + self.hedge_gap_pct) / self.strike_step) * self.strike_step
        pe_hedge  = round(underlying * (1 - self.hedge_gap_pct) / self.strike_step) * self.strike_step
        q = self.quantity

        logger.info(f"[{self.symbol}] Executing BATMAN SPREAD at underlying {underlying:.2f}")
        update_strategy_status(self.redis_client, "running", "Executing Batman Spread")
        
        batman_details = {
            "underlying": underlying,
            "ce_strike": ce_strike,
            "pe_strike": pe_strike,
            "ce_hedge": ce_hedge,
            "pe_hedge": pe_hedge,
            "quantity": q,
            "straddle_gap_pct": self.straddle_gap_pct * 100,
            "hedge_gap_pct": self.hedge_gap_pct * 100
        }
        
        update_strategy_action(self.redis_client, "Batman Spread Execution", batman_details)
        logger.info(f"[{self.symbol}] BATMAN DETAILS: {batman_details}")
        for strike, opt_type in ((ce_strike, "CE"), (pe_strike, "PE")):
            sym = f"{self.symbol}{self.expiry_date}{strike}{opt_type}" #main sell strike
            if opt_type == "CE":
                sym_hedge = f"{self.symbol}{self.expiry_date}{ce_hedge}{opt_type}"
            elif opt_type == "PE":
                sym_hedge = f"{self.symbol}{self.expiry_date}{pe_hedge}{opt_type}"

            key_main = f"{self.exchange_options}:{sym}"
            key_hedge = f"{self.exchange_options}:{sym_hedge}"

            ltp_main = self.kite.ltp(key_main)[key_main]["last_price"]
            ltp_hedge = self.kite.ltp(key_hedge)[key_hedge]["last_price"]

            if self.qty_hedge_ratio != 1:
                hedge_qty = round(((q * ltp_main) * self.qty_hedge_ratio) / ltp_hedge / self.lot_size) * self.lot_size
            else:
                hedge_qty = q

            logger.info(f"[{self.symbol}] BATMAN BUY: {sym_hedge} qty={hedge_qty} at strike {ce_hedge if opt_type == 'CE' else pe_hedge}")
            buy_id = self._place_order_with_fallback(sym_hedge, self.kite.TRANSACTION_TYPE_BUY, hedge_qty, "BATMAN")
            if buy_id:
                update_strategy_action(self.redis_client, f"Batman Buy Order Placed", 
                                     {"symbol": sym_hedge, "quantity": hedge_qty, "order_id": buy_id})

                logger.info(f"[{self.symbol}] BATMAN SELL: {sym} qty={q} at strike {strike}")
                sell_id = self._place_order_with_fallback(sym, self.kite.TRANSACTION_TYPE_SELL, q, "BATMAN")
                if sell_id:
                    update_strategy_action(self.redis_client, f"Batman Sell Order Placed", 
                                        {"symbol": sym, "quantity": q, "order_id": sell_id})
        
        update_strategy_status(self.redis_client, "running", "Batman Spread orders placed successfully")
    
    def _exit_batman_positions(self):
        """
        Exits all Batman positions by closing each leg.
        """
        logger.info(f"[{self.symbol}] Exiting all Batman positions...")
        update_strategy_status(self.redis_client, "running", "Exiting all Batman positions")
        
        positions_to_exit = len(self.batman_positions)
        update_strategy_action(self.redis_client, "Batman Position Exit Started", 
                             {"positions_count": positions_to_exit})
        
        exit_count = 0
        logger.info(f"[{self.symbol}] Total BATMAN positions to exit: {positions_to_exit}")
        # Close all SELL positions first
        for symbol, pos in self.batman_positions.copy().items():
            if pos['quantity'] < 0:
                logger.info(f"[{self.symbol}] Closing BATMAN SELL position: {symbol} quantity={pos['quantity']}")
                close_id = self._place_order_with_fallback(
                    symbol, self.kite.TRANSACTION_TYPE_BUY, abs(pos['quantity']), "BATMAN"
                )
                if close_id:
                    exit_count += 1
                    update_strategy_action(self.redis_client, "Batman Sell Position Closed", 
                        {"symbol": symbol, "quantity": pos['quantity'], "order_id": close_id})

        # Close all BUY positions next
        for symbol, pos in self.batman_positions.copy().items():
            if pos['quantity'] > 0:
                logger.info(f"[{self.symbol}] Closing BATMAN BUY position: {symbol} quantity={pos['quantity']}")
                close_id = self._place_order_with_fallback(
                    symbol, self.kite.TRANSACTION_TYPE_SELL, pos['quantity'], "BATMAN"
                )
                if close_id:
                    exit_count += 1
                    update_strategy_action(self.redis_client, "Batman Buy Position Closed", 
                        {"symbol": symbol, "quantity": pos['quantity'], "order_id": close_id})

        current_mtm = self._calculate_current_mtm()
        self.day_pnl = self.day_pnl + current_mtm     
        self.batman_positions.clear()
        self.batman_closed_pnls.clear()
        self.highest_mtm = 0
        logger.info(f"[{self.symbol}] All Batman positions exited successfully.")
        update_strategy_status(self.redis_client, "running", f"Batman positions exited: {exit_count}/{positions_to_exit} orders placed")
    
    def start_mtm_monitor(self):
        """Start MTM monitoring in a separate thread"""
        logger.info(f"[{self.symbol}] Starting MTM monitor...")
        update_strategy_action(self.redis_client, "Starting MTM Monitor")
        
        self.mtm_thread = threading.Thread(target=self._mtm_monitor_loop, daemon=True)
        self.mtm_thread.start()
        logger.info(f"[{self.symbol}] MTM monitor started")
    
    def _mtm_monitor_loop(self):
        """Background thread to monitor MTM and update status"""
        logger.info(f"[{self.symbol}] Starting MTM monitor loop...")
        update_strategy_action(self.redis_client, "MTM Monitor Loop Started")
        is_in_exit_process = False
        while not self.exit_signal.is_set():
            try:
                if is_in_exit_process:
                    time.sleep(5)
                    continue

                current_mtm = self._calculate_current_mtm()
                self.current_mtm = current_mtm
                update_strategy_action(self.redis_client, f"Day PnL {self.day_pnl:.2f}")
                if current_mtm > self.highest_mtm:
                    self.highest_mtm = current_mtm

                if self.trail_stop_loss and self.highest_mtm > 0:
                    update_trading_status(self.redis_client, self.symbol, exit_pnl=(self.highest_mtm - self.rolling_value))
                else:
                    logger.info(f"[{self.symbol}] Current MTM: {current_mtm:.2f}, Target PnL: {self.target_pnl:.2f}, Exit PnL: {self.exit_pnl:.2f}, Highest MTM: {self.highest_mtm:.2f}")
                    update_trading_status(self.redis_client, self.symbol, exit_pnl=self.exit_pnl)

                if current_mtm >= self.target_pnl:
                    logger.info(f"[{self.symbol}] Target PnL reached! MTM: {current_mtm:.2f} >= Target: {self.target_pnl:.2f}")
                    is_in_exit_process = True
                    self.exit_all_positions()
                    self.stop()

                elif current_mtm <= self.exit_pnl:
                    logger.info(f"[{self.symbol}] Exit PnL breached! MTM: {current_mtm:.2f} <= Exit PnL: {self.exit_pnl:.2f}")
                    is_in_exit_process = True
                    self.exit_all_positions()
                    self.stop()

                elif self.trail_stop_loss and self.highest_mtm > 0:
                    if current_mtm <= self.highest_mtm - self.rolling_value:
                        logger.info(f"[{self.symbol}] Trailing stop triggered! MTM: {current_mtm:.2f} < Highest MTM - Rolling Value: {self.highest_mtm - self.rolling_value:.2f}")
                        is_in_exit_process = True
                        self.exit_all_positions()
                        self.stop()

                elif (current_mtm + self.day_pnl) <= self.rms_cap:
                    logger.info(f"[{self.symbol}] RMS Cap breached! MTM: {current_mtm:.2f} + Day PnL: {self.day_pnl:.2f} <= Cap: {self.rms_cap:.2f}")
                    is_in_exit_process = True
                    update_strategy_status(self.redis_client, "running", 
                                         f"RMS Cap breached: MTM {current_mtm:.2f} + Day PnL {self.day_pnl:.2f} <= Cap {self.rms_cap:.2f}")
                    update_strategy_action(self.redis_client, "RMS Cap Breached - Emergency Stop", 
                                         {"current_mtm": current_mtm, "rms_cap": self.rms_cap})
                    self.exit_all_positions()
                    self.stop()

                time.sleep(3)

            except Exception as e:
                logger.error(f"[{self.symbol}] MTM monitor error: {e}")
                update_strategy_status(self.redis_client, "error", f"MTM monitor error: {str(e)}")
                time.sleep(30)
    
    def _check_exit_all_signal(self):
        """Check if exit all positions signal is set in Redis"""
        try:
            if True:
                logger.warning(f"[{self.symbol}] Exit all positions signal received from frontend!")
                update_strategy_status(self.redis_client, "running", "Exit all positions signal received")
                update_strategy_action(self.redis_client, "Exit All Positions Signal Received")
                self.exit_all_positions()
                    
        except Exception as e:
            logger.error(f"[{self.symbol}] Error checking exit all signal: {e}")
    
    def _calculate_current_mtm(self):
        """Calculate current Mark-to-Market value"""
        try:
            mtm_data = self.compute_mtm()
            total_mtm = mtm_data.get("total", 0.0)
            positions_data = {
                "batman_positions": getattr(self, 'batman_positions', {}),
                "debit_positions": getattr(self, 'debit_spread_positions', {})
            }

            update_trading_status(self.redis_client, self.symbol, positions_data=positions_data)

            return total_mtm
            
        except Exception as e:
            logger.error(f"[{self.symbol}] Error calculating MTM: {e}")
            update_strategy_status(self.redis_client, "error", f"MTM calculation error: {str(e)}")
            return 0.0

    def exit_all_positions(self):
        """Exit all open positions created by this strategy"""
        logger.info(f"[exit_all_positions] : Exiting all positions...")
        update_strategy_status(self.redis_client, "running", "Exiting all positions")
        update_strategy_action(self.redis_client, "Exiting All Positions")

        try:
            if self.exit_in_progress:
                logger.info(f"[{self.symbol}] Exit already in progress, skipping...")
                time.sleep(2)
                return
            self.exit_in_progress = True
            self._exit_batman_positions()
            self._exit_debit_spread_positions()
            
            self.batman_active = False
            self.debit_spread_active = False
            self.pivot_base = None
            self.batman_sl = None
            
            logger.info(f"[{self.symbol}] All positions exited successfully")
            update_strategy_status(self.redis_client, "running", "All positions exited successfully - Restart to take new postions")
            update_strategy_action(self.redis_client, "All Positions Exited Successfully")

        except Exception as e:
            logger.error(f"[{self.symbol}] Error exiting positions: {e}")
            update_strategy_status(self.redis_client, "error", f"Error exiting positions: {str(e)}")

    def stop(self,reason="Stopped"):
        """Stop the strategy and all background threads"""
        logger.info(f"[{self.symbol}] Stopping strategy: {reason}")
        logger.info(f"[{self.symbol}] Stopping strategy...")
        if reason == "REQUESTED":
            update_strategy_status(self.redis_client, "stopping", "Strategy stop requested")
            update_strategy_action(self.redis_client, "Stopping strategy")
        time.sleep(1)
        positions_data = {
                "batman_positions": getattr(self, 'batman_positions', {}),
                "debit_positions": getattr(self, 'debit_spread_positions', {})
            }

        update_trading_status(self.redis_client, self.symbol, positions_data=positions_data)
        self.exit_signal.set()
        StraddleVWAPUpdater.ready_to_execute = False
        logger.info(f"[{self.symbol}] Strategy stopped")
        if reason == "REQUESTED":
            update_strategy_status(self.redis_client, "stopped", "Strategy stopped successfully")
            update_strategy_action(self.redis_client, "stopped", "Strategy stopped successfully")

