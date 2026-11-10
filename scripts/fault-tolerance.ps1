# Deliverable 4 demo: Kubernetes self-healing.
# Usage (repository root, PowerShell):  .\scripts\fault-tolerance.ps1
# Saves every step's output to k6\results\fault-tolerance.txt for the report.
$log = "k6\results\fault-tolerance.txt"
New-Item -ItemType Directory -Force "k6\results" | Out-Null
function Step($title, [scriptblock]$cmd) {
    "`n===== $title  ($(Get-Date -Format 'HH:mm:ss')) =====" | Tee-Object -Append $log
    & $cmd 2>&1 | Out-String | Tee-Object -Append $log
}
"Fault tolerance test $(Get-Date)" | Set-Content $log

$pod = (kubectl get pods -l app=flask-crud-app -o jsonpath="{.items[0].metadata.name}")
Step "1. Before: pods and restart count" { kubectl get pods -o wide }

# Test A - process crash: kill gunicorn (PID 1) inside the container.
# The container exits, the kubelet restarts it in the SAME pod -> RESTARTS +1.
Step "2. Simulate crash: kill PID 1 (gunicorn) in $pod" { kubectl exec $pod -- sh -c "kill 1" }
Start-Sleep -Seconds 3
Step "3. Right after the crash" { kubectl get pods -o wide }
Start-Sleep -Seconds 20
Step "4. After ~20 s: same pod name, RESTARTS increased" { kubectl get pods -o wide }
Step "5. Pod events" { kubectl describe pod $pod | Select-String -Pattern "Restart Count|Last State|Reason|Exit Code|Killing|Started|Pulled|Created" }

# Test B - pod loss: delete the pod. The Deployment's ReplicaSet notices that
# fewer pods exist than desired and creates a NEW pod (new name).
Step "6. Delete pod $pod" { kubectl delete pod $pod --wait=false }
Start-Sleep -Seconds 2
Step "7. Replacement pod being created" { kubectl get pods -o wide }
kubectl rollout status deployment/flask-crud-app --timeout=120s | Out-Null
Step "8. Replacement pod Ready" { kubectl get pods -o wide }

# Test C - database outage: the API returns 500 while MySQL is down and
# recovers by itself once the MySQL pod is back (data kept on the PVC).
$ip = (minikube ip).Trim()
$dbpod = (kubectl get pods -l app=mysql -o jsonpath="{.items[0].metadata.name}")
Step "9. Delete MySQL pod $dbpod" { kubectl delete pod $dbpod --wait=false }
Start-Sleep -Seconds 3
Step "10. API while MySQL is restarting (expect error 500)" {
    try { Invoke-RestMethod "http://${ip}:30080/api/products" -TimeoutSec 10 } catch { "HTTP error: $($_.Exception.Message)" }
}
kubectl rollout status deployment/mysql --timeout=180s | Out-Null
Start-Sleep -Seconds 5
Step "11. API after MySQL is back (data still there)" { Invoke-RestMethod "http://${ip}:30080/api/products" | Format-Table }
Step "12. Final state" { kubectl get pods -o wide }
Write-Host "`nSaved to $log"
