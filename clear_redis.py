import redis

#!/usr/bin/env python3

def clear_redis_data(redis_host='localhost', redis_port=6379, redis_db=0):
    try:
        # Connect to Redis
        client = redis.Redis(host=redis_host, port=redis_port, db=redis_db)
        # Flush all data from all databases
        client.flushall()
        print("Successfully cleared Redis data.")
    except Exception as e:
        print("Error clearing Redis data:", e)

if __name__ == "__main__":
    clear_redis_data()