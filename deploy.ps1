# ── Travel Chatbot — Google Cloud Run Deploy Script ──────────────────────────
# Run this from the chatbot\ folder after installing gcloud CLI and Docker.
# Usage: .\deploy.ps1

Set-StrictMode -Off
$ErrorActionPreference = "Stop"

# ── 1. Project setup ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "=== Google Cloud Run Deployment ===" -ForegroundColor Cyan
Write-Host ""

$PROJECT_ID = Read-Host "Enter a Google Cloud project ID (e.g. travel-chatbot-2024)"
$REGION     = "asia-south1"   # Mumbai — closest to India

Write-Host ""
Write-Host "Creating project and enabling APIs..." -ForegroundColor Yellow

gcloud projects create $PROJECT_ID --name="Travel Chatbot" 2>$null
if (-not $?) { Write-Host "  (Project may already exist — continuing)" -ForegroundColor Gray }

gcloud config set project $PROJECT_ID

gcloud services enable `
    run.googleapis.com `
    cloudbuild.googleapis.com `
    secretmanager.googleapis.com `
    artifactregistry.googleapis.com `
    storage.googleapis.com

Write-Host "APIs enabled." -ForegroundColor Green

# ── 2. Billing check ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "IMPORTANT: Cloud Run requires billing to be enabled on your project." -ForegroundColor Yellow
Write-Host "If you haven't already, enable it at:" -ForegroundColor Yellow
Write-Host "  https://console.cloud.google.com/billing/linkedaccount?project=$PROJECT_ID" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter once billing is enabled (or if already done)"

# ── 3. Store secrets ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Storing secrets in Secret Manager..." -ForegroundColor Yellow

# Load .env file
$envFile = Get-Content .env
$envVars = @{}
foreach ($line in $envFile) {
    if ($line -match "^([^#=]+)=(.*)$") {
        $envVars[$matches[1].Trim()] = $matches[2].Trim()
    }
}

$GOOGLE_AI_KEY   = $envVars["GOOGLE_AI_KEY"]
$ADMIN_PASSWORD  = $envVars["ADMIN_PASSWORD"]

# Create secrets (skip if already exist)
echo $GOOGLE_AI_KEY  | gcloud secrets create GOOGLE_AI_KEY  --data-file=- 2>$null
echo $ADMIN_PASSWORD | gcloud secrets create ADMIN_PASSWORD --data-file=- 2>$null

# Service account JSON for analyzer
if (Test-Path "credentials\service_account.json") {
    gcloud secrets create SERVICE_ACCOUNT_JSON --data-file="credentials\service_account.json" 2>$null
    Write-Host "  Service account secret stored." -ForegroundColor Green
} else {
    Write-Host "  No service_account.json found — Sheets Analyzer will use public CSV fallback." -ForegroundColor Gray
}

Write-Host "Secrets stored." -ForegroundColor Green

# ── 4. Cloud Storage bucket for pricing data ──────────────────────────────────
Write-Host ""
Write-Host "Creating Cloud Storage bucket for pricing data..." -ForegroundColor Yellow

$BUCKET = "$PROJECT_ID-pricing"
gsutil mb -l $REGION "gs://$BUCKET" 2>$null
if (-not $?) { Write-Host "  (Bucket may already exist — continuing)" -ForegroundColor Gray }

gsutil cp pricing_data.json "gs://$BUCKET/pricing_data.json"
Write-Host "  Pricing data uploaded to gs://$BUCKET" -ForegroundColor Green

# Grant Cloud Run service account access to the bucket
$PROJECT_NUMBER = gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
$SA = "$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
gsutil iam ch "serviceAccount:${SA}:objectAdmin" "gs://$BUCKET"
Write-Host "Bucket ready." -ForegroundColor Green

# ── 5. Grant Secret Manager access ────────────────────────────────────────────
Write-Host ""
Write-Host "Granting Secret Manager access to Cloud Run service account..." -ForegroundColor Yellow
gcloud projects add-iam-policy-binding $PROJECT_ID `
    --member="serviceAccount:$SA" `
    --role="roles/secretmanager.secretAccessor" | Out-Null
Write-Host "Access granted." -ForegroundColor Green

# ── 6. Deploy App 1 — Travel Cost Chatbot (Python + Node frontend) ────────────
Write-Host ""
Write-Host "=== Deploying App 1: Travel Cost Chatbot ===" -ForegroundColor Cyan
Write-Host "Building and deploying (this takes 3-5 minutes)..." -ForegroundColor Yellow

gcloud run deploy travel-chatbot `
    --source . `
    --dockerfile Dockerfile `
    --platform managed `
    --region $REGION `
    --port 8080 `
    --allow-unauthenticated `
    --memory 512Mi `
    --cpu 1 `
    --set-env-vars "GCS_BUCKET=$BUCKET" `
    --set-secrets "GOOGLE_AI_KEY=GOOGLE_AI_KEY:latest,ADMIN_PASSWORD=ADMIN_PASSWORD:latest"

$CHATBOT_URL = gcloud run services describe travel-chatbot --region $REGION --format="value(status.url)"
Write-Host ""
Write-Host "App 1 deployed!" -ForegroundColor Green
Write-Host "  Chatbot URL  : $CHATBOT_URL" -ForegroundColor Cyan
Write-Host "  Admin panel  : $CHATBOT_URL/admin" -ForegroundColor Cyan

# ── 7. Deploy App 2 — Sheets / PDF Analyzer (Node.js) ────────────────────────
Write-Host ""
Write-Host "=== Deploying App 2: Sheets/PDF Analyzer ===" -ForegroundColor Cyan
Write-Host "Building and deploying..." -ForegroundColor Yellow

$SECRET_FLAGS = "GOOGLE_AI_KEY=GOOGLE_AI_KEY:latest"
if (Test-Path "credentials\service_account.json") {
    $SECRET_FLAGS = "$SECRET_FLAGS,SERVICE_ACCOUNT_JSON=SERVICE_ACCOUNT_JSON:latest"
}

gcloud run deploy sheets-analyzer `
    --source . `
    --dockerfile Dockerfile.analyzer `
    --platform managed `
    --region $REGION `
    --port 8080 `
    --allow-unauthenticated `
    --memory 512Mi `
    --cpu 1 `
    --set-secrets $SECRET_FLAGS

$ANALYZER_URL = gcloud run services describe sheets-analyzer --region $REGION --format="value(status.url)"
Write-Host ""
Write-Host "App 2 deployed!" -ForegroundColor Green
Write-Host "  Analyzer URL : $ANALYZER_URL" -ForegroundColor Cyan

# ── 8. Summary ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Deployment Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Travel Chatbot : $CHATBOT_URL" -ForegroundColor White
Write-Host "  Admin Panel    : $CHATBOT_URL/admin" -ForegroundColor White
Write-Host "  Sheets Analyzer: $ANALYZER_URL" -ForegroundColor White
Write-Host ""
Write-Host "Both apps scale to zero when idle (no traffic = no cost)." -ForegroundColor Gray
Write-Host ""
