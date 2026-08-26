"""
Savings Goal Tracker Web API Server (Hardened Security Edition)
----------------------------------------------------------------
Serves REST API endpoints with:
- Server-side Gemini API key protection (keys never exposed to browser)
- Rate limiting per IP to prevent API token drain / quota spam
- Input validation & prompt length caps (max 500 characters)
- Error message sanitization to prevent key leaks
- Security HTTP headers (XSS, Frame options, Content-Type, Referrer)
"""

import os
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

import agent

app = Flask(__name__, static_folder=".")
CORS(app)

BASE_DIR = Path(__file__).parent
chat_session = agent.build_chat()

# Simple In-Memory Rate Limiter (IP -> list of timestamps)
RATE_LIMIT_WINDOW = 60  # seconds
MAX_REQUESTS_PER_WINDOW = 20  # max requests per IP in window
ip_request_history = {}


def is_rate_limited(ip_address: str) -> bool:
    """Checks whether an IP has exceeded the allowed rate limit."""
    now = time.time()
    history = ip_request_history.get(ip_address, [])
    # Remove timestamps older than window
    history = [t for t in history if now - t < RATE_LIMIT_WINDOW]
    ip_request_history[ip_address] = history

    if len(history) >= MAX_REQUESTS_PER_WINDOW:
        return True
    history.append(now)
    return False


def sanitize_error(e: Exception) -> str:
    """Strips any potential API key or sensitive backend strings from error messages."""
    err_str = str(e)
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key and api_key in err_str:
        err_str = err_str.replace(api_key, "[REDACTED_API_KEY]")
    return err_str[:200]  # Cap error length


@app.after_request
def add_security_headers(response):
    """Applies security headers to every HTTP response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


def get_full_status():
    """Returns combined state, progress, and catchup data."""
    state_copy = dict(agent.STATE)
    progress_info = None
    catchup_info = None

    if state_copy.get("goal_amount") is not None:
        try:
            progress_info = agent.check_progress()
            if progress_info.get("status") != "error":
                catchup_info = agent.get_catchup_plan()
        except Exception as e:
            progress_info = {"status": "error", "message": sanitize_error(e)}

    return {
        "state": state_copy,
        "progress": progress_info,
        "catchup": catchup_info,
    }


@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(BASE_DIR, filename)


@app.route("/api/state", methods=["GET"])
def api_get_state():
    return jsonify(get_full_status())


@app.route("/api/chat", methods=["POST"])
def api_chat():
    global chat_session
    client_ip = request.remote_addr or "127.0.0.1"

    if is_rate_limited(client_ip):
        return jsonify({"error": "Rate limit exceeded. Please wait a minute before sending more messages."}), 429

    data = request.get_json() or {}
    user_message = data.get("message", "").strip()

    if not user_message:
        return jsonify({"error": "Message cannot be empty."}), 400

    # Input length protection to prevent API token exhaustion
    if len(user_message) > 500:
        return jsonify({"error": "Message exceeds maximum allowed length of 500 characters."}), 400

    try:
        response = chat_session.send_message(user_message)

        # Inspect function calls executed in this turn
        tools_called = []
        try:
            if chat_session.history:
                last_turn = chat_session.history[-2:]
                for msg in last_turn:
                    for part in msg.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            fn_name = part.function_call.name
                            if fn_name and fn_name not in tools_called:
                                tools_called.append(fn_name)
        except Exception:
            pass

        full_status = get_full_status()
        return jsonify({
            "response": response.text,
            "tools_called": tools_called,
            "status": full_status
        })

    except Exception as e:
        return jsonify({"error": f"Agent Error: {sanitize_error(e)}"}), 500


@app.route("/api/deposit", methods=["POST"])
def api_deposit():
    client_ip = request.remote_addr or "127.0.0.1"
    if is_rate_limited(client_ip):
        return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429

    data = request.get_json() or {}
    try:
        amount = float(data.get("amount", 0))
        if amount <= 0 or amount > 100000000:
            return jsonify({"error": "Deposit amount must be between ₹1 and ₹100,000,000."}), 400

        result = agent.log_saving(amount)
        if result.get("status") == "error":
            return jsonify({"error": result.get("message")}), 400

        full_status = get_full_status()
        return jsonify({
            "result": result,
            "status": full_status
        })
    except ValueError:
        return jsonify({"error": "Invalid amount format."}), 400
    except Exception as e:
        return jsonify({"error": sanitize_error(e)}), 500


@app.route("/api/goal", methods=["POST"])
def api_goal():
    global chat_session
    client_ip = request.remote_addr or "127.0.0.1"
    if is_rate_limited(client_ip):
        return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429

    data = request.get_json() or {}
    try:
        amount = float(data.get("amount", 0))
        months = int(data.get("months", 0))

        if amount <= 0 or amount > 1000000000:
            return jsonify({"error": "Target goal amount must be between ₹1 and ₹1,000,000,000."}), 400
        if months <= 0 or months > 360:
            return jsonify({"error": "Goal duration must be between 1 and 360 months."}), 400

        result = agent.set_goal(amount, months)
        full_status = get_full_status()
        return jsonify({
            "result": result,
            "status": full_status
        })
    except ValueError:
        return jsonify({"error": "Invalid input numbers."}), 400
    except Exception as e:
        return jsonify({"error": sanitize_error(e)}), 500


@app.route("/api/reset", methods=["POST"])
def api_reset():
    global chat_session
    client_ip = request.remote_addr or "127.0.0.1"
    if is_rate_limited(client_ip):
        return jsonify({"error": "Rate limit exceeded."}), 429

    try:
        agent.STATE = dict(agent.DEFAULT_STATE)
        agent._save_state(agent.STATE)
        chat_session = agent.build_chat()
        return jsonify({
            "message": "Memory cleared and session reset",
            "status": get_full_status()
        })
    except Exception as e:
        return jsonify({"error": sanitize_error(e)}), 500


if __name__ == "__main__":
    print("Starting Savings Goal Tracker Web Server at http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
