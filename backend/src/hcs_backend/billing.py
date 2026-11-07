"""Stripe Checkout for the landing page paywall (test mode only).

Plans are defined here with inline price_data, so no product needs to be created in the Stripe dashboard
first. Live keys are refused: this is a hackathon demo, nobody should be charged for real.
"""

from __future__ import annotations

from typing import Any

import stripe

PLANS: dict[str, dict[str, Any]] = {
    "pro": {
        "mode": "subscription",
        "name": "H Companion Pro",
        "description": "Unlimited assisted sessions for your users, support dashboard and difficulty grouping.",
        "unit_amount": 4900,  # EUR cents, per month
        "recurring": {"interval": "month"},
    },
    "fixpack": {
        "mode": "payment",
        "name": "H Companion Fix pack",
        "description": "100 verified fixes. A credit is used only when the result is observed, never on failure.",
        "unit_amount": 7900,  # EUR cents, one-time
        "recurring": None,
    },
}


class BillingNotConfigured(RuntimeError):
    pass


def create_checkout(plan: str, secret_key: str, landing_url: str) -> str:
    """Create a Checkout Session and return its URL."""
    if not secret_key:
        raise BillingNotConfigured("Stripe is not configured: set STRIPE_SECRET_KEY=sk_test_... in backend/.env")
    if not secret_key.startswith(("sk_test_", "rk_test_")):
        raise BillingNotConfigured("Only Stripe test keys (sk_test_...) are accepted for the demo")
    p = PLANS[plan]
    price_data: dict[str, Any] = {
        "currency": "eur",
        "unit_amount": p["unit_amount"],
        "product_data": {"name": p["name"], "description": p["description"]},
    }
    if p["recurring"]:
        price_data["recurring"] = p["recurring"]
    base = landing_url.rstrip("/")
    session = stripe.checkout.Session.create(
        api_key=secret_key,
        mode=p["mode"],
        line_items=[{"price_data": price_data, "quantity": 1}],
        success_url=f"{base}/?checkout=success&plan={plan}#pricing",
        cancel_url=f"{base}/?checkout=cancel#pricing",
        metadata={"plan": plan, "source": "hcs-landing"},
    )
    return session.url
