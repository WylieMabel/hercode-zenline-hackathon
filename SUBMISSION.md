# Submission

## Team

- Team name: HerShe(y)
- Team members: Sarah Verreault, Mabel Wylie
- GitHub fork URL: https://github.com/WylieMabel/hercode-zenline-hackathon
- Demo URL: http://localhost:3000 (after `cd frontend && npm install && npm run dev`) — **recommended**
- Alternate UI: http://localhost:8501 (after `streamlit run app/streamlit_app.py`)
- Video walkthrough URL: *(optional — not recorded)*

## Summary

**Zenline Opportunity Scout** is a reusable six-step retail signal pipeline for the Swiss outdoor scenario (Decathlon client). It merges competitor assortment gaps, YouTube and Google Trends signals, regional context (weather, holidays, FX), deterministic multi-dimensional scoring, and optional LLM compilation into ranked business opportunities. Every step writes inspectable CSV/JSON artifacts so judges can audit **trend → evidence → score → recommendation** without trusting a black box.

---

## Repository & deliverables

| Deliverable | Location |
|-------------|----------|
| **Pipeline orchestration** | [`app/pipeline_runner.py`](app/pipeline_runner.py) |
| **Scoring engine** | [`app/scoring.py`](app/scoring.py) |
| **LLM compiler** | [`app/compiler.py`](app/compiler.py) |
| **Signal collection** | [`app/signal_collection.py`](app/signal_collection.py), [`app/regional.py`](app/regional.py), [`app/trends.py`](app/trends.py) |
| **Competitor analysis** | [`app/competitors.py`](app/competitors.py), [`competitors/`](competitors/) |
| **Next.js dashboard** | [`frontend/`](frontend/) — UI + API routes (`/api/results`, `/api/insights`, `/api/run`) |
| **Streamlit dashboard** | [`app/streamlit_app.py`](app/streamlit_app.py) |
| **CLI entrypoint** | [`scraper_pipeline.py`](scraper_pipeline.py) |
| **Bundled data snapshots** | [`data/bundled/`](data/bundled/), [`scripts/snapshot_bundled_signals.py`](scripts/snapshot_bundled_signals.py) |
| **Documentation** | [`docs/PIPELINE.md`](docs/PIPELINE.md), [`docs/DEMO.md`](docs/DEMO.md), [`evidence/METHODOLOGY.md`](evidence/METHODOLOGY.md) |

---

## How to run

Tested on **Python 3.12.6** (macOS). Python 3.10+ and Node 18+ recommended.

### Recommended: Next.js dashboard

```bash
git clone https://github.com/WylieMabel/hercode-zenline-hackathon.git
cd hercode-zenline-hackathon/frontend
npm install
npm run dev
```

Open http://localhost:3000 — **Opportunities** tab loads committed `ranked_recommendations.csv` (no API keys, no pipeline run required).

### Alternate: Streamlit

```bash
cd hercode-zenline-hackathon
python3 -m pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

Open http://localhost:8501.

**No API keys required for the default demo.** Bundled offline data and committed outputs load on first page view.

To re-run the full Python pipeline (Streamlit **Pipeline** tab):

1. Defaults: Switzerland, Swiss outdoor, Decathlon.
2. Optionally paste a **Claude API key** (session only) for richer LLM recommendations.
3. Click **Run Pipeline** → **Opportunities**.

**Do not use the Next.js “Run Pipeline” button for judging** — it re-collects signals only and does not pass a Claude key to the compiler.

Optional keys: see [`.env.example`](.env.example). CLI:

```bash
python3 -c "from app.pipeline_runner import run_pipeline; run_pipeline('Switzerland', 'Swiss outdoor', 'Decathlon')"
```

---

## Scoring methodology

Signals in `raw_signals.csv` are grouped into clusters (by keyword, trend geo, or product category + brand). Each cluster receives one **signal_score** from six weighted dimensions (implementation: [`app/scoring.py`](app/scoring.py)).

### Composite equation

```
signal_score = 0.25 × momentum
             + 0.20 × early_market
             + 0.15 × innovation
             + 0.25 × gap
             + 0.10 × commercial_fit
             + 0.05 × source_diversity
```

| Dimension | Weight | What it measures |
|-----------|--------|------------------|
| `momentum` | 25% | Google Trends velocity; social volume when Trends absent |
| `early_market` | 20% | US/JP vs CH trend lead (stronger abroad → higher) |
| `innovation` | 15% | Trend facets (materials, features, aesthetics) + publication signals |
| `gap` | 25% | Match to brands/categories in `competitor_gap_hints.json` |
| `commercial_fit` | 10% | Overlap with known product categories in client sales proxy |
| `source_diversity` | 5% | Mix of live signal types (social, competitor, regional, trends) |

### Confidence & recommended workflow

| signal_score | Confidence | Workflow (`recommended_workflow`) |
|--------------|------------|-----------------------------------|
| ≥ 0.65 | high | `buy` (0.65–0.80) or `launch` (> 0.80) |
| ≥ 0.40 | medium | `test` |
| < 0.40 | low | `monitor` |

**Trust penalties:** mock-only clusters (Reddit fallback, TikTok sim) capped at **0.35**; mixed mock/live clusters penalized **10%**.

Top 20 scored clusters feed the LLM compiler ([`app/compiler.py`](app/compiler.py)), which synthesizes business opportunities. Final UI ranking sorts by **confidence → workflow (buy/launch first) → signal_score**.

Full methodology: [`evidence/METHODOLOGY.md`](evidence/METHODOLOGY.md).

---

## Evidence sources

| Source | Type | API / URL | Used for |
|--------|------|-----------|----------|
| **YouTube Data API** | Social | https://developers.google.com/youtube/v3 | Video titles, channels, view-ranked queries (bundled: `data/bundled/youtube_signals.csv`) |
| **Google Trends** | Search | https://trends.google.com (via `pytrends`) | CH/US/JP momentum & seasonal series (bundled: `data/bundled/google_trends_signals.csv`) |
| **Open-Meteo** | Regional | https://api.open-meteo.com/v1/forecast | Swiss weather, UV, daylight anomalies |
| **Open-Meteo Archive** | Regional | https://archive-api.open-meteo.com/v1/archive | 5-year weather baseline |
| **Nager.Date** | Regional | https://date.nager.at/api/v3/PublicHolidays | CH public holidays (forward 90 days) |
| **exchangerate.host** | Regional | https://api.exchangerate.host/latest | CHF/EUR/USD/JPY FX context |
| **GearJunkie RSS** | Publication | https://gearjunkie.com/feed | Outdoor editorial signals |
| **Outside RSS** | Publication | https://www.outsideonline.com/rss | Outdoor editorial signals |
| **Decathlon** | Competitor | https://www.decathlon.com | Client / house-brand assortment |
| **Patagonia** | Competitor | https://www.patagonia.com | Competitor catalog |
| **Golfers Paradise CH** | Competitor | https://golfersparadise.ch | Swiss competitor scrape |
| **Other retailers** | Competitor | See `competitors/competitor_products.csv` `url` column | ~4,500 normalized SKUs across 7 retailers |
| **Reddit** | Social | https://www.reddit.com (often 403) | Fallback mock rows, score-capped |
| **TikTok** | Social | Simulated | `tiktok_mock` rows, score-capped |

**Sample evidence URLs cited in top recommendations:**

- Gorpcore / crossover: https://www.youtube.com/watch?v=e-O--bFru48 , https://www.youtube.com/watch?v=6FRlBwiIYOQ
- Napapijri / brand gap: https://www.youtube.com/watch?v=6FRlBwiIYOQ , https://www.youtube.com/watch?v=e-O--bFru48
- Merino / ultralight: https://www.youtube.com/watch?v=FZrhMbwQIT8 , https://www.youtube.com/watch?v=7kGZB_exG0M
- Earth tones: https://www.youtube.com/watch?v=DCNkHS93ez8 , https://www.youtube.com/watch?v=7kGZB_exG0M
- Waterproof education: https://www.youtube.com/watch?v=DCNkHS93ez8 , https://www.youtube.com/watch?v=FZrhMbwQIT8

Master merge: [`raw_signals.csv`](raw_signals.csv) (~4,400 rows). Per-signal scores: [`scored_opportunities.csv`](scored_opportunities.csv).

---

## Dashboard & tool

### Next.js UI (primary) — http://localhost:3000

```mermaid
flowchart LR
  CSV[ranked_recommendations.csv] --> API[/api/results]
  JSON[trend_insights.json] --> INS[/api/insights]
  API --> UI[Opportunities tab]
  INS --> REP[Report tab]
  UI --> SORT[Sort: confidence → workflow → score]
```

| Tab | Purpose |
|-----|---------|
| **Opportunities** | Ranked cards (best-first): opportunity title, confidence badge, workflow (buy/test/monitor), expandable evidence URLs, recommended action, risks, facet chips |
| **Report** | Six-step pipeline narrative, trend facet chips, competitor gap brands, summary table |
| **Pipeline** | Re-run signal collection (optional; not needed for demo) |

Metrics bar shows: total raw signals, opportunity count, high-confidence count, ready-to-act (buy/launch) count.

### Streamlit UI (alternate) — http://localhost:8501

**Pipeline** tab runs all six steps with live status. **Opportunities** tab shows Trend / Why / Evidence / Details cards from the same CSV artifacts.

### Six-step workflow

1. **Competitors** → `competitor_products.csv` + `competitor_gap_hints.json`
2. **Signals** → social (YouTube) + regional + Google Trends → `raw_signals.csv`
3. **Facet extraction** → `trend_insights.json`
4. **Scoring** → `scored_opportunities.csv`
5. **Compile** → `ranked_recommendations.csv`
6. **UI** → Next.js or Streamlit

See [`docs/PIPELINE.md`](docs/PIPELINE.md) for the full diagram.

---

## Ranked opportunities

Committed LLM output in [`ranked_recommendations.csv`](ranked_recommendations.csv). Sorted **best → worst** (same order as the dashboard).

| Rank | Opportunity | Confidence | Next action | Risks |
|------|-------------|------------|-------------|-------|
| 1 | Gorpcore Technical-Casual Crossover Product Line | **high** | Launch curated **Urban Alpine** shop-in-shop online and in flagship stores (`buy`) | Gorpcore saturation; need differentiation from mass retailers |
| 2 | Napapijri Brand Onboarding for DACH Outdoor Retail | **high** | Initiate Napapijri wholesale talks; target **SS26** gorpcore capsule (`buy`) | Exclusivity restrictions; brand may already partner with rival DACH retailers |
| 3 | Merino Wool Ultralight Travel and Hiking Apparel | **high** | Source and list merino ultralight tees/base layers from 2–3 specialist brands (`buy`) | DACH price sensitivity; merino premium may limit volume |
| 4 | Earth Tone Color Palette Expansion in Outdoor Apparel | medium | Introduce **olive/sand/stone** SKUs in fleece, softshell, merino tees next season (`test`) | Trend may be peaking; timing critical |
| 5 | Waterproof & Breathable Feature Content Strategy | medium | Produce **6-part German YouTube series** on waterproof tech featuring own SKUs (`test`) | Content production cost; needs consistent publishing cadence |
| 6 | Mindful Outdoor / Wellness Hiking Occasion | low | Launch **Natur & Wohlbefinden** campaign pairing merino + earth-tone gear (`monitor`) | Niche audience; wellness framing may dilute performance brand |

**Evidence trail** (audit #1 or #2):

1. [`ranked_recommendations.csv`](ranked_recommendations.csv) — `evidence_summary`, `evidence_urls`
2. [`scored_opportunities.csv`](scored_opportunities.csv) — `signal_score`, `notes` (per-dimension breakdown)
3. [`raw_signals.csv`](raw_signals.csv) — original rows (`source`, `signal_name`, `url`)
4. [`trend_insights.json`](trend_insights.json) — facets + provenance
5. [`competitor_gap_hints.json`](competitor_gap_hints.json) — gap brands/categories
6. [`evidence/METHODOLOGY.md`](evidence/METHODOLOGY.md) — scoring weights
7. [`docs/PIPELINE.md`](docs/PIPELINE.md) — end-to-end flow

---

## Inputs

- **Market:** Switzerland / DACH outdoor
- **Client:** Decathlon (Quechua, Simond, Forclaz house brands)
- **Seed keywords:** gorpcore, trail running packs, fastpacking, ultralight hiking (see [`app/vertical_presets.py`](app/vertical_presets.py))
- **Languages:** English signals; CH/US/JP geo comparison for Trends

## Outputs (artifact index)

| File | Purpose |
|------|---------|
| `ranked_recommendations.csv` | Final judge-facing recommendations |
| `raw_signals.csv` | Master evidence merge (~4,400 rows) |
| `scored_opportunities.csv` | Per-signal scores with dimension notes |
| `competitor_products.csv` | Normalized competitor assortment (~4,500 rows) |
| `social_signals.csv` / `google_trends_signals.csv` | Layer-specific signal exports |
| `trend_insights.json` | Facet extraction snapshot |
| `competitor_gap_hints.json` | Gap brands/categories snapshot |
| `data/bundled/*.csv` | Offline snapshots for reproducible demo |

## Reusability

- Change location, market, or client in the UI and re-run.
- Add verticals in [`app/vertical_presets.py`](app/vertical_presets.py).
- Toggle `bundled` vs `live` per source in pipeline config.
- Scoring is fully deterministic; LLM optional for config, facets, and compile narrative.

## Known limitations

- Reddit often blocked (403) → mock rows; TikTok simulated — both score-capped.
- Google Trends live API rate-limits; demo uses bundled trends CSV.
- Competitor catalog includes some non-core retailers (e.g. golf).
- No strict relevance filter between YouTube noise and outdoor SKUs.
- CSV writes **replace** on each pipeline run (not append).
- Opportunity **#6** is low-confidence and directional (`usage_occasion` type).

## Live demo script

See [`docs/DEMO.md`](docs/DEMO.md) for a 3-minute presentation walkthrough.
