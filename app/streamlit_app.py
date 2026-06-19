"""
Zenline Opportunity Scout — Streamlit frontend.

Run from project root:
    streamlit run app/streamlit_app.py
"""

import csv
import os
import sys
from datetime import datetime

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_APP_DIR)
sys.path.insert(0, _APP_DIR)
sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import streamlit as st

import pipeline_runner
from compiler import load_recommendations

st.set_page_config(
    page_title="Zenline Opportunity Scout",
    page_icon="⛰️",
    layout="wide",
)

_DEFAULTS = {
    "pipeline_complete": False,
    "config": {},
    "opportunities": [],
    "gap_hints": {},
    "insights": {},
    "claude_api_key": "",
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

if not st.session_state.opportunities:
    persisted = load_recommendations()
    if persisted:
        st.session_state.opportunities = persisted


CONFIDENCE_BADGE = {"high": "🟢 High", "medium": "🟡 Medium", "low": "🔴 Low"}
WORKFLOW_BADGE = {"launch": "🚀 Launch", "buy": "🛒 Buy", "test": "🧪 Test", "monitor": "👀 Monitor"}
TYPE_LABELS = {
    "product_type": "Product",
    "material": "Material",
    "feature": "Feature",
    "aesthetic": "Aesthetic",
    "color_palette": "Colour",
    "brand": "Brand",
    "price_gap": "Price gap",
    "merchandising": "Merchandising",
    "usage_occasion": "Occasion",
    "content_community": "Content",
}


def _split_field(val) -> list[str]:
    if not val:
        return []
    if isinstance(val, list):
        return [str(v).strip() for v in val if str(v).strip()]
    return [v.strip() for v in str(val).split(";") if v.strip()]


def _parse_why_and_evidence(opp: dict) -> tuple[str, list[str]]:
    """Split rationale (why) from evidence bullets, including CSV round-trips."""
    why = (opp.get("description") or "").strip()
    evidence = _split_field(opp.get("evidence"))

    summary = (opp.get("evidence_summary") or "").strip()
    if summary:
        if " Evidence: " in summary:
            head, _, tail = summary.partition(" Evidence: ")
            if not why:
                why = head.strip()
            if not evidence:
                evidence = [e.strip() for e in tail.split(";") if e.strip()]
        elif not why:
            why = summary

    return why, evidence


def _render_opportunity_card(opp: dict, *, expanded_details: bool = False) -> None:
    rank = opp.get("rank", "?")
    name = opp.get("opportunity", "Unknown")
    conf = opp.get("confidence", "low")
    workflow = opp.get("recommended_workflow", "monitor")
    opp_type = opp.get("opportunity_type", "product_type")
    badge = CONFIDENCE_BADGE.get(conf, conf)
    wf = WORKFLOW_BADGE.get(workflow, workflow)
    type_label = TYPE_LABELS.get(opp_type, opp_type)

    why, evidence = _parse_why_and_evidence(opp)
    urls = [u for u in _split_field(opp.get("evidence_urls")) if u != "N/A"]

    with st.container(border=True):
        st.markdown(f"## #{rank} · {name}")
        st.caption(f"{type_label} · {badge} · {wf}")

        if why:
            st.markdown("**Why**")
            st.markdown(why)

        if evidence or urls:
            st.markdown("**Evidence**")
            for bullet in evidence:
                st.markdown(f"- {bullet}")
            for url in urls:
                st.markdown(f"- [{url}]({url})")

        with st.expander("Details", expanded=expanded_details):
            action = opp.get("action") or opp.get("recommended_action", "")
            if action:
                st.markdown("**Recommended action**")
                st.info(action)

            meta_cols = st.columns(2)
            with meta_cols[0]:
                st.markdown(f"**Confidence:** {badge}")
                st.markdown(f"**Workflow:** {wf}")
                st.markdown(f"**First market:** {opp.get('first_observed_market', 'N/A')}")
            with meta_cols[1]:
                st.markdown(f"**Coverage:** {opp.get('coverage_status', 'unknown')}")
                transfer = opp.get("transferability", "")
                if transfer:
                    st.markdown(f"**DACH transferability:** {transfer}")

            for label, key in (
                ("Products", "products"),
                ("Features", "features"),
                ("Materials", "materials"),
                ("Aesthetics", "aesthetics"),
                ("Colour palettes", "color_palettes"),
            ):
                val = _split_field(opp.get(key))
                if val:
                    st.markdown(f"**{label}:** {', '.join(val)}")

            gap = opp.get("competitor_gap", "")
            if gap:
                st.markdown(f"**Competitor gap:** {gap}")

            risks = opp.get("risks", "")
            if risks:
                st.markdown(f"**Risks:** {risks}")


st.title("⛰️ Zenline Opportunity Scout")
st.caption("Six-step pipeline: competitors → trends → regional → scoring → recommendations")

tab_pipeline, tab_opps, tab_report = st.tabs(["▶ Pipeline", "📊 Opportunities", "📋 Report"])

with tab_pipeline:
    col_form, col_steps = st.columns([1, 1], gap="large")

    with col_form:
        st.subheader("Search Configuration")
        location = st.text_input("Company location", value="Switzerland")
        market = st.text_input("Market / category", value="Swiss outdoor")
        client_company = st.text_input("Client company (optional)", value="Decathlon", placeholder="e.g. Decathlon")

        c_min, c_max = st.columns(2)
        with c_min:
            price_min = st.number_input("Min price (CHF)", min_value=0, value=0, step=10)
        with c_max:
            price_max = st.number_input("Max price (CHF)", min_value=0, value=0, step=10)
        price_min = price_min or None
        price_max = price_max or None

        with st.expander("Advanced: time horizon"):
            time_horizon = st.selectbox(
                "Preset",
                ["fast", "standard", "seasonal"],
                index=1,
                help="fast=3mo trends; standard=+12mo seasonal; seasonal=+10yr weather baseline",
            )

        with st.expander("Claude API key (optional)", expanded=False):
            st.caption(
                "Stored only in this browser session — never written to disk, logs, or config files."
            )
            api_key_input = st.text_input(
                "API key",
                type="password",
                value=st.session_state.claude_api_key,
                placeholder="sk-ant-...",
                label_visibility="collapsed",
            )
            if api_key_input:
                st.session_state.claude_api_key = api_key_input
            elif st.session_state.claude_api_key:
                st.success("API key set for this session")

        api_key = st.session_state.claude_api_key or None

        run_btn = st.button("▶ Run Pipeline", type="primary", use_container_width=True)

    with col_steps:
        st.subheader("Pipeline Steps")

        if run_btn:
            with st.status("Step 1: Finding competitor products...", expanded=True) as s1:
                config = pipeline_runner.generate_config(
                    location, market, client_company, price_min, price_max, time_horizon,
                    api_key=api_key,
                )
                st.session_state.config = config
                ok, msg, products, hints = pipeline_runner.run_competitors(config)
                st.write(msg)
                st.session_state.gap_hints = hints
                if config.get("competitors_skipped"):
                    st.warning(
                        "Competitors not in registry (skipped): "
                        + ", ".join(config["competitors_skipped"])
                    )
                if config.get("competitors"):
                    src = config.get("competitor_data_source", "bundled")
                    if src == "bundled":
                        st.caption(
                            f"Bundled catalog: {len(products)} products across "
                            f"{len(config['competitors'])} retailers"
                        )
                    else:
                        st.caption(f"Live scrape: {', '.join(config['competitors'][:8])}")
                if ok:
                    s1.update(label=f"Step 1: {len(products)} competitor products ✓", state="complete")
                else:
                    s1.update(label="Step 1: Competitor error", state="error")

            with st.status("Steps 2–4: Social, regional & Google Trends...", expanded=True) as s2:
                ok, msg, count = pipeline_runner.run_signal_collection(config)
                st.write(msg)
                if ok:
                    s2.update(label=f"Steps 2–4: {count} signals collected ✓", state="complete")
                else:
                    s2.update(label="Steps 2–4: Collection error", state="error")

            with st.status("Step 2b: Extracting trend facets...", expanded=False) as s2b:
                ok, msg, insights = pipeline_runner.run_trend_extraction(config, api_key=api_key)
                st.write(msg)
                st.session_state.insights = insights
                if insights:
                    with st.expander("Trend facets (debug)"):
                        st.json({k: insights.get(k, []) for k in ("trends", "features", "materials", "aesthetics")})
                s2b.update(label="Step 2b: Trend facets extracted ✓", state="complete")

            with st.status("Step 5: Scoring signals...", expanded=True) as s3:
                ok, msg, scored = pipeline_runner.run_scoring(hints, insights)
                st.write(msg)
                if ok:
                    s3.update(label=f"Step 5: {len(scored)} signals scored ✓", state="complete")
                else:
                    s3.update(label="Step 5: Scoring error", state="error")
                    scored = []

            with st.status("Step 6: Compiling recommendations...", expanded=True) as s4:
                ok, msg, opps = pipeline_runner.run_compiler(
                    scored, "", insights, hints, api_key=api_key
                )
                st.write(msg)
                if ok:
                    st.session_state.opportunities = opps
                    st.session_state.pipeline_complete = True
                    s4.update(label=f"Step 6: {len(opps)} recommendations ✓", state="complete")
                else:
                    s4.update(label="Step 6: Compilation error", state="error")

            if st.session_state.pipeline_complete:
                st.success("Pipeline complete — see Opportunities tab.")

        elif st.session_state.pipeline_complete:
            st.info("Pipeline already run. Click Run Pipeline to refresh.")
            if st.session_state.config:
                with st.expander("Last config"):
                    st.json(st.session_state.config)
        else:
            st.info("Configure inputs and click **Run Pipeline**.")

with tab_opps:
    opps = st.session_state.opportunities
    if not opps:
        st.info("No opportunities yet. Run the pipeline on the **Pipeline** tab.")
    else:
        sorted_opps = sorted(opps, key=lambda x: int(x.get("rank", 99) or 99))
        high_conf = sum(1 for o in sorted_opps if o.get("confidence") == "high")

        st.subheader("Opportunities")
        st.caption(
            f"{len(sorted_opps)} trends ranked · {high_conf} high-confidence · "
            "Each card shows **trend**, **why**, and **evidence**; expand **Details** for actions and metadata."
        )

        for i, opp in enumerate(sorted_opps):
            _render_opportunity_card(opp, expanded_details=(i == 0))


# ── Tab 3: Report ─────────────────────────────────────────────────────────────
with tab_report:
    opps = st.session_state.opportunities
    config = st.session_state.config
    insights = st.session_state.insights
    gap_hints = st.session_state.gap_hints

    if not opps:
        st.info("Run the pipeline first, then come back here for the full report.")
    else:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        market_label = config.get("market", "Swiss outdoor")
        client_label = config.get("client_company") or "—"
        st.subheader(f"Opportunity Report · {market_label}")
        st.caption(f"Client: {client_label} · {now_str} · Six-step signal pipeline")

        # ── Summary metrics ───────────────────────────────────────────────────
        raw_count = 0
        raw_path = os.path.join(_PROJECT_ROOT, "raw_signals.csv")
        if os.path.exists(raw_path):
            with open(raw_path, newline="", encoding="utf-8") as _f:
                raw_count = sum(1 for _ in csv.reader(_f)) - 1

        sorted_opps = sorted(opps, key=lambda x: int(x.get("rank", 99) or 99))
        high_conf = sum(1 for o in sorted_opps if o.get("confidence") == "high")
        gap_brands = gap_hints.get("gap_brands", [])
        gap_cats = gap_hints.get("gap_categories", [])

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Signals collected", raw_count)
        m2.metric("Competitor gap brands", len(gap_brands))
        m3.metric("Opportunities found", len(sorted_opps))
        m4.metric("High confidence", high_conf)
        m5.metric("Ready to act", sum(1 for o in sorted_opps if o.get("recommended_workflow") in ("buy", "launch")))

        st.divider()

        # ── Pipeline data flow ────────────────────────────────────────────────
        st.markdown("### How we got here")
        steps = [
            ("1", "Competitor products", f"Scraped {gap_hints.get('competitor_brand_count', '?')} competitor brands · found {len(gap_brands)} assortment gaps"),
            ("2", "Social & trend signals", f"Reddit, TikTok, GearJunkie, YouTube · keywords: {', '.join((config.get('keywords') or [])[:4])}"),
            ("3", "Regional context", "Swiss weather anomaly · upcoming holidays · daylight hours · FX rates"),
            ("4", "Google Trends (multi-geo)", f"Markets tracked: {', '.join(config.get('compare_markets', ['CH', 'US', 'JP']))} · momentum + seasonal passes"),
            ("5", "Scoring", "Dimensions: momentum · early-market · innovation · gap · commercial fit · source diversity"),
            ("6", "LLM recommendations", f"{len(sorted_opps)} ranked opportunities · {high_conf} high-confidence"),
        ]
        for num, title, detail in steps:
            with st.container(border=True):
                c1, c2 = st.columns([1, 8])
                c1.markdown(f"### {num}")
                c2.markdown(f"**{title}**  \n{detail}")

        st.divider()

        # ── Trend intelligence ────────────────────────────────────────────────
        if insights:
            st.markdown("### Trend intelligence extracted from signals")
            ti_cols = st.columns(2)

            def _chips(items: list, colour: str = "#2d6a4f") -> str:
                return " ".join(
                    f'<span style="background:{colour};color:#fff;padding:2px 8px;border-radius:12px;font-size:0.82em;margin:2px;display:inline-block">{i}</span>'
                    for i in items if i
                )

            with ti_cols[0]:
                if insights.get("features"):
                    st.markdown("**Features / technologies**")
                    st.markdown(_chips(insights["features"], "#1a6b9a"), unsafe_allow_html=True)
                    st.markdown("")
                if insights.get("materials"):
                    st.markdown("**Materials**")
                    st.markdown(_chips(insights["materials"], "#5a3e85"), unsafe_allow_html=True)
                    st.markdown("")
            with ti_cols[1]:
                if insights.get("aesthetics"):
                    st.markdown("**Aesthetics / vibes**")
                    st.markdown(_chips(insights["aesthetics"], "#b5451b"), unsafe_allow_html=True)
                    st.markdown("")
                if insights.get("color_palettes"):
                    st.markdown("**Colour palettes**")
                    st.markdown(_chips(insights["color_palettes"], "#4a7c59"), unsafe_allow_html=True)
                    st.markdown("")
            if insights.get("trends"):
                st.markdown("**Emerging trends**")
                for t in insights["trends"][:6]:
                    st.markdown(f"- {t}")

            st.divider()

        # ── Competitor gap ────────────────────────────────────────────────────
        if gap_brands or gap_cats:
            st.markdown("### Competitor assortment gaps")
            st.caption("Brands and categories seen at competitors but not in client assortment — prime candidates for scouting.")
            g1, g2 = st.columns(2)
            with g1:
                if gap_brands:
                    st.markdown("**Gap brands**")
                    st.dataframe(
                        pd.DataFrame({"Brand": gap_brands}),
                        use_container_width=True, hide_index=True,
                    )
            with g2:
                if gap_cats:
                    st.markdown("**Gap categories**")
                    st.dataframe(
                        pd.DataFrame({"Category": gap_cats}),
                        use_container_width=True, hide_index=True,
                    )
            st.divider()

        # ── Ranked recommendations table ──────────────────────────────────────
        st.markdown("### Ranked recommendations")
        st.caption("Matching data contract: rank · opportunity · type · first market · transferability · workflow · confidence")

        rows = []
        for o in sorted_opps:
            urls = _split_field(o.get("evidence_urls"))
            live_urls = [u for u in urls if u and u != "N/A"]
            rows.append({
                "Rank": o.get("rank", "?"),
                "Opportunity": o.get("opportunity", ""),
                "Type": TYPE_LABELS.get(o.get("opportunity_type", ""), o.get("opportunity_type", "")),
                "First market": o.get("first_observed_market", "—"),
                "Coverage": o.get("coverage_status", "unknown"),
                "Workflow": WORKFLOW_BADGE.get(o.get("recommended_workflow", "monitor"), o.get("recommended_workflow", "")),
                "Confidence": CONFIDENCE_BADGE.get(o.get("confidence", "low"), o.get("confidence", "")),
                "Sources": len(live_urls),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.divider()

        # ── Full detail per recommendation ────────────────────────────────────
        st.markdown("### Full evidence trail")
        for o in sorted_opps:
            rank = o.get("rank", "?")
            name = o.get("opportunity", "")
            conf = o.get("confidence", "low")
            workflow = o.get("recommended_workflow", "monitor")
            with st.expander(
                f"#{rank} · {name} · {WORKFLOW_BADGE.get(workflow, workflow)} · {CONFIDENCE_BADGE.get(conf, conf)}",
                expanded=False,
            ):
                why, evidence = _parse_why_and_evidence(o)
                urls = [u for u in _split_field(o.get("evidence_urls")) if u and u != "N/A"]

                if why:
                    st.markdown(why)

                detail_cols = st.columns(2)
                with detail_cols[0]:
                    st.markdown(f"**Type:** {TYPE_LABELS.get(o.get('opportunity_type',''), o.get('opportunity_type',''))}")
                    st.markdown(f"**First observed:** {o.get('first_observed_market','—')}")
                    st.markdown(f"**Coverage:** {o.get('coverage_status','unknown')}")
                    transfer = o.get("transferability", "")
                    if transfer:
                        st.markdown(f"**DACH transferability:** {transfer}")
                with detail_cols[1]:
                    action = o.get("action") or o.get("recommended_action", "")
                    if action:
                        st.info(f"**Action:** {action}")
                    risks = o.get("risks", "")
                    if risks:
                        st.warning(f"**Risks:** {risks}")

                if evidence:
                    st.markdown("**Evidence**")
                    for b in evidence:
                        st.markdown(f"- {b}")
                if urls:
                    st.markdown("**Sources**")
                    for u in urls:
                        st.markdown(f"- [{u}]({u})")

                for label, key in (("Products", "products"), ("Features", "features"), ("Materials", "materials"), ("Aesthetics", "aesthetics"), ("Colour palettes", "color_palettes")):
                    val = _split_field(o.get(key))
                    if val:
                        st.markdown(f"**{label}:** {', '.join(val)}")

        # ── CSV export ────────────────────────────────────────────────────────
        st.divider()
        rec_path = os.path.join(_PROJECT_ROOT, "ranked_recommendations.csv")
        if os.path.exists(rec_path):
            with open(rec_path, "rb") as _f:
                st.download_button(
                    "Download ranked_recommendations.csv",
                    _f,
                    file_name="ranked_recommendations.csv",
                    mime="text/csv",
                )
