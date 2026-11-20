#!/usr/bin/env python3
"""
dismiss-fixed-alerts.py

Compares open code-scanning alerts between a target branch (e.g. main) and a
release ref (branch or tag), and dismisses on the target branch those alerts
that are absent from the release ref -- i.e. already fixed there, just
waiting for the release ref to ship.

Defaults to a dry run: nothing is mutated unless --dry-run is explicitly
omitted. Always review the dry-run output before a live run.

IMPORTANT -- "absent from release ref" only means "fixed" if the release ref
was actually analyzed by that same tool. Some scanners (e.g. this repo's
OpenSSF Scorecard workflow) only ever run against a fixed branch (main) and
never against release/feature refs at all -- for those, EVERY alert would
incorrectly look "fixed on release" simply because release was never
scanned, not because anything was fixed. --exclude-tool guards against this;
its default already excludes "Scorecard" for that reason. Extend it (repeat
the flag) if another tool in your CI is similarly branch-scoped.

Usage (dry-run, always safe):
  GITHUB_TOKEN=... python dismiss-fixed-alerts.py \
    --owner Sinev-Maksim --repo NoemaForge \
    --release-ref release/0.33.0-dev --target-branch main --dry-run

To actually dismiss (only after reviewing the dry-run output):
  GITHUB_TOKEN=... python dismiss-fixed-alerts.py \
    --owner Sinev-Maksim --repo NoemaForge \
    --release-ref release/0.33.0-dev --target-branch main \
    --dismiss-reason "won't fix" --comment "Fixed in release 0.33.0"
"""

import os
import sys
import time
import argparse
import requests

API = "https://api.github.com"

# GitHub's code-scanning alert API only accepts these three values for
# dismissed_reason. "risk_accepted" is a Dependabot-alert concept and is
# NOT valid here -- passing it fails the PATCH with a 422.
VALID_DISMISS_REASONS = ["false positive", "won't fix", "used in tests"]


def paged_get(url, headers, params=None):
    per_page = 100
    page = 1
    items = []
    while True:
        p = dict(params or {})
        p.update({"per_page": per_page, "page": page})
        r = requests.get(url, headers=headers, params=p, timeout=30)
        if r.status_code != 200:
            raise SystemExit(f"GET {url} failed: {r.status_code} {r.text}")
        data = r.json()
        if not isinstance(data, list):
            return data
        items.extend(data)
        if len(data) < per_page:
            break
        page += 1
        time.sleep(0.1)
    return items


def key_of_alert(a):
    tool = (a.get("tool") or {}).get("name") or a.get("tool_name")
    rule = None
    if a.get("rule"):
        rule = a["rule"].get("id") or a["rule"].get("description")
    rule = rule or a.get("rule_id") or a.get("ruleId")
    inst = a.get("most_recent_instance") or {}
    loc = inst.get("location") or {}
    path = loc.get("path") or ""
    start_line = loc.get("start_line") or loc.get("startLine") or 0
    return (tool, rule, path, start_line)


def list_alerts(owner, repo, ref, token):
    """List open alerts for a ref. Tries raw ref, then refs/heads/, then
    refs/tags/, since ref may name either a branch or a tag."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    url = f"{API}/repos/{owner}/{repo}/code-scanning/alerts"
    for candidate in (ref, f"refs/heads/{ref}", f"refs/tags/{ref}"):
        try:
            return paged_get(url, headers, {"state": "open", "ref": candidate})
        except SystemExit:
            continue
    raise SystemExit(f"Could not list alerts for ref {ref!r} (tried raw, refs/heads/, refs/tags/)")


def dismiss_alert(owner, repo, alert_id, token, reason, comment, dry_run=True):
    url = f"{API}/repos/{owner}/{repo}/code-scanning/alerts/{alert_id}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    body = {"state": "dismissed", "dismissed_reason": reason, "dismissed_comment": comment}
    if dry_run:
        print(f"[DRY-RUN] PATCH {url} => {body}")
        return True
    r = requests.patch(url, headers=headers, json=body, timeout=30)
    if r.status_code not in (200, 201):
        print(f"[ERROR] Failed to dismiss {alert_id}: {r.status_code} {r.text}")
        return False
    print(f"Dismissed alert {alert_id}")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--owner", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--release-ref", required=True, help="branch name or tag (e.g. github.ref_name)")
    p.add_argument("--target-branch", required=True, help="branch whose alerts are reconciled against release-ref (e.g. main)")
    p.add_argument("--dry-run", action="store_true", default=False)
    p.add_argument("--dismiss-reason", default="won't fix", choices=VALID_DISMISS_REASONS)
    p.add_argument("--comment", default=None)
    p.add_argument(
        "--exclude-tool",
        action="append",
        default=None,
        help="Tool name(s) to never treat as dismiss candidates, case-insensitive "
             "(repeatable). Defaults to ['Scorecard'] -- see the module docstring "
             "for why. Pass --exclude-tool with no other value to clear the default.",
    )
    args = p.parse_args()

    excluded_tools = {t.strip().lower() for t in (args.exclude_tool if args.exclude_tool is not None else ["Scorecard"])}

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN env required")
        sys.exit(2)

    release_ref = args.release_ref
    target_ref = args.target_branch

    print("Listing alerts on target branch:", target_ref)
    try:
        target_alerts = list_alerts(args.owner, args.repo, target_ref, token)
    except Exception as e:
        print("Failed to list alerts on target branch:", e)
        sys.exit(1)
    target_map = {}
    for a in target_alerts:
        k = key_of_alert(a)
        target_map.setdefault(k, []).append(a)

    print(f"Found {len(target_alerts)} open alerts on {target_ref} (unique keys: {len(target_map)})")

    print("Listing alerts on release ref:", release_ref)
    try:
        release_alerts = list_alerts(args.owner, args.repo, release_ref, token)
    except Exception as e:
        print("Failed to list alerts on release ref:", e)
        sys.exit(1)
    release_keys = set(key_of_alert(a) for a in release_alerts)

    print(f"Found {len(release_alerts)} open alerts on {release_ref} (unique keys: {len(release_keys)})")

    to_dismiss = []
    skipped_excluded_tool = 0
    for k, alerts in target_map.items():
        if k not in release_keys:
            for a in alerts:
                tool = ((a.get("tool") or {}).get("name") or a.get("tool_name") or "").strip().lower()
                if tool in excluded_tools:
                    skipped_excluded_tool += 1
                    continue
                to_dismiss.append(a)

    if skipped_excluded_tool:
        print(f"Skipped {skipped_excluded_tool} alert(s) from excluded tool(s) {sorted(excluded_tools)} "
              f"-- absence on {release_ref} is not meaningful for a tool that never scans that ref.")
    print(f"Alerts to dismiss (count): {len(to_dismiss)}")
    if args.dry_run:
        print("DRY RUN: listing alerts that WOULD be dismissed:")
        for a in to_dismiss:
            aid = a.get("number") or a.get("id")
            print("-", aid, key_of_alert(a))
        return

    comment = args.comment or f"Fixed in release {release_ref}"
    for a in to_dismiss:
        aid = a.get("number") or a.get("id")
        if not aid:
            print("Skipping alert without id:", a)
            continue
        dismiss_alert(args.owner, args.repo, aid, token, args.dismiss_reason, comment, dry_run=False)


if __name__ == "__main__":
    main()
