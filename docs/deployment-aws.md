# Deploying to AWS (single EC2 server)

The whole stack (nginx + React, API, Redis, Prometheus, Streamlit) runs on **one small EC2 instance**
with Docker Compose. This is the cheapest option and is enough for a demo or portfolio project.

> **Status:** the production configuration (`docker-compose.prod.yml`) was tested locally with Docker
> Desktop. The AWS steps below have **not** been run on a real AWS account yet; check each step as you go.

## What the production override changes

`docker-compose.prod.yml` is layered on top of `docker-compose.yml`:

| | Dev (`docker-compose.yml`) | Production (`+ docker-compose.prod.yml`) |
|---|---|---|
| Published ports | 3000, 8000, 8501, 9090, 6382 | **only** the web port (`HTTP_PORT`, default 80) |
| API / Redis / Prometheus / Streamlit | reachable from the host | private Docker network only |
| `TRUSTED_PROXIES` | all private ranges (so the simulator can fake IPs) | `172.16.0.0/12` (only the nginx container) |

Tested locally: with the override, only the nginx port answers, and 15 requests with rotating fake
`X-Forwarded-For` headers were limited to 10 allowed / 5 blocked. Spoofing does not work.

## Cost (approximate; check the AWS pricing page)

| Item | Approx. per month |
|---|---|
| EC2 `t3.small` (2 GB RAM) | ~$15 |
| 20 GB gp3 disk | ~$2 |
| Public IPv4 address | ~$4 |
| **Total** | **~$20** (so about 5 months on $100 of credits) |

The running stack used roughly 260 MB of RAM in local tests. A `t3.micro` (1 GB) may run it, but building
the images (installing Streamlit and pandas) is more comfortable on a `t3.small`.

**Avoid:** NAT Gateways (~$32/month), Application Load Balancers (~$17/month) and forgotten resources.
Set a **budget alert** first (Billing → Budgets, for example at $20, $50 and $80).

## Steps

1. **Launch the instance** (EC2 → Launch instance)
   - AMI: Ubuntu Server 24.04 LTS, type `t3.small`, 20 GB gp3 disk.
   - Create a key pair and keep the `.pem` file safe.
   - **Security group:** allow `22` (SSH) from **your IP only**, and `80` (HTTP). Nothing else.

2. **Connect and install Docker**
   ```bash
   ssh -i your-key.pem ubuntu@<public-ip>
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker ubuntu && exit        # then SSH in again
   ```

3. **Get the code and start the stack**
   ```bash
   git clone https://github.com/KorraSanthosh/distributed-api-rate-limiter.git
   cd distributed-api-rate-limiter
   HTTP_PORT=80 docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
   docker compose -f docker-compose.yml -f docker-compose.prod.yml ps     # wait for "healthy"
   ```

4. **Check it:** open `http://<public-ip>/` (dashboard) and `http://<public-ip>/docs` (Swagger).

5. **Stop paying when done**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml down
   ```
   Then **terminate** the instance in the EC2 console (stopping alone still bills for the disk and IP).

## Things to know

- **No authentication.** Anyone who can reach the server can view the dashboard and `/docs`. For a demo,
  restrict port 80 in the security group to your own IP, or add HTTP basic auth in `frontend/nginx.conf`.
- **No HTTPS.** Traffic is plain HTTP. For a real deployment add a domain and a TLS terminator
  (for example Caddy or certbot); this is not set up here.
- **The traffic simulator looks like one client.** In production the fake `X-Forwarded-For` IPs are
  intentionally ignored, so simulator traffic appears as a single IP. To see many distinct clients, use real
  traffic or temporarily widen `TRUSTED_PROXIES` on a test machine.
- **Redis is one container with a volume.** There is no replication or backup.
