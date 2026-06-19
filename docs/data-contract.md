# Suggested Data Contract

Use any format that fits your solution. Structured CSV or JSON is recommended so the jury can inspect and rerun your work.

## Signal Row

| Field | Description |
| --- | --- |
| `source` | Source name, such as retailer site, publication, TikTok, marketplace, Google Trends, API, or manual research. |
| `market` | Market where the signal appears, such as CH, DACH, US, Japan, Korea, Nordics, or UK. |
| `keyword` | Keyword, query, hashtag, product phrase, or category label. |
| `signal_name` | Human-readable name of the trend or opportunity. |
| `signal_type` | `search`, `social`, `web`, `marketplace`, `competitor`, `manual`, `api`, or another explicit type. |
| `product_name` | Product or example item, if relevant. |
| `brand` | Brand, supplier, creator, retailer, or source entity, if relevant. |
| `price` | Observed price, if relevant and source-backed. |
| `rank` | Bestseller rank, listing position, popularity rank, or internal rank, if relevant. |
| `url` | Evidence URL. |
| `signal_score` | Your score for signal strength. Define the scale in your submission. |
| `confidence` | `high`, `medium`, `low`, or a documented numeric confidence scale. |
| `notes` | Short evidence notes and limitations. Include measurement window and geo when applicable (e.g. `window: today 3-m, geo: CH`). |
| `observed_at` | Date or timestamp when the signal was observed. |
| `artifact_type` | `csv`, `json`, `markdown`, `pdf`, `dashboard`, `screenshot`, `api`, or another explicit type. |
| `artifact_uri` | Path or URL to the generated artifact. |
| `created_by_tool` | Script, model, notebook, scraper, API, or manual workflow that created the row. |

## Recommendation Row

| Field | Description |
| --- | --- |
| `rank` | Recommendation rank. |
| `opportunity` | The recommended opportunity. |
| `opportunity_type` | Category of opportunity: `product_type`, `material`, `feature`, `aesthetic`, `color_palette`, `brand`, `price_gap`, `merchandising`, `usage_occasion`, or `content_community`. |
| `first_observed_market` | Where the signal appears first or strongest. |
| `evidence_summary` | Concise summary of supporting evidence. |
| `evidence_urls` | List of source URLs. |
| `transferability` | Assessment for Switzerland or DACH. |
| `coverage_status` | `covered`, `partially_covered`, `absent`, `unknown`, or `not_relevant`. |
| `recommended_action` | What the retailer should test, buy, launch, or monitor. |
| `confidence` | Confidence score or label. |
| `risks` | Main risks and missing evidence. |

## Example Files

See [`../examples/signals.csv`](../examples/signals.csv) for a small example shape. Replace it with your own data or add your own files.
