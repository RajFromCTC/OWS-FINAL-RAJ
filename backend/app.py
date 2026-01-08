from flask import Flask, request, jsonify
import redis
import json
import time
import logging
from pathlib import Path
import csv

app = Flask(__name__, static_folder='static', static_url_path='')
r = redis.Redis(host='localhost', port=6379, db=0)

INPUT_PREFIX = "strategy:input:"
OUTPUT_KEY = "strategy:output"
CONTROL_KEY = "strategy:control"

logging.basicConfig(level=logging.INFO)
backend_logger = logging.getLogger("backend")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
EXPIRIES_CSV = DATA_DIR / "expiries.csv"
print(EXPIRIES_CSV)
_exp_cache = {"mtime": 0.0, "rows": []}

def _load_expiry_rows():
    try:
        mtime = EXPIRIES_CSV.stat().st_mtime
    except FileNotFoundError:
        return []

    if mtime != _exp_cache["mtime"]:
        rows = []
        with EXPIRIES_CSV.open("r", newline="", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                rows.append({
                    "symbol": (row.get("symbol") or "").strip(),
                    "expiry_iso": (row.get("expiry") or "").strip(),
                    "zerodha_token": (row.get("zerodha_token") or row.get("token_short") or "").strip(),
                })
        _exp_cache["mtime"] = mtime
        _exp_cache["rows"] = rows
        backend_logger.info("Loaded %d expiry rows from %s", len(rows), EXPIRIES_CSV)
    return _exp_cache["rows"]

@app.route('/api/expiries', methods=['GET'])
def api_expiries():
    try:
        symbol = (request.args.get('symbol') or "").upper().strip()
        rows = _load_expiry_rows()

        if symbol:
            rows = [r for r in rows if (r["symbol"] or "").upper() == symbol]

        rows = sorted(rows, key=lambda r: r.get("expiry", ""))
        seen, items = set(), []
        for r in rows:
            tok = r.get("zerodha_token")
            if tok and tok not in seen:
                seen.add(tok)
                items.append(r)

        return jsonify({
            "items": items,
            "count": len(items),
            "symbol": symbol or None,
            "timestamp": time.time()
        }), 200

    except Exception as e:
        backend_logger.exception("Failed to serve expiries")
        return jsonify({"error": f"Failed to load expiries: {e}"}), 500


@app.route('/api/strategy/input', methods=['POST'])
def set_strategy_input():
    """
    Set strategy input parameters in Redis.
    Expects JSON payload of {"key": ..., "value": ...}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        key = data.get('key')
        value = data.get('value')
        if not key or value is None:
            return jsonify({"error": "Missing key or value"}), 400
        
        r.set(INPUT_PREFIX + key, json.dumps(value))
        return jsonify({"status": "ok", "message": f"Successfully saved {key}"}), 200
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/api/strategy/run', methods=['POST'])
def run_strategy():
    """
    Signal the strategy to start by setting a control flag in Redis.
    The strategy process should be running independently and monitoring this flag.
    """
    try:
        backend_logger.info("Received request to start strategy execution")
        
        # Set the control signal in Redis
        control_signal = {
            "action": "start",
            "timestamp": time.time(),
            "requested_by": "backend_api"
        }
        
        r.set(CONTROL_KEY, json.dumps(control_signal))
        
        # Update execution status
        result = {
            "status": "start_requested",
            "message": "Strategy start signal sent via Redis",
            "timestamp": time.time()
        }
        
        r.set(OUTPUT_KEY, json.dumps(result))
        
        return jsonify(result), 200
        
    except Exception as e:
        error_msg = f"Failed to send start signal: {str(e)}"
        backend_logger.error(error_msg)
        return jsonify({"error": error_msg}), 500

@app.route('/api/strategy/stop', methods=['POST'])
def stop_strategy():
    """
    Signal the strategy to stop by setting a control flag in Redis.
    The strategy process should monitor this flag and stop execution gracefully.
    """
    try:
        backend_logger.info("Received request to stop strategy execution")
        
        # Set the control signal in Redis
        control_signal = {
            "action": "stop",
            "timestamp": time.time(),
            "requested_by": "backend_api"
        }
        
        r.set(CONTROL_KEY, json.dumps(control_signal))
        
        result = {
            "status": "stop_requested", 
            "message": "Strategy stop signal sent via Redis",
            "timestamp": time.time()
        }
        
        r.set(OUTPUT_KEY, json.dumps(result))
        
        return jsonify(result), 200
        
    except Exception as e:
        error_msg = f"Failed to send stop signal: {str(e)}"
        backend_logger.error(error_msg)
        return jsonify({"error": error_msg}), 500

@app.route('/api/strategy/exit-all', methods=['POST'])
def exit_all_positions():
    """
    Signal the strategy to exit all positions by setting a control flag in Redis.
    """
    try:
        backend_logger.info("Received request to exit all positions")
        
        # Set the exit all signal in Redis
        exit_signal = {
            "exit_all_positions": True,
            "timestamp": time.time(),
            "requested_by": "backend_api"
        }
        
        r.set("strategy:exit_all_signal", json.dumps(exit_signal))
        
        result = {
            "status": "exit_all_requested",
            "message": "Exit all positions signal sent via Redis",
            "timestamp": time.time()
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        error_msg = f"Failed to send exit all signal: {str(e)}"
        backend_logger.error(error_msg)
        return jsonify({"error": error_msg}), 500

@app.route('/')
def index():
    """
    Serve the frontend index page
    """
    return app.send_static_file('index.html')

@app.route('/api/strategy/output', methods=['GET'])
def get_strategy_output():
    """
    Get strategy output from Redis.
    """
    result = r.get(OUTPUT_KEY)
    if not result:
        return jsonify({"status": "pending", "message": "No output available yet"}), 204
    return jsonify(json.loads(result)), 200

@app.route('/api/strategy/config', methods=['GET'])
def get_current_config():
    """
    Get current configuration from Redis.
    """
    keys = [
        'index', 'expiry', 'Quantity', 'QtyHedgeRatio', 'PivotRangeMinutes', 'ShiftThresholdPts',
        'StraddleGapPct', 'HedgeGapPct', 'OrderBufferPct', 'FillTimeoutSec',
        'RmsCap', 'TrailStopLossToggle',  'StopLossBufferPct', 'TargetPnl', 
        'ExitPnl', 'RollingValue',
    ]
    config = {}
    for key in keys:
        raw = r.get(INPUT_PREFIX + key)
        if raw:
            try:
                config[key] = json.loads(raw)
            except Exception:
                config[key] = raw.decode('utf-8') if isinstance(raw, bytes) else raw
    
    return jsonify({
        "config": config,
        "timestamp": time.time(),
        "config_available": len(config) > 0
    }), 200

@app.route('/api/strategy/status', methods=['GET'])
def get_strategy_status():
    """
    Get strategy execution status from Redis.
    """
    try:
        # Check Redis for strategy status and control signals
        execution_status = r.get('strategy:execution_status')
        control_signal = r.get(CONTROL_KEY)
        last_output = r.get(OUTPUT_KEY)
        heartbeat = r.get('strategy:heartbeat')
        
        status_info = {
            "timestamp": time.time()
        }

        if execution_status:
            try:
                exec_data = json.loads(execution_status)
                status_info.update(exec_data)
            except json.JSONDecodeError:
                pass
        
        if last_output:
            try:
                output_data = json.loads(last_output)
                status_info["last_run"] = output_data.get('timestamp')
                status_info["last_result"] = output_data.get('status')
            except json.JSONDecodeError:
                pass

        if control_signal:
            try:
                control_data = json.loads(control_signal)
                status_info["control_signal"] = control_data
            except json.JSONDecodeError:
                pass

        essential_keys = ['index', 'Quantity']
        config_available = all(r.exists(INPUT_PREFIX + key) for key in essential_keys)
        status_info["config_available"] = config_available
        
        return jsonify(status_info), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to get status: {str(e)}"}), 500

@app.route('/api/strategy/trading-status', methods=['GET'])
def get_trading_status():
    try:
        trading_status = r.get('strategy:trading_status')
        
        response = {
            "timestamp": time.time()
        }
        
        if trading_status:
            try:
                response.update(json.loads(trading_status))
            except json.JSONDecodeError:
                pass
        
        if not trading_status:
            return jsonify({
                "status": "no_data",
                "message": "No trading status available",
                "timestamp": time.time()
            }), 200
        
        return jsonify(response), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get trading status: {str(e)}"}), 500

@app.route('/api/strategy/logs', methods=['GET'])
def get_strategy_logs():
    """
    Get recent strategy logs
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        logs = r.lrange('strategy:logs', 0, limit - 1)
        parsed_logs = []
        
        for log in logs:
            try:
                parsed_logs.append(json.loads(log))
            except json.JSONDecodeError:
                parsed_logs.append({"message": log.decode('utf-8'), "timestamp": time.time()})
        
        return jsonify({
            "logs": parsed_logs,
            "count": len(parsed_logs),
            "timestamp": time.time()
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get logs: {str(e)}"}), 500

@app.route('/api/strategy/actions', methods=['GET'])
def get_strategy_actions():
    """
    Get recent strategy actions
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        
        latest_action = r.get('strategy:latest_action')
        action_history = r.lrange('strategy:action_history', 0, limit - 1)
        
        response = {
            "timestamp": time.time()
        }
        
        if latest_action:
            try:
                response["latest_action"] = json.loads(latest_action)
            except json.JSONDecodeError:
                pass
        
        if action_history:
            actions = []
            for action in action_history:
                try:
                    actions.append(json.loads(action))
                except json.JSONDecodeError:
                    continue
            response["action_history"] = actions
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to get strategy actions: {str(e)}"}), 500

@app.route('/api/strategy/heartbeat', methods=['GET'])
def get_strategy_heartbeat():
    """
    Get detailed strategy heartbeat information.
    """
    try:
        heartbeat = r.get('strategy:heartbeat')
        
        if not heartbeat:
            return jsonify({
                "status": "no_heartbeat",
                "message": "No heartbeat available - strategy may not be running",
                "timestamp": time.time()
            }), 200
        
        heartbeat_data = json.loads(heartbeat)
        heartbeat_age = time.time() - heartbeat_data.get('timestamp', 0)
        
        response = {
            "heartbeat": heartbeat_data,
            "heartbeat_age_seconds": heartbeat_age,
            "is_responsive": heartbeat_age < 30,
            "status": "alive" if heartbeat_age < 30 else "stale",
            "timestamp": time.time()
        }
        
        # Add responsiveness classification
        if heartbeat_age < 10:
            response["responsiveness"] = "excellent"
        elif heartbeat_age < 30:
            response["responsiveness"] = "good"
        elif heartbeat_age < 60:
            response["responsiveness"] = "poor"
        else:
            response["responsiveness"] = "dead"
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to get heartbeat: {str(e)}"}), 500


@app.route('/api/auth/login', methods=['POST'])
def auto_login():
    """
    Handle auto-login functionality
    """
    try:
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from kite_login import load_access_token, load_credentials
        from kiteconnect import KiteConnect
        
        credentials = load_credentials()
        api_key = credentials["apiKey"]
        kite = KiteConnect(api_key=api_key)
        
        # Check if current token is valid
        access_token = load_access_token()
        if access_token:
            try:
                kite.set_access_token(access_token)
                profile = kite.profile()  # Test token validity
                return jsonify({
                    "status": "already_authenticated",
                    "message": f"Already logged in as {profile['user_name']}",
                    "user_name": profile['user_name']
                }), 200
            except Exception as e:
                # Token is invalid, continue to login flow
                backend_logger.info(f"Token validation failed: {e}")
        
        # Generate URLs for forced fresh login
        logout_url = "https://kite.zerodha.com/logout"  # Main logout
        login_url = f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"
        
        return jsonify({
            "status": "login_required",
            "logout_url": logout_url,
            "login_url": login_url,
            "message": "Please complete fresh login and provide request token"
        }), 200
        
    except Exception as e:
        backend_logger.error(f"Auto login error: {str(e)}")
        return jsonify({"error": f"Login failed: {str(e)}"}), 500

@app.route('/api/auth/token', methods=['POST'])
def submit_request_token():
    """
    Submit request token to complete authentication
    """
    try:
        data = request.get_json()
        request_token = data.get('request_token', '').strip()
        
        if not request_token:
            return jsonify({"error": "Request token is required"}), 400
        
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from kite_login import load_credentials, save_access_token
        from kiteconnect import KiteConnect
        
        credentials = load_credentials()
        api_key = credentials["apiKey"]
        api_secret = credentials["secret"]
        
        kite = KiteConnect(api_key=api_key)
        data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = data["access_token"]
        
        save_access_token(access_token)
        
        # Verify the new token
        kite.set_access_token(access_token)
        profile = kite.profile()
        
        return jsonify({
            "status": "success",
            "message": f"Successfully authenticated as {profile['user_name']}",
            "user_name": profile['user_name']
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Token submission failed: {str(e)}"}), 500

@app.route('/api/auth/status', methods=['GET'])
def check_auth_status():
    """
    Check current authentication status
    """
    try:
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from kite_login import load_access_token, load_credentials
        from kiteconnect import KiteConnect
        
        credentials = load_credentials()
        api_key = credentials["apiKey"]
        kite = KiteConnect(api_key=api_key)
        
        access_token = load_access_token()
        if not access_token:
            return jsonify({"authenticated": False, "message": "No access token found"}), 200
        
        kite.set_access_token(access_token)
        profile = kite.profile()
        
        return jsonify({
            "authenticated": True,
            "user_name": profile['user_name'],
            "message": f"Authenticated as {profile['user_name']}"
        }), 200
        
    except Exception as e:
        return jsonify({"authenticated": False, "message": f"Authentication failed: {str(e)}"}), 200
    
@app.route('/api/auth/session', methods=['POST'])
def submit_session_id():
    """
    Submit session ID to complete authentication
    """
    try:
        data = request.get_json()
        session_id = data.get('session_id', '').strip()
        
        if not session_id:
            return jsonify({"error": "Session ID is required"}), 400
        
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from kite_login import load_credentials, save_access_token
        from kiteconnect import KiteConnect
        
        credentials = load_credentials()
        api_key = credentials["apiKey"]
        
        # Try to use session ID as request token
        kite = KiteConnect(api_key=api_key)
        try:
            # Sometimes session_id can be used as request_token
            api_secret = credentials["secret"]
            session_data = kite.generate_session(session_id, api_secret=api_secret)
            access_token = session_data["access_token"]
            
            save_access_token(access_token)
            
            # Verify the new token
            kite.set_access_token(access_token)
            profile = kite.profile()
            
            return jsonify({
                "status": "success",
                "message": f"Successfully authenticated as {profile['user_name']}",
                "user_name": profile['user_name']
            }), 200
            
        except Exception as e:
            return jsonify({"error": f"Session ID authentication failed: {str(e)}. Please try logging out of Zerodha first."}), 400
        
    except Exception as e:
        return jsonify({"error": f"Session submission failed: {str(e)}"}), 500

# ═══════════════════════════════════════════════════════════════
# TRADINGVIEW WEBHOOK ENDPOINT
# ═══════════════════════════════════════════════════════════════

@app.route('/api/webhook/tradingview',methods=['POST'])
def tradingview_webhook():
    try:
        data = request.get_json()
        backend_logger.info(f"TradingView webhook received: {data}")
        if not data: 
            return jsonify({"error": "No data received"}), 400
        signal = {
            "source" : "tradingview",
            "timestamp": time.time(),
            "raw_data": data
        }
        r.set("strategy:tv_signal",json.dumps(signal))

        return jsonify({
            "status":"received",
            "message":"Signal received successfully"
        }),200

    except Exception as e:
        backend_logger.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500
        

if __name__ == '__main__':
    backend_logger.info("Starting Flask backend server on port 8009")
    backend_logger.info("Strategy execution now managed via Redis control signals")
    app.run(debug=True, port=8009, host='0.0.0.0')
