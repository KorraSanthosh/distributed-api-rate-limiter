# Distributed Rate Limiter & Traffic Analyzer System Design Document

This document explains the deep engineering decisions, performance analysis, scalability bottlenecks, and distributed systems considerations underlying this rate limiting project.

---

## 1. Core Rate Limiting Algorithm

### Why Sliding Window Log?
We selected the **Sliding Window Log** algorithm over Fixed Window and Token Bucket for several key reasons:
1. **Accurate Window Transitions**: Fixed window algorithms suffer from boundary bursts (double-rate allowance on boundaries). If a client has a limit of 100 requests/minute, they can send 100 requests at 11:59:59 and another 100 at 12:00:00, effectively bypassing the limit. Sliding Window Log completely mitigates this.
2. **Dynamic Spacing**: Timestamps are tracked dynamically, preventing micro-burst abuse.
3. **Multi-Policy Adaptability**: Because we store raw timestamps, we can query different interval slices (like our dual check: 60-second main window vs. 2-second burst window) from the exact same sorted set.

### Atomicity and Concurrency Control
Under heavy load, multiple concurrent worker processes will handle requests from the same client IP. A typical application-level rate limiter performs three steps:
1. Fetch timestamps from database.
2. Calculate and decide.
3. Write back the new timestamp.

If two requests hit separate API processes simultaneously, both can fetch the database state at the same time, see that the count is `Limit - 1`, and allow the request. Both write back their timestamps, violating the rate limit by allowing `Limit + 1` requests.

#### Solution: Redis Lua Scripts
We solve this race condition by encapsulating the entire read-decide-write logic into a single **Lua Script**.
- **Single-Threaded Execution**: Redis runs command scripts in a single execution thread. No other commands can execute while the Lua script is running.
- **Network Round Trip Reduction**: The entire transactional pipeline is pushed to the Redis database memory, eliminating network latency overhead between reads and writes.

---

## 2. Caching & Memory Analysis

### Memory Cost per IP
Since we use Redis Sorted Sets (`ZSET`), we must quantify the memory consumption per client IP to size our cluster correctly.

Let's assume:
- **Key size**: `rate_limit:255.255.255.255` = ~30 bytes.
- **Value**: Epoch timestamp string (e.g., `1719654160.123456`) = ~17 bytes.
- **Score**: Float64 timestamp = 8 bytes.

In Redis, a Sorted Set uses a skip list and a hash table. The overhead per entry in a ZSET is roughly:
- Hash entry: ~32 bytes
- Skip list node: ~32 bytes
- ZSET metadata: ~100 bytes (per key)

Assuming a maximum limit of **100 requests per window**:
$$\text{Memory per key} \approx 100 \text{ bytes} + 100 \times (17 \text{ bytes} + 8 \text{ bytes} + 64 \text{ bytes}) \approx 9,000 \text{ bytes} \approx 9 \text{ KB}$$

For **100,000 active clients** (IPs browsing within a window):
$$100,000 \times 9 \text{ KB} = 900,000 \text{ KB} \approx 900 \text{ MB} \approx 1 \text{ GB of Redis RAM}$$

This shows the Sliding Window Log is memory-intensive but highly feasible for modern Redis instances. To prune idle memory, we set a **TTL** on the Redis keys equal to the window length (e.g. 60 seconds). If a client goes idle, the entire sorted set is garbage collected by Redis.

### Computational Complexity
- `ZREMRANGEBYSCORE` (evicting old logs): $O(\log N + M)$ where $N$ is the number of elements in the sorted set and $M$ is the number of elements removed.
- `ZCARD` (counting elements): $O(1)$.
- `ZCOUNT` (burst calculation): $O(\log N)$.
- `ZADD` (inserting current timestamp): $O(\log N)$.
- `EXPIRE` (refreshing TTL): $O(1)$.

With a maximum set size $N \le 100$, these operations take less than **0.2ms** inside Redis, executing in microseconds.

---

## 3. Distributed Scalability Discussion

### Horizontal Scaling of the API
Since the API servers are stateless, we can scale them horizontally behind an Nginx or AWS Application Load Balancer (ALB). The load balancer routes requests using consistent hashing on the client IP, or round-robin.

### Redis Scalability at Scale
When scaling to millions of active users, a single Redis node will become a bottleneck. We scale Redis using three strategies:
1. **Redis Cluster (Sharding)**:
   - Redis automatically shards keys across 16,384 hash slots.
   - Keys like `rate_limit:{client_ip}` are hashed by IP. This distributes the rate limiting load evenly across multiple Redis master nodes.
   - Since Lua scripts require all keys inside the script to belong to the same slot, we must ensure our rate limit key is the only key referenced. Our script complies with this rule (it uses `KEYS[1]` only).
2. **Redis Sentinel**:
   - For high availability, Sentinel provides automatic failover if a Redis master node goes down, promoting a replica.
3. **Local In-Memory Cache (L1 Cache)**:
   - For ultra-high load APIs, we can add a local in-memory L1 cache (e.g., using Python's `cachetools` or `dict`) with a tiny TTL (e.g., 500ms).
   - If a client is hitting the API at 1,000 RPS, we can block them locally on the API server for 500ms before querying Redis again, saving database network calls.

---

## 4. Observability Architecture

Our observability pipeline implements a production-style metrics and event architecture:
- **Telemetry**: Exposes `/metrics` containing counters and latency histograms. Prometheus scrapes this data, allowing engineers to configure Alertmanager alerts for high HTTP 429 rates (indicating potential DDoS attacks or api abuse).
- **Audit Event Logging**: Pushing logs to a Redis Stream is non-blocking to the API request path. A separate consumer (in this case, Streamlit) processes these logs sequentially. In a large system, this Redis Stream can be consumed by log shippers (like Logstash or Vector) to index events in Elasticsearch or OpenSearch.

---

## 5. Future Engineering Improvements

1. **Token Bucket / Leaky Bucket Lua Script Transition**:
   - If memory becomes a critical bottleneck, we can transition from Sliding Window Log to **Token Bucket**.
   - Token Bucket only requires storing two fields per IP: `tokens_remaining` (float) and `last_updated_time` (float) inside a Hash.
   - This reduces memory from ~9KB per IP to ~100 bytes, enabling 10x scale on the same Redis hardware, though losing high-precision logging of individual request offsets.
2. **Dynamic Adaptive Limiting**:
   - The rate limit can dynamically adjust depending on the downstream database load or CPU utilization. If the database CPU exceeds 80%, the API gateway can automatically scale down client rate limits.
3. **User-Agent & Client ID Tiering**:
   - Extend the rate limiter to look at JWT claims (e.g. `client_tier: premium` gets 10,000 RPM, `client_tier: basic` gets 100 RPM) rather than relying solely on IP addresses.
