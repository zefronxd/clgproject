"""Editable phrase list for local distress-signal checks.

Phrase matching is a prompt to show support resources, not a diagnosis.
"""

import re


DISTRESS_PHRASES = [
    "can't go on",
    "cannot go on",
    "don't want to live",
    "do not want to live",
    "want to die",
    "wish i were dead",
    "wish i was dead",
    "end my life",
    "ending my life",
    "kill myself",
    "hurt myself",
    "harm myself",
    "self harm",
    "self-harm",
    "suicidal",
    "no reason to live",
    "hopelessness",
    "no way out",
    "can't take it anymore",
    "cannot take it anymore",
    "better off dead",
    "everyone would be better off without me",
    "i feel hopeless",
    "there is no hope",
    "nothing will ever get better",
    "i can't keep myself safe",
]


def matches_distress_phrase(text):
    normalized = text.casefold()
    for phrase in DISTRESS_PHRASES:
        pattern = re.escape(phrase).replace(r"\ ", r"\s+")
        if re.search(r"(?<!\w)" + pattern + r"(?!\w)", normalized):
            return True
    return False
