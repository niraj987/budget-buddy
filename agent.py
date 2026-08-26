"""
Savings Goal Tracker Agent
---------------------------
An agentic assistant (built on Google Gemini function calling) that helps
a user save toward a target amount by a target date.

Why this is an AGENT and not a chatbot:
  - Plan-act loop: Gemini's automatic function calling lets the model
    decide which tool to call, look at the result, and decide the NEXT
    tool to call, before it ever answers the user. E.g. after log_saving
    it decides on its own to also call check_progress, and if the user is
    behind, it decides to also call get_catchup_plan -- all in one turn.
  - Tools: set_goal, log_saving, check_progress, get_catchup_plan
    (4 tools, at least 2 required).
  - Memory: the goal + full savings history persist to memory.json across
    runs, AND the Gemini chat session keeps full conversation history so
    later turns ("how am I doing?") can refer back to earlier ones
    ("I saved ₹200 last week") without repeating them.
"""

import os
import json
import datetime as dt
from pathlib import Path

from dotenv import load_dotenv
import google.generativeai as genai

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------
import tempfile

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
    MEMORY_FILE = Path(tempfile.gettempdir()) / "memory.json"
else:
    MEMORY_FILE = Path(__file__).parent / "memory.json"

DEFAULT_STATE = {
    "goal_amount": None,
    "goal_months": None,
    "start_date": None,
    "deadline_date": None,
    "saved_total": 0.0,
    "history": [],  # list of {date, amount}
}

CURRENCY_SYMBOL = "₹"


def format_inr(amount: float) -> str:
    """Formats a numeric amount for display in Indian rupees."""
    return f"{CURRENCY_SYMBOL}{amount:,.2f}"


def _load_state() -> dict:
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return dict(DEFAULT_STATE)


def _save_state(state: dict) -> None:
    with open(MEMORY_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


STATE = _load_state()

# --------------------------------------------------------------------------
# TOOLS
# Plain python functions. Gemini's automatic function calling reads the
# type hints + docstring to build the schema, calls the function itself,
# and feeds the result back to the model so it can decide what to do next.
# --------------------------------------------------------------------------


def set_goal(amount: float, months: int) -> dict:
    """Sets or replaces the user's savings goal.

    Args:
        amount: The total amount of money the user wants to save.
        months: The number of months the user has to reach the goal.

    Returns:
        A dict confirming the new goal, the deadline date, and the
        required average monthly saving.
    """
    today = dt.date.today()
    deadline = today + dt.timedelta(days=30 * months)

    STATE["goal_amount"] = amount
    STATE["goal_months"] = months
    STATE["start_date"] = str(today)
    STATE["deadline_date"] = str(deadline)
    STATE["saved_total"] = 0.0
    STATE["history"] = []
    _save_state(STATE)

    monthly_needed = round(amount / months, 2) if months else amount

    return {
        "status": "goal_set",
        "goal_amount": amount,
        "months": months,
        "deadline_date": str(deadline),
        "required_monthly_saving": monthly_needed,
    }


def log_saving(amount: float) -> dict:
    """Records a new savings deposit made by the user.

    Args:
        amount: The amount of money the user just saved/deposited.

    Returns:
        A dict with the updated total saved and remaining amount needed.
    """
    if STATE["goal_amount"] is None:
        return {"status": "error", "message": "No goal set yet. Call set_goal first."}

    STATE["saved_total"] = round(STATE["saved_total"] + amount, 2)
    STATE["history"].append({"date": str(dt.date.today()), "amount": amount})
    _save_state(STATE)

    remaining = round(STATE["goal_amount"] - STATE["saved_total"], 2)

    return {
        "status": "saving_logged",
        "amount_logged": amount,
        "saved_total": STATE["saved_total"],
        "remaining_amount": max(remaining, 0),
        "goal_reached": remaining <= 0,
    }


def check_progress() -> dict:
    """Checks whether the user is on track to reach their goal by the deadline.

    Computes elapsed time, expected savings pace, and whether the user is
    ahead, on track, or behind schedule.

    Returns:
        A dict with progress stats: months elapsed, months remaining,
        saved_total, remaining_amount, expected_saved_by_now,
        on_track (bool), and required_monthly_saving_going_forward.
    """
    if STATE["goal_amount"] is None:
        return {"status": "error", "message": "No goal set yet. Call set_goal first."}

    today = dt.date.today()
    start = dt.date.fromisoformat(STATE["start_date"])
    deadline = dt.date.fromisoformat(STATE["deadline_date"])

    total_days = max((deadline - start).days, 1)
    elapsed_days = max((today - start).days, 0)
    remaining_days = max((deadline - today).days, 0)

    months_elapsed = round(elapsed_days / 30, 1)
    months_remaining = max(round(remaining_days / 30, 1), 0.1)

    expected_saved_by_now = round(STATE["goal_amount"] * (elapsed_days / total_days), 2)
    remaining_amount = round(STATE["goal_amount"] - STATE["saved_total"], 2)
    on_track = STATE["saved_total"] >= expected_saved_by_now

    required_monthly_going_forward = round(max(remaining_amount, 0) / months_remaining, 2)

    return {
        "status": "progress_checked",
        "saved_total": STATE["saved_total"],
        "goal_amount": STATE["goal_amount"],
        "remaining_amount": max(remaining_amount, 0),
        "months_elapsed": months_elapsed,
        "months_remaining": months_remaining,
        "expected_saved_by_now": expected_saved_by_now,
        "on_track": on_track,
        "required_monthly_saving_going_forward": required_monthly_going_forward,
        "goal_reached": remaining_amount <= 0,
    }


def get_catchup_plan() -> dict:
    """Builds a catch-up plan for when the user has fallen behind schedule.

    Splits the shortfall over the remaining months (and offers an
    accelerated sprint option over up to 3 months) so the user can still
    hit the deadline.

    Returns:
        A dict with the shortfall amount, a standard catch-up monthly
        figure, and an accelerated sprint monthly figure.
    """
    progress = check_progress()
    if progress.get("status") == "error":
        return progress

    if progress["on_track"] or progress["goal_reached"]:
        return {
            "status": "no_catchup_needed",
            "message": "User is currently on track or has already reached the goal.",
        }

    shortfall = round(progress["expected_saved_by_now"] - progress["saved_total"], 2)
    months_remaining = max(progress["months_remaining"], 0.1)
    remaining_amount = progress["remaining_amount"]

    standard_catchup_monthly = round(remaining_amount / months_remaining, 2)
    sprint_months = min(3, months_remaining)
    sprint_monthly = round(remaining_amount / sprint_months, 2)

    return {
        "status": "catchup_plan",
        "shortfall_vs_schedule": shortfall,
        "remaining_amount": remaining_amount,
        "months_remaining": months_remaining,
        "standard_catchup_monthly_saving": standard_catchup_monthly,
        "accelerated_sprint_months": sprint_months,
        "accelerated_sprint_monthly_saving": sprint_monthly,
    }


TOOLS = [set_goal, log_saving, check_progress, get_catchup_plan]

# --------------------------------------------------------------------------
# AGENT
# --------------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are Budget Buddy, an AI savings & finance agent. You help the
user save toward a target amount by a target date.

You have four tools: set_goal, log_saving, check_progress, get_catchup_plan.

Behave like an agent, not a plain chatbot:
- When the user states a goal (amount + timeframe), call set_goal.
- When the user reports money saved, call log_saving, THEN automatically
  call check_progress to see if they're still on track. Do this without
  waiting to be asked again.
- If check_progress shows the user is behind schedule (on_track is false
  and the goal is not reached), automatically call get_catchup_plan too,
  and clearly present the catch-up options to the user.
- If the user asks generic questions like "how am I doing", call
  check_progress (and get_catchup_plan if it turns out they're behind).
- Always reason from the ACTUAL tool results, never guess numbers.
- Keep replies short, warm, and encouraging, but be honest about being
    behind. Display every currency amount in Indian rupees using the ₹ symbol.
- If no goal has been set yet and the user asks about progress, ask them
  to set a goal first.
"""

MODEL_NAME = "gemini-3.6-flash"


def build_chat():
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        tools=TOOLS,
        system_instruction=SYSTEM_INSTRUCTION,
    )
    chat = model.start_chat(enable_automatic_function_calling=True)
    return chat


def main():
    global STATE
    print("=" * 60)
    print(" Savings Goal Tracker Agent (Gemini)")
    print(" Type 'quit' to exit. Type 'reset' to clear memory.")
    print("=" * 60)

    if STATE.get("goal_amount"):
        print(
            f"[memory] Existing goal found: save {format_inr(STATE['goal_amount'])} "
            f"by {STATE['deadline_date']} "
            f"(saved so far: {format_inr(STATE['saved_total'])})"
        )

    chat = build_chat()

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break
        if user_input.lower() == "reset":
            STATE = dict(DEFAULT_STATE)
            _save_state(STATE)
            chat = build_chat()
            print("[memory cleared]")
            continue

        response = chat.send_message(user_input)
        print(f"\nAgent: {response.text}")


if __name__ == "__main__":
    main()
