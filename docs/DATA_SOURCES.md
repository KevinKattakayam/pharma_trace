# Free data sources and API keys

Everything below is free to obtain. Where a licence or usage rule applies it is stated, because
"free to download" is not the same as "free to redistribute". Items marked **Built in** are already
wired up; **Adapter ready** means the code path exists and only needs the key or data; **Candidate**
means it is a sensible next integration that nobody has built yet.

Check what your deployment is actually using at any time:

```bash
cd backend && ./venv/bin/python -m scripts.doctor
```

## 1. No key required

| Source | What it gives | Status | Rules to respect |
|---|---|---|---|
| **openFDA** (api.fda.gov) | US drug labels, NDC directory, enforcement/recall reports, adverse events (FAERS), shortages | **Built in** | Works without a key at a lower rate limit; a free key raises it (see §2). Not evidence about Indian products. |
| **RxNorm / RxNav** (NLM) | Normalised drug names, ingredients, RxCUI identifiers, brand↔generic links | **Built in** (`drug_resolver`) | Public domain US government data; be polite with request rates. |
| **DailyMed** (NLM) | Full US structured product labels (SPL), including images | Candidate | Free bulk download; large files. |
| **MedlinePlus Connect** (NLM) | Patient-friendly leaflets in English and Spanish, by RxCUI | Candidate | Free; attribution requested. Useful for plain-language side-effect text. |
| **OpenStreetMap / Overpass** | Real pharmacy locations worldwide | **Built in** (`scripts/import_osm_pharmacies.py`) | **ODbL**: you must attribute "© OpenStreetMap contributors" (the app does) and share back derived geodata. Overpass is a shared volunteer service: import one district at a time. |
| **Nominatim** (OSM geocoding) | Address → coordinates | Candidate | Max 1 request/second, a real User-Agent, no bulk geocoding. Heavy use should self-host. |
| **Open-Meteo** | Weather, for cold-chain context | **Built in** (`cold_chain`) | Free for non-commercial use without a key; check their terms for commercial use. |
| **CDSCO publications** | Monthly NSQ / spurious / misbranded batch alerts; QR-code FAQs; spurious-drug guidance | **Built in** (`scripts/cdsco_pdf_to_draft_csv.py` → human review → `import_regulator_alerts.py`) | Government publications. PDF layout changes monthly, so a person must review every row (the importer enforces this). |
| **NPPA** | Ceiling prices for scheduled (essential) formulations under DPCO 2013 | **Built in** (`scripts/import_nppa_ceiling_prices.py`, `/safety/price-check`) | Published as notifications (PDF/Excel). Prices are **per unit, excluding GST**, and are revised; re-import after each revision. |
| **WHO** | Medical Product Alerts on falsified products; Essential Medicines List | Candidate | Free to read; check WHO's reuse terms before redistributing text. |
| **GS1 India / GS1 general specs** | Barcode and QR structure, Digital Link | **Built in** (parsers) | Specifications are free to read; GS1 company prefixes are a paid membership (not needed here). |
| **Jan Aushadhi (PMBI)** | Generic medicine product list and prices, store locations | Candidate | Public programme data; good for "cheaper equivalent" and nearby-store features. |
| **data.gov.in** | Various Indian health datasets | Candidate | Free API key (see §2); dataset licences vary, check each one. |

## 2. Free key, free tier

| Service | Free tier | Where it is used | How to get it |
|---|---|---|---|
| **openFDA API key** | Higher rate limit than anonymous | `OPENFDA_API_KEY` | open.fda.gov → "Get an API key" (email only) |
| **Groq** | Generous free tier on open models | `GROQ_API_KEY`: photo analysis, plain-language explanations | console.groq.com |
| **OpenRouter** | Several models with free tiers | `OPENROUTER_API_KEY`: fallback AI provider | openrouter.ai |
| **Google Gemini** | Free tier via Google AI Studio | `GEMINI_API_KEY`: alternative vision provider | aistudio.google.com |
| **Supabase** | Free Postgres project with PostGIS | `SUPABASE_URL`, `SUPABASE_KEY` | supabase.com |
| **Sentry** | Free developer tier | `SENTRY_DSN`: error monitoring | sentry.io |
| **Upstash Redis** | Free tier, HTTP/Redis | `RATE_LIMIT_STORAGE_URI`: shared rate limits | upstash.com |
| **data.gov.in** | Free key for Indian open data | Candidate integrations | data.gov.in → register |
| **Web push (VAPID)** | No service needed | `VAPID_PRIVATE_KEY` / `VAPID_PUBLIC_KEY` | Generate locally: `npx web-push generate-vapid-keys` |

AI output stays labelled `ai_generated: true` and requires review, whichever provider you use.

## 3. Not free, and why the app works without them

| Thing | Reality | What the app does instead |
|---|---|---|
| Manufacturer serial verification | Needs a commercial agreement with each manufacturer or their platform | Without it the app never says `authentic`/`counterfeit`; everything stays "record match only" |
| Full Indian brand database (brand → composition for every product) | Commercial drug databases are licensed | `scripts/import_brands.py` imports a list you are licensed to use; coverage is reported honestly |
| Clinical interaction database (DrugBank, First Databank, Micromedex) | Licensed | Interaction output is labelled as general information needing professional review |
| GS1 company prefix / licensed GTIN data | Paid membership | The app parses codes and validates check digits without needing membership |

## 4. Suggested order

1. **Groq key** (5 minutes) → photo analysis and explanations start working.
2. **openFDA key** (5 minutes) → fewer rate-limit failures.
3. **Supabase project** (20 minutes) → real shared database; then run the migrations.
4. **OSM pharmacy import** for your district (10 minutes) → the map stops being empty.
5. **One month of CDSCO alerts** (1–2 hours including review) → batch checking becomes real.
6. **NPPA ceiling prices** for common medicines (1–2 hours including review) → price checking becomes real.
7. Sentry and Upstash before any public launch.
