"""
Seed the local SentinelChain database with dummy suppliers.

Usage:
    python scripts/seed.py [--url http://localhost:8000]

Requires the backend API to be running.
"""
import argparse
import json
import sys
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed dummy suppliers via the dev endpoint")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the SentinelChain API")
    args = parser.parse_args()

    endpoint = f"{args.url.rstrip('/')}/api/v1/seed"
    try:
        with urllib.request.urlopen(urllib.request.Request(endpoint, method="POST"), timeout=120) as res:
            body = json.loads(res.read().decode())
    except Exception as exc:
        print(f"Seed failed: {exc}\nIs the backend running at {args.url}?")
        return 1

    print(f"Created {body.get('created', '?')} suppliers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
