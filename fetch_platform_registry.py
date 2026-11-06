#!/usr/bin/env python3
"""Collect the public intermediary-platform registry and keep change history."""

import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SOURCE = "https://platform.economy.gov.ru/ru"
API = os.environ.get("PLATFORM_REGISTRY_API_URL", "https://platform.economy.gov.ru/api/pcp/ru/registry/list")
FIELDS = ("name", "domain", "operator", "inn", "updated_at", "status")


def fetch_all():
    rows = []
    totals = None
    for page in range(1, 101):
        url = API + ("&" if "?" in API else "?") + urlencode({"page": page, "itemsPerPage": 100, "sort": "default"})
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        token = os.environ.get("PLATFORM_REGISTRY_API_TOKEN")
        if token:
            headers["X-Registry-Token"] = token
        request = Request(url, headers=headers)
        with urlopen(request, timeout=25) as response:
            if response.status != 200:
                raise ValueError(f"Registry API returned HTTP {response.status}")
            payload = json.load(response)
        if payload.get("error") is not False or not isinstance(payload.get("result"), dict):
            raise ValueError("Registry API returned an error or unexpected response")
        result = payload["result"]
        page_totals = {}
        has_more = False
        for status in ("active", "inactive"):
            bucket = result.get(status)
            if not isinstance(bucket, dict) or not isinstance(bucket.get("items"), list):
                raise ValueError(f"Registry API has no {status} items")
            total = bucket.get("total")
            if not isinstance(total, int) or total < 0:
                raise ValueError(f"Registry API has invalid {status} total")
            page_totals[status] = total
            has_more |= bucket.get("hasMore") is True
            for item in bucket["items"]:
                number = str(item.get("registry_number") or "").strip()
                identifier = str(item.get("id") or "").strip()
                name = str(item.get("name") or "").strip()
                if not (number or identifier) or not name:
                    raise ValueError("Registry API has an incomplete record")
                row = {
                    "key": number or f"id:{identifier}",
                    "number": number,
                    "name": name,
                    "domain": str(item.get("domain") or "").strip(),
                    "operator": str(item.get("operator") or "").strip(),
                    "inn": str(item.get("inn") or "").strip(),
                    "updated_at": str(item.get("updated_at") or "").strip(),
                    "status": status,
                }
                rows.append(row)
        if totals is None:
            totals = page_totals
        elif page_totals != totals:
            raise ValueError("Registry totals changed during pagination")
        if not has_more:
            break
    else:
        raise ValueError("Registry pagination exceeds 100 pages")
    if len(rows) != sum(totals.values()):
        raise ValueError("Registry item count differs from reported totals")
    if len({row["key"] for row in rows}) != len(rows):
        raise ValueError("Registry contains duplicate record numbers")
    rows.sort(key=lambda row: (0, int(row["number"])) if row["number"].isdigit()
              else (1, row["key"]))
    return rows, totals


def make_snapshot(rows, totals, previous, checked_at):
    old = {row["key"]: row for row in previous["records"]} if previous else {}
    new = {row["key"]: row for row in rows}
    changes = []
    if previous:
        for key in sorted(new.keys() - old.keys()):
            row = new[key]
            changes.append({"at": checked_at, "kind": "added", "number": row["number"],
                            "name": row["name"], "fields": {}})
        for key in sorted(old.keys() - new.keys()):
            row = old[key]
            changes.append({"at": checked_at, "kind": "removed", "number": row["number"],
                            "name": row["name"], "fields": {}})
        for key in sorted(new.keys() & old.keys()):
            before, after = old[key], new[key]
            changed = {field: [before.get(field, ""), after.get(field, "")]
                       for field in FIELDS if before.get(field, "") != after.get(field, "")}
            if changed:
                changes.append({"at": checked_at, "kind": "changed", "number": after["number"],
                                "name": after["name"], "fields": changed})
    history = (changes + (previous.get("history", []) if previous else []))[:100]
    return {
        "schema": 1,
        "source": SOURCE,
        "checked_at": checked_at,
        "totals": totals,
        "records": rows,
        "history": history,
        "baseline": previous is None,
    }, len(changes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path(__file__).with_name("platform_registry.json"))
    args = parser.parse_args()
    previous = None
    if args.out.exists():
        previous = json.loads(args.out.read_text(encoding="utf-8"))
        if previous.get("schema") != 1 or not isinstance(previous.get("records"), list):
            raise ValueError("Existing registry snapshot has an unexpected format")
    rows, totals = fetch_all()
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    snapshot, change_count = make_snapshot(rows, totals, previous, checked_at)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.out.with_suffix(args.out.suffix + ".new")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, args.out)
    print(f"platform_registry active={totals['active']} inactive={totals['inactive']} changes={change_count}")


if __name__ == "__main__":
    main()
