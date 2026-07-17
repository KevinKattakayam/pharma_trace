# PharmaTrace Deployment Checklist

**Status:** All local checks passed. Ready for production deployment.

---

## ✅ Completed Locally

- [x] Backend preflight check — `./venv/bin/python -m scripts.preflight` (PASS)
- [x] Backend test suite — 6/6 tests passed
- [x] Frontend production build — `npm run build` (40 entries precached, 1936.35 KiB)
- [x] Secrets generated:
  - JWT_SECRET: `aVlbKys2aDO0Mi-w4o2QH7FjwI9nsPRdQQ1htjxTla3myc4Gdjp7F6WLxd8GdAtrH3aCfOQ7FdSyJkz_-N3Ts0nQBS5TisPxNIoIEzROoU9pxKFCb9giwvDLzhJwnfTS`
  - HMAC_DAILY_SECRET: `nfakCcN3wMiv9WCPuW5Z-YAMoHzx7Fgk2EVl-lUP7mquxnCYkMN_n0ibnJbVaRHC`

---

## 🔜 Next Steps (You Need to Run)

### 1. Apply Supabase Migrations (in order)

**Option A: Using Supabase SQL Editor (UI)**
1. Open Supabase dashboard → SQL Editor
2. Run these files one at a time (wait for each to complete):
   - `backend/migrations/phase2_security.sql`
   - `backend/migrations/phase3_data_governance.sql`
   - `backend/migrations/phase4_safety_cases.sql`

**Option B: Using psql (CLI)**
```bash
# Replace with your actual Supabase connection string
SUPABASE_DB_URL="postgresql://postgres:[password]@[host]/postgres"

psql "$SUPABASE_DB_URL" -f backend/migrations/phase2_security.sql
psql "$SUPABASE_DB_URL" -f backend/migrations/phase3_data_governance.sql
psql "$SUPABASE_DB_URL" -f backend/migrations/phase4_safety_cases.sql
```

### 2. Set Railway Environment Variables

Go to Railway Dashboard → Your Project → Settings → Variables

Add/update these exact keys and values:

| Key | Value |
|-----|-------|
| `ENVIRONMENT` | `prod` |
| `DEBUG` | `false` |
| `JWT_SECRET` | `aVlbKys2aDO0Mi-w4o2QH7FjwI9nsPRdQQ1htjxTla3myc4Gdjp7F6WLxd8GdAtrH3aCfOQ7FdSyJkz_-N3Ts0nQBS5TisPxNIoIEzROoU9pxKFCb9giwvDLzhJwnfTS` |
| `HMAC_DAILY_SECRET` | `nfakCcN3wMiv9WCPuW5Z-YAMoHzx7Fgk2EVl-lUP7mquxnCYkMN_n0ibnJbVaRHC` |
| `CORS_ORIGINS` | `https://your-vercel-domain.vercel.app` |
| `SUPABASE_URL` | `https://<project>.supabase.co` |
| `SUPABASE_KEY` | `<your_service_role_or_anon_key>` |

**Or use Railway CLI:**
```bash
railway login
railway variables set ENVIRONMENT=prod
railway variables set DEBUG=false
railway variables set JWT_SECRET="aVlbKys2aDO0Mi-w4o2QH7FjwI9nsPRdQQ1htjxTla3myc4Gdjp7F6WLxd8GdAtrH3aCfOQ7FdSyJkz_-N3Ts0nQBS5TisPxNIoIEzROoU9pxKFCb9giwvDLzhJwnfTS"
railway variables set HMAC_DAILY_SECRET="nfakCcN3wMiv9WCPuW5Z-YAMoHzx7Fgk2EVl-lUP7mquxnCYkMN_n0ibnJbVaRHC"
railway variables set CORS_ORIGINS="https://your-vercel-domain.vercel.app"
railway variables set SUPABASE_URL="https://<project>.supabase.co"
railway variables set SUPABASE_KEY="<key>"
```

### 3. Redeploy Railway

- **Via UI:** Dashboard → Deployments → Redeploy (or push a commit to trigger auto-redeploy)
- **Via CLI:**
```bash
railway up
```

### 4. Verify Deployment

Once redeployed, test the endpoints:

```bash
# Replace your-railway-backend-domain with actual domain
curl https://your-railway-backend-domain/api/v1/health
curl https://your-railway-backend-domain/api/v1/capabilities
```

Expected responses:
- `/health`: JSON with status, service name, version, audit chain length, cabinet stats, databases, services.
- `/capabilities`: JSON with verification, clinical, data, and safety feature flags.

### 5. Deploy Frontend to Vercel

```bash
cd frontend
vercel deploy --prod
```

---

## 📋 Troubleshooting

**500 Error on /health**
- Likely cause: Missing Supabase connection. Verify `SUPABASE_URL` and `SUPABASE_KEY` are set and correct in Railway.

**401 Unauthorized**
- Verify `JWT_SECRET` is set and non-empty in Railway.

**CORS errors**
- Verify `CORS_ORIGINS` includes your Vercel domain and is correctly formatted.

**Migration errors**
- Ensure migrations run in order: phase2 → phase3 → phase4.
- Check Supabase logs for constraint or schema conflicts.

---

## 🔒 Security Notes

- Keep `JWT_SECRET` and `HMAC_DAILY_SECRET` private — they are now in Railway production.
- Rotate these secrets every 90 days in production.
- The `.env` file in `backend/.env` is `.gitignored` and never committed.

---

## 📞 Support

After deployment, if any endpoint returns an error, provide:
1. The endpoint URL
2. The HTTP status code
3. The full error JSON
4. Your Railway deployment logs

I'll help debug from there.
