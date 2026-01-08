import logging
import time
import json
import os
import redis

class RedisLogHandler(logging.Handler):
    def __init__(self, redis_client, key='strategy:logs'):
        super().__init__()
        self.redis_client = redis_client
        self.key = key
        
    def emit(self, record):
        try:
            log_entry = {
                'timestamp': time.time(),
                'level': record.levelname,
                'message': self.format(record),
                'logger': record.name
            }
            self.redis_client.lpush(self.key, json.dumps(log_entry))
            self.redis_client.ltrim(self.key, 0, 99)
        except Exception:
            pass

def check_control_signal(redis_client):
    """Check Redis for control signals from the backend"""
    try:
        control_signal = redis_client.get("strategy:control")
        if control_signal:
            control_data = json.loads(control_signal)
            return control_data.get("action"), control_data
    except Exception:
        pass
    return None, None

def send_heartbeat(redis_client):
    """Send heartbeat to Redis to indicate strategy is running"""
    try:
        heartbeat_data = {
            "timestamp": time.time(),
            "status": "alive",
            "process_id": os.getpid() if 'os' in globals() else None
        }
        redis_client.set("strategy:heartbeat", json.dumps(heartbeat_data))
    except Exception:
        pass

def update_strategy_status(redis_client, status, message):
    """Update strategy execution status in Redis"""
    status_data = {
        "execution_status": status,
        "message": message,
        "timestamp": time.time()
    }
    redis_client.set("strategy:execution_status", json.dumps(status_data))


def update_trading_status(redis_client, symbol, straddle_price=None, vwap=None, pnl_batman=None, pnl_spread=None, positions_data=None, exit_pnl=None):
    """Incrementally update trading status for frontend display"""
    existing_status = {}
    try:
        status_json = redis_client.get("strategy:trading_status")
        if status_json:
            existing_status = json.loads(status_json)
    except Exception:
        pass

    existing_status["timestamp"] = time.time()
    existing_status["symbol"] = symbol
    existing_status["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")

    if straddle_price is not None:
        existing_status["straddle_price"] = straddle_price
    if vwap is not None:
        existing_status["vwap"] = vwap
    if exit_pnl is not None:
        existing_status["exit_pnl"] = exit_pnl
    if pnl_batman is not None:
        existing_status["pnl_batman"] = pnl_batman
    if pnl_spread is not None:
        existing_status["pnl_spread"] = pnl_spread
    if positions_data is not None:
        existing_status["positions_data"] = positions_data

    redis_client.set("strategy:trading_status", json.dumps(existing_status))


def update_strategy_action(redis_client, action, details=None):
    """Update strategy action in Redis for frontend monitoring"""
    try:

        action_data = {
            "timestamp": time.time(),
            "action": action,
            "details": details or {}
        }

        redis_client.set("strategy:latest_action", json.dumps(action_data))
        redis_client.lpush("strategy:action_history", json.dumps(action_data))
        redis_client.ltrim("strategy:action_history", 0, 49)

    except Exception as e:
        action_data = {
            "timestamp": time.time(),
            "action": action,
            "details": details or {}
        }
        redis_client.set("strategy:latest_action", json.dumps(action_data))
        redis_client.lpush("strategy:action_history", json.dumps(action_data))
        redis_client.ltrim("strategy:action_history", 0, 49)
    except Exception as e:
        pass