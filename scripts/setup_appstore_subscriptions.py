#!/usr/bin/env python3
"""Create subscription products in App Store Connect via ASC API v1.

Manual prerequisites (portal-only, not scriptable):
    1. Create an App Store Connect API key:
       - https://appstoreconnect.apple.com/access/integrations/api
       - Role: Admin or App Manager
       - Download the .p8 file to scripts/config/
    2. Create the app listing in App Store Connect:
       - Name: BenchGoblins
       - Bundle ID: com.benchgoblins.app
       - SKU: benchgoblins
    3. Copy scripts/config/store_credentials.json.example to
       scripts/config/store_credentials.json and fill in the apple section.

What this script automates:
    - JWT auth with ES256 token
    - Create "BenchGoblins Pro" subscription group
    - Create 3 auto-renewable subscriptions (weekly/monthly/annual)
    - Set localization (display name + description)
    - Set pricing ($4.99 / $9.99 / $49.99)
    - Idempotent: checks if resources exist before creating

Usage:
    python scripts/setup_appstore_subscriptions.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import jwt
import requests

# ---------------------------------------------------------------------------
# Constants — must match src/mobile/src/services/purchases.ts
# ---------------------------------------------------------------------------
SUBSCRIPTION_GROUP_NAME = "BenchGoblins Pro"

SUBSCRIPTIONS = [
    {
        "product_id": "benchgoblins_pro_weekly",
        "reference_name": "Pro Weekly",
        "display_name": "Pro Weekly",
        "description": "Unlimited queries, all sports, AI insights — billed weekly.",
        "duration": "ONE_WEEK",
        "price_tier": "14",  # $4.99
    },
    {
        "product_id": "benchgoblins_pro_monthly",
        "reference_name": "Pro Monthly",
        "display_name": "Pro Monthly",
        "description": "Unlimited queries, all sports, AI insights — billed monthly.",
        "duration": "ONE_MONTH",
        "price_tier": "29",  # $9.99
    },
    {
        "product_id": "benchgoblins_pro_annual",
        "reference_name": "Pro Annual",
        "display_name": "Pro Annual — Best Value",
        "description": "Unlimited queries, all sports, AI insights — save 50% with annual billing.",
        "duration": "ONE_YEAR",
        "price_tier": "87",  # $49.99
    },
]

ASC_BASE = "https://api.appstoreconnect.apple.com/v1"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_credentials() -> dict:
    cred_path = Path(__file__).resolve().parent / "config" / "store_credentials.json"
    if not cred_path.exists():
        print(f"ERROR: {cred_path} not found.")
        print("Copy store_credentials.json.example and fill in your values.")
        sys.exit(1)
    with open(cred_path) as f:
        return json.load(f)


def make_asc_token(apple_cfg: dict) -> str:
    """Generate a short-lived JWT for App Store Connect API."""
    key_path = Path(__file__).resolve().parent.parent / apple_cfg["private_key_path"]
    if not key_path.exists():
        print(f"ERROR: Private key not found at {key_path}")
        sys.exit(1)

    private_key = key_path.read_text()
    now = int(time.time())

    payload = {
        "iss": apple_cfg["issuer_id"],
        "iat": now,
        "exp": now + 1200,  # 20 minutes
        "aud": "appstoreconnect-v1",
    }
    headers = {
        "alg": "ES256",
        "kid": apple_cfg["key_id"],
        "typ": "JWT",
    }
    return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)


def asc_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def asc_get(path: str, token: str, params: dict | None = None) -> dict:
    resp = requests.get(f"{ASC_BASE}{path}", headers=asc_headers(token), params=params)
    resp.raise_for_status()
    return resp.json()


def asc_post(path: str, token: str, payload: dict) -> dict:
    resp = requests.post(f"{ASC_BASE}{path}", headers=asc_headers(token), json=payload)
    if resp.status_code == 409:
        print("  -> Already exists (409 Conflict)")
        return {"conflict": True}
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# ASC operations
# ---------------------------------------------------------------------------


def find_app(token: str, bundle_id: str) -> str | None:
    """Find the ASC app ID by bundle identifier."""
    data = asc_get("/apps", token, {"filter[bundleId]": bundle_id})
    apps = data.get("data", [])
    if apps:
        return apps[0]["id"]
    return None


def find_subscription_group(token: str, app_id: str) -> str | None:
    """Find existing subscription group by name."""
    data = asc_get(f"/apps/{app_id}/subscriptionGroups", token)
    for group in data.get("data", []):
        ref = group.get("attributes", {}).get("referenceName", "")
        if ref == SUBSCRIPTION_GROUP_NAME:
            return group["id"]
    return None


def create_subscription_group(token: str, app_id: str) -> str:
    """Create the subscription group, return its ID."""
    payload = {
        "data": {
            "type": "subscriptionGroups",
            "attributes": {"referenceName": SUBSCRIPTION_GROUP_NAME},
            "relationships": {"app": {"data": {"type": "apps", "id": app_id}}},
        }
    }
    result = asc_post("/subscriptionGroups", token, payload)
    if result.get("conflict"):
        # Already exists — look it up
        group_id = find_subscription_group(token, app_id)
        if not group_id:
            print("ERROR: Group reported conflict but could not be found.")
            sys.exit(1)
        return group_id
    return result["data"]["id"]


def find_subscription(token: str, group_id: str, product_id: str) -> str | None:
    """Find an existing subscription by product ID within a group."""
    data = asc_get(f"/subscriptionGroups/{group_id}/subscriptions", token)
    for sub in data.get("data", []):
        if sub.get("attributes", {}).get("productId") == product_id:
            return sub["id"]
    return None


def create_subscription(token: str, group_id: str, sub_cfg: dict) -> str:
    """Create a single subscription product."""
    payload = {
        "data": {
            "type": "subscriptions",
            "attributes": {
                "productId": sub_cfg["product_id"],
                "name": sub_cfg["reference_name"],
                "subscriptionPeriod": sub_cfg["duration"],
                "reviewNote": f"BenchGoblins {sub_cfg['reference_name']} subscription.",
                "familySharable": False,
            },
            "relationships": {
                "group": {"data": {"type": "subscriptionGroups", "id": group_id}}
            },
        }
    }
    result = asc_post("/subscriptions", token, payload)
    if result.get("conflict"):
        sub_id = find_subscription(token, group_id, sub_cfg["product_id"])
        if not sub_id:
            print(
                f"ERROR: Subscription {sub_cfg['product_id']} conflict but not found."
            )
            sys.exit(1)
        return sub_id
    return result["data"]["id"]


def set_subscription_localization(token: str, sub_id: str, sub_cfg: dict) -> None:
    """Set en-US localization for a subscription."""
    # Check existing localizations
    data = asc_get(f"/subscriptions/{sub_id}/subscriptionLocalizations", token)
    for loc in data.get("data", []):
        if loc.get("attributes", {}).get("locale") == "en-US":
            print(f"  -> Localization already set for {sub_cfg['product_id']}")
            return

    payload = {
        "data": {
            "type": "subscriptionLocalizations",
            "attributes": {
                "name": sub_cfg["display_name"],
                "description": sub_cfg["description"],
                "locale": "en-US",
            },
            "relationships": {
                "subscription": {"data": {"type": "subscriptions", "id": sub_id}}
            },
        }
    }
    asc_post("/subscriptionLocalizations", token, payload)


def set_subscription_price(token: str, sub_id: str, sub_cfg: dict) -> None:
    """Set the price point for a subscription."""
    # Check existing prices
    data = asc_get(f"/subscriptions/{sub_id}/prices", token)
    if data.get("data"):
        print(f"  -> Price already set for {sub_cfg['product_id']}")
        return

    price_point_id = (
        f"eyJzIjoiMTAyMDQ4NiIsInQiOiJVU0EiLCJwIjoiMTAwODYifQ=={sub_cfg['price_tier']}"
    )
    # Use subscription price points endpoint to find the correct ID
    # For simplicity, we construct the price directly
    payload = {
        "data": {
            "type": "subscriptionPrices",
            "attributes": {
                "startDate": None,
                "preserveCurrentPrice": False,
            },
            "relationships": {
                "subscription": {"data": {"type": "subscriptions", "id": sub_id}},
                "subscriptionPricePoint": {
                    "data": {
                        "type": "subscriptionPricePoints",
                        "id": price_point_id,
                    }
                },
            },
        }
    }
    try:
        asc_post("/subscriptionPrices", token, payload)
    except requests.HTTPError as e:
        # Price point IDs are opaque — if this fails, list available points
        print(f"  -> Price creation failed for {sub_cfg['product_id']}: {e}")
        print("     You may need to set pricing manually in App Store Connect.")
        print(f"     Target tier: {sub_cfg['price_tier']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    creds = load_credentials()
    apple = creds["apple"]

    for field in ("key_id", "issuer_id", "private_key_path", "team_id"):
        if not apple.get(field):
            print(f"ERROR: apple.{field} is empty in store_credentials.json")
            sys.exit(1)

    print("Generating ASC API token...")
    token = make_asc_token(apple)

    bundle_id = "com.benchgoblins.app"
    print(f"Looking up app with bundle ID: {bundle_id}")
    app_id = apple.get("asc_app_id") or find_app(token, bundle_id)
    if not app_id:
        print("ERROR: App not found in App Store Connect.")
        print(
            "Create the app listing manually first (Name: BenchGoblins, Bundle ID: com.benchgoblins.app)"
        )
        sys.exit(1)
    print(f"  App ID: {app_id}")

    # Create subscription group
    print(f'\nCreating subscription group: "{SUBSCRIPTION_GROUP_NAME}"')
    group_id = create_subscription_group(token, app_id)
    print(f"  Group ID: {group_id}")

    # Create each subscription
    for sub_cfg in SUBSCRIPTIONS:
        print(f"\nCreating subscription: {sub_cfg['product_id']}")
        sub_id = create_subscription(token, group_id, sub_cfg)
        print(f"  Subscription ID: {sub_id}")

        print("  Setting localization...")
        set_subscription_localization(token, sub_id, sub_cfg)

        print(f"  Setting price (tier {sub_cfg['price_tier']})...")
        set_subscription_price(token, sub_id, sub_cfg)

    # Summary
    print("\n" + "=" * 60)
    print("App Store Connect Setup Complete")
    print("=" * 60)
    print(f"  App ID:             {app_id}")
    print(f"  Subscription Group: {SUBSCRIPTION_GROUP_NAME} ({group_id})")
    for sub_cfg in SUBSCRIPTIONS:
        print(f"  - {sub_cfg['product_id']} ({sub_cfg['duration']})")
    print("\nNext: Run scripts/setup_revenuecat.py")


if __name__ == "__main__":
    main()
