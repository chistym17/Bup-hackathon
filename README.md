# GridWise Smart Campus Energy Optimization

HTTP API for BUP CSE Fest 2026 preliminary: interpret operator notes with an LLM, validate directives, then optimize a 24-hour campus energy schedule with PuLP/CBC.

| Resource | URL |
| -------- | --- |
| Live API | https://gridwiseai.onrender.com |
| Health | https://gridwiseai.onrender.com/health |
| Source | https://github.com/chistym17/Bup-hackathon |

## Pipeline

```
POST /optimize-energy
        │
        ▼
┌───────────────────────┐
│  LLM Interpreter      │  Groq (default) → Gemini (fallback)
│  operator_notes →     │  structured directive JSON
│  directive candidates │
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│  Deterministic        │  allowed types, hours 0–23, factor/reserve/grid
│  Guardrails           │  bad note → safe no_op (no invented directives)
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│  Optimizer (PuLP+CBC) │  apply directives, minimize Σ grid × tariff
│  24h schedule         │  balance, battery, end-of-day neutrality
└───────────┬───────────┘
            ▼
┌───────────────────────┐
│  Replay check         │  same rules the judge uses
└───────────┬───────────┘
            ▼
   JSON: interpretation + hourly_plan + totals
```

Endpoints:

- `GET /health` → `{"status":"ok"}`
- `POST /optimize-energy` → interpretation + 24h plan

## Local setup

```bash
git clone https://github.com/chistym17/Bup-hackathon.git
cd Bup-hackathon
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` (names only — do not commit secrets):

```
GROQ_API_KEY=...
GEMINI_API_KEY=...
```

Models (see `llmclient/config.py`):

- Default: Groq `openai/gpt-oss-20b`
- Fallback: Gemini `gemini-3.6-flash`

Start command (local and Render):

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Locally use port `8000` if `PORT` is unset:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Quick test (no local files needed)

Health:

```bash
curl -s https://gridwiseai.onrender.com/health
```

Full optimize call — builds the sample JSON in memory (only needs `curl` + `python3`):

```bash
curl -sS https://gridwiseai.onrender.com/optimize-energy \
  -H 'Content-Type: application/json' \
  -d "$(python3 - <<'PY'
import json
hours = [{
  "hour": h,
  "demand_kwh": 180 if h < 8 else 220,
  "solar_kwh": 80 if 10 <= h <= 16 else 0,
  "tariff_bdt_per_kwh": 6 if h < 8 else (12 if h in (18, 19, 20) else 8),
} for h in range(24)]
print(json.dumps({
  "scenario_id": "GRID-101",
  "operator_notes": [
    "Solar output will drop to about 20% from 1 PM to 3 PM.",
    "Do not charge the battery between 2 PM and 4 PM.",
    "The cafeteria menu changes tomorrow.",
  ],
  "hours": hours,
  "battery": {
    "capacity_kwh": 500,
    "initial_energy_kwh": 200,
    "minimum_energy_kwh": 50,
    "max_charge_kwh_per_hour": 100,
    "max_discharge_kwh_per_hour": 100,
  },
}))
PY
)"
```

Expected fields: `scenario_id`, `directive_interpretation`, `hourly_plan`, `total_grid_kwh`, `total_cost_bdt`, `peak_grid_kwh`, `plan_summary`.

## Sample smoke test (after cloning the repo)

Runs three cases: 2 valid + 1 invalid (expects 400). Needs the `samples/` folder from the repo.

| Sample | Expected |
| ------ | -------- |
| `samples/01_ok_solar_nocharge.json` | 200 — solar cut + no-charge + no_op |
| `samples/02_ok_reserve_gridcap.json` | 200 — reserve + grid cap + no-discharge |
| `samples/03_bad_request.json` | 400 — more than 3 operator notes |

```bash
git clone https://github.com/chistym17/Bup-hackathon.git
cd Bup-hackathon
pip install httpx
python scripts/smoke_test.py https://gridwiseai.onrender.com
```

## Docker fallback

Image (exact digest):

```
chisty17/gridwise-energy@sha256:f76d18127aa4e14bb7e05d02b4a3bca99fefe00d83e12d9cd1c26cd3b38ec28b
```

Also tagged: `chisty17/gridwise-energy:v1`

```bash
docker pull chisty17/gridwise-energy@sha256:f76d18127aa4e14bb7e05d02b4a3bca99fefe00d83e12d9cd1c26cd3b38ec28b
docker run --rm -p 8000:8000 chisty17/gridwise-energy@sha256:f76d18127aa4e14bb7e05d02b4a3bca99fefe00d83e12d9cd1c26cd3b38ec28b
curl -s http://127.0.0.1:8000/health
```

`/health` works with no API keys. For `/optimize-energy` pass keys:

```bash
docker run --rm -p 8000:8000 \
  -e GROQ_API_KEY=... \
  -e GEMINI_API_KEY=... \
  chisty17/gridwise-energy@sha256:f76d18127aa4e14bb7e05d02b4a3bca99fefe00d83e12d9cd1c26cd3b38ec28b
```

## Stack

| Piece | Choice |
| ----- | ------ |
| API | FastAPI + Uvicorn |
| LLM | Groq → Gemini |
| Guardrails | Deterministic validator |
| Optimizer | PuLP + CBC (MILP) |
| Hosting | Render (`gridwiseai.onrender.com`) |

