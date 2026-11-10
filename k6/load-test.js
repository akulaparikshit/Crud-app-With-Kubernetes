import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

// Full CRUD cycle per virtual user: create -> read all -> read one -> update -> delete.
//
// Run (PowerShell, from the repository root; k6 runs inside the Minikube Docker network):
//   docker run --rm -i --network minikube -v "${PWD}\k6:/k6" `
//     -e K6_WEB_DASHBOARD=true -e K6_WEB_DASHBOARD_EXPORT=/k6/results/report.html `
//     grafana/k6 run -e BASE_URL=http://<minikube-ip>:30080 `
//     --summary-export=/k6/results/summary.json --out csv=/k6/results/raw.csv /k6/load-test.js
const BASE_URL = __ENV.BASE_URL || "http://localhost:3000";

// Per-endpoint error rates so one failing endpoint can't hide behind the others.
const createErrors = new Rate("create_errors");
const readErrors   = new Rate("read_errors");
const updateErrors = new Rate("update_errors");
const deleteErrors = new Rate("delete_errors");

export const options = {
  stages: [
    { duration: "30s", target: 100 },  // warm up gunicorn, MySQL and the HPA
    { duration: "30s", target: 500 },  // ramp to target
    { duration: "60s", target: 500 },  // hold 500 VUs for 60 s (the required phase)
    { duration: "15s", target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_failed:   ["rate<0.01"],     // < 1 % failed requests
    http_req_duration: ["p(95)<2000"],    // 95 % of requests under 2 s
    create_errors:     ["rate<0.01"],
    read_errors:       ["rate<0.01"],
    update_errors:     ["rate<0.01"],
    delete_errors:     ["rate<0.01"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

// Group every /api/products/<id> URL under one name. Without this, each new id
// creates its own metric series (800 000+ in a 2-minute run), which makes k6
// itself slow and memory-hungry and distorts the measurement.
const ONE = "/api/products/:id";
const params = (name) => ({
  headers: { "Content-Type": "application/json" },
  timeout: "10s",
  tags: { name },
});

// Log the first few failures so the reason is visible in the k6 output.
// status 0 = no HTTP response at all (connection refused/reset, timeout).
let logged = 0;
function logFailure(step, res) {
  if (logged < 5) {
    logged++;
    console.warn(`${step} failed VU=${__VU} status=${res.status} ` +
                 `error="${res.error}" body=${String(res.body).slice(0, 120)}`);
  }
}

export default function () {
  // CREATE
  const created = http.post(
    `${BASE_URL}/api/products`,
    JSON.stringify({ name: `Product ${__VU}-${__ITER}`, quantity: 10, price: 9.99 }),
    params("/api/products"),
  );
  const createOk = check(created, {
    "create 201": (r) => r.status === 201,
    "create has id": (r) => {
      try { return !!r.json("id"); } catch (_) { return false; }
    },
  });
  createErrors.add(!createOk);
  if (!createOk) {
    logFailure("CREATE", created);
    sleep(1);
    return;
  }
  const id = created.json("id");

  // READ ALL + READ ONE
  const listRes = http.get(`${BASE_URL}/api/products`, params("/api/products"));
  const listOk = check(listRes, { "read all 200": (r) => r.status === 200 });
  readErrors.add(!listOk);
  if (!listOk) logFailure("READ ALL", listRes);

  const oneRes = http.get(`${BASE_URL}/api/products/${id}`, params(ONE));
  const oneOk = check(oneRes, { "read one 200": (r) => r.status === 200 });
  readErrors.add(!oneOk);
  if (!oneOk) logFailure("READ ONE", oneRes);

  // UPDATE (the API only updates quantity, like the original Node app)
  const upd = http.put(`${BASE_URL}/api/products/${id}`, JSON.stringify({ quantity: 25 }), params(ONE));
  const updOk = check(upd, { "update 200": (r) => r.status === 200 });
  updateErrors.add(!updOk);
  if (!updOk) logFailure("UPDATE", upd);

  // DELETE (keeps the table small, so READ ALL stays cheap during the test)
  const del = http.del(`${BASE_URL}/api/products/${id}`, null, params(ONE));
  const delOk = check(del, { "delete 200": (r) => r.status === 200 });
  deleteErrors.add(!delOk);
  if (!delOk) logFailure("DELETE", del);

  sleep(1);
}
