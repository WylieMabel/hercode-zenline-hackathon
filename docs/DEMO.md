# 3-Minute Live Demo Script

For finalist presentation. Keep the demo on what works; judges can inspect depth from the fork.

## Setup (before presenting)

```bash
cd hercode-zenline-hackathon
python3 -m pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

Open http://localhost:8501. No API keys needed.

---

## 0:00–0:30 — Problem and inputs

> "Retail teams drown in noisy signals — TikTok, search spikes, competitor drops. We built a pipeline that answers one question: **what should a Swiss outdoor retailer do next?**"

- Show **Pipeline** tab
- Point at inputs: **Switzerland**, **Swiss outdoor**, **Decathlon**
- One line: "Same flow works for another vertical — we change config, not code."

---

## 0:30–1:30 — Run pipeline (bundled, no APIs)

- Click **Run Pipeline**
- As steps complete, call out:
  - **Step 1:** ~4,500 competitor products from offline catalog
  - **Steps 2–4:** YouTube + regional + Google Trends → separate CSVs merged into `raw_signals.csv`
  - **Step 2b:** Trend facets (materials, features, aesthetics)
  - **Step 5:** Deterministic scoring — six dimensions, documented in `evidence/METHODOLOGY.md`
  - **Step 6:** Ranked recommendations

> "Everything is CSV-backed. Nothing is a black box."

---

## 1:30–3:00 — Opportunities and audit trail

- Open **Opportunities** tab
- Expand **#2 Gore-Tex & Advanced Waterproof Technology** (high confidence):
  - **Trend** — material opportunity
  - **Why** — waterproof/breathable facets + competitor gap
  - **Evidence** — YouTube URLs (click one if network allows)
  - **Details** — recommended action, risks, workflow `buy`

> "To verify this isn't hallucinated: open `ranked_recommendations.csv` in the repo — same URLs. Search those URLs in `scored_opportunities.csv` for the score breakdown in `notes`."

- Optional: show **#5** briefly as **low confidence** / `monitor` — we label weak evidence honestly.

---

## 3:00–3:30 — Reusability and limitations

> "Bundled data means judges can run this without API keys. Live mode needs YouTube and optionally Claude. We don't oversell mock sources — they're score-capped at 0.35."

- Mention: `app/vertical_presets.py`, `competitors/competitor_products.csv`, `docs/PIPELINE.md`

---

## Q&A prep

| Question | Answer |
|----------|--------|
| How is score calculated? | `evidence/METHODOLOGY.md` — 25% momentum, 25% gap, 20% early market, etc. |
| Where does evidence come from? | `raw_signals.csv` → `scored_opportunities.csv` → `ranked_recommendations.csv` |
| Does it work without Claude? | Yes — rule-based fallback for compile and facets |
| DACH transferability? | Multi-geo Trends (CH vs US/JP) + explicit field per recommendation |
| Reuse for skincare / another market? | New preset in `vertical_presets.py`, new competitor CSV |
