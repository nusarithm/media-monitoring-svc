#!/bin/bash

# Start script for Media Monitoring Service Authentication API

echo "🚀 Starting Media Monitoring Service..."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Run: python3 -m venv venv"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "Copy .env.example to .env and configure it"
    exit 1
fi

# Install dependencies if needed
echo "📦 Checking dependencies..."
pip install -q -r requirements.txt

echo ""
echo "✅ Starting server..."
echo "📡 API Documentation: http://localhost:8000/docs"
echo "📡 Alternative Docs: http://localhost:8000/redoc"
echo "📡 Health Check: http://localhost:8000/health"
echo ""
echo "Press CTRL+C to stop the server"
echo ""

# Run the application
python main.py
