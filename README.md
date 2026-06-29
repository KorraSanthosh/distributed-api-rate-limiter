# Distributed API Rate Limiter & Traffic Analyzer

A production-grade, high-performance distributed rate limiter and traffic analytics gateway built using FastAPI, Redis Sorted Sets, Redis Streams, Streamlit, Docker, and Prometheus.

---

## 🚀 Key Features

*   **Atomic Sliding Window Rate Limiting**: Implements a precise sliding window log algorithm using Redis Sorted Sets (`ZSET`).
*   **Dual-Policy Guardrails**: Protects routes against overall limit violations (e.g. 60 RPM) and micro-burst spikes (e.g. 15 requests in 2 seconds).
*   **Race-Condition Free**: Bundles evaluation and write logic into atomic **Lua scripts** executed inside Redis.
*   **Non-Blocking Stream Analytics**: Logs traffic events to **Redis Streams** asynchronously via non-blocking `asyncio` background tasks.
*   **Real-Time Analytics Dashboard**: Visualizes request rates, block rates, p95 latencies, top requested routes, and malicious client IPs on a **Streamlit** dashboard.
*   **Observability Exporter**: Integrates a Prometheus endpoint (`/metrics`) tracking HTTP statistics, Redis pool sizes, latency histograms, and server errors.
*   **Robust Testing**: Tests rate eviction, IP proxy spoofing, fail-open logic, and route query filters using `pytest` and `pytest-asyncio`.

---

## 🛠️ Technology Stack

*   **API Framework**: Python 3.11, FastAPI, Pydantic v2, Uvicorn
*   **Database/Cache**: Redis (`redis.asyncio` driver)
*   **Monitoring**: Prometheus
*   **Visualization**: Streamlit, Plotly, Pandas
*   **Testing**: Pytest, Pytest-Asyncio, HTTPX
*   **Dev Quality**: Ruff, Black, Mypy
*   **Orchestration**: Docker, Docker Compose

---

## 📂 Project Structure

```
distributed-rate-limiter/
├── app/                  # Main FastAPI Application
│   ├── api/              # Controllers & Dependency Injectors
│   ├── core/             # Settings, Logging & Metrics configurations
│   ├── middleware/       # Rate-Limiting & Analytics interception
│   ├── models/           # Pure Domain representation
│   ├── repositories/     # Redis Data Access layer (Lua scripts)
│   └── schemas/          # Pydantic v2 validation definitions
├── config/               # Prometheus configuration files
├── dashboard/            # Streamlit dashboard analytics console
├── docs/                 # System Design & Interview preparation documents
├── scripts/              # Async traffic generator simulator
└── tests/                # Complete Pytest test suite
```

---

## 📦 Getting Started

### Prerequisites

Ensure you have the following installed:
*   [Docker & Docker Compose](https://docs.docker.com/get-docker/)
*   [Python 3.11+](https://www.python.org/downloads/) (if running tests locally)

---

### 1. Run with Docker Compose (Recommended)

To spin up the entire cluster (API Gateway, Redis, Streamlit, Prometheus) run:

```bash
docker compose up --build
```

Once all containers are healthy, you can access the following services:

| Service | Port / URL | Description |
| :--- | :--- | :--- |
| **FastAPI Gateway** | [http://localhost:8000](http://localhost:8000) | Root API endpoint |
| **API Interactive Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | Swagger OpenAPI UI |
| **Prometheus Exporter** | [http://localhost:8000/metrics](http://localhost:8000/metrics) | Telemetry raw scraping endpoint |
| **Streamlit Dashboard** | [http://localhost:8501](http://localhost:8501) | Real-time traffic UI dashboard |
| **Prometheus Console** | [http://localhost:9090](http://localhost:9090) | Prometheus metric server console |

---

### 2. Run the Traffic Simulator

Open a new terminal window and run the traffic simulator to feed events into the rate limiter:

```bash
# Set up virtual environment and install requirements
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the traffic generator in 'all' mode (simulating normal, burst, and DDoS requests)
python scripts/traffic_generator.py --host http://localhost:8000 --mode all --duration 60
```

Watch the Streamlit dashboard (`http://localhost:8501`) refresh in real-time to display the spikes, blocked traffic counts, and latency percentages!

---

### 3. Running the Test Suite

To run tests with full code coverage reporting:

```bash
# Ensure a local Redis server is running (tests default to using DB 9)
pytest -v --cov=app tests/
```

---

## ⚙️ Configurable Rate Limit Policies

The system enforces custom rate limit parameters at the route level inside `app/services/rate_limit_service.py`:

*   `/api/v1/status`: 100 requests per 60 seconds (Burst: 120 per 2s)
*   `/api/v1/users`: 30 requests per 60 seconds (Burst: 45 per 2s)
*   `/api/v1/orders`: 10 requests per 60 seconds (Burst: 15 per 2s)
*   *Default (all other paths)*: 60 requests per 60 seconds (Burst: 80 per 2s)
