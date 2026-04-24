# PharmaTrace

PharmaTrace is a pharmaceutical verification and safety platform that helps users identify counterfeit medicines, check drug interactions, and access clinical safety data. It connects to live FDA databases, runs a 6-agent AI verification pipeline, and provides tools for health workers, caregivers, and everyday users in regions where counterfeit drugs are a serious public health problem.

The platform consists of a Python/FastAPI backend with 37 REST API endpoints and a React frontend built as a Progressive Web App. Every verification query hits real FDA data -- there are no mock endpoints or placeholder responses.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
  - [Verification](#verification)
  - [Drug Information](#drug-information)
  - [Drug Interactions](#drug-interactions)
  - [Barcode and GTIN](#barcode-and-gtin)
  - [Vision AI](#vision-ai)
  - [AI Intelligence](#ai-intelligence)
  - [LangGraph Agent Pipeline](#langgraph-agent-pipeline)
  - [Reports and Pharmacies](#reports-and-pharmacies)
  - [Caregiver](#caregiver)
  - [Translation](#translation)
  - [System](#system)
- [Frontend Pages](#frontend-pages)
- [LangGraph Pipeline](#langgraph-pipeline)
- [Database Schema](#database-schema)
- [Deployment](#deployment)
  - [Backend on Railway](#backend-on-railway)
  - [Frontend on Vercel](#frontend-on-vercel)
  - [Docker](#docker)
- [SDK Examples](#sdk-examples)
  - [Python](#python)
  - [JavaScript](#javascript)
- [External Services](#external-services)
- [License](#license)

---

## What It Does

**Drug Verification** -- Scan a barcode, photograph a pill, or type an NDC code. The system queries the OpenFDA drug database, validates the GTIN/GS1 barcode structure, checks for active FDA recalls, analyzes cold chain conditions at the user's location, and returns a confidence score with a transparent evidence trail showing exactly what matched and what failed.

**Drug Interaction Checking** -- Enter two or more medications. The system cross-references every pair against a clinically validated interaction database of 20+ known dangerous combinations, queries FDA label data for contraindications, and optionally uses Groq/Llama 3.3 to generate patient-friendly explanations of each interaction's mechanism and clinical effect.

**Side Effect Explainer** -- Takes raw FDA drug label text and rewrites it in plain language at a 6th-grade reading level. Each side effect is categorized by severity (mild, moderate, severe) and can be translated into 20+ languages through LibreTranslate.

**Dosage Personalizer** -- Flags unsafe doses for elderly patients, children, and patients with kidney impairment. Takes age, weight, and kidney function as inputs and returns risk-adjusted dosing recommendations based on clinical guidelines.

**Generic Drug Finder** -- Given a branded drug's NDC, queries OpenFDA to find all FDA-approved generic alternatives with the same active ingredient, including manufacturer and strength information.

**Outbreak Map** -- Leaflet.js-based heatmap showing reported counterfeit drug incidents by geographic location. Supports animated timeline playback and pharmacy trust scoring with anti-gaming ML that flags suspicious review patterns.

**Batch Verification** -- Designed for health workers and clinic settings. Accepts rapid barcode input (including USB scanner support) and verifies each drug against FDA databases. Generates downloadable PDF reports for clinic records.

**Caregiver Dashboard** -- Remote medication monitoring. Caregivers generate an invite code, share it with a care recipient, and can then monitor their medication verification history and receive alerts for suspicious drugs or dangerous interactions.

**Anonymous Reporting** -- Zero-knowledge reporting system for suspicious medicines. Reports are assigned a random anonymous ID with no link to the reporter's identity. Location data is rounded to city level. No IP addresses or device fingerprints are stored.

**Pill Identification** -- GPT-4o Vision analyzes photographs of pills and packaging, identifying shape, color, imprint codes, and suspicion indicators. Also accepts text descriptions for pill identification.

**Voice Interface** -- Built-in voice command support using the Web Speech API. Users can say "verify medicine," "check interactions," or "show nearby pharmacies" to navigate the app hands-free.

**Immutable Audit Log** -- Every verification is recorded in a SHA-256 hash-chained audit log. Each record's hash includes the previous record's hash, creating a tamper-evident chain that can be independently verified.

---

## Architecture

```
Frontend (React + Vite)          Backend (FastAPI + LangGraph)
--------------------------       ---------------------------------
React 19 SPA                     FastAPI application server
React Router (client-side)       6 API router modules
Progressive Web App (PWA)        16 service modules
Leaflet.js maps                  6-agent LangGraph pipeline
Chart.js visualizations          SHA-256 audit chain
ZXing barcode scanner            Pydantic request/response schemas
Web Speech API (voice)           Supabase (PostgreSQL + PostGIS)
jsPDF report generation
                                 External APIs:
Vite dev server proxies           - OpenFDA (drugs, labels, recalls, FAERS)
/api/* to backend                 - Open-Meteo (weather/cold chain)
                                  - LibreTranslate (translation)
                                  - Groq (Llama 3.3 70B inference)
                                  - OpenRouter (GPT-4o Vision)
```

The frontend communicates with the backend exclusively through `/api/v1/*` endpoints. During development, Vite's proxy forwards these requests to `http://localhost:8000`. In production, the Vercel configuration rewrites `/api/*` requests to the Railway-hosted backend.

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend framework | FastAPI | REST API server with automatic OpenAPI docs |
| AI orchestration | LangGraph + LangChain | 6-agent drug verification pipeline |
| LLM inference | Groq (Llama 3.3 70B) | Side effect parsing, interaction explanations, drug analysis |
| Vision AI | OpenRouter (GPT-4o) | Pill and packaging image analysis |
| Drug database | OpenFDA API | NDC lookup, labels, recalls, adverse events, generics |
| Barcode validation | WHO GTIN/GS1 | International barcode format validation and country detection |
| Cold chain | Open-Meteo API | Temperature and humidity monitoring at verification location |
| Translation | LibreTranslate | Free translation to 20+ languages, no API key required |
| Database | Supabase (PostgreSQL + PostGIS) | Persistent storage with geospatial queries |
| Frontend framework | React 19 | Component-based UI |
| Build tool | Vite 5 | Development server and production bundler |
| Routing | React Router 7 | Client-side navigation |
| Maps | Leaflet.js + CARTO tiles | Outbreak heatmap and pharmacy locations |
| Charts | Chart.js | Data visualization |
| Barcode scanning | ZXing | Camera-based barcode reading |
| PDF generation | jsPDF | Batch verification reports |
| PWA | vite-plugin-pwa + Workbox | Offline support and installability |
| Voice | Web Speech API | Voice command navigation |

---

## Project Structure

```
pharma_trace/
|-- backend/
|   |-- main.py                      # FastAPI application entry point
|   |-- config.py                    # Pydantic settings (env vars)
|   |-- requirements.txt             # Python dependencies
|   |-- Dockerfile                   # Container image definition
|   |-- railway.toml                 # Railway deployment config
|   |-- supabase_migration.sql       # Database schema (PostgreSQL + PostGIS)
|   |-- .env                         # Environment variables (not committed)
|   |-- models/
|   |   |-- schemas.py               # Pydantic request/response models
|   |-- routers/
|   |   |-- verify.py                # /verify/* endpoints (barcode, image, batch)
|   |   |-- interactions.py          # /interactions/* endpoints
|   |   |-- drugs.py                 # /drugs/* endpoints (side effects, dosage, generics)
|   |   |-- reports.py               # /reports/* endpoints (anonymous reporting)
|   |   |-- pharmacies.py            # /pharmacies/* endpoints (trust scores)
|   |   |-- caregiver.py             # /caregiver/* endpoints
|   |-- services/
|       |-- openfda.py               # OpenFDA API client (NDC, labels, recalls, FAERS)
|       |-- gtin.py                  # GTIN/GS1 barcode validation and parsing
|       |-- cold_chain.py            # Open-Meteo weather API for cold chain
|       |-- groq_ai.py              # Groq/Llama 3.3 LLM client
|       |-- vision.py                # GPT-4o Vision pill analysis
|       |-- interactions.py          # Drug interaction database and checker
|       |-- side_effects.py          # FDA label parser for side effects
|       |-- dosage.py                # Dosage safety calculator
|       |-- drugbank.py              # Drug information service
|       |-- confidence.py            # Confidence score calculation engine
|       |-- translation.py           # LibreTranslate client
|       |-- anonymous.py             # Zero-knowledge anonymous reporting
|       |-- audit.py                 # SHA-256 hash-chained audit log
|       |-- supabase.py              # Supabase/PostgreSQL client
|       |-- langgraph_pipeline.py    # 6-agent LangGraph verification pipeline
|
|-- frontend/
    |-- index.html                   # HTML entry point
    |-- package.json                 # Node dependencies
    |-- vite.config.js               # Vite + PWA configuration
    |-- vercel.json                  # Vercel deployment config
    |-- src/
        |-- main.jsx                 # React entry point
        |-- App.jsx                  # Router and layout
        |-- index.css                # Design system (all styles)
        |-- components/
        |   |-- Navbar.jsx           # Top bar + bottom navigation + tools menu
        |   |-- Scanner.jsx          # Camera/barcode/manual entry scanner
        |   |-- DrugResult.jsx       # Verification result card with evidence trail
        |   |-- ConfidenceGauge.jsx  # SVG circular confidence indicator
        |   |-- PharmacyCard.jsx     # Pharmacy trust score card
        |   |-- VoiceInterface.jsx   # Voice command button
        |   |-- LowBandwidth.jsx     # Network quality detection banner
        |-- pages/
        |   |-- Home.jsx             # Landing page with feature overview
        |   |-- ScanPage.jsx         # Drug verification interface
        |   |-- InteractionChecker.jsx  # Multi-drug interaction scanner
        |   |-- MapView.jsx          # Outbreak heatmap + pharmacy map
        |   |-- BatchVerification.jsx   # Rapid-scan batch mode
        |   |-- CaregiverDashboard.jsx  # Remote medication monitoring
        |   |-- ReportForm.jsx       # Anonymous drug reporting
        |   |-- SideEffectsPage.jsx  # Plain-language side effect viewer
        |   |-- DosagePage.jsx       # Dosage safety checker
        |   |-- GenericFinder.jsx    # Generic alternative finder
        |   |-- ApiDocs.jsx          # API documentation and SDK examples
        |-- hooks/
        |   |-- useScanner.js        # Camera and barcode scanning logic
        |   |-- useVoice.js          # Web Speech API integration
        |   |-- useConnection.js     # Network quality detection
        |   |-- useAuth.js           # Authentication state
        |-- utils/
            |-- api.js               # HTTP client for all backend calls
            |-- formatters.js        # Display formatting utilities
```

---

## Getting Started

### Prerequisites

- Python 3.12 or later
- Node.js 18 or later
- npm 9 or later

No API keys are required to run the core functionality. OpenFDA, Open-Meteo, LibreTranslate, and GTIN validation all work without authentication. Optional services (Groq, OpenRouter, Supabase) require keys for extended features.

### Backend Setup

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Copy the environment file and add your keys (optional)
cp .env.example .env

# Start the development server
python main.py
```

The backend starts at `http://localhost:8000`. Interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

The frontend starts at `http://localhost:5173`. The Vite dev server proxies all `/api/*` requests to the backend at `http://localhost:8000`.

To create a production build:

```bash
npm run build     # outputs to frontend/dist/
npm run preview   # preview the production build locally
```

---

## Environment Variables

Create a `.env` file in the `backend/` directory:

```bash
# OpenFDA (free -- 240 requests/min with key, 40/min without)
OPENFDA_API_KEY=

# OpenRouter (GPT-4o Vision for pill image analysis)
OPENROUTER_API_KEY=

# Groq (Llama 3.3 70B -- side effects, interactions, drug analysis)
GROQ_API_KEY=

# Supabase (PostgreSQL + PostGIS -- persistent storage)
SUPABASE_URL=
SUPABASE_KEY=

# Security
JWT_SECRET=change-this-in-production
DEBUG=true
```

All keys are optional. The platform degrades gracefully:

| Service | Without Key | With Key |
|---------|------------|----------|
| OpenFDA | Works (40 req/min) | Higher rate limit (240 req/min) |
| Groq | AI explanations disabled | Llama 3.3 70B inference available |
| OpenRouter | Image analysis disabled | GPT-4o Vision pill identification |
| Supabase | In-memory storage (data lost on restart) | Persistent PostgreSQL with PostGIS |

---

## API Reference

Base URL: `/api/v1`

### Verification

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/verify/barcode` | Verify a drug by barcode or NDC code |
| POST | `/verify/image` | Verify a drug by photograph (GPT-4o Vision) |
| POST | `/verify/batch` | Batch verify multiple barcodes |
| GET | `/verify/history` | Retrieve verification history |

### Drug Information

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/drugs/{ndc}` | Look up drug details from OpenFDA |
| GET | `/drugs/{ndc}/side-effects?lang=en` | Plain-language side effects with optional translation |
| POST | `/drugs/{ndc}/dosage` | Dosage safety check (age, weight, kidney function) |
| GET | `/drugs/{ndc}/generics` | Find generic alternatives with the same active ingredient |
| GET | `/adverse-events/{drug}` | Query FDA FAERS adverse event reports |

### Drug Interactions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/interactions/check` | Check interactions between 2-10 drugs |

### Barcode and GTIN

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/barcode/validate` | Validate GTIN/EAN/UPC barcode format and check digit |
| POST | `/barcode/parse-gs1` | Parse GS1 DataMatrix (GTIN, lot, expiry, serial) |

### Vision AI

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/vision/analyze` | Analyze pill/packaging photo with GPT-4o Vision |
| POST | `/vision/identify` | Identify a pill from a text description |

### AI Intelligence

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ai/explain-interaction` | Patient-friendly interaction explanation (Groq/Llama) |
| POST | `/ai/analyze-drug` | Comprehensive drug analysis (food interactions, timing, storage) |

### LangGraph Agent Pipeline

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/agents/verify` | Run the full 6-agent verification pipeline |

### Reports and Pharmacies

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/reports` | Submit a suspicious drug report (supports anonymous mode) |
| GET | `/reports/heatmap` | Counterfeit drug heatmap data for map visualization |
| GET | `/pharmacies/nearby` | Find nearby pharmacies with trust scores (PostGIS) |

### Caregiver

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/caregiver/link` | Generate a caregiver invite code |
| POST | `/caregiver/accept` | Accept a caregiver link using an invite code |
| GET | `/caregiver/dashboard` | Caregiver monitoring dashboard data |
| GET | `/caregiver/alerts` | Active medication safety alerts |

### Translation

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/translate/languages` | List all supported translation languages |
| POST | `/translate` | Translate text to any supported language |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health check with status of all integrations |
| GET | `/audit/verify` | Verify SHA-256 audit chain integrity |
| GET | `/audit/log` | Retrieve audit log entries |
| GET | `/cold-chain` | Check storage conditions at a location (Open-Meteo) |
| GET | `/refill/schedule` | Refill reminders based on scan history |

---

## Frontend Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Home | Landing page with animated stats, live API status, feature cards, and tech stack overview |
| `/scan` | Scan and Verify | Camera barcode scanner, image capture, and manual NDC entry with real-time verification results |
| `/interactions` | Interaction Checker | Multi-drug interaction scanner with severity matrix and AI-powered explanations |
| `/map` | Outbreak Map | Leaflet.js heatmap of counterfeit drug reports with pharmacy trust scores and geospatial filtering |
| `/batch` | Batch Verification | Rapid-scan mode for health workers with USB scanner support and PDF report export |
| `/dashboard` | Caregiver Dashboard | Remote medication monitoring with invite code linking and safety alerts |
| `/report` | Report Form | Multi-step anonymous reporting form with zero-knowledge privacy guarantees |
| `/side-effects` | Side Effects | Plain-language side effect viewer with severity categorization and 20+ language translation |
| `/dosage` | Dosage Safety | Patient-specific dosage checker for elderly, pediatric, and renal-impaired patients |
| `/generics` | Generic Finder | FDA-verified generic alternative lookup by active ingredient |
| `/api-docs` | API Documentation | Interactive endpoint reference with Python and JavaScript SDK code samples |

---

## LangGraph Pipeline

The backend includes a 6-agent LangGraph pipeline that orchestrates a comprehensive drug verification workflow. Each agent is a node in a directed graph, and the output of each agent feeds into the next.

```
Barcode Agent --> FDA Lookup Agent --> Recall Agent --> Interaction Agent --> Safety Agent --> Report Agent
```

**Agent 1 -- Barcode Agent**: Validates the barcode format using the GS1 check-digit algorithm. Detects the country of origin from the GTIN prefix and extracts the NDC if present.

**Agent 2 -- FDA Lookup Agent**: Queries the OpenFDA drug database using the NDC code. Retrieves brand name, generic name, manufacturer, active ingredients, route of administration, and product type.

**Agent 3 -- Recall Agent**: Checks the OpenFDA enforcement endpoint for active recalls and safety alerts associated with the drug.

**Agent 4 -- Interaction Agent**: If the user provides a list of other medications they are taking, this agent cross-references all drug pairs against the interaction database.

**Agent 5 -- Safety Agent**: Aggregates all evidence from previous agents and calculates a weighted confidence score. Considers GTIN validity, FDA match quality, recall status, cold chain conditions, and interaction severity.

**Agent 6 -- Report Agent**: Uses Groq/Llama 3.3 to generate a patient-friendly summary of the verification results, including plain-language explanations of any risks identified.

The pipeline state is defined as a TypedDict with annotated list fields that automatically merge evidence from all agents using `operator.add`.

---

## Database Schema

The `supabase_migration.sql` file contains the full PostgreSQL schema. Run it in the Supabase SQL Editor to set up persistent storage.

**Tables:**

| Table | Purpose |
|-------|---------|
| `verifications` | Drug verification records with geospatial location (PostGIS) |
| `reports` | Community-submitted suspicious drug reports (supports anonymous) |
| `pharmacies` | Pharmacy locations with trust scores and verification stats |
| `pharmacy_reviews` | User reviews with anti-gaming ML flagging |
| `audit_chain` | SHA-256 hash-chained verification audit records |
| `caregiver_links` | Invite-code-based caregiver-recipient relationships |
| `scan_history` | Per-user scan history for refill prediction |

**PostGIS Functions:**

| Function | Purpose |
|----------|---------|
| `nearby_pharmacies(lat, lng, radius_m)` | Find pharmacies within a radius using `ST_DWithin` |
| `nearby_reports(lat, lng, radius_m)` | Find counterfeit drug reports within a radius for heatmap rendering |

All geospatial columns use the `GEOGRAPHY(Point, 4326)` type for accurate distance calculations on the WGS 84 ellipsoid.

---

## Deployment

### Backend on Railway

The repository includes a `railway.toml` and `Dockerfile` for one-click Railway deployment.

1. Create a new project on [Railway](https://railway.app)
2. Connect the repository and point the root directory to `backend/`
3. Set environment variables in the Railway dashboard
4. Railway will build the Docker image and start the server automatically

The health check endpoint is `/api/v1/health`. Railway will monitor it and restart the service on failure.

### Frontend on Vercel

The `vercel.json` file configures the frontend for Vercel deployment.

1. Create a new project on [Vercel](https://vercel.com)
2. Point the root directory to `frontend/`
3. Update the API rewrite in `vercel.json` to point to your Railway backend URL:

```json
{ "source": "/api/(.*)", "destination": "https://your-app.railway.app/api/$1" }
```

4. Deploy. Vercel will run `npm run build` and serve the static files from `dist/`.

Security headers (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy) are configured automatically. Static assets under `/assets/` are served with immutable cache headers (1 year).

### Docker

To run the backend in a container locally:

```bash
cd backend
docker build -t pharmatrace-api .
docker run -p 8000:8000 --env-file .env pharmatrace-api
```

The container uses Python 3.12-slim, runs uvicorn with 2 workers, and includes a health check that pings `/api/v1/health` every 30 seconds.

---

## SDK Examples

### Python

```python
import httpx

BASE = "http://localhost:8000/api/v1"

# Verify a drug by NDC
resp = httpx.post(f"{BASE}/verify/barcode", json={
    "barcode": "59726-065-30",
    "location": {"lat": 19.076, "lng": 72.877}
})
result = resp.json()
print(f"{result['verdict']} -- {result['confidence']}% -- {result['brand_name']}")

# Check drug interactions
resp = httpx.post(f"{BASE}/interactions/check", json={
    "drugs": ["Warfarin", "Aspirin", "Ibuprofen"]
})
for ix in resp.json()["interactions"]:
    print(f"{ix['drug_a']} + {ix['drug_b']}: {ix['severity']} -- {ix['clinical_effect']}")

# Get side effects in Hindi
resp = httpx.get(f"{BASE}/drugs/59726-065-30/side-effects?lang=hi")
for se in resp.json()["side_effects"]:
    print(f"[{se['severity']}] {se['description']}")

# Validate an international barcode
resp = httpx.post(f"{BASE}/barcode/validate?barcode=8901234567890")
print(resp.json())  # format, country, check_digit_valid

# Check cold chain conditions
resp = httpx.get(f"{BASE}/cold-chain?lat=19.076&lng=72.877")
print(resp.json())  # temperature, humidity, storage safety
```

### JavaScript

```javascript
const BASE = 'http://localhost:8000/api/v1';

// Verify a drug
const verify = await fetch(`${BASE}/verify/barcode`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    barcode: '59726-065-30',
    location: { lat: 19.076, lng: 72.877 }
  })
}).then(r => r.json());

console.log(`${verify.verdict} -- ${verify.confidence}% -- ${verify.brand_name}`);

// Check interactions
const ix = await fetch(`${BASE}/interactions/check`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ drugs: ['Warfarin', 'Aspirin', 'Ibuprofen'] })
}).then(r => r.json());

ix.interactions.forEach(i =>
  console.log(`${i.drug_a} + ${i.drug_b}: ${i.severity}`)
);

// Get side effects in Spanish
const se = await fetch(`${BASE}/drugs/59726-065-30/side-effects?lang=es`)
  .then(r => r.json());

// Find generic alternatives
const generics = await fetch(`${BASE}/drugs/59726-065-30/generics`)
  .then(r => r.json());
```

---

## External Services

| Service | Cost | API Key Required | What It Does |
|---------|------|------------------|-------------|
| [OpenFDA](https://open.fda.gov/) | Free | No (optional for higher rate limits) | Drug database, labels, recalls, adverse events, generic alternatives |
| [Open-Meteo](https://open-meteo.com/) | Free | No | Weather data for cold chain temperature and humidity analysis |
| [LibreTranslate](https://libretranslate.com/) | Free | No | Text translation to 20+ languages using public instances |
| [Groq](https://groq.com/) | Free tier available | Yes | Fast Llama 3.3 70B inference for AI explanations and drug analysis |
| [OpenRouter](https://openrouter.ai/) | Pay-per-use | Yes | GPT-4o Vision access for pill and packaging image analysis |
| [Supabase](https://supabase.com/) | Free tier available | Yes | PostgreSQL database with PostGIS geospatial extensions |

The core verification pipeline (barcode validation, FDA lookup, recall checking, interaction scanning, confidence scoring) works entirely with free, keyless APIs. Groq, OpenRouter, and Supabase extend the platform with AI intelligence, vision capabilities, and persistent storage.

---

## License

This project is open source. See the LICENSE file for details.
