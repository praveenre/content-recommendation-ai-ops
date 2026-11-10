# Interactive Pipeline Demo Runner
Clear-Host
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  🎬 AI Content Recommendation Model Deployment Pipeline Demo  " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Select an option to execute:"
Write-Host "  [1] Step 1: Run Dependency Validation (Clean vs Conflicting)"
Write-Host "  [2] Step 2: Start Performance Monitoring Dashboard (Web UI)"
Write-Host "  [3] Step 3: Run Canary Deployment (Success Rollout)"
Write-Host "  [4] Step 3: Run Canary Deployment with Latency Spike (Auto-Rollback)"
Write-Host "  [5] Step 4: Run System Health Analysis & Root Cause Diagnosis"
Write-Host "  [6] Step 5: Run Component Unit Tests (11 tests)"
Write-Host "  [7] Step 5: Run Integration Tests (3 tests)"
Write-Host "  [8] Run Complete Pipeline End-to-End (run_pipeline.py)"
Write-Host "  [Q] Exit"
Write-Host ""

$choice = Read-Host "Enter option number [1-8, Q]"

switch ($choice) {
    "1" {
        Write-Host "`n[+] Running clean dependency validation..." -ForegroundColor Green
        python src/dependency_validator.py --reqs requirements.txt --dockerfile Dockerfile
        Write-Host "`n[+] Testing conflict detection against incompatible candidate..." -ForegroundColor Yellow
        python src/dependency_validator.py --reqs requirements.txt requirements_conflict.txt
    }
    "2" {
        Write-Host "`n[+] Starting Monitoring Dashboard at http://localhost:5001..." -ForegroundColor Green
        Write-Host "    Press Ctrl+C to stop the dashboard server." -ForegroundColor Gray
        python src/monitoring_dashboard.py
    }
    "3" {
        Write-Host "`n[+] Running successful Canary Deployment (v1.1.0)..." -ForegroundColor Green
        python src/deployment_orchestrator.py --candidate v1.1.0 --reqs requirements_candidate.txt
    }
    "4" {
        Write-Host "`n[+] Running Canary Deployment with Latency Spike at Stage 2..." -ForegroundColor Red
        python src/deployment_orchestrator.py --candidate v1.2.0-slow --reqs requirements_candidate.txt --fault-stage 2 --fault-type latency
    }
    "5" {
        Write-Host "`n[+] Executing System Health Analysis & RCA..." -ForegroundColor Cyan
        python src/health_analyzer.py --generate-sample-logs
    }
    "6" {
        Write-Host "`n[+] Running Component Isolation Tests..." -ForegroundColor Yellow
        python tests/test_components.py
    }
    "7" {
        Write-Host "`n[+] Running Integration Tests..." -ForegroundColor Yellow
        python tests/test_integration.py
    }
    "8" {
        Write-Host "`n[+] Running Complete Pipeline End-to-End..." -ForegroundColor Cyan
        python run_pipeline.py
    }
    Default {
        Write-Host "`nExiting demo runner." -ForegroundColor Gray
    }
}
