#!/bin/bash
# LOCAL MACHINE DEPLOYMENT GUIDE
# Run this on your home/work computer with internet access

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 PharmaTrace Local Machine Deployment Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 1: Check for git
echo "Step 1️⃣  Checking for git..."
if ! command -v git &> /dev/null; then
    echo "❌ git not found. Install from: https://git-scm.com/download"
    exit 1
fi
echo "✓ git found"

# Step 2: Check for psql
echo ""
echo "Step 2️⃣  Checking for psql (PostgreSQL client)..."
if ! command -v psql &> /dev/null; then
    echo "❌ psql not found. Install PostgreSQL client:"
    echo ""
    echo "   macOS:"
    echo "   brew install postgresql"
    echo ""
    echo "   Ubuntu/Debian:"
    echo "   sudo apt-get install postgresql-client"
    echo ""
    echo "   Windows:"
    echo "   choco install postgresql"
    echo "   OR download: https://www.postgresql.org/download/"
    echo ""
    echo "   Then come back and run this script again."
    exit 1
fi
echo "✓ psql found: $(psql --version)"

# Step 3: Check for railway CLI
echo ""
echo "Step 3️⃣  Checking for railway CLI..."
if ! command -v railway &> /dev/null; then
    echo "❌ railway CLI not found. Install with:"
    echo ""
    echo "   npm install -g @railway/cli"
    echo ""
    echo "   (Make sure you have Node.js/npm installed first)"
    echo ""
    echo "   Then come back and run this script again."
    exit 1
fi
echo "✓ railway CLI found"

# Step 4: Clone repo
echo ""
echo "Step 4️⃣  Getting latest code from GitHub..."
if [ -d "pharma_trace" ]; then
    echo "   Repository exists. Pulling latest changes..."
    cd pharma_trace
    git pull origin main
else
    echo "   Cloning repository..."
    git clone https://github.com/Kevinbastin/pharma_trace.git
    cd pharma_trace
fi

echo "✓ Code ready"

# Step 5: Run deployment
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ All dependencies ready!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Now run the deployment script:"
echo ""
echo "   bash DEPLOY_FROM_LOCAL.sh"
echo ""
echo "This will:"
echo "  1. Connect to Supabase and apply 3 migrations"
echo "  2. Authenticate with Railway"
echo "  3. Set all 7 environment variables"
echo "  4. Trigger a redeploy"
echo "  5. Show you how to verify the deployment"
echo ""
