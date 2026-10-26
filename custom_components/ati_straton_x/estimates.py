"""Schedule-only channel estimates; never device output readback."""
from datetime import datetime

CHANNELS = (
    ("uv_violet", "UV/Violet"),
    ("royal_blue", "Royal blue"),
    ("blue", "Blue"),
    ("horti_white", "Cyan/Horti white"),
    ("white", "White"),
    ("red", "Red"),
)
LIMITATIONS = "Does not include moonlight, acclimation, or day-length adjustments"


def estimate_channels(data):
    """Return six percentages and a reason, using the last light-clock snapshot."""
    remaining = data.get("live_remaining")
    if type(remaining) is not int or remaining < 0:
        return None, "live_mode_unknown"
    if remaining > 0:
        return None, "live_mode_active"
    try:
        clock = datetime.fromisoformat(data["local_time"])
    except (KeyError, TypeError, ValueError):
        return None, "clock_unknown"
    schedule = data.get("schedule")
    nodes = schedule.get("nodes") if isinstance(schedule, dict) else None
    if not isinstance(nodes, list) or len(nodes) < 2:
        return None, "schedule_invalid"
    previous = -1
    for node in nodes:
        if not isinstance(node, dict):
            return None, "schedule_invalid"
        stamp, values = node.get("timestamp"), node.get("channelValues")
        if (type(stamp) is not int or not previous < stamp < 86400
                or not isinstance(values, list) or len(values) != 6
                or any(type(v) is not int or not 0 <= v <= 1023 for v in values)):
            return None, "schedule_invalid"
        previous = stamp
    now = clock.hour * 3600 + clock.minute * 60 + clock.second
    for node in nodes:
        if now == node["timestamp"]:
            return [round(v * 100 / 1023, 1) for v in node["channelValues"]], "schedule_estimate"
    if now < nodes[0]["timestamp"] or now > nodes[-1]["timestamp"]:
        # Only infer overnight darkness when both boundary nodes explicitly
        # request darkness. Do not invent wraparound behavior for other plans.
        if not any(nodes[0]["channelValues"] + nodes[-1]["channelValues"]):
            return [0.0] * 6, "schedule_estimate"
        return None, "outside_schedule"
    for left, right in zip(nodes, nodes[1:]):
        if left["timestamp"] < now < right["timestamp"]:
            fraction = (now - left["timestamp"]) / (right["timestamp"] - left["timestamp"])
            return [
                round((a + (b - a) * fraction) * 100 / 1023, 1)
                for a, b in zip(left["channelValues"], right["channelValues"])
            ], "schedule_estimate"
    return None, "schedule_invalid"
