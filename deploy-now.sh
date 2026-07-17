#!/bin/bash
# Complete production deployment — run this on your local machine with internet access

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 PharmaTrace Complete Production Deployment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
SUPABASE_PASSWORD="B9dD@Ndp4sS7p+%"
SUPABASE_HOST="lfzxaxefdasqribypllf.supabase.co"
SUPABASE_USER="postgres"
SUPABASE_DB="postgres"
RAILWAY_TOKEN="f1105107-965c-49d2-951f-3b52f8223239"
JWT_SECRET="aVlbKys2aDO0Mi-w4o2QH7FjwI9nsPRdQQ1htjxTla3myc4Gdjp7F6WLxd8GdAtrH3aCfOQ7FdSyJkz_-N3Ts0nQBS5TisPxNIoIEzROoU9pxKFCb9giwvDLzhJwnfTS"
HMAC_DAILY_SECRET="nfakCcN3wMiv9WCPuW5Z-YAMoHzx7Fgk2EVl-lUP7mquxnCYkMN_n0ibnJbVaRHC"

# Export for Python subprocess
export SUPABASE_PASSWORD
export SUPABASE_HOST
export SUPABASE_USER
export SUPABASE_DB
export BACKEND_DIR

# Step 1: Apply Supabase migrations
echo ""
echo "📝 Step 1: Applying Supabase migrations..."
echo ""

echo "   Connecting to: $SUPABASE_HOST"

# Use backend venv Python which has psycopg2
if [ -f "$BACKEND_DIR/venv/bin/python" ]; then
    PYTHON_BIN="$BACKEND_DIR/venv/bin/python"
else
    PYTHON_BIN="python3"
fi

$PYTHON_BIN << 'PYMIGRATE'
import psycopg2
import os
import sys
from urllib.parse import quote_plus

supabase_host = os.getenv("SUPABASE_HOST")
supabase_user = os.getenv("SUPABASE_USER")
supabase_password = os.getenv("SUPABASE_PASSWORD")
supabase_db = os.getenv("SUPABASE_DB")
backend_dir = os.getenv("BACKEND_DIR")

# URL encode the password for special characters
password_encoded = quote_plus(supabase_password)
connection_string = f"postgresql://{supabase_user}:{password_encoded}@{supabase_host}/{supabase_db}"

try:
    conn = psycopg2.connect(connection_string)
    cursor = conn.cursor()
    
    migrations = [
        f"{backend_dir}/migrations/phase2_security.sql",
        f"{backend_dir}/migrations/phase3_data_governance.sql",
        f"{backend_dir}/migrations/phase4_safety_cases.sql"
    ]
    
    for migration_file in migrations:
        if not os.path.exists(migration_file):
            print(f"❌ Migration file not found: {migration_file}")
            sys.exit(1)
        
        with open(migration_file, 'r') as f:
            sql_content = f.read()
        
        cursor.execute(sql_content)
        conn.commit()
        print(f"✓ {os.path.basename(migration_file)}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Migration failed: {e}")
    sys.exit(1)
PYMIGRATE

if [ $? -ne 0 ]; then
    exit 1
fi

# Step 2: Configure Railway
echo ""
echo "🔧 Step 2: Setting Railway environment variables..."
echo ""

if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Install with:"
    echo "   npm install -g @railway/cli"
    echo ""
    echo "   Then authenticate:"
    echo "   railway login"
    exit 1
fi

# List current environment to verify CLI works
railway env || {
    echo "⚠️  Please run 'railway login' first"
    exit 1
}

echo "   Setting variables..."
railway variables set ENVIRONMENT=prod
railway variables set DEBUG=false
railway variables set JWT_SECRET="$JWT_SECRET"
railway variables set HMAC_DAILY_SECRET="$HMAC_DAILY_SECRET"
railway variables set CORS_ORIGINS="https://your-vercel-domain.vercel.app"
railway variables set SUPABASE_URL="https://lfzxaxefdasqribypllf.supabase.co"
railway variables set SUPABASE_KEY="sb_publishable_xqmz2ub2x9BM-XhAI8LEoQ_talRKGrq"

echo "✓ Variables set"

# Step 3: Redeploy
echo ""
echo "🚄 Step 3: Redeploying Railway..."
railway up

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Next steps:"
echo "   1. Wait 2-5 minutes for Railway redeploy to finish"
echo "   2. Get your Railway domain:"
echo "      railway domains"
echo "   3. Test endpoints:"
echo "      curl https://<your-domain>/api/v1/health"
echo "      curl https://<your-domain>/api/v1/capabilities"
echo ""
echo "✨ If both return 200 OK → your backend is live!"
echo ""
