#!/usr/bin/env python3
"""Watcher-cadence load check (BE-07.1).

    python scripts/load_watch.py --base https://<domain> --key <demo key> \
        [--sessions 2] [--minutes 3] [--frame x.jpg] [--watch-interval 2.5] [--check-interval 20]

Each simulated session creates a real session, sends /watch on a fixed 2.5 s grid and one /check
every 20 s (cycling through the recipe's steps), then ends the session. Ticks are scheduled from
the session's start time, not from the end of the previous call. A watch tick that finds the
previous /watch of that session still running is skipped and counted, so a session never has two
/watch calls in flight (API-CONTRACT §3.3 "never overlap"; the contract measures the interval from
the END of the previous call, so this grid is the harder case for the server).
A /check does not pause the watcher here, the way the real clients do, so this is worst case.

Reports per endpoint: counts by HTTP status, error codes, p50 / p90 / max client latency, 429s,
skipped ticks. Exit code 1 on any 5xx or transport error, 2 on bad arguments.
This sends real frames: against production with real Gemini it spends quota, run it once.
Never prints the demo key.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import math
import sys
import time
import uuid
from pathlib import Path

import httpx

SEED_RECIPE_ID = "00000000-0000-4000-8000-000000000001"
DEFAULT_FRAME = Path(__file__).resolve().parents[2] / "ai" / "fixtures" / "images" / "step-3.jpg"


class Stats:
    def __init__(self) -> None:
        self.status: collections.Counter[str] = collections.Counter()
        self.codes: collections.Counter[str] = collections.Counter()
        self.latency_ms: list[float] = []
        self.skipped = 0
        self.transport_errors: collections.Counter[str] = collections.Counter()

    def record(self, status: int, code: str | None, ms: float) -> None:
        self.status[str(status)] += 1
        if code:
            self.codes[code] += 1
        self.latency_ms.append(ms)

    @property
    def n(self) -> int:
        return sum(self.status.values()) + sum(self.transport_errors.values())

    @property
    def n_429(self) -> int:
        return self.status.get("429", 0)

    @property
    def n_5xx(self) -> int:
        return sum(v for k, v in self.status.items() if k.startswith("5"))


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q / 100 * len(ordered)) - 1)]


async def send_frame(
    http: httpx.AsyncClient,
    stats: Stats,
    endpoint: str,
    frame: bytes,
    step_id: str,
    session_id: str,
) -> None:
    t0 = time.perf_counter()
    try:
        r = await http.post(
            f"/{endpoint}",
            data={"step_id": step_id, "request_id": str(uuid.uuid4()), "session_id": session_id},
            files={"frame": ("frame.jpg", frame, "image/jpeg")},
        )
    except httpx.HTTPError as exc:
        stats.transport_errors[type(exc).__name__] += 1
        return
    ms = (time.perf_counter() - t0) * 1000
    code = None
    if r.status_code >= 400:
        try:
            code = r.json()["error"]["code"]
        except (ValueError, KeyError, TypeError):
            code = "non_json_error"
    stats.record(r.status_code, code, ms)


async def run_session(
    http: httpx.AsyncClient,
    args: argparse.Namespace,
    frame: bytes,
    steps: list[dict],
    watch: Stats,
    check: Stats,
    failures: list[str],
    index: int,
) -> None:
    r = await http.post(
        "/sessions",
        json={
            "recipe_id": args.recipe,
            "client": "web-sim",
            "device_label": f"load_watch.py #{index + 1}",
        },
    )
    if r.status_code != 201:
        failures.append(f"session {index + 1}: POST /sessions -> {r.status_code}")
        return
    sid = r.json()["session_id"]
    watched = [s for s in steps if s.get("watch_fors")] or steps

    duration = args.minutes * 60
    start = time.monotonic()
    in_flight: set[asyncio.Task] = set()
    watch_busy = False
    check_n = 0

    async def do_watch(step_id: str) -> None:
        nonlocal watch_busy
        try:
            await send_frame(http, watch, "watch", frame, step_id, sid)
        finally:
            watch_busy = False

    def spawn(coro) -> None:
        task = asyncio.create_task(coro)
        in_flight.add(task)
        task.add_done_callback(in_flight.discard)

    tick = 0
    next_check = 0.0  # first /check right away, then every check_interval
    while True:
        due = tick * args.watch_interval
        if due >= duration:
            break
        await asyncio.sleep(max(0.0, start + due - time.monotonic()))
        step = watched[(tick // 8) % len(watched)]  # a new step every ~20 s
        if watch_busy:
            watch.skipped += 1
        else:
            watch_busy = True
            spawn(do_watch(step["id"]))
        if due >= next_check:
            next_check += args.check_interval
            check_step = steps[check_n % len(steps)]
            check_n += 1
            spawn(send_frame(http, check, "check", frame, check_step["id"], sid))
        tick += 1

    if in_flight:
        await asyncio.gather(*in_flight, return_exceptions=True)
    r = await http.post(f"/sessions/{sid}/events", json={"kind": "session_end"})
    if r.status_code != 201:
        failures.append(f"session {index + 1}: session_end -> {r.status_code}")


def report(name: str, s: Stats) -> None:
    print(f"\n{name}: {s.n} responses, {s.skipped} skipped ticks")
    if not s.n:
        return
    print("  status: " + ", ".join(f"{k}={v}" for k, v in sorted(s.status.items())))
    if s.codes:
        print("  error codes: " + ", ".join(f"{k}={v}" for k, v in sorted(s.codes.items())))
    if s.transport_errors:
        print("  transport errors: " + ", ".join(f"{k}={v}" for k, v in s.transport_errors.items()))
    if s.latency_ms:
        print(
            f"  latency ms: p50={percentile(s.latency_ms, 50):.0f} "
            f"p90={percentile(s.latency_ms, 90):.0f} max={max(s.latency_ms):.0f}"
        )
    print(f"  429s: {s.n_429}")


async def main_async(args: argparse.Namespace) -> int:
    frame = args.frame.read_bytes()
    failures: list[str] = []
    watch, check = Stats(), Stats()
    limits = httpx.Limits(max_connections=args.sessions * 4 + 4)
    async with httpx.AsyncClient(
        base_url=args.base.rstrip("/"),
        headers={"X-Demo-Key": args.key},
        timeout=httpx.Timeout(30.0),
        limits=limits,
    ) as http:
        try:
            r = await http.get(f"/recipes/{args.recipe}")
        except httpx.HTTPError as exc:
            print(f"cannot reach {args.base}: {type(exc).__name__}", file=sys.stderr)
            return 1
        if r.status_code != 200:
            print(f"GET /recipes/{args.recipe} -> {r.status_code}", file=sys.stderr)
            return 1
        steps = r.json()["steps"]
        if not steps:
            print("recipe has no steps", file=sys.stderr)
            return 1
        print(
            f"load: {args.sessions} session(s) x {args.minutes:g} min, watch every "
            f"{args.watch_interval:g} s, check every {args.check_interval:g} s, "
            f"frame {len(frame)} bytes"
        )
        started = time.monotonic()
        results = await asyncio.gather(
            *(
                run_session(http, args, frame, steps, watch, check, failures, i)
                for i in range(args.sessions)
            ),
            return_exceptions=True,
        )
        for i, res in enumerate(results):
            if isinstance(res, BaseException):
                failures.append(f"session {i + 1}: {type(res).__name__}")
        print(f"elapsed: {time.monotonic() - started:.1f} s")

    report("POST /watch", watch)
    report("POST /check", check)
    bad = watch.n_5xx + check.n_5xx
    transport = sum(watch.transport_errors.values()) + sum(check.transport_errors.values())
    if watch.n_429 + check.n_429:
        print(
            f"\n429 seen ({watch.n_429} watch, {check.n_429} check): quota or cool-down; "
            "with fewer sessions this may disappear"
        )
    if bad or transport or failures:
        print(f"\nFAILED: {bad} 5xx, {transport} transport errors", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("\nOK: no 5xx, no transport errors")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--key", default="dev-key")
    ap.add_argument("--sessions", type=int, default=2)
    ap.add_argument("--minutes", type=float, default=3.0)
    ap.add_argument("--frame", type=Path, default=DEFAULT_FRAME, help="a real JPEG")
    ap.add_argument("--watch-interval", type=float, default=2.5)
    ap.add_argument("--check-interval", type=float, default=20.0)
    ap.add_argument("--recipe", default=SEED_RECIPE_ID)
    args = ap.parse_args()
    if (
        args.sessions < 1
        or args.minutes <= 0
        or args.watch_interval <= 0
        or args.check_interval <= 0
    ):
        print("--sessions, --minutes and the intervals must be positive", file=sys.stderr)
        return 2
    if not args.frame.is_file():
        print(f"frame not found: {args.frame}", file=sys.stderr)
        return 2
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
