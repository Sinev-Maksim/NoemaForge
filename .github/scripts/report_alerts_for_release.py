#!/usr/bin/env python3
"""
report_alerts_for_release.py

Read-only report: open code-scanning alerts for a release ref, prioritized by
severity/confidence, plus the set of alerts open on a compare branch (e.g.
main) that are absent from the release ref -- candidates to reconcile once
the release ref ships.

This script only reads; it never mutates alert state. See
dismiss-fixed-alerts.py for the (also dry-run-by-default) mutating tool.

Usage:
  GITHUB_TOKEN=... python report_alerts_for_release.py \
    --owner Sinev-Maksim --repo NoemaForge \
    --release-ref release/0.33.0-dev --compare-branch main

Options:
  --top N        : show only the top N release alerts (default 50)
  --out csv/path : also write the full release-alert report to CSV (optional)
"""
import os
import sys
import time
import argparse
import csv
import requests

API = "https://api.github.com"


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
        if isinstance(data, dict):
            # Some endpoints may return an object (not a list).
            return data
        items.extend(data)
        if len(data) < per_page:
            break
        page += 1
        time.sleep(0.05)
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


def _list_alerts_for_ref(owner, repo, ref, token):
    """Try raw ref, then refs/heads/<ref>, then refs/tags/<ref>."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    url = f"{API}/repos/{owner}/{repo}/code-scanning/alerts"
    for candidate in (ref, f"refs/heads/{ref}", f"refs/tags/{ref}"):
        try:
            return paged_get(url, headers, {"state": "open", "ref": candidate})
        except SystemExit:
            continue
    raise SystemExit(f"Could not list alerts for ref {ref!r} (tried raw, refs/heads/, refs/tags/)")


def list_alerts(owner, repo, ref, token):
    return _list_alerts_for_ref(owner, repo, ref, token)


def severity_rank(s):
    order = {"critical": 4, "high": 3, "medium": 2, "low": 1, None: 0}
    return order.get((s or "").lower(), 0)


def confidence_rank(c):
    order = {"high": 3, "medium": 2, "low": 1, None: 0}
    return order.get((c or "").lower(), 0)


def summarize(alerts):
    by_sev = {}
    for a in alerts:
        sev = (a.get("rule") or {}).get("severity") or a.get("severity") or "unknown"
        by_sev[sev] = by_sev.get(sev, 0) + 1
    return by_sev


def flatten_alert(a, owner, repo):
    num = a.get("number") or a.get("id")
    tool = (a.get("tool") or {}).get("name") or a.get("tool_name")
    rule = None
    if a.get("rule"):
        rule = a["rule"].get("id") or a["rule"].get("description")
    rule = rule or a.get("rule_id") or a.get("ruleId")
    inst = a.get("most_recent_instance") or {}
    loc = inst.get("location") or {}
    path = loc.get("path") or ""
    start_line = loc.get("start_line") or loc.get("startLine") or ""
    severity = (a.get("rule") or {}).get("severity") or a.get("severity") or ""
    confidence = inst.get("severity") or inst.get("confidence") or ""
    commit = inst.get("commit_sha") or ""
    html = a.get("html_url") or f"https://github.com/{owner}/{repo}/security/code-scanning/{num}"
    title = (a.get("rule") or {}).get("description") or a.get("message") or ""
    return {
        "id": num, "tool": tool, "rule": rule, "title": title,
        "severity": severity, "confidence": confidence,
        "path": path, "line": start_line, "commit": commit, "url": html,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--owner", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--release-ref", required=True, help="branch name or tag to report on")
    p.add_argument("--compare-branch", required=True, help="branch whose extra-vs-release alerts are listed as reconcile candidates")
    p.add_argument("--top", type=int, default=50)
    p.add_argument("--out", default=None)
    p.add_argument(
        "--exclude-tool",
        action="append",
        default=None,
        help="Tool name(s) to exclude from the 'reconcile candidates' list, case-insensitive "
             "(repeatable). Defaults to ['Scorecard']: that scanner only runs against a fixed "
             "branch (see this repo's scorecard.yml, push: branches: main) and never analyzes "
             "release/feature refs, so its alerts would always look 'absent from release' "
             "regardless of fix status -- that's a scan-coverage gap, not evidence of a fix.",
    )
    args = p.parse_args()

    excluded_tools = {t.strip().lower() for t in (args.exclude_tool if args.exclude_tool is not None else ["Scorecard"])}

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN required")
        sys.exit(2)

    print("Listing alerts for release ref:", args.release_ref)
    release_alerts = list_alerts(args.owner, args.repo, args.release_ref, token)
    print("Listing alerts for compare branch:", args.compare_branch)
    compare_alerts = list_alerts(args.owner, args.repo, args.compare_branch, token)

    release_keys = {key_of_alert(a) for a in release_alerts}
    compare_map = {}
    for a in compare_alerts:
        compare_map.setdefault(key_of_alert(a), []).append(a)

    release_flat = [flatten_alert(a, args.owner, args.repo) for a in release_alerts]

    # Alerts open on compare_branch but not on release_ref: already fixed on
    # release, just pending propagation once release_ref ships to compare_branch.
    # Excludes tools that never scan release_ref at all (see --exclude-tool):
    # for those, "absent from release_ref" means "never checked", not "fixed".
    dismiss_candidates = []
    skipped_excluded_tool = 0
    for k, alerts in compare_map.items():
        if k not in release_keys:
            for a in alerts:
                tool = ((a.get("tool") or {}).get("name") or a.get("tool_name") or "").strip().lower()
                if tool in excluded_tools:
                    skipped_excluded_tool += 1
                    continue
                dismiss_candidates.append(flatten_alert(a, args.owner, args.repo))

    release_flat.sort(key=lambda x: (-severity_rank(x["severity"]), -confidence_rank(x["confidence"])))

    print("\nSummary (release):")
    for sev, cnt in summarize(release_alerts).items():
        print(f"  {sev}: {cnt}")
    print("\nTop release alerts (by severity/confidence):")
    for a in release_flat[: args.top]:
        print(f"- [{a['severity']}/{a['confidence']}] {a['rule']} @ {a['path']}:{a['line']} -> {a['url']}")

    if skipped_excluded_tool:
        print(f"\n({skipped_excluded_tool} alert(s) from excluded tool(s) {sorted(excluded_tools)} omitted from "
              f"the list below -- that tool never scans {args.release_ref}, so absence there isn't meaningful.)")
    print(f"\nAlerts open on {args.compare_branch} but NOT on {args.release_ref} "
          f"(reconcile candidates once {args.release_ref} ships): {len(dismiss_candidates)}")
    for a in dismiss_candidates[: min(30, len(dismiss_candidates))]:
        print(f"- [{a['severity']}] {a['rule']} @ {a['path']}:{a['line']} -> {a['url']}")

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "tool", "rule", "title", "severity", "confidence", "path", "line", "commit", "url"])
            w.writeheader()
            for a in release_flat:
                w.writerow(a)
        print("Saved CSV:", args.out)


if __name__ == "__main__":
    main()
