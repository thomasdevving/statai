#!/usr/bin/env python3
"""End-to-end smoke test of the Ghost Chef API (backend/README.md).

    python scripts/smoke.py --base http://localhost:8000 --key dev-key [--fast]

Plain httpx, no test framework. Exits non-zero on any unexpected HTTP status.
Never prints the demo key or the Live token.
"""

from __future__ import annotations

import argparse
import collections
import re
import statistics
import sys
import time
import uuid
from pathlib import Path

import httpx

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
DEFAULT_FRAME = Path(__file__).resolve().parents[2] / "ai" / "fixtures" / "images" / "step-3.jpg"


class Smoke:
    def __init__(self, base: str, key: str) -> None:
        self.http = httpx.Client(base_url=base.rstrip("/"), timeout=30.0)
        self.headers = {"X-Demo-Key": key}
        self.rows: list[tuple[str, str, int, int | None, str]] = []
        self.failures: list[str] = []

    def call(
        self, method: str, path: str, *, expect: int = 200, step: str = "-", auth: bool = True, **kw
    ) -> httpx.Response:
        headers = self.headers if auth else {}
        r = self.http.request(method, path, headers=headers, **kw)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        latency = body.get("latency_ms") if isinstance(body, dict) else None
        outcome = ""
        if isinstance(body, dict):
            outcome = str(body.get("verdict") or body.get("status") or "")
            if isinstance(body.get("error"), dict):
                outcome = body["error"].get("code", "error")
        endpoint = f"{method} {UUID_RE.sub('{id}', path.split('?')[0])}"
        self.rows.append((step, endpoint, r.status_code, latency, outcome))
        if r.status_code != expect:
            self.failures.append(f"{endpoint}: expected {expect}, got {r.status_code} {outcome}")
        return r

    def fetch_url(self, url: str, step: str) -> None:
        r = httpx.get(url, timeout=30.0)
        self.rows.append(
            (step, "GET <signed url>", r.status_code, None, r.headers.get("content-type", ""))
        )
        if r.status_code != 200:
            self.failures.append(f"signed url for step {step}: {r.status_code}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--key", default="dev-key")
    ap.add_argument("--frame", type=Path, default=DEFAULT_FRAME, help="JPEG sent to check/watch")
    ap.add_argument(
        "--watch-frame", type=Path, default=None, help="JPEG sent to /watch (default: --frame)"
    )
    ap.add_argument(
        "--allow-model-errors",
        action="store_true",
        help="real-condition run: count 429/503/504 from /check and /watch instead of failing",
    )
    ap.add_argument("--watch-n", type=int, default=6)
    ap.add_argument("--fast", action="store_true", help="skip the 2.5 s sleep between /watch")
    args = ap.parse_args()

    if not args.frame.is_file():
        print(f"frame not found: {args.frame}", file=sys.stderr)
        return 2
    frame = args.frame.read_bytes()
    watch_path = args.watch_frame or args.frame
    if not watch_path.is_file():
        print(f"frame not found: {watch_path}", file=sys.stderr)
        return 2
    watch_frame = watch_path.read_bytes()
    s = Smoke(args.base, args.key)

    try:
        # 1. health
        h = s.call("GET", "/health", auth=False).json()
        print(
            f"health: ai_mode={h.get('ai_mode')} storage={h.get('storage')} "
            f"contract={h.get('contract_version')}"
        )

        # 2. recipes
        recipes = s.call("GET", "/recipes").json()["recipes"]
        published = [r for r in recipes if r["status"] == "published"]
        if not published:
            print("no published recipe found", file=sys.stderr)
            return 1
        recipe = s.call("GET", f"/recipes/{published[0]['id']}").json()
        print(f"recipe: {recipe['title']} ({len(recipe['steps'])} steps)")
        for st in recipe["steps"]:
            if st["ref_image_url"]:
                s.fetch_url(st["ref_image_url"], str(st["idx"]))

        # 3. session + step_change
        sid = s.call(
            "POST",
            "/sessions",
            expect=201,
            json={"recipe_id": recipe["id"], "client": "web-sim", "device_label": "smoke.py"},
        ).json()["session_id"]
        target = next((st for st in recipe["steps"] if st["watch_fors"]), recipe["steps"][0])
        s.call(
            "POST",
            f"/sessions/{sid}/events",
            expect=201,
            step=str(target["idx"]),
            json={
                "kind": "step_change",
                "step_id": target["id"],
                "payload": {"from_idx": 1, "to_idx": target["idx"], "via": "tap"},
            },
        )

        # 4. check twice, watch N times
        def frame_call(endpoint: str) -> None:
            n = len(s.failures)
            r = s.call(
                "POST",
                f"/{endpoint}",
                step=str(target["idx"]),
                data={"step_id": target["id"], "request_id": str(uuid.uuid4()), "session_id": sid},
                files={
                    "frame": (
                        "frame.jpg",
                        frame if endpoint == "check" else watch_frame,
                        "image/jpeg",
                    )
                },
            )
            if args.allow_model_errors and r.status_code in (429, 503, 504):
                del s.failures[n:]  # counted in the error table below, not a smoke failure

        for _ in range(2):
            frame_call("check")
        for i in range(args.watch_n):
            if i and not args.fast:
                time.sleep(2.5)
            frame_call("watch")

        # 5. live token (never print the token itself)
        live = s.call("GET", f"/live-token?recipe_id={recipe['id']}&session_id={sid}").json()
        print(f"live: model={live.get('model')} locked={live.get('locked')}")

        # 6. monitor, session, end
        s.call("GET", f"/sessions/{sid}/monitor")
        summary = s.call("GET", f"/sessions/{sid}").json().get("summary")
        print(f"summary: {summary}")
        s.call("POST", f"/sessions/{sid}/events", expect=201, json={"kind": "session_end"})
    except httpx.HTTPError as exc:
        s.failures.append(f"transport error: {type(exc).__name__}: {exc}")

    # 7. table + latency
    print()
    print(f"{'step':>4}  {'endpoint':<36} {'http':>4} {'latency_ms':>10}  result")
    for step, endpoint, code, lat, outcome in s.rows:
        print(f"{step:>4}  {endpoint:<36} {code:>4} {'' if lat is None else lat:>10}  {outcome}")
    print()
    for name in ("POST /check", "POST /watch"):
        lats = [lat for _, e, _, lat, _ in s.rows if e == name and lat is not None]
        if lats:
            print(
                f"{name:<12} n={len(lats):<3} p50={int(statistics.median(lats))} ms "
                f"max={max(lats)} ms"
            )
    errors = collections.Counter(
        f"{e} {code} {outcome}" for _, e, code, _, outcome in s.rows if code >= 400
    )
    if errors:
        print("\nerror responses:")
        for name, n in sorted(errors.items()):
            print(f"  {name}: {n}")
    if s.failures:
        print("\nFAILED:", file=sys.stderr)
        for f in s.failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
