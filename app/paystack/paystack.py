import os
import requests
from datetime import datetime


PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
BASE_URL = "https://api.paystack.co"


def _headers():
    return {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }


def initialize_payment(email, amount_naira, order_id, callback_url, metadata=None):
    """
    Initialize a Paystack transaction.
    Returns (authorization_url, reference) or (None, None) on failure.
    """
    # Paystack requires amount in kobo (naira * 100)
    amount_kobo = int(float(amount_naira) * 100)

    # Unique reference per transaction
    reference = f"ORDER-{order_id}-{int(datetime.utcnow().timestamp())}"

    payload = {
        "email": email,
        "amount": amount_kobo,
        "reference": reference,
        "callback_url": callback_url,
        "currency": "NGN",
        "metadata": metadata or {"order_id": order_id},
    }

    try:
        response = requests.post(
            f"{BASE_URL}/transaction/initialize",
            json=payload,
            headers=_headers(),
            timeout=10
        )
        result = response.json()

        if result.get("status"):
            return (
                result["data"]["authorization_url"],
                result["data"]["reference"]
            )
        else:
            print(f"Paystack init error: {result.get('message')}")
            return None, None

    except requests.RequestException as e:
        print(f"Paystack request failed: {e}")
        return None, None


def verify_payment(reference):
    """
    Verify a Paystack transaction by reference.
    Returns (True, data) if successful, (False, {}) otherwise.
    """
    try:
        response = requests.get(
            f"{BASE_URL}/transaction/verify/{reference}",
            headers=_headers(),
            timeout=10
        )
        result = response.json()

        if result.get("status") and result["data"]["status"] == "success":
            return True, result["data"]
        else:
            print(f"Paystack verify failed: {result.get('message')}")
            return False, {}

    except requests.RequestException as e:
        print(f"Paystack verify request failed: {e}")
        return False, {}
