import argparse
import asyncio
import ipaddress
import random
import sys
import time
import uuid
from typing import List
import httpx

# Predefined target endpoints
ENDPOINTS = [
    "/api/v1/status",
    "/api/v1/data",
    "/api/v1/users",
    "/api/v1/orders",
]


def generate_fake_ips(count: int) -> List[str]:
    """Generates random public client IPs.

    Private/reserved addresses are skipped: the gateway treats those as trusted proxies
    (TRUSTED_PROXIES) and would not use them as the client identity.
    """
    ips: List[str] = []
    while len(ips) < count:
        ip = f"{random.randint(1, 254)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"
        if ipaddress.ip_address(ip).is_global:
            ips.append(ip)
    return ips


async def send_request(
    client: httpx.AsyncClient,
    base_url: str,
    ip: str,
    endpoint: str,
    method: str = "GET",
) -> None:
    """Dispatches a single HTTP request with custom header tracing."""
    url = f"{base_url.rstrip('/')}{endpoint}"
    req_id = str(uuid.uuid4())
    headers = {
        "X-Forwarded-For": ip,
        "X-Request-ID": req_id,
        "User-Agent": "TrafficGeneratorSimulator/1.0",
    }
    
    start = time.perf_counter()
    try:
        if method == "GET":
            response = await client.get(url, headers=headers, timeout=5.0)
        else:
            response = await client.post(url, headers=headers, timeout=5.0)
            
        latency = (time.perf_counter() - start) * 1000
        status = response.status_code
        
        # Format terminal log depending on status
        if status == 200:
            status_str = f"\033[32m{status} OK\033[reset"
        elif status == 429:
            status_str = f"\033[31m{status} TOO MANY REQUESTS (Rate Limited)\033[reset"
        else:
            status_str = f"\033[33m{status} ERROR\033[reset"
            
        # Clean terminal color reset helper
        status_str = status_str.replace("reset", "0m")
        
        print(
            f"[Simulator] IP: {ip:<15} | Path: {endpoint:<15} | "
            f"Status: {status_str:<32} | Latency: {latency:.2f}ms"
        )
    except httpx.HTTPError as e:
        print(f"\033[31m[Simulator] Connection error hitting {url} from {ip}: {e}\033[0m", file=sys.stderr)


async def worker_normal(client: httpx.AsyncClient, base_url: str, ips: List[str], stop_event: asyncio.Event) -> None:
    """Simulates a normal web user browsing randomly with delays."""
    print("[Simulator] Started Normal Traffic worker.")
    while not stop_event.is_set():
        ip = random.choice(ips)
        endpoint = random.choice(ENDPOINTS)
        await send_request(client, base_url, ip, endpoint)
        # Sleep for a random delay between 0.5s and 2.0s
        await asyncio.sleep(random.uniform(0.5, 2.0))


async def worker_burst(client: httpx.AsyncClient, base_url: str, ip: str, endpoint: str) -> None:
    """Fires a sudden burst of requests from a single IP to trigger rate limiting limits."""
    print(f"[Simulator] Launching burst traffic from IP {ip} on {endpoint}")
    # Fire 15 requests consecutively with no delay
    tasks = [send_request(client, base_url, ip, endpoint) for _ in range(15)]
    await asyncio.gather(*tasks)


async def worker_ddos(client: httpx.AsyncClient, base_url: str, ips: List[str], stop_event: asyncio.Event) -> None:
    """Aggressively hammers the server from many different fake IPs simultaneously."""
    while not stop_event.is_set():
        ip = random.choice(ips)
        endpoint = random.choice(ENDPOINTS)
        # Fire request and yield control immediately without delay
        asyncio.create_task(send_request(client, base_url, ip, endpoint))
        await asyncio.sleep(0.01)  # 10ms delay between generating tasks to avoid overloading client CPU


async def run_traffic_simulator(args: argparse.Namespace) -> None:
    """Main coordinator for starting traffic simulation profiles."""
    print("=== Starting Traffic Simulator ===")
    print(f"Target Host: {args.host}")
    print(f"Mode:        {args.mode.upper()}")
    print(f"Duration:    {args.duration} seconds")
    print("==================================")

    # Initialize shared AsyncClient
    limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
    async with httpx.AsyncClient(limits=limits) as client:
        stop_event = asyncio.Event()

        # Set up general IP pool
        normal_ips = generate_fake_ips(50)
        ddos_ips = generate_fake_ips(500)

        tasks = []

        if args.mode in ("normal", "all"):
            # Spawn normal traffic workers
            for _ in range(args.concurrency):
                tasks.append(asyncio.create_task(worker_normal(client, args.host, normal_ips, stop_event)))

        if args.mode in ("ddos", "all"):
            # Spawn DDoS workers
            for _ in range(args.concurrency * 2):
                tasks.append(asyncio.create_task(worker_ddos(client, args.host, ddos_ips, stop_event)))

        if args.mode in ("burst", "all"):
            # Periodically trigger bursts in the background
            async def burst_scheduler():
                burst_ip = "203.0.113.99"  # public-looking (TEST-NET-3); private IPs would be treated as proxies
                while not stop_event.is_set():
                    # Pick a high-value endpoint (e.g. orders)
                    target = "/api/v1/orders"
                    await worker_burst(client, args.host, burst_ip, target)
                    # Sleep 10s between bursts
                    await asyncio.sleep(10.0)

            tasks.append(asyncio.create_task(burst_scheduler()))

        # Run for specified duration
        await asyncio.sleep(args.duration)
        print("[Simulator] Duration elapsed. Shutting down traffic generator...")
        stop_event.set()

        # Gather running workers
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    print("=== Traffic Simulator Finished ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distributed API Rate Limiter Traffic Simulator")
    parser.add_argument(
        "--host",
        type=str,
        default="http://localhost:8000",
        help="Target base URL of the API gateway (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="normal",
        choices=["normal", "burst", "ddos", "all"],
        help="Traffic profile mode (default: normal)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Duration of the traffic run in seconds (default: 30)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Number of concurrent workers (default: 3)",
    )

    args = parser.parse_args()
    
    # Run loop
    try:
        asyncio.run(run_traffic_simulator(args))
    except KeyboardInterrupt:
        print("\n[Simulator] Terminated by user.")
