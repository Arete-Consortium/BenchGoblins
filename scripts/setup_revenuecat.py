#!/usr/bin/env python3
"""Configure RevenueCat products, entitlements, offerings, and packages via REST API v2.

Manual prerequisites (portal-only, not scriptable):
    1. Create a RevenueCat account at https://app.revenuecat.com
    2. Create a project named "BenchGoblins"
    3. Add an iOS app:
       - Bundle ID: com.benchgoblins.app
       - App Store Connect shared secret (from ASC > App > In-App Purchases > Manage)
    4. Generate a V2 secret API key:
       - Project Settings > API Keys > + New
    5. Copy scripts/config/store_credentials.json.example to
       scripts/config/store_credentials.json and fill in the revenuecat section:
       - v2_secret_key: the sk_... key from step 4
       - project_id: from the URL (https://app.revenuecat.com/projects/<id>)
       - ios_app_id: from the app settings page
       - public_api_key_ios: the appl_... public key (for mobile SDK)

What this script automates:
    - Create 3 products (app_store type, matching ASC product IDs)
    - Create "pro" entitlement
    - Attach all 3 products to "pro" entitlement
    - Create "default" offering
    - Create 3 packages ($rc_weekly, $rc_monthly, $rc_annual)
    - Idempotent: GETs existing resources first, skips if present

Usage:
    python scripts/setup_revenuecat.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Constants — must match src/mobile/src/services/purchases.ts
# ---------------------------------------------------------------------------
PRODUCT_IDS = [
    "benchgoblins_pro_weekly",
    "benchgoblins_pro_monthly",
    "benchgoblins_pro_annual",
]

ENTITLEMENT_ID = "pro"

OFFERING_ID = "default"

PACKAGES = [
    {"identifier": "$rc_weekly", "product_id": "benchgoblins_pro_weekly"},
    {"identifier": "$rc_monthly", "product_id": "benchgoblins_pro_monthly"},
    {"identifier": "$rc_annual", "product_id": "benchgoblins_pro_annual"},
]

RC_BASE = "https://api.revenuecat.com/v2"

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


def rc_headers(secret_key: str) -> dict:
    return {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }


def rc_get(path: str, secret_key: str) -> dict:
    resp = requests.get(f"{RC_BASE}{path}", headers=rc_headers(secret_key))
    resp.raise_for_status()
    return resp.json()


def rc_post(path: str, secret_key: str, payload: dict) -> dict:
    resp = requests.post(
        f"{RC_BASE}{path}", headers=rc_headers(secret_key), json=payload
    )
    if resp.status_code == 409:
        print("  -> Already exists (409 Conflict)")
        return {"conflict": True}
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# RevenueCat operations
# ---------------------------------------------------------------------------


def get_existing_products(project_id: str, secret_key: str) -> set[str]:
    """Return set of existing product identifiers."""
    data = rc_get(f"/projects/{project_id}/products", secret_key)
    existing = set()
    for item in data.get("items", []):
        store_id = item.get("store_identifier", "")
        if store_id:
            existing.add(store_id)
        # Also check nested structure
        if not store_id and "store_identifier" in item.get("attributes", {}):
            existing.add(item["attributes"]["store_identifier"])
    return existing


def create_product(
    project_id: str, app_id: str, product_id: str, secret_key: str
) -> None:
    """Create a single product in RevenueCat."""
    payload = {
        "store_identifier": product_id,
        "app_id": app_id,
        "type": "subscription",
    }
    result = rc_post(f"/projects/{project_id}/products", secret_key, payload)
    if not result.get("conflict"):
        print(f"  Created product: {product_id}")


def get_existing_entitlements(project_id: str, secret_key: str) -> dict[str, str]:
    """Return mapping of entitlement lookup_key -> id."""
    data = rc_get(f"/projects/{project_id}/entitlements", secret_key)
    result = {}
    for item in data.get("items", []):
        lookup = item.get("lookup_key", "")
        ent_id = item.get("id", "")
        if lookup:
            result[lookup] = ent_id
    return result


def create_entitlement(project_id: str, secret_key: str) -> str:
    """Create the 'pro' entitlement, return its ID."""
    payload = {
        "lookup_key": ENTITLEMENT_ID,
        "display_name": "Pro",
    }
    result = rc_post(f"/projects/{project_id}/entitlements", secret_key, payload)
    if result.get("conflict"):
        existing = get_existing_entitlements(project_id, secret_key)
        ent_id = existing.get(ENTITLEMENT_ID)
        if not ent_id:
            print("ERROR: Entitlement conflict but could not find it.")
            sys.exit(1)
        return ent_id
    return result.get("id", "")


def get_entitlement_products(
    project_id: str, entitlement_id: str, secret_key: str
) -> set[str]:
    """Return set of product IDs already attached to an entitlement."""
    data = rc_get(
        f"/projects/{project_id}/entitlements/{entitlement_id}/products",
        secret_key,
    )
    attached = set()
    for item in data.get("items", []):
        store_id = item.get("store_identifier", "")
        if store_id:
            attached.add(store_id)
    return attached


def attach_product_to_entitlement(
    project_id: str, entitlement_id: str, product_id: str, secret_key: str
) -> None:
    """Attach a product to an entitlement."""
    payload = {"product_id": product_id}
    rc_post(
        f"/projects/{project_id}/entitlements/{entitlement_id}/products",
        secret_key,
        payload,
    )


def get_existing_offerings(project_id: str, secret_key: str) -> dict[str, str]:
    """Return mapping of offering lookup_key -> id."""
    data = rc_get(f"/projects/{project_id}/offerings", secret_key)
    result = {}
    for item in data.get("items", []):
        lookup = item.get("lookup_key", "")
        off_id = item.get("id", "")
        if lookup:
            result[lookup] = off_id
    return result


def create_offering(project_id: str, secret_key: str) -> str:
    """Create the 'default' offering, return its ID."""
    payload = {
        "lookup_key": OFFERING_ID,
        "display_name": "Default",
        "is_current": True,
    }
    result = rc_post(f"/projects/{project_id}/offerings", secret_key, payload)
    if result.get("conflict"):
        existing = get_existing_offerings(project_id, secret_key)
        off_id = existing.get(OFFERING_ID)
        if not off_id:
            print("ERROR: Offering conflict but could not find it.")
            sys.exit(1)
        return off_id
    return result.get("id", "")


def get_existing_packages(
    project_id: str, offering_id: str, secret_key: str
) -> set[str]:
    """Return set of package identifiers in an offering."""
    data = rc_get(
        f"/projects/{project_id}/offerings/{offering_id}/packages",
        secret_key,
    )
    existing = set()
    for item in data.get("items", []):
        lookup = item.get("lookup_key", "")
        if lookup:
            existing.add(lookup)
    return existing


def create_package(
    project_id: str, offering_id: str, pkg_cfg: dict, secret_key: str
) -> None:
    """Create a package in an offering."""
    payload = {
        "lookup_key": pkg_cfg["identifier"],
        "display_name": pkg_cfg["identifier"].replace("$rc_", "").title(),
        "position": PACKAGES.index(pkg_cfg) + 1,
    }
    result = rc_post(
        f"/projects/{project_id}/offerings/{offering_id}/packages",
        secret_key,
        payload,
    )
    if not result.get("conflict"):
        print(f"  Created package: {pkg_cfg['identifier']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    creds = load_credentials()
    rc = creds["revenuecat"]

    for field in ("v2_secret_key", "project_id", "ios_app_id"):
        if not rc.get(field):
            print(f"ERROR: revenuecat.{field} is empty in store_credentials.json")
            sys.exit(1)

    secret_key = rc["v2_secret_key"]
    project_id = rc["project_id"]
    app_id = rc["ios_app_id"]

    # 1. Create products
    print("Creating products...")
    existing_products = get_existing_products(project_id, secret_key)
    for product_id in PRODUCT_IDS:
        if product_id in existing_products:
            print(f"  Product already exists: {product_id}")
        else:
            create_product(project_id, app_id, product_id, secret_key)

    # 2. Create entitlement
    print(f'\nCreating entitlement: "{ENTITLEMENT_ID}"')
    entitlement_id = create_entitlement(project_id, secret_key)
    print(f"  Entitlement ID: {entitlement_id}")

    # 3. Attach products to entitlement
    print("\nAttaching products to entitlement...")
    attached = get_entitlement_products(project_id, entitlement_id, secret_key)
    for product_id in PRODUCT_IDS:
        if product_id in attached:
            print(f"  Already attached: {product_id}")
        else:
            attach_product_to_entitlement(
                project_id, entitlement_id, product_id, secret_key
            )
            print(f"  Attached: {product_id}")

    # 4. Create offering
    print(f'\nCreating offering: "{OFFERING_ID}"')
    offering_id = create_offering(project_id, secret_key)
    print(f"  Offering ID: {offering_id}")

    # 5. Create packages
    print("\nCreating packages...")
    existing_packages = get_existing_packages(project_id, offering_id, secret_key)
    for pkg_cfg in PACKAGES:
        if pkg_cfg["identifier"] in existing_packages:
            print(f"  Package already exists: {pkg_cfg['identifier']}")
        else:
            create_package(project_id, offering_id, pkg_cfg, secret_key)

    # Summary
    print("\n" + "=" * 60)
    print("RevenueCat Setup Complete")
    print("=" * 60)
    print(f"  Project ID:    {project_id}")
    print(f"  Entitlement:   {ENTITLEMENT_ID} ({entitlement_id})")
    print(f"  Offering:      {OFFERING_ID} ({offering_id})")
    print(f"  Products:      {', '.join(PRODUCT_IDS)}")
    print(f"  Packages:      {', '.join(p['identifier'] for p in PACKAGES)}")
    if rc.get("public_api_key_ios"):
        print(f"  Public Key:    {rc['public_api_key_ios']}")
    print("\nNext: Run scripts/inject_config.py")


if __name__ == "__main__":
    main()
