"""
Zenline Opportunity Scout — Streamlit frontend.

Run from project root:
    streamlit run app/streamlit_app.py
"""

import os
import sys

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_APP_DIR)
sys.path.insert(0, _APP_DIR)
sys.path.insert(0, _PROJECT_ROOT)

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

tab_pipeline, tab_opps = st.tabs(["▶ Pipeline", "📊 Opportunities"])

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
