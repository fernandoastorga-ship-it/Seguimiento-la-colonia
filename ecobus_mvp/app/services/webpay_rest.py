from __future__ import annotations

import os
import requests


def get_webpay_base_url() -> str:
    env = os.getenv("TBK_ENV", "integration").strip().lower()
    if env == "production":
        return "https://webpay3g.transbank.cl"
    return "https://webpay3gint.transbank.cl"


def get_webpay_headers() -> dict:
    commerce_code = os.getenv("TBK_COMMERCE_CODE", "").strip()
    api_key = os.getenv("TBK_API_KEY", "").strip()

    if not commerce_code or not api_key:
        raise RuntimeError("Faltan TBK_COMMERCE_CODE o TBK_API_KEY en variables de entorno.")

    return {
        "Tbk-Api-Key-Id": commerce_code,
        "Tbk-Api-Key-Secret": api_key,
        "Content-Type": "application/json",
    }


def webpay_create_transaction(
    buy_order: str,
    session_id: str,
    amount: int,
    return_url: str,
) -> dict:
    url = f"{get_webpay_base_url()}/rswebpaytransaction/api/webpay/v1.2/transactions"

    payload = {
        "buy_order": buy_order,
        "session_id": session_id,
        "amount": amount,
        "return_url": return_url,
    }

    response = requests.post(
        url,
        headers=get_webpay_headers(),
        json=payload,
        timeout=30,
    )

    response.raise_for_status()
    return response.json()


def webpay_commit_transaction(token_ws: str) -> dict:
    url = f"{get_webpay_base_url()}/rswebpaytransaction/api/webpay/v1.2/transactions/{token_ws}"

    response = requests.put(
        url,
        headers=get_webpay_headers(),
        timeout=30,
    )

    response.raise_for_status()
    return response.json()
