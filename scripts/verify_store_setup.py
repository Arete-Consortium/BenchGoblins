#!/usr/bin/env python3
"""Validate that App Store Connect, RevenueCat, and local config are consistent.

Checks:
    1. ASC API: Do the 3 subscription products exist?
    2. RevenueCat API: Products, "pro" entitlement, "default" offering exist?
    3. app.json: No placeholder values, RevenueCat key set?
    4. eas.json: No placeholder values, Apple IDs set?

Exits non-zero on any failure.

Usage:
    python scripts/verify_store_setup.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import jwt
import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EXPECTED_PRODUCTS = {
    "benchgoblins_pro_weekly",
    "benchgoblins_pro_monthly",
    "benchgoblins_pro_annual",
}
EXPECTED_ENTITLEMENT = "pro"
EXPECTED_OFFERING = "default"
BUNDLE_ID = "com.benchgoblins.app"

MOBILE_DIR = Path(__file__).resolve().parent.parent / "src" / "mobile"
APP_JSON = MOBILE_DIR / "app.json"
EAS_JSON = MOBILE_DIR / "eas.json"

ASC_BASE = "https://api.appstoreconnect.apple.com/v1"
RC_BASE = "https://api.revenuecat.com/v2"

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------
_results: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    _results.append((name, passed, detail))
    return passed


# ---------------------------------------------------------------------------
# Credential loading
# ---------------------------------------------------------------------------


def load_credentials() -> dict | None:
    cred_path = Path(__file__).resolve().parent / "config" / "store_credentials.json"
    if not cred_path.exists():
        print(f"WARNING: {cred_path} not found. Skipping API checks.")
        return None
    with open(cred_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# ASC token
# ---------------------------------------------------------------------------


def make_asc_token(apple_cfg: dict) -> str | None:
    key_path = Path(__file__).resolve().parent.parent / apple_cfg["private_key_path"]
    if not key_path.exists():
        return None
    private_key = key_path.read_text()
    now = int(time.time())
    payload = {
        "iss": apple_cfg["issuer_id"],
        "iat": now,
        "exp": now + 1200,
        "aud": "appstoreconnect-v1",
    }
    headers = {"alg": "ES256", "kid": apple_cfg["key_id"], "typ": "JWT"}
    return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)


# ---------------------------------------------------------------------------
# ASC verification
# ---------------------------------------------------------------------------


def verify_asc(creds: dict) -> None:
    print("\nApp Store Connect:")
    apple = creds.get("apple", {})

    if not apple.get("key_id") or not apple.get("issuer_id"):
        check("ASC credentials", False, "key_id or issuer_id missing")
        return

    token = make_asc_token(apple)
    if not token:
        check("ASC API key file", False, f"{apple.get('private_key_path')} not found")
        return
    check("ASC API key file", True)

    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Find app
        app_id = apple.get("asc_app_id", "")
        if app_id:
            resp = requests.get(f"{ASC_BASE}/apps/{app_id}", headers=headers)
            check("ASC app exists", resp.status_code == 200, f"ID: {app_id}")
        else:
            resp = requests.get(
                f"{ASC_BASE}/apps",
                headers=headers,
                params={"filter[bundleId]": BUNDLE_ID},
            )
            data = resp.json()
            apps = data.get("data", [])
            found = len(apps) > 0
            check("ASC app exists", found, BUNDLE_ID)
            if found:
                app_id = apps[0]["id"]

        if not app_id:
            check("ASC subscriptions", False, "App not found, cannot check subs")
            return

        # Check subscription groups
        resp = requests.get(
            f"{ASC_BASE}/apps/{app_id}/subscriptionGroups", headers=headers
        )
        groups = resp.json().get("data", [])
        check("ASC subscription groups", len(groups) > 0, f"{len(groups)} group(s)")

        # Check individual subscriptions
        found_products: set[str] = set()
        for group in groups:
            group_id = group["id"]
            resp = requests.get(
                f"{ASC_BASE}/subscriptionGroups/{group_id}/subscriptions",
                headers=headers,
            )
            for sub in resp.json().get("data", []):
                pid = sub.get("attributes", {}).get("productId", "")
                if pid in EXPECTED_PRODUCTS:
                    found_products.add(pid)

        for pid in sorted(EXPECTED_PRODUCTS):
            check(f"ASC product: {pid}", pid in found_products)

    except requests.RequestException as e:
        check("ASC API connection", False, str(e))


# ---------------------------------------------------------------------------
# RevenueCat verification
# ---------------------------------------------------------------------------


def verify_revenuecat(creds: dict) -> None:
    print("\nRevenueCat:")
    rc = creds.get("revenuecat", {})

    if not rc.get("v2_secret_key") or not rc.get("project_id"):
        check("RC credentials", False, "v2_secret_key or project_id missing")
        return

    secret_key = rc["v2_secret_key"]
    project_id = rc["project_id"]
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }

    try:
        # Check products
        resp = requests.get(
            f"{RC_BASE}/projects/{project_id}/products", headers=headers
        )
        resp.raise_for_status()
        products = resp.json().get("items", [])
        found_products = {p.get("store_identifier", "") for p in products}

        for pid in sorted(EXPECTED_PRODUCTS):
            check(f"RC product: {pid}", pid in found_products)

        # Check entitlements
        resp = requests.get(
            f"{RC_BASE}/projects/{project_id}/entitlements", headers=headers
        )
        resp.raise_for_status()
        entitlements = resp.json().get("items", [])
        ent_keys = {e.get("lookup_key", "") for e in entitlements}
        check(
            f'RC entitlement: "{EXPECTED_ENTITLEMENT}"',
            EXPECTED_ENTITLEMENT in ent_keys,
        )

        # Check offerings
        resp = requests.get(
            f"{RC_BASE}/projects/{project_id}/offerings", headers=headers
        )
        resp.raise_for_status()
        offerings = resp.json().get("items", [])
        off_keys = {o.get("lookup_key", "") for o in offerings}
        check(
            f'RC offering: "{EXPECTED_OFFERING}"',
            EXPECTED_OFFERING in off_keys,
        )

    except requests.RequestException as e:
        check("RC API connection", False, str(e))


# ---------------------------------------------------------------------------
# Local config verification
# ---------------------------------------------------------------------------


def verify_app_json() -> None:
    print("\napp.json:")
    with open(APP_JSON) as f:
        data = json.load(f)

    extra = data.get("expo", {}).get("extra", {})

    # RevenueCat key
    rc_key = extra.get("revenueCatApiKey", {}).get("ios", "")
    check(
        "RC API key configured",
        bool(rc_key) and not rc_key.startswith("YOUR_"),
        rc_key[:20] + "..." if len(rc_key) > 20 else rc_key,
    )

    # EAS project ID
    eas_id = extra.get("eas", {}).get("projectId", "")
    check("EAS project ID set", bool(eas_id), eas_id or "(empty)")

    # No placeholders
    content = APP_JSON.read_text()
    has_placeholders = "YOUR_" in content
    check("No placeholder values in app.json", not has_placeholders)


def verify_eas_json() -> None:
    print("\neas.json:")
    with open(EAS_JSON) as f:
        data = json.load(f)

    ios_submit = data.get("submit", {}).get("production", {}).get("ios", {})

    for field in ("appleId", "ascAppId", "appleTeamId"):
        value = ios_submit.get(field, "")
        is_set = bool(value) and not value.startswith("YOUR_")
        check(f"eas.json {field}", is_set, value or "(empty)")

    content = EAS_JSON.read_text()
    has_placeholders = "YOUR_" in content
    check("No placeholder values in eas.json", not has_placeholders)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("BenchGoblins Store Setup Verification")
    print("=" * 50)

    creds = load_credentials()

    if creds:
        verify_asc(creds)
        verify_revenuecat(creds)

    verify_app_json()
    verify_eas_json()

    # Summary
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total = len(_results)

    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{total} passed, {failed} failed")

    if failed:
        print("\nFailed checks:")
        for name, ok, detail in _results:
            if not ok:
                msg = f"  - {name}"
                if detail:
                    msg += f": {detail}"
                print(msg)
        sys.exit(1)
    else:
        print("\nAll checks passed!")


if __name__ == "__main__":
    main()
