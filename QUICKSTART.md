# 🚀 PharmaTrace Production Deployment — Quick Start

All systems ready for deployment. Follow these steps:

---

## Step 1: Apply Database Migrations

Your Supabase project:
- **URL:** https://lfzxaxefdasqribypllf.supabase.co
- **Connection:** `postgresql://postgres:sb_publishable_xqmz2ub2x9BM-XhAI8LEoQ_talRKGrq@lfzxaxefdasqribypllf.supabase.co/postgres`

**Option A: Using the script (recommended)**
```bash
cd /home/kevin/pharma_trace
PGPASSWORD="<your_supabase_password>" ./scripts/setup-prod.sh
```

**Option B: Using Supabase SQL Editor (UI)**
1. Open https://supabase.com → Login → Select `pharmatrace` project
2. Go to SQL Editor
3. Run these files in order:
   - File: `backend/migrations/phase2_security.sql`
   - File: `backend/migrations/phase3_data_governance.sql`
   - File: `backend/migrations/phase4_safety_cases.sql`

**Option C: Using psql (CLI)**
```bash
psql "postgresql://postgres:sb_publishable_xqmz2ub2x9BM-XhAI8LEoQ_talRKGrq@lfzxaxefdasqribypllf.supabase.co/postgres" -f backend/migrations/phase2_security.sql
psql "postgresql://postgres:sb_publishable_xqmz2ub2x9BM-XhAI8LEoQ_talRKGrq@lfzxaxefdasqribypllf.supabase.co/postgres" -f backend/migrations/phase3_data_governance.sql
psql "postgresql://postgres:sb_publishable_xqmz2ub2x9BM-XhAI8LEoQ_talRKGrq@lfzxaxefdasqribypllf.supabase.co/postgres" -f backend/migrations/phase4_safety_cases.sql
```

---

## Step 2: Configure Railway

**Production Environment Variables** (all required):

| Key | Value |
|-----|-------|
| `ENVIRONMENT` | `prod` |
| `DEBUG` | `false` |
| `JWT_SECRET` | `aVlbKys2aDO0Mi-w4o2QH7FjwI9nsPRdQQ1htjxTla3myc4Gdjp7F6WLxd8GdAtrH3aCfOQ7FdSyJkz_-N3Ts0nQBS5TisPxNIoIEzROoU9pxKFCb9giwvDLzhJwnfTS` |
| `HMAC_DAILY_SECRET` | `nfakCcN3wMiv9WCPuW5Z-YAMoHzx7Fgk2EVl-lUP7mquxnCYkMN_n0ibnJbVaRHC` |
| `CORS_ORIGINS` | `https://your-vercel-domain.vercel.app` |
| `SUPABASE_URL` | `https://lfzxaxefdasqribypllf.supabase.co` |
| `SUPABASE_KEY` | `sb_publishable_xqmz2ub2x9BM-XhAI8LEoQ_talRKGrq` |

**Option A: Using Railway Dashboard (UI)**
1. Go to railway.app → Login
2. Select your `pharmatrace` project
3. Settings → Variables
4. Add/update each variable above
5. Redeploy

**Option B: Using Railway CLI**
```bash
railway login
railway link
railway variables set ENVIRONMENT=prod
railway variables set DEBUG=false
railway variables set JWT_SECRET="aVlbKys2aDO0Mi-w4o2QH7FjwI9nsPRdQQ1htjxTla3myc4Gdjp7F6WLxd8GdAtrH3aCfOQ7FdSyJkz_-N3Ts0nQBS5TisPxNIoIEzROoU9pxKFCb9giwvDLzhJwnfTS"
railway variables set HMAC_DAILY_SECRET="nfakCcN3wMiv9WCPuW5Z-YAMoHzx7Fgk2EVl-lUP7mquxnCYkMN_n0ibnJbVaRHC"
railway variables set CORS_ORIGINS="https://your-vercel-domain.vercel.app"
railway variables set SUPABASE_URL="https://lfzxaxefdasqribypllf.supabase.co"
railway variables set SUPABASE_KEY="sb_publishable_xqmz2ub2x9BM-XhAI8LEoQ_talRKGrq"
```

---

## Step 3: Redeploy Railway

**Option A: Via Dashboard**
- Railway → Deployments → Click Redeploy button

**Option B: Via CLI**
```bash
railway up
```

---

## Step 4: Verify Deployment

Wait 2-5 minutes for the redeploy to complete, then test:

```bash
# Replace YOUR_RAILWAY_DOMAIN with your actual domain (e.g., pharmatrace.up.railway.app)
curl https://YOUR_RAILWAY_DOMAIN/api/v1/health
curl https://YOUR_RAILWAY_DOMAIN/api/v1/capabilities
```

**Expected responses:**
- `/health` → JSON with status, version, audit chain, databases, services
- `/capabilities` → JSON with verification, clinical, data, safety feature flags

---

## 🎉 Done!

Once both endpoints return 200 OK, your backend is live.

Next:
1. Deploy frontend to Vercel: `cd frontend && vercel deploy --prod`
2. Update `CORS_ORIGINS` in Railway with your final Vercel domain
3. Share endpoints with frontend team for integration testing

---

## 📞 Troubleshooting

**500 Error on /health**
- Check Railway logs for exceptions
- Verify Supabase migrations applied successfully
- Confirm `SUPABASE_URL` and `SUPABASE_KEY` are set in Railway

**401 Unauthorized**
- Verify `JWT_SECRET` is set and not empty

**CORS Errors**
- Update `CORS_ORIGINS` to match your Vercel domain exactly

**Migration Failed**
- Ensure migrations run in order: phase2 → phase3 → phase4
- Check for SQL syntax errors in Supabase SQL Editor

---

## 📂 Local Development (Offline)

Run both servers locally:
```bash
./scripts/dev.sh
```
Then open http://localhost:5173

---

**Questions?** See `DEPLOYMENT_CHECKLIST.md` for detailed reference guide.
