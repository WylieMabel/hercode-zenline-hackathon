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

import pandas as pd
import streamlit as st

import pipeline_runner
from compiler import load_recommendations
from chatbot.shared import claude_client

st.set_page_config(
    page_title="Zenline Opportunity Scout",
    page_icon="⛰️",
    layout="wide",
)

_DEFAULTS = {
    "pipeline_complete": False,
    "config": {},
    "opportunities": [],
    "sales_summary": "",
    "sales_df": None,
    "messages": [],
    "gap_hints": {},
    "insights": {},
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# Load persisted recommendations on startup
if not st.session_state.opportunities:
    persisted = load_recommendations()
    if persisted:
        st.session_state.opportunities = persisted


def summarise_sales(df: pd.DataFrame) -> str:
    lines = []
    if "Product Category" in df.columns and "Total Purchase Amount" in df.columns:
        top = (
            df.groupby("Product Category")["Total Purchase Amount"]
            .sum().sort_values(ascending=False).head(3).index.tolist()
        )
        lines.append(f"Top revenue categories: {', '.join(top)}")
    if "Churn" in df.columns:
        lines.append(f"Overall churn rate: {df['Churn'].mean():.1%}")
    if "Returns" in df.columns:
        lines.append(f"Overall return rate: {df['Returns'].mean():.1%}")
    if "Total Purchase Amount" in df.columns:
        lines.append(f"Average transaction value: CHF {df['Total Purchase Amount'].mean():.2f}")
    return "\n".join(lines)


def build_agent_system_prompt() -> str:
    opps = st.session_state.opportunities
    opp_block = ""
    if opps:
        for o in opps[:5]:
            opp_block += (
                f"\n{o.get('rank', '?')}. {o.get('opportunity', '')}\n"
                f"   {o.get('description', o.get('evidence_summary', ''))}\n"
                f"   Workflow: {o.get('recommended_workflow', '')} | Action: {o.get('action', o.get('recommended_action', ''))}\n"
            )
    sales = st.session_state.sales_summary
    return f"""\
You are an assortment planning agent for a Swiss outdoor retailer (DACH market).
{"Ranked opportunities:" + opp_block if opp_block else "No opportunities loaded."}
{"Customer data:" + chr(10) + sales if sales else ""}
Be specific and commercially grounded. Flag weak evidence.
"""


CONFIDENCE_BADGE = {"high": "🟢 High", "medium": "🟡 Medium", "low": "🔴 Low"}
WORKFLOW_BADGE = {"launch": "🚀 Launch", "buy": "🛒 Buy", "test": "🧪 Test", "monitor": "👀 Monitor"}


st.title("⛰️ Zenline Opportunity Scout")
st.caption("Six-step pipeline: competitors → trends → regional → scoring → recommendations")

tab_pipeline, tab_opps, tab_agent = st.tabs(["▶ Pipeline", "📊 Opportunities", "💬 Assortment Agent"])

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

        st.divider()
        uploaded = st.file_uploader("Upload company sales CSV (optional)", type=["csv"])
        if uploaded:
            try:
                df = pd.read_csv(uploaded)
                st.session_state.sales_df = df
                st.session_state.sales_summary = summarise_sales(df)
                st.success(f"Loaded {len(df):,} rows")
            except Exception as exc:
                st.error(f"Could not parse CSV: {exc}")

        run_btn = st.button("▶ Run Pipeline", type="primary", use_container_width=True)

    with col_steps:
        st.subheader("Pipeline Steps")

        if run_btn:
            with st.status("Step 1: Finding competitor products...", expanded=True) as s1:
                config = pipeline_runner.generate_config(
                    location, market, client_company, price_min, price_max, time_horizon
                )
                st.session_state.config = config
                ok, msg, products, hints = pipeline_runner.run_competitors(config)
                st.write(msg)
                st.session_state.gap_hints = hints
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

            with st.status("Step 2b: Extracting trend facets...", expanded=True) as s2b:
                ok, msg, insights = pipeline_runner.run_trend_extraction(config)
                st.write(msg)
                st.session_state.insights = insights
                if insights:
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
                    scored, st.session_state.sales_summary, insights, hints
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
    df = st.session_state.sales_df
    if df is not None:
        st.subheader("Your Sales Snapshot")
        m1, m2, m3 = st.columns(3)
        if "Total Purchase Amount" in df.columns:
            m1.metric("Avg spend", f"CHF {df['Total Purchase Amount'].mean():.0f}")
        if "Churn" in df.columns:
            m2.metric("Churn rate", f"{df['Churn'].mean():.1%}")
        if "Returns" in df.columns:
            m3.metric("Return rate", f"{df['Returns'].mean():.1%}")
        st.divider()

    opps = st.session_state.opportunities
    if not opps:
        st.info("No opportunities yet. Run the pipeline on the **Pipeline** tab.")
    else:
        st.subheader(f"Ranked Opportunities ({len(opps)} found)")
        for opp in sorted(opps, key=lambda x: int(x.get("rank", 99) or 99)):
            rank = opp.get("rank", "?")
            name = opp.get("opportunity", "Unknown")
            conf = opp.get("confidence", "low")
            workflow = opp.get("recommended_workflow", "monitor")
            badge = CONFIDENCE_BADGE.get(conf, conf)
            wf = WORKFLOW_BADGE.get(workflow, workflow)

            with st.expander(f"#{rank}  {name}  ·  {badge}  ·  {wf}", expanded=(str(rank) == "1")):
                left, right = st.columns([2, 1])
                with left:
                    desc = opp.get("description") or opp.get("evidence_summary", "")
                    st.markdown(f"**{desc}**")

                    evidence = opp.get("evidence") or []
                    if evidence:
                        st.markdown("**Evidence**")
                        for e in evidence:
                            st.markdown(f"- {e}")

                    urls = opp.get("evidence_urls") or []
                    if isinstance(urls, str) and urls:
                        urls = [u.strip() for u in urls.split(";")]
                    if urls:
                        st.markdown("**Sources**")
                        for u in urls:
                            if u and u != "N/A":
                                st.markdown(f"- [{u}]({u})")

                    for label, key in (
                        ("Products", "products"), ("Features", "features"),
                        ("Materials", "materials"), ("Aesthetics", "aesthetics"),
                        ("Colour palettes", "color_palettes"),
                    ):
                        val = opp.get(key, [])
                        if isinstance(val, str) and val:
                            val = [v.strip() for v in val.split(";") if v.strip()]
                        if val:
                            st.markdown(f"**{label}:** {', '.join(val)}")

                    gap = opp.get("competitor_gap", "")
                    if gap:
                        st.markdown(f"**Competitor gap:** {gap}")
                    st.markdown(f"**DACH transferability:** {opp.get('transferability', '')}")
                    st.markdown(f"**Risks:** {opp.get('risks', '')}")
                with right:
                    st.markdown(f"**Confidence:** {badge}")
                    st.markdown(f"**Workflow:** {wf}")
                    st.markdown(f"**First market:** {opp.get('first_observed_market', 'N/A')}")
                    st.markdown(f"**Coverage:** {opp.get('coverage_status', 'unknown')}")
                    st.divider()
                    action = opp.get("action") or opp.get("recommended_action", "")
                    st.markdown("**Recommended action**")
                    st.info(action)

with tab_agent:
    st.subheader("Assortment Agent")
    if not st.session_state.opportunities:
        st.warning("Run the pipeline first.")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("Ask about your assortment..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                reply = claude_client.chat(build_agent_system_prompt(), st.session_state.messages[:-1], prompt)
            st.write(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
