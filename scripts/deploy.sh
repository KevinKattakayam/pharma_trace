#!/bin/bash
# PharmaTrace Production Deployment Script
# Usage: ./scripts/deploy.sh <supabase_db_url> <railway_token> <vercel_domain>
# Example: ./scripts/deploy.sh "postgresql://user:pass@host/db" "rly_..." "https://pharmatrace.vercel.app"

set -e

if [ "$#" -lt 3 ]; then
    echo "Usage: $0 <supabase_db_url> <railway_token> <vercel_domain>"
    echo ""
    echo "Example:"
    echo "  $0 'postgresql://postgres:password@db.supabase.co/postgres' 'rly_token_here' 'https://pharmatrace.vercel.app'"
    exit 1
fi

SUPABASE_DB_URL="$1"
RAILWAY_TOKEN="$2"
VERCEL_DOMAIN="$3"
BACKEND_DIR="$(cd "$(dirname "$0")/../backend" && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 PharmaTrace Production Deployment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Step 1: Apply migrations
echo ""
echo "📝 Step 1: Applying Supabase migrations..."
echo "   Connecting to: $SUPABASE_DB_URL"
echo ""

if psql "$SUPABASE_DB_URL" -f "$BACKEND_DIR/migrations/phase2_security.sql" 2>&1 | grep -i error; then
    echo "❌ phase2_security.sql failed. Review error above."
    exit 1
fi
echo "✓ phase2_security.sql applied"

if psql "$SUPABASE_DB_URL" -f "$BACKEND_DIR/migrations/phase3_data_governance.sql" 2>&1 | grep -i error; then
    echo "❌ phase3_data_governance.sql failed. Review error above."
    exit 1
fi
echo "✓ phase3_data_governance.sql applied"

if psql "$SUPABASE_DB_URL" -f "$BACKEND_DIR/migrations/phase4_safety_cases.sql" 2>&1 | grep -i error; then
    echo "❌ phase4_safety_cases.sql failed. Review error above."
    exit 1
fi
echo "✓ phase4_safety_cases.sql applied"

# Step 2: Set Railway variables (requires Railway CLI authenticated)
echo ""
echo "🔧 Step 2: Setting Railway environment variables..."
echo "   (Requires: railway CLI installed and authenticated)"
echo ""

JWT_SECRET="aVlbKys2aDO0Mi-w4o2QH7FjwI9nsPRdQQ1htjxTla3myc4Gdjp7F6WLxd8GdAtrH3aCfOQ7FdSyJkz_-N3Ts0nQBS5TisPxNIoIEzROoU9pxKFCb9giwvDLzhJwnfTS"
HMAC_DAILY_SECRET="nfakCcN3wMiv9WCPuW5Z-YAMoHzx7Fgk2EVl-lUP7mquxnCYkMN_n0ibnJbVaRHC"

if ! command -v railway &> /dev/null; then
    echo "⚠️  Railway CLI not installed. Install it or set variables manually in Railway Dashboard."
    echo "   See DEPLOYMENT_CHECKLIST.md for manual steps."
    exit 1
fi

railway variables set ENVIRONMENT=prod || echo "⚠️  Could not set ENVIRONMENT (may need railway login)"
railway variables set DEBUG=false || echo "⚠️  Could not set DEBUG"
railway variables set JWT_SECRET="$JWT_SECRET" || echo "⚠️  Could not set JWT_SECRET"
railway variables set HMAC_DAILY_SECRET="$HMAC_DAILY_SECRET" || echo "⚠️  Could not set HMAC_DAILY_SECRET"
railway variables set CORS_ORIGINS="$VERCEL_DOMAIN" || echo "⚠️  Could not set CORS_ORIGINS"

echo "✓ Railway variables set (verify in Dashboard)"

# Step 3: Redeploy
echo ""
echo "🚄 Step 3: Redeploying Railway..."
railway up || echo "⚠️  Could not trigger redeploy (may need manual trigger in Dashboard)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment script completed!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Next:"
echo "   1. Wait 2-5 minutes for Railway redeploy to finish"
echo "   2. Test endpoints:"
echo "      curl https://<railway-domain>/api/v1/health"
echo "      curl https://<railway-domain>/api/v1/capabilities"
echo "   3. See DEPLOYMENT_CHECKLIST.md for full verification steps"
echo ""
