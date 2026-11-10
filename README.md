# Flask CRUD App – Inventory Management System

The original Node.js/PostgreSQL inventory app (`original-node-app/`) rewritten in
Python/Flask with MySQL, containerized with Docker, deployed on Minikube, load-tested
with k6 and checked for self-healing.

## Project structure
```
app.py                       Flask app (CRUD API + /health)
gunicorn.conf.py             Gunicorn settings (gthread, 4 workers x 4 threads, env-configurable)
templates/index.html         Web page (same page as the original app)
requirements.txt             Python dependencies (pinned)
Dockerfile                   Multi-stage build (python:3.12 -> python:3.12-slim), non-root user
docker-compose.yaml          Flask app + MySQL, named network, named volume, healthchecks
k8s/secret.yaml              Database credentials (Secret)
k8s/mysql.yaml               MySQL PVC + Deployment + ClusterIP Service
k8s/deployment.yaml          Flask Deployment (1 replica, requests/limits, startup/readiness/liveness on /health)
k8s/service.yaml             NodePort Service (port 30080)
k8s/hpa.yaml                 HorizontalPodAutoscaler (1-5 pods at 60 % CPU)
k6/load-test.js              Ramp to 500 virtual users, hold 60 s, full CRUD cycle per user
k6/analyze_results.py        Builds tables + charts (latency percentiles, errors, CPU) from the results
k6/results/                  Output of a test run (git-ignored except what you commit for the report)
tests/functional_test.py     Functional test of every endpoint incl. error cases (no dependencies)
scripts/deploy-minikube.ps1  Build + deploy + functional test on Minikube
scripts/run-load-test.ps1    Runs k6 and records kubectl top every 5 s during the test
scripts/fault-tolerance.ps1  Crash / pod deletion / database outage demo, output saved to a file
docs/REPORT.md               Report draft (follows the assignment structure)
docs/reference-run/          Results of a reference run with Docker Compose
original-node-app/           Original Node.js app, kept for reference
```

## API endpoints
| Method | Endpoint             | Success | Errors |
|--------|----------------------|---------|--------|
| GET    | /health              | 200 `{"status":"healthy"}` | – |
| POST   | /api/products        | 201 product | 400 invalid name/quantity/price, 500 DB error |
| GET    | /api/products        | 200 list ordered by id | 500 |
| GET    | /api/products/<id>   | 200 product | 400 non-numeric id, 404, 500 |
| PUT    | /api/products/<id>   | 200 product (updates quantity only) | 400, 404, 500 |
| DELETE | /api/products/<id>   | 200 `{"message":"Product deleted successfully"}` | 400, 404, 500 |

## Assumptions
- Python 3.12, Flask 3.1.3, gunicorn 27.0.0, mysql-connector-python 26.10.0, MySQL 8.4 (official image).
- App listens on port 3000 (same as the original), MySQL on 3306, NodePort 30080.
- The `products` table is created automatically on the first request (`CREATE TABLE IF NOT EXISTS`), so no migration tool is needed. `BIGINT AUTO_INCREMENT` replaces PostgreSQL's `GENERATED ALWAYS AS IDENTITY`, `DECIMAL(10,2)` replaces `NUMERIC(10,2)`.
- Ids are returned as strings and prices as numbers, like the original app's read endpoints.
- Gunicorn runs 4 workers x 4 threads (`gthread`) = 16 requests in parallel per pod. Each worker has its own MySQL pool whose size equals its thread count (4), so the pool can never run dry; 5 pods (HPA maximum) x 4 x 4 = 80 connections, below `max_connections=300`.
- MySQL runs with `--skip-log-bin` (single server, no replication) and `--innodb-flush-log-at-trx-commit=2` (redo log flushed once per second): up to ~1 s of writes could be lost if the node crashes. Acceptable here, not for a bank.
- Docker Compose keeps the credentials as plain environment variables for simplicity; Kubernetes reads them from a Secret. Real passwords would never be committed to Git.
- `/health` does not query MySQL on purpose: restarting the app would not repair the database, and the API already answers 500 while MySQL is down.

## Run with Docker Compose
```
docker compose up --build -d
docker compose ps
python tests/functional_test.py
```
Open http://localhost:3000. Stop with `docker compose down` (add `-v` to also delete the data).

## Deploy on Minikube (PowerShell)
```
minikube start
.\scripts\deploy-minikube.ps1
```
or step by step:
```
minikube addons enable metrics-server
minikube image build -t flask-crud-app:1.0 .
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/mysql.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
kubectl get pods,services,hpa
python tests/functional_test.py http://<minikube-ip>:30080
```

## Load test
k6 runs in a container on the Minikube Docker network and calls the NodePort directly
(the `minikube service` tunnel on Windows cannot handle 500 connections).
```
.\scripts\run-load-test.ps1
python k6\analyze_results.py
```
Results: `k6/results/k6-output.txt`, `summary.json`, `report.html` (k6 web dashboard with
charts over time), `pod-usage.csv`, `results-tables.md` and `*.svg` charts.

## Fault tolerance
```
.\scripts\fault-tolerance.ps1
```
Kills gunicorn inside the pod (restart count goes up), deletes the pod (ReplicaSet creates a
new one) and deletes the MySQL pod (API returns 500, then recovers with the data intact).
Output is saved to `k6/results/fault-tolerance.txt`.
