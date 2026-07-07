"""Combined-rating partner eligibility.

A combined-rating event caps the sum of both partners' DUPR (e.g. a "9.5" cap).
Females and 50+ players get a rating "allowance" (they count as lower). Given your
rating and a candidate, decide whether the pairing fits under the cap.
"""
from __future__ import annotations

from typing import Any

from . import config

EPS = 1e-6


def default_rules() -> dict[str, Any]:
    """AZ Cash / manual-event defaults (from config)."""
    return {
        "gender_target": config.COMBINED_GENDER_TARGET,
        "gender_reduction": config.COMBINED_GENDER_REDUCTION,
        "reduce_by_gender": True,
        "age_threshold": config.COMBINED_AGE_THRESHOLD,
        "age_reduction": config.COMBINED_AGE_REDUCTION,
        "age_threshold_2": None,
        "age_reduction_2": None,
        "reduce_by_age": True,
        "stack": config.COMBINED_STACK,
        "round_one_decimal": config.COMBINED_ROUND_ONE_DECIMAL,
    }


def _r1(x: float, on: bool) -> float:
    return round(x, 1) if on else x


def _age_reduction(age: int | None, rules: dict) -> float:
    if not rules.get("reduce_by_age") or age is None:
        return 0.0
    t2, r2 = rules.get("age_threshold_2"), rules.get("age_reduction_2")
    if t2 and r2 and age >= t2:
        return float(r2)
    t, r = rules.get("age_threshold"), rules.get("age_reduction")
    if t and r and age >= t:
        return float(r)
    return 0.0


def _gender_reduction(gender: str | None, rules: dict) -> float:
    if not rules.get("reduce_by_gender") or not gender:
        return 0.0
    if gender.upper() == str(rules.get("gender_target", "FEMALE")).upper():
        return float(rules.get("gender_reduction") or 0.0)
    return 0.0


def evaluate(my_rating: float, partner_rating: float | None, cap: float | None,
             gender: str | None, age: int | None, rules: dict | None = None) -> dict[str, Any]:
    """Return eligibility detail for pairing you with one candidate at a cap.

    Keys: eligible, combined, reduction, partner_effective, max_partner_rating,
    reasons[], and 'unknown' (True when rating/cap missing).
    """
    rules = rules or default_rules()
    if partner_rating is None or cap is None:
        return {"eligible": None, "unknown": True, "combined": None,
                "reduction": 0.0, "partner_effective": None,
                "max_partner_rating": None, "reasons": []}

    round_on = bool(rules.get("round_one_decimal", True))
    mine = _r1(my_rating, round_on)
    theirs = _r1(partner_rating, round_on)

    g_red = _gender_reduction(gender, rules)
    a_red = _age_reduction(age, rules)
    if rules.get("stack", True):
        reduction = g_red + a_red
    else:
        reduction = max(g_red, a_red)

    reasons = []
    if g_red:
        reasons.append(f"-{g_red:g} female")
    if a_red:
        reasons.append(f"-{a_red:g} age {rules.get('age_threshold')}+")

    partner_eff = theirs - reduction
    combined = mine + partner_eff
    eligible = combined <= cap + EPS
    # Highest actual rating a player with this gender/age could have and still fit.
    max_partner = cap - mine + reduction
    return {
        "eligible": eligible,
        "unknown": False,
        "combined": round(combined, 2),
        "reduction": round(reduction, 2),
        "partner_effective": round(partner_eff, 2),
        "max_partner_rating": round(max_partner, 2),
        "reasons": reasons,
    }
