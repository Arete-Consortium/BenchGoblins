#!/usr/bin/env python3
"""Inject store credentials into app.json and eas.json.

Reads scripts/config/store_credentials.json and patches:
    - src/mobile/app.json: extra.revenueCatApiKey.ios + extra.eas.projectId
    - src/mobile/eas.json: submit.production.ios (appleId, ascAppId, appleTeamId)

Validates no YOUR_ placeholder values remain after injection.

Usage:
    python scripts/inject_config.py             # Apply changes
    python scripts/inject_config.py --dry-run   # Preview without writing
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MOBILE_DIR = Path(__file__).resolve().parent.parent / "src" / "mobile"
APP_JSON = MOBILE_DIR / "app.json"
EAS_JSON = MOBILE_DIR / "eas.json"


def load_credentials() -> dict:
    cred_path = Path(__file__).resolve().parent / "config" / "store_credentials.json"
    if not cred_path.exists():
        print(f"ERROR: {cred_path} not found.")
        print("Copy store_credentials.json.example and fill in your values.")
        sys.exit(1)
    with open(cred_path) as f:
        return json.load(f)


def patch_app_json(creds: dict, dry_run: bool) -> list[str]:
    """Patch app.json with RevenueCat key and EAS project ID. Returns list of changes."""
    with open(APP_JSON) as f:
        data = json.load(f)

    changes: list[str] = []
    extra = data.get("expo", {}).get("extra", {})

    # RevenueCat iOS public key
    rc_key = creds.get("revenuecat", {}).get("public_api_key_ios", "")
    if rc_key and not rc_key.startswith("YOUR_"):
        old = extra.get("revenueCatApiKey", {}).get("ios", "")
        if old != rc_key:
            extra.setdefault("revenueCatApiKey", {})["ios"] = rc_key
            changes.append(f"  revenueCatApiKey.ios: {old!r} -> {rc_key!r}")

    # EAS project ID
    eas_id = creds.get("eas", {}).get("project_id", "")
    if eas_id:
        old = extra.get("eas", {}).get("projectId", "")
        if old != eas_id:
            extra.setdefault("eas", {})["projectId"] = eas_id
            changes.append(f"  eas.projectId: {old!r} -> {eas_id!r}")

    if changes and not dry_run:
        with open(APP_JSON, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    return changes


def patch_eas_json(creds: dict, dry_run: bool) -> list[str]:
    """Patch eas.json with Apple submission credentials. Returns list of changes."""
    with open(EAS_JSON) as f:
        data = json.load(f)

    changes: list[str] = []
    apple = creds.get("apple", {})
    ios_submit = data.get("submit", {}).get("production", {}).get("ios", {})

    field_map = {
        "appleId": ("apple_id_email", apple.get("apple_id_email", "")),
        "ascAppId": ("asc_app_id", apple.get("asc_app_id", "")),
        "appleTeamId": ("team_id", apple.get("team_id", "")),
    }

    for eas_field, (_, value) in field_map.items():
        if value and not value.startswith("YOUR_"):
            old = ios_submit.get(eas_field, "")
            if old != value:
                ios_submit[eas_field] = value
                changes.append(f"  {eas_field}: {old!r} -> {value!r}")

    if changes and not dry_run:
        with open(EAS_JSON, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    return changes


def check_placeholders() -> list[str]:
    """Check for remaining YOUR_ placeholder values in config files."""
    issues: list[str] = []
    for path in (APP_JSON, EAS_JSON):
        content = path.read_text()
        if "YOUR_" in content:
            # Find specific placeholder lines
            for i, line in enumerate(content.splitlines(), 1):
                if "YOUR_" in line:
                    issues.append(f"  {path.name}:{i}: {line.strip()}")
    return issues


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("DRY RUN — no files will be modified\n")

    creds = load_credentials()

    # Patch app.json
    print(f"Patching {APP_JSON.name}...")
    app_changes = patch_app_json(creds, dry_run)
    if app_changes:
        for change in app_changes:
            print(change)
    else:
        print("  No changes needed.")

    # Patch eas.json
    print(f"\nPatching {EAS_JSON.name}...")
    eas_changes = patch_eas_json(creds, dry_run)
    if eas_changes:
        for change in eas_changes:
            print(change)
    else:
        print("  No changes needed.")

    # Validate
    if not dry_run:
        print("\nValidating...")
        issues = check_placeholders()
        if issues:
            print("WARNING: Placeholder values still present:")
            for issue in issues:
                print(issue)
        else:
            print("  All placeholder values have been replaced.")

    total = len(app_changes) + len(eas_changes)
    action = "would change" if dry_run else "changed"
    print(f"\n{total} field(s) {action}.")

    if dry_run and total > 0:
        print("\nRun without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
