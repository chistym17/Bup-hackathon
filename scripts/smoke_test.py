#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
SAMPLES = sorted(Path("samples").glob("0*.json"))


def main() -> None:
    print(f"base: {BASE}\n")
    health = httpx.get(f"{BASE}/health", timeout=60.0)
    print(f"GET /health -> {health.status_code} {health.text}\n")

    for path in SAMPLES:
        payload = json.loads(path.read_text())
        print("=" * 60)
        print(f"file: {path.name}")
        print(f"scenario: {payload.get('scenario_id')}")
        print(f"notes: {payload.get('operator_notes')}")
        try:
            r = httpx.post(f"{BASE}/optimize-energy", json=payload, timeout=90.0)
        except Exception as exc:
            print(f"ERROR: {exc}\n")
            continue

        print(f"status: {r.status_code}")
        data = r.json()
        if r.status_code != 200:
            print(f"error: {json.dumps(data, indent=2)}\n")
            continue

        print("directives:")
        for d in data["directive_interpretation"]:
            print(
                f"  [{d['note_index']}] {d['directive_type']} "
                f"applies={d['applies']} adj={d['structured_adjustment']}"
            )
        print(
            f"cost={data['total_cost_bdt']} "
            f"grid={data['total_grid_kwh']} "
            f"peak={data['peak_grid_kwh']}"
        )
        print(f"summary: {data['plan_summary']}\n")


if __name__ == "__main__":
    main()
