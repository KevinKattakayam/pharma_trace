# PharmaTrace Deployment — Manual Web UI Steps

## Option 1: Supabase Migrations (via SQL Editor)

Go to: https://app.supabase.com/project/lfzxaxefdasqribypllf/sql/new

Run each SQL file in order:

### Phase 2: Security Schema (run first)
Copy contents of `backend/migrations/phase2_security.sql` and execute in Supabase SQL editor.

### Phase 3: Data Governance (run second)
Copy contents of `backend/migrations/phase3_data_governance.sql` and execute in Supabase SQL editor.

### Phase 4: Safety Cases (run third)
Copy contents of `backend/migrations/phase4_safety_cases.sql` and execute in Supabase SQL editor.

---

## Option 2: Railway Environment Variables (via Dashboard)

Go to: https://railway.app/project/lfzxaxefdasqribypllf

1. **Settings → Variables**
2. Add these 7 environment variables:

| Variable | Value |
|----------|-------|
| `ENVIRONMENT` | `prod` |
| `DEBUG` | `false` |
| `JWT_SECRET` | `aVlbKys2aDO0Mi-w4o2QH7FjwI9nsPRdQQ1htjxTla3myc4Gdjp7F6WLxd8GdAtrH3aCfOQ7FdSyJkz_-N3Ts0nQBS5TisPxNIoIEzROoU9pxKFCb9giwvDLzhJwnfTS` |
| `HMAC_DAILY_SECRET` | `nfakCcN3wMiv9WCPuW5Z-YAMoHzx7Fgk2EVl-lUP7mquxnCYkMN_n0ibnJbVaRHC` |
| `CORS_ORIGINS` | `https://your-vercel-domain.vercel.app` |
| `SUPABASE_URL` | `https://lfzxaxefdasqribypllf.supabase.co` |
| `SUPABASE_KEY` | `sb_publishable_xqmz2ub2x9BM-XhAI8LEoQ_talRKGrq` |

3. **Deploy → Redeploy** (button in top right)
4. Wait 2-5 minutes for deploy to complete

---

## Step 3: Verify Endpoints

Once Railway redeploy finishes:

```bash
# Get your Railway domain
railway domains

# Test health endpoint (expects: { "status": "healthy", ... })
curl https://<your-railway-domain>/api/v1/health

# Test capabilities endpoint (expects: { "verification": true, "clinical": true, ... })
curl https://<your-railway-domain>/api/v1/capabilities
```

✅ **If both return 200 OK → backend is live!**

---

## Troubleshooting

**"Cannot connect to Supabase"**
- Verify password special characters: `B9dD@Ndp4sS7p+%`
- In psql: Use single quotes: `psql -U 'postgres' -h 'lfzxaxefdasqribypllf.supabase.co'`

**"Railway redeploy stuck"**
- Check Railway logs: https://railway.app/project/lfzxaxefdasqribypllf/logs
- Verify all 7 variables are set before redeploying

**"Endpoints return 500 or 503"**
- Wait another 2 minutes (backend container may still be booting)
- Check that SUPABASE_URL and SUPABASE_KEY are correct
- Verify database migrations actually ran (check Supabase SQL)
