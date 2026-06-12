from __future__ import annotations


# Maps business-goal keywords to customer-centric phrasings.
# Key   = lowercase substring that may appear in a goal string.
# Value = ordered alternatives; index 0 is used by default.
GOAL_TRANSLATIONS: dict[str, list[str]] = {
    "signups": ["take the first step", "try it today", "get started for free"],
    "signup": ["take the first step", "try it today", "get started for free"],
    "demos": ["see it in action", "get a personal walkthrough", "talk to someone who knows"],
    "demo": ["see it in action", "get a personal walkthrough"],
    "purchases": ["find the right fit", "get what you actually need"],
    "purchase": ["find the right fit", "get what you actually need"],
    "downloads": ["get it on your device", "start using it today"],
    "download": ["get it on your device", "start using it today"],
    "bookings": ["lock in your time", "reserve your spot today"],
    "booking": ["lock in your time", "reserve your spot today"],
    "activations": ["start making progress", "experience it yourself"],
    "activation": ["start making progress", "experience it yourself"],
    "conversions": ["make the move", "take the next step"],
    "conversion": ["make the move", "take the next step"],
    "trials": ["give it a real try", "test it with no commitment"],
    "trial": ["give it a real try", "test it with no commitment"],
    "visits": ["come see for yourself", "stop by and experience it"],
    "visit": ["come see for yourself", "stop by"],
    "donations": ["make a difference today", "contribute to something bigger"],
    "donation": ["make a difference today", "contribute to something bigger"],
    "subscriptions": ["join and stay connected", "become a member"],
    "subscription": ["join and stay connected", "become a member"],
    "retention": ["keep growing with us", "build on what is working"],
    "referrals": ["spread the word", "invite someone who would love this"],
    "referral": ["spread the word", "invite someone who would love this"],
    "appointments": ["book your time", "find a slot that works for you"],
    "appointment": ["book your time", "find a slot that works for you"],
}


def translate_goal(goal: str) -> str:
    """Convert a business-internal campaign goal into customer-facing language.

    Scans the goal string for known business keywords and returns the
    most natural customer-centric phrasing. Falls back to the original
    goal string unchanged if no keyword is matched — this is intentional,
    since not every goal needs translation.

    Examples:
        "increase app signups"       -> "take the first step"
        "book more demos"            -> "see it in action"
        "drive subscription growth"  -> "join and stay connected"
        "launch new product line"    -> "launch new product line"  (unchanged)
    """
    lower = goal.lower()
    for keyword, alternatives in GOAL_TRANSLATIONS.items():
        if keyword in lower:
            return alternatives[0]
    return goal
