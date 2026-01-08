"""
Redis-based configuration reader for strategy parameters
"""
import redis
import json
from typing import Any, Optional, Union
import datetime

class RedisConfigReader:
    """
    Configuration reader that fetches strategy parameters from Redis
    """
    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        self.r = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
        self.prefix = "strategy:input:"
    
    def get(self, key: str, fallback: Optional[Any] = None, type: Union[type, None] = str) -> Any:
        """
        Retrieve a value from Redis and convert to the requested type.
        """
        try:
            raw = self.r.get(self.prefix + key)
            if raw is None:
                return fallback
            
            # Parse JSON value
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                value = raw.decode('utf-8') if isinstance(raw, bytes) else raw
            
            # Convert to requested type
            if type is bool:
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ('true', '1', 'yes', 'on')
            elif type is int:
                return int(value)
            elif type is float:
                return float(value)
            elif type is datetime.date:
                return datetime.datetime.strptime(str(value), "%Y-%m-%d").date()
            elif type is datetime.time:
                return datetime.datetime.strptime(str(value), "%H:%M").time()
            else:
                return str(value)
                
        except Exception as e:
            print(f"Error reading config key '{key}': {e}")
            return fallback
    
    def get_all_config(self) -> dict:
        """
        Get all strategy configuration parameters
        """
        config = {}
        keys = [
            'index', 'expiry', 'Quantity', 'QtyHedgeRatio','PivotRangeMinutes', 'ShiftThresholdPts',
            'StraddleGapPct', 'HedgeGapPct', 'OrderBufferPct', 'FillTimeoutSec',
            'RmsCap', 'TrailStopLossToggle', 'ConsoleVerbosity', 'StopLossBufferPct',
            'SegregateTrades', 'TargetPnl', 'ExitPnl', 'RollingValue'
        ]
        
        for key in keys:
            raw = self.r.get(self.prefix + key)
            if raw:
                try:
                    config[key] = json.loads(raw)
                except json.JSONDecodeError:
                    config[key] = raw.decode('utf-8') if isinstance(raw, bytes) else raw
        
        return config
    
    def is_config_available(self) -> bool:
        """
        Check if configuration is available in Redis
        """
        essential_keys = ['index', 'Quantity']
        for key in essential_keys:
            if not self.r.exists(self.prefix + key):
                return False
        return True
