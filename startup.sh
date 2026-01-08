#!/bin/bash

echo "🚀 Starting Trading Strategy Control Panel..."

if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis is not running. Please start Redis first:"
    echo "   brew install redis (if not installed)"
    echo "   brew services start redis"
    echo "   OR"
    echo "   redis-server"
    exit 1
fi

echo "✅ Redis is running"

# Activate virtual environment
if [ -d "my_env" ]; then
    echo "🐍 Activating virtual environment..."
    source venv/bin/activate
else
    echo "❌ Virtual environment 'my_env' not found. Creating one..."
    python3 -m venv venv
    source my_env/bin/activate
fi

# # Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

## Clear Old Redis Data
echo "🧹 Clearing old Redis data..."
python3 clear_redis.py

## make expiries
mkdir -p data/
echo "📅 Making expiries..."
python3 make_expiries.py

# Start Flask backend
echo "🌐 Starting Flask backend on http://127.0.0.1:8009..."
export FLASK_APP=backend/app.py
export FLASK_ENV=development
python3 backend/app.py &

# Store the backend PID
BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

echo ""
echo "🎉 Project is now running!"
echo "📱 Open your browser and go to: http://127.0.0.1:8009"
echo ""
echo "To stop the project, press Ctrl+C or run:"
echo "   kill $BACKEND_PID"
echo ""

trap "kill $BACKEND_PID; exit" SIGINT

wait $BACKEND_PID
