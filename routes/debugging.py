"""routes/debugging.py — Mixtape debug/test-only routes

Lets you set up listening-streak scenarios from curl/Postman without
hand-writing a script or waiting for real calendar days to line up.

Only mounted when MIXTAPE_DEBUG_ROUTES=1 (see app.py) — never enable this
outside of local/dev environments, since it lets any caller create users
and backdate listening events.
"""

from flask import Blueprint, request, jsonify
from services.debug_service import simulate_listen

debug_bp = Blueprint("debug", __name__)


@debug_bp.route("/seed-listen", methods=["POST"])
def seed_listen():
    """
    Simulate a user listening to a song on a given (possibly fake) date.

    Body (all fields optional):
        user_id: Reuse an existing user; omit to create a new debug user.
        song_id: Use a specific song; omit to use any existing song.
        date: "YYYY-MM-DD" — the date the listen happened.
        days_ago: Integer number of days before today. Ignored if `date`
            is given.

    Call this repeatedly with the same user_id and different dates to
    build up a multi-day streak scenario.
    """
    data = request.get_json() or {}
    try:
        result = simulate_listen(
            user_id=data.get("user_id"),
            song_id=data.get("song_id"),
            date=data.get("date"),
            days_ago=data.get("days_ago"),
        )
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
