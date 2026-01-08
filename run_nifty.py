import logging
import signal
import sys
import os
import json
import time
import threading
import redis
from kite_login import kite_login
from algo_strategy import AlgoStrategy
from utils.redis_config import RedisConfigReader
from utils.logger import setup_logger
from utils.redis_utils import RedisLogHandler, check_control_signal, send_heartbeat, update_strategy_status

if __name__ == "__main__":

    r = redis.Redis(host='localhost', port=6379, db=0)
    update_strategy_status(r, "starting", "Starting NIFTY strategy... Please wait.")

    setup_logger("root", log_file=f"{'NIFTY'}_strategy.log", rotate=True)
    logger = logging.getLogger("root")
    redis_handler = RedisLogHandler(r)
    redis_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    redis_handler.setFormatter(formatter)
    logger.addHandler(redis_handler)

    redis_config = RedisConfigReader()
    
    while not redis_config.is_config_available():
        update_strategy_status(r, "waiting", "Waiting for configuration to be set in Redis...")
        logger.info("No configuration available in Redis. Waiting for strategy parameters to be set.")
        time.sleep(5)
    
    config = redis_config.get_all_config()
    symbol = config.get('index')

    # Wait for symbol to be NIFTY before proceeding
    while symbol != "NIFTY":
        time.sleep(5)
        config = redis_config.get_all_config()
        symbol = config.get('index')

    logger.info(f"Symbol validation passed: {symbol}")
    
    strat = None
    strategy_running = False

    def _shutdown(sig=None, frame=None):
        logger.info("Shutdown signal received")
        update_strategy_status(r, "stopping", "Strategy is shutting down...")
        if strat:
            strat.stop("REQUESTED")
        update_strategy_status(r, "stopped", "Strategy has stopped")
        sys.exit(0)
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        update_strategy_status(r, "waiting", f"waiting for Kite login")
        kite = kite_login()
        logger.info("Kite login successful")
                
        update_strategy_status(r, "waiting", f"{symbol} strategy initialized, waiting for start signal from backend")
        strat = AlgoStrategy()

        while True:
            try:
                send_heartbeat(r)
                
                action, _ = check_control_signal(r)

                if action == "start" and not strategy_running:
                    # Re-check symbol before starting strategy
                    current_config = redis_config.get_all_config()
                    current_symbol = current_config.get('index')
                    
                    if current_symbol != "NIFTY":
                        pass
                    else:
                        logger.info("Received START")
                        update_strategy_status(r, "starting", "Strategy execution starting…")
                        strategy_running = True
                        strat_thread = threading.Thread(target=strat.start_algo_class, args=(kite, current_symbol), daemon=True)
                        strat_thread.start()

                elif (action == "stop" or action==None) and strategy_running and ((action == "stop" )):
                    logger.info("Received STOP")
                    update_strategy_status(r, "stopping", "Stopping strategy…")
                    update_strategy_status(r, "stopping", "Exiting All Positions")
                    strat._check_exit_all_signal()
                    strat.stop(reason="REQUESTED")
                    strat_thread.join()
                    strategy_running = False
                    update_strategy_status(r, "stopped", "Strategy stopped")

                time.sleep(1)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in control loop: {e}")
                time.sleep(5)
            
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Shutting down gracefully...")
        _shutdown()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        update_strategy_status(r, "error", f"Fatal error: {str(e)}")
        sys.exit(1)
