# 🚀 PharmaTrace Production Deployment Guide

**Status:** ✅ All code ready | 🔴 Network blocked in this environment

---

## Quick Start

### ✅ What's Already Done
- Backend preflight validation: **PASS**
- Unit tests: **6/6 PASS**
- Frontend production build: **READY** (1.9 MB, 40 precached)
- Migrations generated: **3 files ready** (phase2, phase3, phase4)
- Secrets generated: **JWT_SECRET, HMAC_DAILY_SECRET**
- All code pushed to GitHub: **https://github.com/Kevinbastin/pharma_trace.git**

### 🔴 What's Blocked by Network Isolation
- Supabase migrations (DNS fails: `Name or service not known`)
- Railway API calls (cannot reach external services)

---

## Deployment Path A: Automated (Recommended)

**Run this on your local machine with internet access:**

```bash
bash DEPLOY_FROM_LOCAL.sh
```

**What it does:**
1. Clones/pulls latest code from GitHub
2. Applies all 3 Supabase migrations (phase2, phase3, phase4 in order)
3. Authenticates with Railway CLI
4. Sets 7 environment variables
5. Triggers redeploy
6. Provides verification commands

**Requirements:**
- macOS / Linux / Windows (Git Bash)
- `git` installed
- `psql` installed (PostgreSQL client)
- `railway` CLI installed (`npm install -g @railway/cli`)
- Internet access to reach Supabase & Railway

**Time:** ~10 minutes total

---

## Deployment Path B: Manual via Web UI

### Step 1: Apply Supabase Migrations

Go to: https://app.supabase.com/project/lfzxaxefdasqribypllf/sql/new

For each of the 3 migration files (in this order), copy the entire SQL content and paste into the SQL editor, then click "Execute":

**Phase 2 - Security Schema:**
File location: `/backend/migrations/phase2_security.sql`

**Phase 3 - Data Governance:**
File location: `/backend/migrations/phase3_data_governance.sql`

**Phase 4 - Safety Cases:**
File location: `/backend/migrations/phase4_safety_cases.sql`

✅ All 3 migrations must complete without errors.

### Step 2: Set Railway Environment Variables

Go to: https://railway.app/project/lfzxaxefdasqribypllf

1. Click **Settings** → **Variables**
2. Create these 7 variables:

| Key | Value |
|-----|-------|
| `ENVIRONMENT` | `prod` |
| `DEBUG` | `false` |
| `JWT_SECRET` | `aVlbKys2aDO0Mi-w4o2QH7FjwI9nsPRdQQ1htjxTla3myc4Gdjp7F6WLxd8GdAtrH3aCfOQ7FdSyJkz_-N3Ts0nQBS5TisPxNIoIEzROoU9pxKFCb9giwvDLzhJwnfTS` |
| `HMAC_DAILY_SECRET` | `nfakCcN3wMiv9WCPuW5Z-YAMoHzx7Fgk2EVl-lUP7mquxnCYkMN_n0ibnJbVaRHC` |
| `CORS_ORIGINS` | `https://your-vercel-domain.vercel.app` |
| `SUPABASE_URL` | `https://lfzxaxefdasqribypllf.supabase.co` |
| `SUPABASE_KEY` | `sb_publishable_xqmz2ub2x9BM-XhAI8LEoQ_talRKGrq` |

### Step 3: Redeploy Railway

1. In Railway dashboard, click **Deploy** → **Redeploy** (top right button)
2. Wait 2-5 minutes for backend to restart

---

## Deployment Path C: Via Railway CLI

**From your local machine with internet access:**

```bash
# Login to Railway
railway login

# Set environment to the PharmaTrace project
railway env --project lfzxaxefdasqribypllf

# Set all 7 variables
railway variables set ENVIRONMENT=prod
railway variables set DEBUG=false
railway variables set JWT_SECRET="aVlbKys2aDO0Mi-w4o2QH7FjwI9nsPRdQQ1htjxTla3myc4Gdjp7F6WLxd8GdAtrH3aCfOQ7FdSyJkz_-N3Ts0nQBS5TisPxNIoIEzROoU9pxKFCb9giwvDLzhJwnfTS"
railway variables set HMAC_DAILY_SECRET="nfakCcN3wMiv9WCPuW5Z-YAMoHzx7Fgk2EVl-lUP7mquxnCYkMN_n0ibnJbVaRHC"
railway variables set CORS_ORIGINS="https://your-vercel-domain.vercel.app"
railway variables set SUPABASE_URL="https://lfzxaxefdasqribypllf.supabase.co"
railway variables set SUPABASE_KEY="sb_publishable_xqmz2ub2x9BM-XhAI8LEoQ_talRKGrq"

# Redeploy
railway up
```

---

## Verification

Once Railway redeploy completes:

```bash
# Get your Railway domain
railway domains

# Should output something like: pharmatrace.up.railway.app

# Test health endpoint
curl https://pharmatrace.up.railway.app/api/v1/health

# Expected response (200 OK):
# {
#   "status": "healthy",
#   "version": "1.0.0",
#   "audit_chain_length": 0,
#   "cabinet_stats": {...},
#   "databases": {...},
#   "services": {...}
# }

# Test capabilities endpoint
curl https://pharmatrace.up.railway.app/api/v1/capabilities

# Expected response (200 OK):
# {
#   "verification": true,
#   "clinical": true,
#   "data": true,
#   "safety": true
# }
```

✅ **If both endpoints return 200 OK → Backend is live!**

---

## Troubleshooting

### "Cannot connect to Supabase"
- Check password: `B9dD@Ndp4sS7p+%` (includes special chars)
- If using psql: Use single quotes for password with special chars
- Verify psql version supports URL encoding in connection strings

### "Railway redeploy stuck"
- Check Railway logs: https://railway.app/project/lfzxaxefdasqribypllf/logs
- Verify all 7 environment variables are present before deploying
- Try clicking **Deploy → Redeploy** again

### "Backend returns 500 or 503"
- Wait another 2 minutes (container may still be starting)
- Verify SUPABASE_URL and SUPABASE_KEY match exactly
- Check that all 3 migrations actually executed without SQL errors
- Look at Railway logs for detailed errors

### "CORS errors from frontend"
- Make sure CORS_ORIGINS matches your Vercel domain exactly
- Example: `https://pharmatrace-seven.vercel.app` (no trailing slash)

---

## Files Reference

**Migration Files:**
- [backend/migrations/phase2_security.sql](backend/migrations/phase2_security.sql) — Security schema
- [backend/migrations/phase3_data_governance.sql](backend/migrations/phase3_data_governance.sql) — Data governance
- [backend/migrations/phase4_safety_cases.sql](backend/migrations/phase4_safety_cases.sql) — Safety cases

**Deployment Scripts:**
- [DEPLOY_FROM_LOCAL.sh](DEPLOY_FROM_LOCAL.sh) — Fully automated deployment
- [deploy-now.sh](deploy-now.sh) — Automated (requires network from current env)

**Environment Files:**
- [backend/.env](backend/.env) — Production configuration (JWT_SECRET, HMAC_DAILY_SECRET, etc.)

---

## Next Steps After Backend Deployed

1. **Deploy Frontend to Vercel**
   - Frontend build is ready at `frontend/dist/`
   - Deploy to Vercel: `vercel deploy --prod`

2. **Configure Frontend API Endpoint**
   - Update `frontend/src/utils/api.js` to use Railway domain
   - Example: `https://pharmatrace.up.railway.app/api/v1`

3. **Test End-to-End**
   - Verify frontend loads
   - Test drug scanning
   - Test interaction checking
   - Verify all API calls succeed

---

## Support

For issues:
1. Check Railway logs: https://railway.app/project/lfzxaxefdasqribypllf/logs
2. Check Supabase logs: https://app.supabase.com/project/lfzxaxefdasqribypllf/logs
3. Verify all environment variables are set correctly
4. Ensure all 3 migrations executed successfully
