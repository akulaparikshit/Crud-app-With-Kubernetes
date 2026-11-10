# Runs the 500-VU k6 test against the Minikube NodePort and records CPU/memory
# of every pod while the test runs.
# Usage (repository root, PowerShell):  .\scripts\run-load-test.ps1
$ip   = (minikube ip).Trim()
$url  = "http://${ip}:30080"
$out  = Join-Path $PWD "k6\results"
New-Item -ItemType Directory -Force $out | Out-Null

Write-Host "Target: $url"
kubectl get pods,hpa -o wide | Tee-Object "$out\before-pods.txt"

# Background job: kubectl top every 5 s -> k6\results\pod-usage.csv
$monitor = Start-Job -ArgumentList $out -ScriptBlock {
    param($out)
    "time,pod,cpu_millicores,memory_mib" | Set-Content "$out\pod-usage.csv"
    while ($true) {
        $t = Get-Date -Format "HH:mm:ss"
        kubectl top pods --no-headers 2>$null | ForEach-Object {
            $c = ($_ -split "\s+")
            "$t,$($c[0]),$($c[1] -replace 'm',''),$($c[2] -replace 'Mi','')" | Add-Content "$out\pod-usage.csv"
        }
        kubectl get hpa flask-crud-hpa --no-headers 2>$null | ForEach-Object { "$t $_" } | Add-Content "$out\hpa-during-test.txt"
        Start-Sleep -Seconds 5
    }
}

# k6 runs as a container on the Minikube Docker network (the 'minikube service'
# tunnel on Windows cannot carry 500 connections). Results land in k6\results.
docker run --rm -i --network minikube `
    -v "${PWD}\k6:/k6" `
    -e K6_WEB_DASHBOARD=true `
    -e K6_WEB_DASHBOARD_EXPORT=/k6/results/report.html `
    grafana/k6 run -e BASE_URL=$url `
    --summary-export=/k6/results/summary.json `
    --out csv=/k6/results/raw.csv `
    /k6/load-test.js 2>&1 | Tee-Object "$out\k6-output.txt"

Stop-Job $monitor; Remove-Job $monitor
kubectl get pods,hpa -o wide | Tee-Object "$out\after-pods.txt"
Write-Host "`nResults in k6\results: k6-output.txt, summary.json, report.html, pod-usage.csv"
Write-Host "Make the tables for the report with:  python k6\analyze_results.py"
