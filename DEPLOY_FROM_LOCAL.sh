#!/bin/bash
# PharmaTrace Production Deployment — Execute this on your local machine WITH internet access
# This script will deploy everything to Supabase + Railway

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 PharmaTrace Production Deployment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⚠️  RUN THIS FROM YOUR LOCAL MACHINE (macOS/Linux/Windows Git Bash)"
echo "    This machine must have internet access to reach Supabase + Railway"
echo ""

# Check dependencies
check_command() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ $1 not found. Install with:"
        if [ "$1" = "railway" ]; then
            echo "   npm install -g @railway/cli"
        elif [ "$1" = "git" ]; then
            echo "   https://git-scm.com/download"
        else
            echo "   https://www.postgresql.org/download/"
        fi
        exit 1
    fi
}

echo "📋 Checking dependencies..."
check_command "git"
check_command "psql"
check_command "railway"

# Clone or pull latest code
echo ""
echo "📥 Pulling latest code from GitHub..."
if [ ! -d "pharma_trace" ]; then
    git clone https://github.com/Kevinbastin/pharma_trace.git
    cd pharma_trace
else
    cd pharma_trace
    git pull origin main
fi

# Apply Supabase migrations
echo ""
echo "📝 Step 1: Applying Supabase migrations (3 phases)..."
echo ""

SUPABASE_HOST="lfzxaxefdasqribypllf.supabase.co"
SUPABASE_USER="postgres"
SUPABASE_PASSWORD="B9dD@Ndp4sS7p+%"
SUPABASE_DB="postgres"

export PGPASSWORD="$SUPABASE_PASSWORD"

echo "   Connecting to $SUPABASE_HOST..."

psql -h "$SUPABASE_HOST" -U "$SUPABASE_USER" -d "$SUPABASE_DB" \
    -f backend/migrations/phase2_security.sql \
    && echo "✓ Phase 2: Security schema"

psql -h "$SUPABASE_HOST" -U "$SUPABASE_USER" -d "$SUPABASE_DB" \
    -f backend/migrations/phase3_data_governance.sql \
    && echo "✓ Phase 3: Data governance"

psql -h "$SUPABASE_HOST" -U "$SUPABASE_USER" -d "$SUPABASE_DB" \
    -f backend/migrations/phase4_safety_cases.sql \
    && echo "✓ Phase 4: Safety cases"

unset PGPASSWORD

# Configure Railway
echo ""
echo "🔧 Step 2: Authenticating with Railway..."
railway login

echo ""
echo "📌 Step 3: Setting Railway environment variables..."

RAILWAY_PROJECT_ID="lfzxaxefdasqribypllf"
railway env --project "$RAILWAY_PROJECT_ID"

# Set variables
railway variables set ENVIRONMENT=prod
railway variables set DEBUG=false
railway variables set JWT_SECRET="aVlbKys2aDO0Mi-w4o2QH7FjwI9nsPRdQQ1htjxTla3myc4Gdjp7F6WLxd8GdAtrH3aCfOQ7FdSyJkz_-N3Ts0nQBS5TisPxNIoIEzROoU9pxKFCb9giwvDLzhJwnfTS"
railway variables set HMAC_DAILY_SECRET="nfakCcN3wMiv9WCPuW5Z-YAMoHzx7Fgk2EVl-lUP7mquxnCYkMN_n0ibnJbVaRHC"
railway variables set CORS_ORIGINS="https://your-vercel-domain.vercel.app"
railway variables set SUPABASE_URL="https://lfzxaxefdasqribypllf.supabase.co"
railway variables set SUPABASE_KEY="sb_publishable_xqmz2ub2x9BM-XhAI8LEoQ_talRKGrq"

echo "✓ Variables configured"

# Redeploy
echo ""
echo "🚄 Step 4: Redeploying Railway backend..."
railway up

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⏳ Wait 2-5 minutes for Railway to finish redeploying..."
echo ""
echo "📋 Then verify:"
echo "   1. Get your Railway domain:"
echo "      railway domains"
echo ""
echo "   2. Test the health endpoint:"
echo "      curl https://<your-domain>/api/v1/health"
echo ""
echo "   3. Test the capabilities endpoint:"
echo "      curl https://<your-domain>/api/v1/capabilities"
echo ""
echo "✨ If both return 200 → backend is live!"
echo ""
