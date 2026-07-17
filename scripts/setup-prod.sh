#!/bin/bash
# Apply Supabase migrations and update Railway variables
# This script must be run from a machine with network access to Supabase and Railway CLI

set -e

BACKEND_DIR="$(cd "$(dirname "$0")/../backend" && pwd)"
SUPABASE_HOST="${SUPABASE_HOST:-lfzxaxefdasqribypllf.supabase.co}"
SUPABASE_USER="${SUPABASE_USER:-postgres}"
SUPABASE_DB="${SUPABASE_DB:-postgres}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 PharmaTrace Production Setup & Migration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Step 1: Apply Supabase migrations
echo ""
echo "📝 Applying Supabase migrations (phase2, phase3, phase4)..."
echo ""

# Note: Set PGPASSWORD if using psql
if command -v psql &> /dev/null; then
    echo "   Using psql to connect to Supabase..."
    # Ensure we have the password in PGPASSWORD env var
    if [ -z "$PGPASSWORD" ]; then
        echo "   ⚠️  Set PGPASSWORD environment variable or enter password when prompted:"
        read -sp "   Enter Supabase password: " PGPASSWORD
        export PGPASSWORD
    fi
    
    psql -h "$SUPABASE_HOST" -U "$SUPABASE_USER" -d "$SUPABASE_DB" \
        -f "$BACKEND_DIR/migrations/phase2_security.sql" && echo "✓ phase2_security.sql"
    psql -h "$SUPABASE_HOST" -U "$SUPABASE_USER" -d "$SUPABASE_DB" \
        -f "$BACKEND_DIR/migrations/phase3_data_governance.sql" && echo "✓ phase3_data_governance.sql"
    psql -h "$SUPABASE_HOST" -U "$SUPABASE_USER" -d "$SUPABASE_DB" \
        -f "$BACKEND_DIR/migrations/phase4_safety_cases.sql" && echo "✓ phase4_safety_cases.sql"
else
    echo "   ⚠️  psql not found. Trying Python + psycopg2..."
    cd "$BACKEND_DIR"
    ./venv/bin/python - << 'PY'
import os
import psycopg2

try:
    conn = psycopg2.connect(
        host=os.getenv("SUPABASE_HOST", "lfzxaxefdasqribypllf.supabase.co"),
        user=os.getenv("SUPABASE_USER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
        database=os.getenv("SUPABASE_DB", "postgres")
    )
    cursor = conn.cursor()
    
    for phase in ["phase2_security", "phase3_data_governance", "phase4_safety_cases"]:
        with open(f"migrations/{phase}.sql", "r") as f:
            cursor.execute(f.read())
        conn.commit()
        print(f"✓ {phase}.sql")
    
    cursor.close()
    conn.close()
    print("\n✅ All migrations applied!")
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)
PY
fi

# Step 2: Railway setup (requires CLI)
echo ""
echo "🔧 Configuring Railway environment variables..."
echo ""

if ! command -v railway &> /dev/null; then
    echo "   ⚠️  Railway CLI not found. Install with:"
    echo "      npm install -g @railway/cli"
    echo ""
    echo "   Then run:"
    echo "      railway login"
    echo "      railway link"
    echo "      railway variables set ENVIRONMENT=prod"
    echo "      railway variables set DEBUG=false"
    echo "      railway variables set JWT_SECRET=\"...\" (from .env)"
    echo "      railway variables set HMAC_DAILY_SECRET=\"...\" (from .env)"
    echo "      railway variables set CORS_ORIGINS=\"https://your-vercel-domain.vercel.app\""
else
    railway variables set ENVIRONMENT=prod
    railway variables set DEBUG=false
    railway variables set JWT_SECRET="aVlbKys2aDO0Mi-w4o2QH7FjwI9nsPRdQQ1htjxTla3myc4Gdjp7F6WLxd8GdAtrH3aCfOQ7FdSyJkz_-N3Ts0nQBS5TisPxNIoIEzROoU9pxKFCb9giwvDLzhJwnfTS"
    railway variables set HMAC_DAILY_SECRET="nfakCcN3wMiv9WCPuW5Z-YAMoHzx7Fgk2EVl-lUP7mquxnCYkMN_n0ibnJbVaRHC"
    railway variables set CORS_ORIGINS="https://your-vercel-domain.vercel.app"
    echo "✓ Railway variables set"
    
    echo ""
    echo "🚄 Triggering Railway redeploy..."
    railway up || echo "   ⚠️  Could not auto-redeploy; trigger manually in Railway Dashboard"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Next steps:"
echo "   1. Wait 2-5 minutes for Railway redeploy"
echo "   2. Test: curl https://<railway-domain>/api/v1/health"
echo "   3. Test: curl https://<railway-domain>/api/v1/capabilities"
echo ""
