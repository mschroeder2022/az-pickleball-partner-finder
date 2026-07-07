"""Launch the AZ Pickleball Partner Finder dashboard.

    py run.py            # start the web app at http://127.0.0.1:8000
    py run.py --port 9000

Then open the printed URL in your browser. Put your login credentials in .env
(copy from .env.example) to enable the DUPR / PickleMoneyBall / APP fetchers.
"""
from __future__ import annotations

import argparse
import webbrowser

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser")
    args = ap.parse_args()

    url = f"http://{args.host}:{args.port}"
    print(f"\n  AZ Pickleball Partner Finder -> {url}\n")
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
