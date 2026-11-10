# Load test results

## Overall

| Requests | Throughput | Failed | p50 | p90 | p95 | p99 | max |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 195870 | 1399 req/s | 0.00 % | 12 ms | 71 ms | 99 ms | 178 ms | 309 ms |

## Over time (10-second windows)

| Window | VUs | req/s | Error rate | p50 | p90 | p95 | p99 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0-10s | 30 | 84 | 0.00 % | 2 ms | 3 ms | 3 ms | 4 ms |
| 10-20s | 63 | 246 | 0.00 % | 2 ms | 3 ms | 3 ms | 5 ms |
| 20-30s | 96 | 410 | 0.00 % | 2 ms | 3 ms | 4 ms | 5 ms |
| 30-40s | 217 | 814 | 0.00 % | 2 ms | 4 ms | 5 ms | 9 ms |
| 40-50s | 350 | 1464 | 0.00 % | 3 ms | 8 ms | 10 ms | 18 ms |
| 50-60s | 483 | 1999 | 0.00 % | 8 ms | 37 ms | 64 ms | 102 ms |
| 60-70s | 500 | 1975 | 0.00 % | 35 ms | 141 ms | 181 ms | 240 ms |
| 70-80s | 500 | 2144 | 0.00 % | 24 ms | 76 ms | 100 ms | 147 ms |
| 80-90s | 500 | 2142 | 0.00 % | 22 ms | 79 ms | 99 ms | 172 ms |
| 90-100s | 500 | 2168 | 0.00 % | 19 ms | 74 ms | 108 ms | 177 ms |
| 100-110s | 500 | 2140 | 0.00 % | 21 ms | 75 ms | 106 ms | 207 ms |
| 110-120s | 500 | 2092 | 0.00 % | 24 ms | 86 ms | 108 ms | 143 ms |
| 120-130s | 500 | 1654 | 0.00 % | 4 ms | 43 ms | 73 ms | 129 ms |
| 130-140s | 196 | 255 | 0.00 % | 2 ms | 4 ms | 6 ms | 14 ms |

## Per endpoint

| Endpoint | Requests | Failed | p50 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| `DELETE /api/products/:id` | 39174 | 0.00 % | 12 ms | 95 ms | 172 ms |
| `GET /api/products [GET]` | 39174 | 0.00 % | 13 ms | 102 ms | 179 ms |
| `GET /api/products/:id` | 39174 | 0.00 % | 12 ms | 101 ms | 184 ms |
| `POST /api/products [POST]` | 39174 | 0.00 % | 11 ms | 95 ms | 172 ms |
| `PUT /api/products/:id` | 39174 | 0.00 % | 13 ms | 100 ms | 181 ms |

## CPU and memory per pod during the test (kubectl top, every 5 s)

| Pod | Samples | Avg CPU | Max CPU | Max CPU vs limit | Avg memory | Max memory | Max memory vs limit |
|---|---:|---:|---:|---:|---:|---:|---:|
| flask-crud-app | 271 | 1411m | 2064m | 103 % of 2000m | 131 Mi | 151 Mi | 29 % of 512 Mi |
| mysql | 271 | 430m | 671m | 34 % of 2000m | 480 Mi | 482 Mi | 47 % of 1024 Mi |
