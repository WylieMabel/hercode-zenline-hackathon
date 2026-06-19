# Scoring Methodology

This document maps business questions from the challenge brief to evidence sources, score dimensions, and recommended workflows.

## Business Questions → Score Dimensions

| Question | Evidence sources | Dimension (0–1) | Weight |
|----------|------------------|-------------------|--------|
| Which brands are gaining momentum? | Competitor new arrivals, social mentions, Google Trends momentum pass | `momentum` | 25% |
| Which product types appear first in other markets? | Multi-geo Trends (US/JP vs CH velocity delta) | `early_market` | 20% |
| Which materials/features move niche → mainstream? | Trend facets, publication RSS, YouTube | `innovation` | 15% |
| Which local assortment gaps exist? | `competitor_gap_hints.json`, client vs competitor diff | `gap` | 25% |
| Margin / differentiation / loyalty fit? | Price band, `fake_data.csv` category match | `commercial_fit` | 10% |
| Strong enough to act? | Source diversity across signal types | `actionability` (diversity) | 5% |

## Composite Formula

```
signal_score = 0.25×momentum + 0.20×early_market + 0.15×innovation
             + 0.25×gap + 0.10×commercial_fit + 0.05×source_diversity
```

- Mock-only clusters capped at **0.35**
- Mixed mock/live clusters penalized 10%
- Confidence: high ≥ 0.65, medium ≥ 0.40, else low

## Recommended Workflows

| Score | Workflow | Retail action |
|-------|----------|---------------|
| < 0.45 | `monitor` | Watch for 30–60 days; no buy commitment |
| 0.45 – 0.65 | `test` | Limited test buy or supplier conversation |
| 0.65 – 0.80 | `buy` | Add to assortment or expand depth |
| > 0.80 | `launch` | Priority launch with marketing support |

## Temporal Windows

Per-source windows in `pipeline_config.json` → `time_windows`:

- **Trends momentum:** `today 3-m` (recent 4w vs prior 4w)
- **Trends seasonal:** `today 12-m` (quarter-over-quarter)
- **Weather baseline:** 5 years same-calendar-day (configurable)
- **Holidays:** forward 90 days
- **Social / competitors:** point-in-time snapshot at `observed_at`

Window metadata is stored in signal `notes` (e.g. `window: today 3-m, geo: CH`).

## Clustering

- **Competitor rows:** `product::{category}::{brand}` (not flat "new arrivals")
- **Trends rows:** `trend::{keyword}::{market}`
- **Other:** `keyword::{keyword}`

## Evidence Quality

| Source type | Trust level | Notes |
|-------------|-------------|-------|
| Live API (Open-Meteo, Nager, FX) | High | No auth, reproducible |
| Google Trends (pytrends) | Medium | Unofficial API; rate limits |
| Shopify JSON retailers | High | Stable public endpoint |
| CSS scrapes | Low–medium | Often blocked; fallback mocks |
| TikTok, tourism mock | Simulated | Explicitly labeled in `notes` |

## Transferability

A signal is flagged **stronger abroad** when US or JP Trends velocity exceeds CH by > 5 points on the momentum pass. The compiler uses `first_observed_market` from cited signal rows — never guessed.

## Gap Analysis

`competitor_gap_hints.json` lists:
- **gap_brands:** brands at ≥2 competitors, absent from client scrape
- **gap_categories:** product categories frequent at competitors, absent from client

Gap dimension scores highest when cluster text matches gap hints.
