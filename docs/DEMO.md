# 3-Minute Live Demo Script

For finalist presentation. **Use the Next.js UI** — data is pre-loaded, no pipeline run needed.

## Setup (before presenting)

```bash
cd hercode-zenline-hackathon/frontend
npm install
npm run dev
```

Open http://localhost:3000. No API keys needed. **Do not click Run Pipeline.**

---

## 0:00–0:30 — Problem

> "Retail teams drown in noisy signals — YouTube, search spikes, competitor drops. We built a pipeline that answers: **what should a Swiss outdoor retailer do next?**"

- Show header: **Zenline Opportunity Scout** · Switzerland · Decathlon
- Metrics bar: ~4,400 signals → 6 ranked opportunities

---

## 0:30–1:30 — Top opportunities (sorted best-first)

- **Opportunities** tab — #1 **Gorpcore Technical-Casual** (high confidence, buy)
- Expand card: evidence URLs, recommended action, DACH transferability
- Scroll to **#2 Napapijri brand onboarding** — competitor gap proof
- One line: "Sorted by confidence and action — not raw YouTube titles."

---

## 1:30–2:15 — Evidence trail

- **Report** tab → six-step pipeline story
- Trend facets: gorpcore, merino, waterproof, olive/sand/stone
- Gap brands: Napapijri, Peak Performance, etc.
- Point judges to fork: `raw_signals.csv` → `scored_opportunities.csv` → `ranked_recommendations.csv`

---

## 2:15–3:00 — Reusability + limitations

> "Change market, client, or vertical preset — same six-step flow. Bundled mode runs without API keys; Claude optional for richer compile."

- Mention: Reddit/TikTok mocked and score-capped; YouTube earth-tone noise is a known limitation
- Close: "Three high-confidence actions ready: gorpcore edit, Napapijri, merino ultralight."

---

## Backup: Streamlit

```bash
cd hercode-zenline-hackathon
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

Open http://localhost:8501 — same CSV artifacts.
