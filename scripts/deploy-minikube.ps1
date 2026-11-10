# Builds the image inside Minikube and deploys everything.
# Usage (repository root, PowerShell):  .\scripts\deploy-minikube.ps1
minikube addons enable metrics-server
minikube image build -t flask-crud-app:1.0 .
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/mysql.yaml
kubectl rollout status deployment/mysql --timeout=300s
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
# Restart so the pods pick up a rebuilt image with the same tag
kubectl rollout restart deployment/flask-crud-app
kubectl rollout status deployment/flask-crud-app --timeout=180s
kubectl get pods,services,hpa -o wide
python tests/functional_test.py "http://$((minikube ip).Trim()):30080"
