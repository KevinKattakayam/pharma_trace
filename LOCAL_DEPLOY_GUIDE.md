# 🖥️ Deploy PharmaTrace from Your Local Machine

This guide will help you deploy to production from your home/work computer.

---

## Prerequisites Setup (5 minutes)

### 1️⃣ Install PostgreSQL Client (`psql`)

**macOS:**
```bash
brew install postgresql
```

**Ubuntu/Debian:**
```bash
sudo apt-get install postgresql-client
```

**Windows:**
- Option A: `choco install postgresql`
- Option B: Download from https://www.postgresql.org/download/

Verify installation:
```bash
psql --version
```

### 2️⃣ Install Railway CLI

Make sure you have Node.js/npm first, then:

```bash
npm install -g @railway/cli
```

Verify:
```bash
railway --version
```

### 3️⃣ Have Your Railway Token Ready

You'll need: `f1105107-965c-49d2-951f-3b52f8223239`

---

## Deployment Steps (10 minutes)

### Step 1: Clone the Code

```bash
git clone https://github.com/Kevinbastin/pharma_trace.git
cd pharma_trace
```

Or if you already have it, pull latest:
```bash
cd pharma_trace
git pull origin main
```

### Step 2: Run Dependency Check

```bash
bash SETUP_LOCAL.sh
```

This verifies you have `psql`, `railway`, and `git` installed.

### Step 3: Run Deployment

```bash
bash DEPLOY_FROM_LOCAL.sh
```

**What happens:**
- Connects to Supabase
- Applies 3 database migrations (phase2 → phase3 → phase4)
- Authenticates with Railway
- Sets 7 environment variables
- Triggers redeploy
- Waits for deployment to finish

**When prompted for Railway login:**
- Your browser will open
- Click "Authorize" 
- Return to terminal

### Step 4: Verify Success

After redeploy finishes (~5 minutes):

```bash
# Get your Railway domain
railway domains

# Test health endpoint
curl https://<your-domain>/api/v1/health

# Test capabilities endpoint
curl https://<your-domain>/api/v1/capabilities
```

✅ **Both should return 200 OK with JSON responses**

---

## Troubleshooting

### "psql: command not found"
PostgreSQL client not installed. Follow prerequisite Step 1 above.

### "railway: command not found"
Railway CLI not installed. Follow prerequisite Step 2 above.

### "Authentication failed" (Railway)
- Make sure you're logged in: `railway login`
- Token may have expired, re-authenticate

### "could not translate host name"
Network connectivity issue. Try:
- Restart internet connection
- Check firewall isn't blocking PostgreSQL (port 5432)

### "Cannot connect to Supabase"
Verify:
- Internet connection is working
- Supabase isn't down (check status.supabase.com)
- Password is correct: `B9dD@Ndp4sS7p+%` (with special characters)

### "Migration failed: duplicate key"
Migration already applied. This is OK—you can proceed or cancel.

---

## What Gets Deployed

**Backend (Railway):**
- FastAPI server on port 8000
- All 7 environment variables configured
- Connected to Supabase database
- 3 schema migrations applied

**Database (Supabase):**
- Phase 2: Security schema (RLS policies, audit tables)
- Phase 3: Data governance (compliance, retention)
- Phase 4: Safety cases (adverse event tracking)

**Frontend:**
- Still need to deploy separately to Vercel
- Build ready at: `frontend/dist/`

---

## Next: Deploy Frontend to Vercel

Once backend is live, deploy frontend:

```bash
cd frontend
npm install
npm run build
vercel deploy --prod
```

Or connect GitHub repo directly to Vercel for auto-deploys.

---

## Support

If something goes wrong:
1. Check the error message—it usually explains the issue
2. Look at detailed logs: `railway logs`
3. Verify Supabase status: https://status.supabase.com
4. Check Railway status: https://status.railway.app

