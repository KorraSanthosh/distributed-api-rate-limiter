"""Replays a real web-server access log (Common Log Format) through the rate limiter.

Designed for the public NASA HTTP logs (https://ita.ee.lbl.gov/html/contrib/NASA-HTTP.html)
but works with any Common Log Format file (plain or .gz).

Each log line becomes one request to the gateway:
  * timing   - original inter-arrival gaps, divided by --speed
  * client   - the real client host/IP, sent as X-Forwarded-For (hostnames are mapped to a
               stable pseudonymous IP, since the limiter only accepts valid IPs)
  * route    - the real URL is mapped to one of the API routes by a stable hash
The status codes recorded are the gateway's real responses (200/429), not the log's.

The gateway must trust the sender's address for X-Forwarded-For to be honoured
(TRUSTED_PROXIES; the docker-compose demo config already does).

Example:
    python scripts/replay_access_log.py NASA_access_log_Jul95.gz --start 100000 --count 20000 --speed 200
"""

import argparse
import asyncio
import gzip
import ipaddress
import re
import sys
import time
import uuid
import zlib
from collections import Counter
from datetime import datetime
from itertools import islice
from typing import IO, Iterator, List, NamedTuple, Optional

import httpx

ROUTES = ["/api/v1/status", "/api/v1/data", "/api/v1/users", "/api/v1/orders"]

# host - - [01/Jul/1995:00:00:01 -0400] "GET /path HTTP/1.0" 200 6245
LOG_RE = re.compile(
    r'^(?P<host>\S+) \S+ \S+ \[(?P<ts>[^\]]+)\] "(?P<method>[A-Z]+) (?P<path>\S+)[^"]*" (?P<status>\d{3}) (?P<size>\S+)'
)


class LogEntry(NamedTuple):
    host: str
    timestamp: float
    method: str
    path: str


def parse_line(line: str) -> Optional[LogEntry]:
    """Parses one Common Log Format line; returns None for malformed lines."""
    m = LOG_RE.match(line)
    if not m:
        return None
    try:
        ts = datetime.strptime(m["ts"], "%d/%b/%Y:%H:%M:%S %z").timestamp()
    except ValueError:
        return None
    return LogEntry(m["host"], ts, m["method"], m["path"])


def map_route(path: str) -> str:
    """Maps a real URL onto one of the API routes. Stable: same URL -> same route."""
    return ROUTES[zlib.crc32(path.encode()) % len(ROUTES)]


def client_ip(host: str) -> str:
    """Returns the client's IP for X-Forwarded-For.

    Public IPs are kept as-is. Hostnames (and private/reserved IPs, which the gateway's demo
    config trusts as proxies) map to a stable address in 198.18.0.0/15 (RFC 2544 benchmarking).
    """
    try:
        ip = ipaddress.ip_address(host)
        if ip.version == 4 and ip.is_global:
            return str(ip)
    except ValueError:
        pass
    n = zlib.crc32(host.encode()) & 0x1FFFF  # 17 bits -> /15
    return str(ipaddress.ip_address(int(ipaddress.ip_address("198.18.0.0")) + n))


def open_log(path: str) -> IO[str]:
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="latin-1", errors="replace")
    return open(path, encoding="latin-1", errors="replace")


def read_entries(path: str, start: int, count: int) -> Iterator[LogEntry]:
    """Yields up to `count` parsed entries beginning at line `start` (0-based)."""
    with open_log(path) as fh:
        for line in islice(fh, start, None):
            entry = parse_line(line)
            if entry is not None:
                yield entry
                count -= 1
                if count <= 0:
                    return


async def replay(args: argparse.Namespace) -> int:
    entries = list(read_entries(args.logfile, args.start, args.count))
    if not entries:
        print("No parsable entries found in the requested slice.", file=sys.stderr)
        return 1

    span = entries[-1].timestamp - entries[0].timestamp
    print("=== Access Log Replay ===")
    print(f"Log file:   {args.logfile}")
    print(f"Requests:   {len(entries):,} (lines {args.start:,}+)")
    print(f"Log span:   {span / 3600:.2f} h  ->  replayed in ~{span / args.speed:.0f}s at {args.speed:g}x")
    print(f"Target:     {args.host}")
    print("=========================")

    statuses: Counter = Counter()
    per_route: Counter = Counter()
    errors = 0
    sem = asyncio.Semaphore(args.concurrency)
    max_lag = 0.0

    async def send(client: httpx.AsyncClient, entry: LogEntry) -> None:
        nonlocal errors
        route = map_route(entry.path)
        headers = {
            "X-Forwarded-For": client_ip(entry.host),
            "X-Request-ID": str(uuid.uuid4()),
            "User-Agent": "AccessLogReplay/1.0",
        }
        try:
            async with sem:
                resp = await client.get(f"{args.host.rstrip('/')}{route}", headers=headers, timeout=10.0)
            statuses[resp.status_code] += 1
            per_route[route] += 1
        except httpx.HTTPError:
            errors += 1

    t0_log = entries[0].timestamp
    t0_wall = time.perf_counter()
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(limits=limits) as client:
        tasks: List[asyncio.Task] = []
        for i, entry in enumerate(entries, 1):
            due = (entry.timestamp - t0_log) / args.speed
            delay = due - (time.perf_counter() - t0_wall)
            if delay > 0:
                await asyncio.sleep(delay)
            else:
                max_lag = max(max_lag, -delay)
            tasks.append(asyncio.create_task(send(client, entry)))
            if i % 5000 == 0:
                print(f"[replay] {i:,}/{len(entries):,} sent")
        await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - t0_wall
    total = sum(statuses.values())
    print("=== Replay finished ===")
    print(f"Elapsed:    {elapsed:.1f}s  ({total / elapsed:.0f} req/s achieved, max schedule lag {max_lag:.2f}s)")
    for code, n in sorted(statuses.items()):
        print(f"HTTP {code}:   {n:,}  ({n / max(total, 1) * 100:.1f}%)")
    print(f"Conn errors: {errors:,}")
    for route in ROUTES:
        print(f"{route:<16} {per_route[route]:,}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Replay a real access log through the rate limiter")
    p.add_argument("logfile", help="Common Log Format file (.gz supported)")
    p.add_argument("--host", default="http://localhost:8000", help="Gateway base URL")
    p.add_argument("--start", type=int, default=0, help="First line to replay (0-based)")
    p.add_argument("--count", type=int, default=20000, help="Number of requests to replay")
    p.add_argument("--speed", type=float, default=100.0, help="Time compression factor (default 100x)")
    p.add_argument("--concurrency", type=int, default=100, help="Max in-flight requests")
    return p


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(replay(build_parser().parse_args())))
    except KeyboardInterrupt:
        print("\n[replay] Terminated by user.")
        sys.exit(130)
