#!/bin/bash
# Complete end-to-end test script
# Starts the server, runs tests, and cleans up

set -e

echo "========================================================================"
echo "End-to-End Test Script"
echo "========================================================================"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "========================================================================"
    echo "Cleaning up..."
    echo "========================================================================"

    # Kill the background server process
    if [ -n "$SERVER_PID" ]; then
        echo "Stopping server (PID: $SERVER_PID)..."
        kill $SERVER_PID 2>/dev/null || true
        wait $SERVER_PID 2>/dev/null || true
        echo "✅ Server stopped"
    fi

    # Clean up any remaining Python processes
    pkill -f "python main.py" 2>/dev/null || true
}

# Set trap to cleanup on exit
trap cleanup EXIT INT TERM

# Start the server in the background
echo ""
echo "Starting server in the background..."
python main.py > server.log 2>&1 &
SERVER_PID=$!

echo "Server started with PID: $SERVER_PID"
echo "Waiting for server to be ready..."

# Wait for server to start (max 60 seconds)
for i in {1..60}; do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        echo "✅ Server is ready!"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "❌ Server failed to start within 60 seconds"
        echo "Server log:"
        cat server.log
        exit 1
    fi
    sleep 1
done

# Run the end-to-end test
echo ""
echo "========================================================================"
echo "Running End-to-End Tests"
echo "========================================================================"
echo ""

if python test_api_e2e.py; then
    echo ""
    echo "========================================================================"
    echo "✅✅✅ ALL TESTS PASSED ✅✅✅"
    echo "========================================================================"
    exit 0
else
    echo ""
    echo "========================================================================"
    echo "❌ TESTS FAILED"
    echo "========================================================================"
    echo ""
    echo "Server log (last 50 lines):"
    tail -50 server.log
    exit 1
fi
