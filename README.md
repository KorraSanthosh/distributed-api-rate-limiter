# Distributed API Rate Limiter & Traffic Analyzer

A distributed rate limiter and traffic-analytics gateway built with **FastAPI**, **Redis** (Sorted Sets, Lua scripts, Streams), a **React** dashboard, and **Prometheus** metrics, packaged with Docker Compose.

Every request passes through a sliding-window rate limiter backed by Redis, so limits hold across multiple API instances. Allowed *and* blocked requests are streamed to Redis and visualised live.

---

## 🚀 Key Features

*   **Atomic sliding-window rate limiting**: a sliding-window log on Redis Sorted Sets (`ZSET`), evaluated and updated in a single **Lua script**, so there are no race conditions between instances.
*   **Dual-policy guardrails**: each route has a per-window limit (e.g. 10 requests / 60 s) *and* a short burst limit (e.g. 15 requests / 2 s).
*   **Per-route, per-client limits**: every route keeps its own counter per client (`rate_limit:<route>:<client_ip>`), so one route never consumes another's budget.
*   **Spoof-resistant client IP**: `X-Forwarded-For` / `X-Real-IP` are only trusted from proxies you list in `TRUSTED_PROXIES`.
*   **Fail-open**: if Redis is down, requests are still served and `/api/v1/status` reports `degraded`. The limiter recovers on its own when Redis returns.
*   **Non-blocking analytics**: every request (including `429`s) is written to a **Redis Stream** by a background task, off the request path.
*   **React dashboard**: live KPIs, traffic chart, status split, per-endpoint traffic, top abusive clients, a **recently blocked requests** feed (client IP, endpoint, time), and a live request table.
*   **Prometheus exporter** at `/metrics`: request counters, blocked counters, latency histograms, Redis operation counters, and error counters.
*   **Standard 429 responses**: `Retry-After` and `X-RateLimit-*` headers plus a JSON error body.

---

## 🧭 How it works

```
Client ──► FastAPI gateway ───────────────► route handlers (/status /data /users /orders)
             │  ▲
             │  └── AnalyticsMiddleware  ──► Redis Stream  api_traffic_stream
             └───── RateLimiterMiddleware ─► Redis ZSET + Lua  (allow / block + headers)

React dashboard ──► GET /api/v1/analytics/summary ──► aggregates the stream
Prometheus ───────► GET /metrics
```

`AnalyticsMiddleware` is the outermost layer, so it also records the `429` responses the limiter short-circuits.

---

## 🛠️ Technology Stack

*   **API**: Python 3.11+, FastAPI, Pydantic v2, Uvicorn
*   **Data store**: Redis (`redis.asyncio`): Sorted Sets, Lua scripting, Streams
*   **Dashboard**: React 18, Vite, Recharts (plus a legacy Streamlit dashboard)
*   **Monitoring**: Prometheus
*   **Testing**: Pytest, pytest-asyncio, pytest-cov, HTTPX
*   **Dev quality**: Ruff, Black, Mypy
*   **Orchestration**: Docker, Docker Compose, nginx (serves the React build)

---

## 📂 Project Structure

```
distributed-api-rate-limiter/
├── app/                  # FastAPI application
│   ├── api/              # Routes (v1) & dependency injectors
│   ├── core/             # Settings, logging, Prometheus metrics
│   ├── middleware/       # Rate limiting & analytics interception
│   ├── models/           # Domain dataclasses
│   ├── repositories/     # Redis data access (Lua script, streams)
│   ├── schemas/          # Pydantic schemas
│   └── services/         # Rate-limit policies & analytics aggregation
├── frontend/             # React + Vite dashboard (nginx Dockerfile included)
├── dashboard/            # Legacy Streamlit dashboard
├── config/               # Prometheus configuration
├── scripts/              # Traffic simulator & access-log replay tool
├── tests/                # Pytest suite
└── docs/                 # System design notes
```

---

## 📦 Getting Started

### Prerequisites

*   [Docker & Docker Compose](https://docs.docker.com/get-docker/) for the one-command setup
*   Python 3.11+ and a local Redis, to run the API or tests without Docker
*   Node.js 20+, to run the React dashboard in development

### 1. Run everything with Docker Compose

```bash
docker compose up --build
```

| Service | URL | Description |
| :--- | :--- | :--- |
| **React Dashboard** | [http://localhost:3000](http://localhost:3000) | Live traffic UI (primary) |
| **FastAPI Gateway** | [http://localhost:8000](http://localhost:8000) | API |
| **Swagger Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | Interactive API docs |
| **Prometheus Exporter** | [http://localhost:8000/metrics](http://localhost:8000/metrics) | Raw metrics |
| **Streamlit Dashboard** | [http://localhost:8501](http://localhost:8501) | Legacy dashboard |
| **Prometheus Console** | [http://localhost:9090](http://localhost:9090) | Prometheus UI |

### 2. Run locally without Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Redis must be listening on localhost:6379
# TRUSTED_PROXIES lets the traffic simulator fake client IPs (see "Client IP & trusted proxies")
TRUSTED_PROXIES=127.0.0.0/8 uvicorn app.main:app --port 8000 --no-proxy-headers

# In another terminal: the React dashboard (proxies /api to localhost:8000)
cd frontend && npm install && npm run dev      # http://localhost:3000
```

Set `VITE_API_TARGET` to point the dev proxy at a different API host. `npm run build` produces a static bundle.

The legacy Streamlit dashboard needs the repo root on the Python path when run outside Docker:

```bash
PYTHONPATH=. streamlit run dashboard/main.py   # http://localhost:8501
```

### 3. Generate traffic

**Synthetic traffic** (normal users, bursts, and many-IP floods):

```bash
python scripts/traffic_generator.py --host http://localhost:8000 --mode all --duration 60
```

**Real traffic**: replay a real public web-server access log (Common Log Format, `.gz` supported) through the limiter, with the original request timing and client identities. The public [NASA HTTP logs](https://ita.ee.lbl.gov/html/contrib/NASA-HTTP.html) work well (download one yourself, e.g. `NASA_access_log_Jul95.gz`):

```bash
python scripts/replay_access_log.py NASA_access_log_Jul95.gz --start 600000 --count 20000 --speed 200
```

Each log URL is mapped to one of the four API routes by a stable hash, hostnames are mapped to stable pseudonymous IPs, and the recorded `200`/`429` statuses are the gateway's real responses. In the Docker demo (which trusts private ranges as proxies) these appear in `198.18.0.0/15`.

### 4. Run the tests

```bash
# A local Redis must be running; tests use Redis DB 9
pytest -v --cov=app tests/
```

---

## 🔌 API Reference

| Endpoint | Description | Rate limit (per client, per 60 s) |
| :--- | :--- | :--- |
| `GET /api/v1/status` | Service and Redis health | 100 (burst 120 / 2 s) |
| `GET /api/v1/data` | Paginated mock metrics (`page`, `limit`) | 60 (burst 80 / 2 s) |
| `GET /api/v1/users` | Mock users (`role`, `is_active` filters) | 30 (burst 45 / 2 s) |
| `GET /api/v1/orders` | Mock orders (`customer_id`, `status` filters) | 10 (burst 15 / 2 s) |
| `GET /api/v1/analytics/summary` | Aggregated traffic stats for the dashboard, incl. the newest blocked requests (`window_seconds`) | not limited, not logged |
| `GET /metrics` | Prometheus metrics | not limited |
| `GET /docs` | Swagger UI | not limited |

Any other path uses the default policy (60 per 60 s, burst 80 per 2 s). `/users`, `/orders` and `/data` return **static mock data**: they exist as targets for the rate limiter.

Policies live in `app/services/rate_limit_service.py`.

**When a limit is hit** the gateway returns `429` with `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining: 0` and `X-RateLimit-Reset`, and a body like:

```json
{"detail": {"message": "Rate limit exceeded. Please try again later.",
            "limit": 10, "burst_limit": 15, "current_count": 10, "reset_in_seconds": 60}}
```

Allowed responses carry `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` and `X-Request-ID`.

### Client IP & trusted proxies

`X-Forwarded-For` / `X-Real-IP` are client-controlled, so they are **ignored by default** and the socket peer address is used. To run behind a reverse proxy or load balancer, set `TRUSTED_PROXIES` to a comma-separated list of proxy IPs/CIDRs (e.g. `TRUSTED_PROXIES=10.0.0.0/8`). When the peer is trusted, the client is the right-most address in `X-Forwarded-For` that is not itself a trusted proxy; malformed values are rejected.

`docker-compose.yml` trusts private ranges so the traffic simulator can fake client IPs for the demo. **Narrow this in production.** Start uvicorn with `--no-proxy-headers` (as `Dockerfile.api` does) so uvicorn's own forwarded-header handling doesn't override `TRUSTED_PROXIES`.

---

## ⚙️ Configuration

All settings are environment variables (a `.env` file is also read). Every one has a default.

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `ENV` | `dev` | `dev`, `prod` or `test` profile |
| `REDIS_HOST` / `REDIS_PORT` | `localhost` / `6379` | Redis location |
| `REDIS_DB` | `0` (`9` in tests) | Redis database |
| `REDIS_PASSWORD` | unset | Redis auth |
| `REDIS_TIMEOUT` / `REDIS_MAX_CONNECTIONS` | `2.0` / `50` | Connection pool |
| `TRUSTED_PROXIES` | empty | Proxies whose forwarded-IP headers are trusted |
| `RATE_LIMIT_WINDOW_SECONDS` / `RATE_LIMIT_MAX_REQUESTS` / `RATE_LIMIT_BURST_LIMIT` | `60` / `60` / `80` | Default policy for unlisted paths |
| `LOG_LEVEL` / `LOG_FILE_PATH` | `INFO` / `logs/app.json` | Logging |

---

## 🩺 Troubleshooting

*   **Streamlit: `No module named 'app'`**: run it with `PYTHONPATH=.` (Docker does this for you).
*   **Dashboard shows "Can't reach the API"**: the API isn't running on port 8000 (or `VITE_API_TARGET` is wrong).
*   **Everything is blocked in the simulator / one client shows all the traffic**: the gateway isn't trusting the sender, so every request looks like it came from one IP. Set `TRUSTED_PROXIES` (see above).
*   **Tests skip or fail to connect**: start Redis on `localhost:6379`.
