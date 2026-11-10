"""Turns raw k6 / kubectl-top output into tables and charts for the report.

Standard library only (no pip install). Run from the repository root after a test:
    python k6/analyze_results.py [results-dir]

Reads   k6/results/raw.csv        (k6 --out csv=...)
        k6/results/pod-usage.csv  (written by scripts/run-load-test.ps1, optional)
Writes  k6/results/results-tables.md   latency percentiles, error rate and throughput
                                       per 10-second window + per-endpoint table
                                       + CPU/memory per pod
        k6/results/latency-over-time.svg
        k6/results/errors-throughput-over-time.svg
        k6/results/pod-cpu-over-time.svg
"""
import csv
import math
import os
import sys
from collections import defaultdict

RESULTS = sys.argv[1] if len(sys.argv) > 1 else os.path.join("k6", "results")
WINDOW = 10  # seconds per row


def pct(values, p):
    if not values:
        return float("nan")
    v = sorted(values)
    k = (len(v) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def fmt_ms(x):
    return "-" if math.isnan(x) else (f"{x / 1000:.2f} s" if x >= 1000 else f"{x:.0f} ms")


# ---------- k6 raw CSV ----------
durations = defaultdict(list)          # window -> [ms]
failed = defaultdict(lambda: [0, 0])   # window -> [failed, total]
vus = {}
per_ep = defaultdict(list)             # endpoint -> [ms]
per_ep_fail = defaultdict(lambda: [0, 0])
status0 = defaultdict(int)
t0 = None

with open(os.path.join(RESULTS, "raw.csv"), newline="") as f:
    for row in csv.DictReader(f):
        m = row["metric_name"]
        if m not in ("http_req_duration", "http_req_failed", "vus"):
            continue
        ts = float(row["timestamp"])
        t0 = ts if t0 is None else min(t0, ts)
        row["_t"] = ts
        if m == "vus":
            vus[ts] = float(row["metric_value"])
            continue
        name = f'{row.get("method", "")} {row.get("name", "")}'.strip()
        if m == "http_req_duration":
            durations[ts].append(float(row["metric_value"]))
            per_ep[name].append(float(row["metric_value"]))
        else:
            v = int(float(row["metric_value"]))
            failed[ts][0] += v
            failed[ts][1] += 1
            per_ep_fail[name][0] += v
            per_ep_fail[name][1] += 1
            if v and row.get("status") == "0":
                status0[row.get("error", "") or "no response"] += 1


def bucket(d, merge):
    out = defaultdict(merge)
    for ts, val in d.items():
        w = int((ts - t0) // WINDOW)
        if isinstance(val, list) and merge is list:
            out[w].extend(val)
        elif merge is list:
            out[w].append(val)
        else:
            out[w][0] += val[0]
            out[w][1] += val[1]
    return out


dur_w = bucket(durations, list)
fail_w = bucket(failed, lambda: [0, 0])
vus_w = defaultdict(list)
for ts, v in vus.items():
    vus_w[int((ts - t0) // WINDOW)].append(v)

windows = sorted(set(dur_w) | set(fail_w))
rows = []
for w in windows:
    d = dur_w.get(w, [])
    fl, tot = fail_w.get(w, [0, 0])
    rows.append({
        "t": f"{w * WINDOW}-{(w + 1) * WINDOW}s",
        "x": w * WINDOW + WINDOW / 2,
        "vus": max(vus_w.get(w, [0])),
        "rps": tot / WINDOW,
        "err": 100 * fl / tot if tot else 0.0,
        "p50": pct(d, 50), "p90": pct(d, 90), "p95": pct(d, 95), "p99": pct(d, 99),
    })

all_d = [x for v in durations.values() for x in v]
all_f = sum(v[0] for v in failed.values())
all_t = sum(v[1] for v in failed.values())
duration_s = (windows[-1] + 1) * WINDOW if windows else 1

md = ["# Load test results", ""]
md += ["## Overall", "",
       "| Requests | Throughput | Failed | p50 | p90 | p95 | p99 | max |",
       "|---:|---:|---:|---:|---:|---:|---:|---:|",
       f"| {all_t} | {all_t / duration_s:.0f} req/s | {100 * all_f / max(all_t, 1):.2f} % | "
       f"{fmt_ms(pct(all_d, 50))} | {fmt_ms(pct(all_d, 90))} | {fmt_ms(pct(all_d, 95))} | "
       f"{fmt_ms(pct(all_d, 99))} | {fmt_ms(max(all_d) if all_d else float('nan'))} |", ""]
md += [f"## Over time ({WINDOW}-second windows)", "",
       "| Window | VUs | req/s | Error rate | p50 | p90 | p95 | p99 |",
       "|---|---:|---:|---:|---:|---:|---:|---:|"]
for r in rows:
    md.append(f"| {r['t']} | {r['vus']:.0f} | {r['rps']:.0f} | {r['err']:.2f} % | "
              f"{fmt_ms(r['p50'])} | {fmt_ms(r['p90'])} | {fmt_ms(r['p95'])} | {fmt_ms(r['p99'])} |")
md += ["", "## Per endpoint", "",
       "| Endpoint | Requests | Failed | p50 | p95 | p99 |", "|---|---:|---:|---:|---:|---:|"]
for name in sorted(per_ep):
    fl, tot = per_ep_fail[name]
    d = per_ep[name]
    md.append(f"| `{name}` | {tot} | {100 * fl / max(tot, 1):.2f} % | "
              f"{fmt_ms(pct(d, 50))} | {fmt_ms(pct(d, 95))} | {fmt_ms(pct(d, 99))} |")
if status0:
    md += ["", "## Requests with no HTTP response (status 0)", "", "| Error | Count |", "|---|---:|"]
    md += [f"| {e} | {c} |" for e, c in sorted(status0.items(), key=lambda x: -x[1])]


# ---------- SVG charts ----------
def svg_chart(path, title, series, y_label, x_max, y_max=None, right=None):
    """series: [(label, colour, [(x, y), ...])]; right: optional (label, colour, points, max)"""
    W, H, L, R, T, B = 760, 340, 64, 64 if right else 20, 40, 48
    pw, ph = W - L - R, H - T - B
    ys = [y for _, _, pts in series for _, y in pts if not math.isnan(y)]
    y_max = y_max or (max(ys) * 1.1 if ys else 1) or 1
    sx = lambda x: L + pw * x / x_max
    sy = lambda y, m=y_max: T + ph - ph * min(y, m) / m
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Arial" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="white"/>',
         f'<text x="{W / 2}" y="22" text-anchor="middle" font-size="15" font-weight="bold">{title}</text>']
    for i in range(6):
        y = y_max * i / 5
        o.append(f'<line x1="{L}" x2="{L + pw}" y1="{sy(y)}" y2="{sy(y)}" stroke="#e5e5e5"/>')
        o.append(f'<text x="{L - 6}" y="{sy(y) + 4}" text-anchor="end" fill="#555">{y:.0f}</text>')
    step = next(s for s in (10, 20, 30, 60, 120, 300, 600, 1800, 3600, 10**9) if x_max / s <= 10)
    for i in range(0, int(x_max) + 1, step):
        o.append(f'<text x="{sx(i)}" y="{T + ph + 18}" text-anchor="middle" fill="#555">{i}s</text>')
    o.append(f'<text x="{L + pw / 2}" y="{H - 8}" text-anchor="middle" fill="#333">time since start</text>')
    o.append(f'<text transform="translate(16 {T + ph / 2}) rotate(-90)" text-anchor="middle" fill="#333">{y_label}</text>')
    o.append(f'<line x1="{L}" x2="{L}" y1="{T}" y2="{T + ph}" stroke="#333"/>'
             f'<line x1="{L}" x2="{L + pw}" y1="{T + ph}" y2="{T + ph}" stroke="#333"/>')
    legend = list(series)
    lw = max(120, max(len(lbl) for lbl, _, _ in legend) * 7 + 30)
    if right:
        rl, rc, rpts, rmax = right
        rmax = rmax or 1
        for i in range(6):
            y = rmax * i / 5
            o.append(f'<text x="{L + pw + 6}" y="{sy(y, rmax) + 4}" fill="{rc}">{y:.1f}</text>')
        o.append(f'<polyline fill="none" stroke="{rc}" stroke-width="2" stroke-dasharray="5 3" points="'
                 + " ".join(f"{sx(x):.1f},{sy(y, rmax):.1f}" for x, y in rpts) + '"/>')
        legend.append((rl, rc, None))
    lw = max(120, max(len(lbl) for lbl, _, _ in legend) * 7 + 30)
    for label, colour, pts in series:
        pts = [(x, y) for x, y in pts if not math.isnan(y)]
        o.append(f'<polyline fill="none" stroke="{colour}" stroke-width="2" points="'
                 + " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in pts) + '"/>')
    for i, (label, colour, _) in enumerate(legend):
        o.append(f'<rect x="{L + 10 + i * lw}" y="{T + 4}" width="12" height="12" fill="{colour}"/>'
                 f'<text x="{L + 26 + i * lw}" y="{T + 14}">{label}</text>')
    o.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(o))


x_max = duration_s
svg_chart(os.path.join(RESULTS, "latency-over-time.svg"), "Response time percentiles over time",
          [("p50", "#2c7be5", [(r["x"], r["p50"]) for r in rows]),
           ("p90", "#f0a202", [(r["x"], r["p90"]) for r in rows]),
           ("p95", "#e55353", [(r["x"], r["p95"]) for r in rows]),
           ("p99", "#7a3fbf", [(r["x"], r["p99"]) for r in rows])],
          "milliseconds", x_max)
svg_chart(os.path.join(RESULTS, "errors-throughput-over-time.svg"), "Throughput, VUs and error rate over time",
          [("req/s", "#2c7be5", [(r["x"], r["rps"]) for r in rows]),
           ("VUs", "#999999", [(r["x"], r["vus"]) for r in rows])],
          "requests per second / VUs", x_max,
          right=("error % (right)", "#e55353", [(r["x"], r["err"]) for r in rows],
                 max(5.0, max((r["err"] for r in rows), default=0) * 1.2)))

# ---------- kubectl top CSV (optional) ----------
usage_file = os.path.join(RESULTS, "pod-usage.csv")
if os.path.exists(usage_file):
    usage = defaultdict(list)
    order = []
    with open(usage_file, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                usage[r["pod"]].append((r["time"], float(r["cpu_millicores"]), float(r["memory_mib"])))
            except (ValueError, KeyError):
                continue
            if r["time"] not in order:
                order.append(r["time"])
    md += ["", "## CPU and memory per pod during the test (kubectl top, every 5 s)", "",
           "| Pod | Samples | Avg CPU | Max CPU | Max CPU vs limit | Avg memory | Max memory | Max memory vs limit |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for pod, vals in sorted(usage.items()):
        cpu = [v[1] for v in vals]
        mem = [v[2] for v in vals]
        is_db = pod.startswith("mysql")
        cpu_lim, mem_lim = (2000, 1024) if is_db else (2000, 512)
        md.append(f"| {pod} | {len(vals)} | {sum(cpu) / len(cpu):.0f}m | {max(cpu):.0f}m | "
                  f"{100 * max(cpu) / cpu_lim:.0f} % of {cpu_lim}m | {sum(mem) / len(mem):.0f} Mi | "
                  f"{max(mem):.0f} Mi | {100 * max(mem) / mem_lim:.0f} % of {mem_lim} Mi |")
    idx = {t: i * 5 for i, t in enumerate(order)}
    palette = ["#2c7be5", "#e55353", "#f0a202", "#2a9d8f", "#7a3fbf", "#555555", "#d6336c"]
    svg_chart(os.path.join(RESULTS, "pod-cpu-over-time.svg"), "CPU per pod during the test (kubectl top)",
              [(p[-24:], palette[i % len(palette)], [(idx[t], c) for t, c, _ in v])
               for i, (p, v) in enumerate(sorted(usage.items()))],
              "millicores", max(idx.values()) or 1)

with open(os.path.join(RESULTS, "results-tables.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(md) + "\n")
print("\n".join(md))
print(f"\nWritten to {RESULTS}: results-tables.md and *.svg charts")
