import logging
from utils.redis_utils import update_trading_status 
import time 

logger = logging.getLogger(__name__)
class KiteTrader:
    def __init__(self):
        pass

    def _update_position(self, tradingsymbol, transaction_type, quantity, price, strategy):

        if strategy == "BATMAN":
            positions_dict = self.batman_positions
            closed_pnls_list = self.batman_closed_pnls
        elif strategy == "DEBIT_SPREAD":
            positions_dict = self.debit_spread_positions
            closed_pnls_list = self.debit_spread_closed_pnls
            
        pos = positions_dict.get(tradingsymbol, {'quantity': 0, 'avg_price': 0.0})
        qty, avg = pos['quantity'], pos['avg_price']

        if transaction_type == self.kite.TRANSACTION_TYPE_BUY:
            if qty >= 0:
                new_qty = qty + quantity
                new_avg = ((qty * avg) + (quantity * price)) / new_qty
            else:
                cover_qty = min(quantity, -qty)
                pnl = (avg - price) * cover_qty
                closed_pnls_list.append(pnl)

                if quantity > -qty:
                    new_qty = quantity + qty      # qty is negative
                    new_avg = price               # new long basis = this price
                else:
                    new_qty = qty + quantity
                    new_avg = avg

        else:  # SELL
            if qty <= 0:
                new_qty = qty - quantity      # more negative
                total_shorts = -qty + quantity
                new_avg = ((-qty * avg) + (quantity * price)) / total_shorts
            else:
                # unwinding long
                close_qty = min(quantity, qty)
                pnl = (price - avg) * close_qty
                closed_pnls_list.append(pnl)

                if quantity > qty:
                    # flipped from long to net short
                    new_qty = qty - quantity      # negative
                    new_avg = price               # new short basis = this price
                else:
                    # still long
                    new_qty = qty - quantity
                    new_avg = avg

        if new_qty == 0:
            positions_dict.pop(tradingsymbol, None)
        else:
            positions_dict[tradingsymbol] = {
                'quantity': new_qty,
                'avg_price': new_avg
            }
            
        logger.info(f"[{strategy}] Updated position for {tradingsymbol}: qty={new_qty}, avg={new_avg:.2f}")


    def _place_order_with_fallback(self, tradingsymbol, transaction_type, quantity, strategy):
        """
        1. Fetch LTP
        2. Place LIMIT @ ±buffer
        3. Wait fill_timeout_sec
        4. If not filled, MODIFY to MARKET
        """
        try:
            logger.info(f"[{tradingsymbol}] Placing {transaction_type} order for {tradingsymbol} qty={quantity}")
            key = f"{self.exchange_options}:{tradingsymbol}"
            ltp = self.kite.ltp(key)[key]["last_price"]

            if transaction_type == self.kite.TRANSACTION_TYPE_BUY:
                limit_price = round(ltp * (1 + self.order_buffer_pct) / 0.05) * 0.05
            else:
                limit_price = round(ltp * (1 - self.order_buffer_pct) / 0.05) * 0.05

            # order_id = self.kite.place_order(
            #     variety=self.kite.VARIETY_REGULAR,
            #     exchange=self.exchange_options,
            #     tradingsymbol=tradingsymbol,
            #     transaction_type=transaction_type,
            #     quantity=quantity,
            #     order_type=self.kite.ORDER_TYPE_MARKET,
            #     price=None,  # MARKET order
            #     product=self.product_type
            # )
            logger.info(f"[{tradingsymbol}] MARKET {transaction_type} {tradingsymbol} @ {ltp:.2f} → ID {123}")
            self._update_position(tradingsymbol, transaction_type, quantity, limit_price, strategy)

            # order_id = self.kite.place_order(
            #     variety=self.kite.VARIETY_REGULAR,
            #     exchange=self.exchange_options,
            #     tradingsymbol=tradingsymbol,
            #     transaction_type=transaction_type,
            #     quantity=quantity,
            #     order_type=self.kite.ORDER_TYPE_LIMIT,
            #     price=round(limit_price, 2),
            #     product=self.product_type
            # )
            # logger.info(f"[{tradingsymbol}] LIMIT {transaction_type} {tradingsymbol} @ {limit_price:.2f} → ID {order_id}")

            # # 3. wait for fill
            # start = time.time()
            # while time.time() - start < self.fill_timeout_sec:
            #     hist = self.kite.order_history(order_id)
            #     complete = next((o for o in hist if o.get("status") == "COMPLETE"), None)
            #     if complete:
            #         traded_price = complete.get("average_price") or complete.get("price")
            #         self._update_position(tradingsymbol, transaction_type, quantity, traded_price, strategy)
            #         logger.info(f"[{tradingsymbol}] Order {order_id} filled @ {traded_price:.2f}")
            #         return order_id
            #     time.sleep(0.5)

            # # 4. fallback → modify to MARKET
            # self.kite.modify_order(
            #     variety=self.kite.VARIETY_REGULAR,
            #     order_id=order_id,
            #     order_type=self.kite.ORDER_TYPE_MARKET,
            #     price=None
            # )
            # logger.warning(f"[{tradingsymbol}] LIMIT {order_id} not filled in {self.fill_timeout_sec}s → modified to MARKET")

            # # wait for modified order to fill
            # start = time.time()
            # while time.time() - start < self.fill_timeout_sec:
            #     hist = self.kite.order_history(order_id)
            #     complete = next((o for o in hist if o.get("status") == "COMPLETE"), None)
            #     if complete:
            #         traded_price = complete.get("average_price") or complete.get("price")
            #         self._update_position(tradingsymbol, transaction_type, quantity, traded_price)
            #         logger.info(f"[{tradingsymbol}] MARKET {order_id} filled @ {traded_price:.2f}")
            #         break
            #     time.sleep(0.5)

            return 123

        except Exception as e:
            logger.error(f"[{tradingsymbol}] Error placing order {tradingsymbol}: {e}")
            return None

    def compute_mtm(self):
        """Return a dict with realized, unrealized & total PnL computed separately for BATMAN and DEBIT_SPREAD strategies."""
        # Compute unrealized PnL for BATMAN
        batman_unrealized = 0.0
        if hasattr(self, 'batman_positions'):
            # Create a copy to avoid "dictionary changed size during iteration" error
            batman_positions_copy = dict(self.batman_positions)
            for sym, pos in batman_positions_copy.items():
                try:
                    key = f"{self.exchange_options}:{sym}"
                    ltp = self.kite.ltp(key)[key]["last_price"]
                    batman_unrealized += (ltp - pos['avg_price']) * pos['quantity']
                except Exception as e:
                    logger.error(f"MTM fetch error for {sym} in BATMAN: {e}")
        
        # Compute unrealized PnL for DEBIT_SPREAD
        debit_unrealized = 0.0
        if hasattr(self, 'debit_spread_positions'):
            # Create a copy to avoid "dictionary changed size during iteration" error
            debit_positions_copy = dict(self.debit_spread_positions)
            for sym, pos in debit_positions_copy.items():
                try:
                    key = f"{self.exchange_options}:{sym}"
                    ltp = self.kite.ltp(key)[key]["last_price"]
                    debit_unrealized += (ltp - pos['avg_price']) * pos['quantity']
                except Exception as e:
                    logger.error(f"MTM fetch error for {sym} in DEBIT_SPREAD: {e}")
        
        batman_realized = sum(self.batman_closed_pnls) if hasattr(self, 'batman_closed_pnls') else 0.0
        debit_realized = sum(self.debit_spread_closed_pnls) if hasattr(self, 'debit_spread_closed_pnls') else 0.0
        
        # Total realised and unrealised PnL across both strategies
        total_realized = batman_realized + debit_realized
        total_unrealized = batman_unrealized + debit_unrealized
        total = total_realized + total_unrealized
        
        update_trading_status(self.redis_client, 
                              symbol=self.symbol, 
                              pnl_batman=batman_realized+batman_unrealized, 
                              pnl_spread=debit_realized+debit_unrealized)

        logger.info(f"[BATMAN] Realized PnL={batman_realized:.2f}, Unrealized MTM={batman_unrealized:.2f}")
        logger.info(f"[DEBIT_SPREAD] Realized PnL={debit_realized:.2f}, Unrealized MTM={debit_unrealized:.2f}")
        logger.info(f"Total: Realized PnL={total_realized:.2f}, Unrealized MTM={total_unrealized:.2f}, Total={total:.2f}")
        
        return {"realized": total_realized, "unrealized": total_unrealized, "total": total , "batman_pnl": batman_realized + batman_unrealized, "debit_pnl": debit_realized + debit_unrealized}