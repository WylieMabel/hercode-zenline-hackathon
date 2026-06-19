# Submission

## Team

- Team name: HerShe(y)
- Team members: Sarah Verreault, Mabel Wylie
- GitHub fork URL: https://github.com/WylieMabel/hercode-zenline-hackathon
- Demo URL: http://localhost:8501 (after `streamlit run app/streamlit_app.py`)
- Video walkthrough URL: *(optional — not recorded)*

## Summary

We built **Zenline Opportunity Scout**: a reusable six-step retail signal pipeline for the Swiss outdoor scenario (Decathlon client). It merges competitor assortment gaps, YouTube and Google Trends signals, regional context (weather, holidays, RSS), deterministic multi-dimensional scoring, and optional LLM compilation into ranked business opportunities. Every step writes inspectable CSV artifacts so judges can audit **trend → evidence → score → recommendation** without trusting a black box.

Full pipeline documentation: [`docs/PIPELINE.md`](docs/PIPELINE.md). Scoring methodology: [`evidence/METHODOLOGY.md`](evidence/METHODOLOGY.md).

## How To Run

Tested on **Python 3.12.6** (macOS). Python 3.10+ recommended.

```bash
git clone https://github.com/WylieMabel/hercode-zenline-hackathon.git
cd hercode-zenline-hackathon
python3 -m pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

Open http://localhost:8501 in your browser.

**No API keys required for the default demo.** The pipeline uses bundled offline data (`data/bundled/*.csv` and `competitors/competitor_products.csv`). On first load, the **Opportunities** tab shows recommendations from committed `ranked_recommendations.csv`.

To run the full pipeline in the UI:

1. Open the **Pipeline** tab.
2. Leave defaults: Switzerland, Swiss outdoor, Decathlon.
3. Click **Run Pipeline**.
4. Switch to **Opportunities** for ranked results.

Optional:

- **Claude API key** — enter in the Streamlit sidebar (session only, never saved to disk) for richer config and recommendations.
- **YouTube API key** — only needed to refresh bundled social data: `YOUTUBE_API_KEY=your_key python3 scripts/snapshot_bundled_signals.py --live`

CLI alternative (full pipeline, no UI):

```bash
python3 -c "from app.pipeline_runner import run_pipeline; run_pipeline('Switzerland', 'Swiss outdoor', 'Decathlon')"
```

See [`.env.example`](.env.example) for optional environment variables.

## Inputs

- **Market:** Switzerland / DACH outdoor
- **Category:** Outdoor retail (hiking, trail running, alpine gear, gorpcore crossover)
- **Client:** Decathlon
- **Seed keywords:** gorpcore, trail running packs, fastpacking, ultralight hiking, alpine crossover (see `app/vertical_presets.py`)
- **Languages:** English (signals); CH/US/JP geo comparison for Trends
- **Sources:**
  - Competitor catalog: `competitors/competitor_products.csv` (~4,500 products, 7 retailers)
  - YouTube: bundled in `data/bundled/youtube_signals.csv` (~380 videos)
  - Google Trends: bundled in `data/bundled/google_trends_signals.csv`
  - Regional: Open-Meteo weather/UV, Nager.Date holidays, exchangerate.host FX, GearJunkie/Outside RSS
  - Publications and competitor product rows merged into `raw_signals.csv`

## Outputs

- **Dashboard / UI:** Streamlit app (`app/streamlit_app.py`) — Pipeline tab + Opportunities tab (Trend / Why / Evidence / Details)
- **Report:** [`ranked_recommendations.csv`](ranked_recommendations.csv) — final ranked opportunities
- **Structured data:**

| File | Purpose |
|------|---------|
| `ranked_recommendations.csv` | Final judge-facing recommendations |
| `raw_signals.csv` | Master evidence merge (~4,400 rows) |
| `scored_opportunities.csv` | Per-signal scores with dimension notes |
| `competitor_products.csv` | Normalized competitor assortment |
| `social_signals.csv` | Social layer (YouTube-led) |
| `google_trends_signals.csv` | Google Trends layer only |
| `data/bundled/*.csv` | Offline snapshots for reproducible demo |

- **Generated on pipeline run** (gitignored, reproducible): `pipeline_config.json`, `trend_insights.json`, `competitor_gap_hints.json`

## Ranked Opportunities

| Rank | Opportunity | Evidence | Confidence |
| --- | --- | --- | --- |
| 1 | Earth Tone Colorway Expansion in Outdoor Apparel | YouTube earth-tone video cluster (26 videos); olive/sand/stone palettes in trend facets | medium |
| 2 | Gore-Tex & Advanced Waterproof Technology as Hero Narrative | Waterproof/breathable facets; Gore-Tex material signal; 89 competitor gap brands | high |
| 3 | Ultralight & Fastpacking Product Category Build-Out | fastpacking/ultralight top trends; assortment white space vs 106 competitor brands | medium |
| 4 | Gorpcore x Technical Casual Merchandising Edit | Gorpcore aesthetic + YouTube outdoor-streetwear crossover content | medium |
| 5 | Mindfulness & Nature-Wellbeing Content Community | YouTube wellness/nature frequency cluster (directional; see limitations) | low |

## Evidence Trail

To audit recommendation **#1** or **#2**:

1. [`ranked_recommendations.csv`](ranked_recommendations.csv) — `evidence_summary`, `evidence_urls`
2. [`scored_opportunities.csv`](scored_opportunities.csv) — search for YouTube URLs; read `signal_score` and `notes` (momentum, gap, innovation breakdown)
3. [`raw_signals.csv`](raw_signals.csv) — original signal rows (`source`, `signal_name`, `url`, `observed_at`)
4. [`trend_insights.json`](trend_insights.json) — extracted facets + provenance URLs (generated on run)
5. [`competitor_gap_hints.json`](competitor_gap_hints.json) — gap brands/categories (generated on run)
6. [`evidence/METHODOLOGY.md`](evidence/METHODOLOGY.md) — scoring weights and source trust levels
7. [`docs/PIPELINE.md`](docs/PIPELINE.md) — end-to-end flow diagram and file index

## Reusability

- Change **location**, **market**, or **client** in the Streamlit Pipeline tab and re-run.
- Add new verticals in [`app/vertical_presets.py`](app/vertical_presets.py) (`VERTICAL_PRESETS` dict).
- Swap competitor data by updating [`competitors/competitor_products.csv`](competitors/competitor_products.csv) (source list in `competitors/extracted_websites.csv`).
- Toggle data sources in config: `competitor_data_source`, `youtube_data_source`, `regional_data_source`, `trends_data_source` — `bundled` (offline demo) vs `live` (APIs).
- Scoring is fully deterministic (`app/scoring.py`); LLM is optional for config, facet extraction, and recommendation narrative.

## Known Limitations

- **Reddit** is often blocked (403) → `reddit_fallback_mock` rows; **TikTok** is simulated (`tiktok_mock`).
- **Google Trends** live API rate-limits; demo uses bundled `data/bundled/google_trends_signals.csv`.
- Competitor catalog includes some non-core outdoor retailers (e.g. golf) from `competitors/extracted_websites.csv`.
- **No strict relevance filter** between YouTube/Trends rows and competitor SKUs — product seeds influence search queries but do not gate results.
- `commercial_fit` scoring references `data_generation/fake_data.csv` (archived); dimension uses a neutral fallback when file is absent.
- CSV writes **replace** on each pipeline run (not append).
- Opportunity **#5** (nature-wellbeing content) is low-confidence and directional — included to show `content_community` opportunity type, not core outdoor product proof.

## Architecture Notes

Six-step flow orchestrated by [`app/pipeline_runner.py`](app/pipeline_runner.py):

1. **Competitors** — load bundled catalog → `competitor_products.csv` + `competitor_gap_hints.json`
2. **Signals** — social (YouTube) → regional → Google Trends (keywords fed from social) → merge `raw_signals.csv`
3. **Facet extraction** — `trend_insights.json` (materials, features, aesthetics)
4. **Scoring** — cluster signals, six weighted dimensions → `scored_opportunities.csv`
5. **Compile** — top signals + gaps → `ranked_recommendations.csv`
6. **UI** — Streamlit presents Trend / Why / Evidence cards

See [`docs/PIPELINE.md`](docs/PIPELINE.md) for the full diagram and artifact index.

## Live demo script

See [`docs/DEMO.md`](docs/DEMO.md) for a 3-minute presentation walkthrough.