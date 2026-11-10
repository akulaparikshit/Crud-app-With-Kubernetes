"""Functional test of every CRUD endpoint (standard library only, no pip install).

Usage:
    python tests/functional_test.py                       # http://localhost:3000
    python tests/functional_test.py http://192.168.49.2:30080

Checks the same behaviour as the original Node.js app, including the error
cases (400 for invalid input / invalid id, 404 for a missing product).
"""
import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000").rstrip("/")
results = []


def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw.decode(errors="replace")


def expect(name, method, path, body, want_status, check=None):
    status, data = call(method, path, body)
    ok = status == want_status and (check is None or check(data))
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {method:6} {path:28} -> {status}  {name}")
    if not ok:
        print(f"      expected {want_status}, got {status}: {data}")
    return data


expect("health endpoint", "GET", "/health", None, 200,
       lambda d: d.get("status") == "healthy")
p = expect("create product", "POST", "/api/products",
           {"name": "Functional test", "quantity": 5, "price": 12.5}, 201,
           lambda d: d["name"] == "Functional test" and d["quantity"] == 5 and d["price"] == 12.5)
pid = p["id"] if isinstance(p, dict) and "id" in p else "0"

expect("read all contains it", "GET", "/api/products", None, 200,
       lambda d: any(x["id"] == pid for x in d))
expect("read one", "GET", f"/api/products/{pid}", None, 200,
       lambda d: d["id"] == pid and d["price"] == 12.5)
expect("update quantity", "PUT", f"/api/products/{pid}", {"quantity": 42}, 200,
       lambda d: d["quantity"] == 42)
expect("update same value", "PUT", f"/api/products/{pid}", {"quantity": 42}, 200)
expect("delete", "DELETE", f"/api/products/{pid}", None, 200,
       lambda d: d["message"] == "Product deleted successfully")
expect("read deleted -> 404", "GET", f"/api/products/{pid}", None, 404)
expect("update deleted -> 404", "PUT", f"/api/products/{pid}", {"quantity": 1}, 404)
expect("delete deleted -> 404", "DELETE", f"/api/products/{pid}", None, 404)

# Validation (same rules as the Node.js version)
expect("missing name -> 400", "POST", "/api/products", {"quantity": 1, "price": 1}, 400)
expect("null name -> 400", "POST", "/api/products", {"name": None, "quantity": 1, "price": 1}, 400)
expect("negative qty -> 400", "POST", "/api/products", {"name": "x", "quantity": -1, "price": 1}, 400)
expect("decimal qty -> 400", "POST", "/api/products", {"name": "x", "quantity": 1.5, "price": 1}, 400)
expect("negative price -> 400", "POST", "/api/products", {"name": "x", "quantity": 1, "price": -1}, 400)
expect("bad update qty -> 400", "PUT", "/api/products/1", {"quantity": "abc"}, 400)
expect("non-numeric id -> 400", "GET", "/api/products/abc", None, 400,
       lambda d: d["error"] == "Invalid product ID")
expect("non-numeric id PUT -> 400", "PUT", "/api/products/abc", {"quantity": 1}, 400)
expect("non-numeric id DELETE -> 400", "DELETE", "/api/products/abc", None, 400)

passed = sum(results)
print(f"\n{passed}/{len(results)} checks passed")
sys.exit(0 if passed == len(results) else 1)
