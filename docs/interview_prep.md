# Interview Preparation & Resume Guide

This document contains simulated technical interview questions, deep architectural answers, and high-impact resume bullet points designed for senior/staff software engineering roles.

---

## 1. Technical Interview Questions & Answers

### Q1: How does your rate limiter handle clock drift between different API nodes?
**Answer**:
Our rate limiter reads the epoch timestamp from the application server (`time.time()`) and sends it to Redis as an argument. If the system clocks of different API servers drift, the rate limiter can produce incorrect results (e.g. evaluating window sizes inconsistently).
- **Mitigation**: Instead of trusting the API node clock, we can request the time directly from Redis using the Redis `TIME` command. Since all rate limit checks hit the same Redis cluster, using Redis's internal server clock guarantees a unified, monotonic, drift-free timeline.
- **Implementation**: We can call `await redis.time()` on the repository layer before the Lua script run and pass that timestamp. Since the `TIME` call adds a small round-trip delay, we make a trade-off: use node time for performance (sub-millisecond latency) if servers are NTP-synchronized, or use Redis time for strict monotonic correctness.

### Q2: What happens to the system if Redis goes down completely?
**Answer**:
A critical design choice is whether a rate limiter should **fail-open** or **fail-closed**:
- **Fail-Open (Our implementation)**: If Redis throws a connection exception, we catch it, increment a Prometheus error counter (`app_errors_total`), log a critical warning, and return `allowed = True`. This ensures that a database outage doesn't result in a complete outage of the customer-facing API.
- **Fail-Closed**: Under strict security or monetization mandates (e.g., paid billing APIs), we would fail-closed: return an HTTP 500/503 service unavailable to block traffic and protect downstream systems from un-throttled abuse.

### Q3: How do you address the "Hot Key" issue in Redis under a massive traffic spike?
**Answer**:
If a single client IP (or a highly active crawler) hammers the API, all rate limit checks for that IP hit the exact same Redis key. This creates a "hot key" bottleneck on a single Redis cluster node.
- **Local In-Memory Cache (L1 Cache)**: We can introduce a short-lived local cache (e.g., using Python's `cachetools` or memory dict) directly on the API server. If a client is blocked, we cache the blocked status for 1 second. Subsequent requests within that second are rejected locally on the API node, completely bypassing Redis.
- **Consistent Hashing**: Configure load balancers to hash requests by client IP. This pins client requests to specific API instances, maximizing the hit rate of local L1 rate limit caches.

### Q4: What are the trade-offs of using Lua scripts inside Redis?
**Answer**:
- **Pros**: Lua scripts execute atomically, avoiding race conditions without requiring slow distributed locks (`Redlock`). They also minimize network round trips by bundling multiple commands.
- **Cons**: Redis is single-threaded. If a Lua script is poorly written or runs complex operations (like iterating over large sets), it blocks the entire Redis server process, stalling all other client operations. We mitigate this by keeping our ZSET sizes small ($N \le 100$) and using `ZREMRANGEBYSCORE` to prune old elements, ensuring script execution takes microseconds.

---

## 2. High-Impact Resume Bullet Points

Here is how you can represent this project on a resume targeting companies like Google, Cloudflare, Stripe, or Meta:

- **Distributed Systems & Architecture**:
  > Designed and implemented a high-throughput, distributed rate limiter in FastAPI and Redis using a dual-check Sliding Window Log algorithm, supporting configurable normal (60s) and burst (2s) request windows for 100k+ active client IPs.
- **Performance & Concurrency**:
  > Eliminated rate-limiting race conditions under high concurrency by authoring atomic Lua scripts to manage Redis Sorted Sets, keeping rate-limiting evaluation latency under 2ms.
- **Observability & Analytics**:
  > Structured real-time request analytics by building a non-blocking request interception pipeline that logs API traffic to Redis Streams asynchronously via `asyncio.create_task`, preventing performance degradation.
- **Infrastructure & Monitoring**:
  > Exposed service health metrics using Prometheus exporters and integrated structured JSON logging, enabling real-time Grafana/Streamlit dashboards to track 95th percentile request latencies and trace malicious client IP addresses.
