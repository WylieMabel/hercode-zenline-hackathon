"""
Zenline Opportunity Scout — Streamlit frontend.

Run from project root:
    streamlit run app/streamlit_app.py
"""

import os
import sys

# Make both project root and app/ importable
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_APP_DIR)
sys.path.insert(0, _APP_DIR)
sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd
import streamlit as st

import pipeline_runner
from archive.chatbot.shared import claude_client

st.set_page_config(
    page_title="Zenline Opportunity Scout",
    page_icon="⛰️",
    layout="wide",
)

# ── Session state defaults ───────────────────────────────────────────────────
_DEFAULTS = {
    "pipeline_complete": False,
    "config": {},
    "opportunities": [],
    "sales_summary": "",
    "sales_df": None,
    "messages": [],
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ── Helpers ──────────────────────────────────────────────────────────────────

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
    if "Product Category" in df.columns and "Churn" in df.columns:
        top_churn = df.groupby("Product Category")["Churn"].mean().idxmax()
        rate = df.groupby("Product Category")["Churn"].mean().max()
        lines.append(f"Highest churn category: {top_churn} ({rate:.1%})")
    return "\n".join(lines)


def build_agent_system_prompt() -> str:
    opps = st.session_state.opportunities
    opp_block = ""
    if opps:
        for o in opps:
            opp_block += (
                f"\n{o.get('rank', '?')}. {o.get('opportunity', '')}\n"
                f"   {o.get('description', '')}\n"
                f"   Confidence: {o.get('confidence', '')} | Action: {o.get('action', '')}\n"
            )
    sales = st.session_state.sales_summary

    return f"""\
You are an assortment planning agent for a Swiss outdoor retailer (DACH market).

Your role is to help the merchandising team decide:
- Which products and brands to add, expand, or drop from the assortment
- How to structure price architecture (good / better / best tiers)
- How to respond to emerging market signals
- How to allocate open-to-buy budget across categories

{"Ranked opportunities from the signal pipeline:" + opp_block if opp_block else "No opportunity data loaded yet — run the pipeline first."}

{"Customer data context:" + chr(10) + sales if sales else ""}

Be specific and commercially grounded. Reference the opportunity data and customer metrics when relevant.
Always finish with a concrete next action. Flag where the evidence is weak.
"""


CONFIDENCE_BADGE = {"high": "🟢 High", "medium": "🟡 Medium", "low": "🔴 Low"}


# ── Header ───────────────────────────────────────────────────────────────────
st.title("⛰️ Zenline Opportunity Scout")
st.caption("Swiss outdoor retail · signals → scoring → opportunities → assortment intelligence")

tab_pipeline, tab_opps, tab_agent = st.tabs(["▶ Pipeline", "📊 Opportunities", "💬 Assortment Agent"])


# ── Tab 1: Pipeline ──────────────────────────────────────────────────────────
with tab_pipeline:
    col_form, col_steps = st.columns([1, 1], gap="large")

    with col_form:
        st.subheader("Search Configuration")
        location = st.text_input("Company location", value="Switzerland")
        market = st.text_input("Market / category", value="Outdoor")

        c_min, c_max = st.columns(2)
        with c_min:
            price_min = st.number_input("Min price (CHF)", min_value=0, value=0, step=10)
        with c_max:
            price_max = st.number_input("Max price (CHF)", min_value=0, value=0, step=10)
        price_min = price_min or None
        price_max = price_max or None

        st.divider()
        st.subheader("Sales Data (optional)")
        uploaded = st.file_uploader(
            "Upload company sales CSV",
            type=["csv"],
            help="Compatible with data_generation/fake_data.csv format",
        )
        if uploaded:
            try:
                df = pd.read_csv(uploaded)
                st.session_state.sales_df = df
                st.session_state.sales_summary = summarise_sales(df)
                st.success(f"Loaded {len(df):,} rows")
            except Exception as exc:
                st.error(f"Could not parse CSV: {exc}")

        st.divider()
        run_btn = st.button("▶ Run Pipeline", type="primary", use_container_width=True)

    with col_steps:
        st.subheader("Pipeline Steps")

        if run_btn:
            # Step 1 ─────────────────────────────────────────────────────────
            with st.status("Step 1: Generating search config...", expanded=True) as s1:
                config = pipeline_runner.generate_config(location, market, price_min, price_max)
                st.session_state.config = config
                st.json(config)
                s1.update(label="Step 1: Search config ready ✓", state="complete")

            # Step 2 ─────────────────────────────────────────────────────────
            with st.status("Step 2: Collecting market signals...", expanded=True) as s2:
                ok, msg = pipeline_runner.run_scraper()
                st.code(msg, language=None)
                if ok:
                    s2.update(label="Step 2: Market signals collected ✓", state="complete")
                else:
                    s2.update(label="Step 2: Scraper issue (see output)", state="error")

            # Step 3 ─────────────────────────────────────────────────────────
            with st.status("Step 3: Scoring signals...", expanded=True) as s3:
                ok, msg, scored = pipeline_runner.run_scoring()
                st.write(msg)
                if ok:
                    s3.update(label=f"Step 3: Signals scored ✓ ({len(scored)} rows)", state="complete")
                else:
                    s3.update(label="Step 3: Scoring error", state="error")
                    scored = []

            # Step 4 ─────────────────────────────────────────────────────────
            with st.status("Step 4: Compiling opportunities via LLM...", expanded=True) as s4:
                ok, msg, opps = pipeline_runner.run_compiler(
                    scored, st.session_state.sales_summary
                )
                st.write(msg)
                if ok:
                    st.session_state.opportunities = opps
                    st.session_state.pipeline_complete = True
                    s4.update(label=f"Step 4: {len(opps)} opportunities compiled ✓", state="complete")
                else:
                    s4.update(label="Step 4: Compilation error", state="error")

            if st.session_state.pipeline_complete:
                st.success("Pipeline complete — see the Opportunities tab.")

        elif st.session_state.pipeline_complete:
            st.info("Pipeline already run. Click Run Pipeline to refresh.")
            if st.session_state.config:
                with st.expander("Last config"):
                    st.json(st.session_state.config)
        else:
            st.info("Fill in the configuration and click **Run Pipeline**.")


# ── Tab 2: Opportunities ──────────────────────────────────────────────────────
with tab_opps:
    df = st.session_state.sales_df
    if df is not None:
        st.subheader("Your Sales Snapshot")
        m1, m2, m3, m4 = st.columns(4)
        if "Total Purchase Amount" in df.columns:
            m1.metric("Avg spend", f"CHF {df['Total Purchase Amount'].mean():.0f}")
        if "Churn" in df.columns:
            m2.metric("Churn rate", f"{df['Churn'].mean():.1%}")
        if "Returns" in df.columns:
            m3.metric("Return rate", f"{df['Returns'].mean():.1%}")
        if "Product Category" in df.columns and "Total Purchase Amount" in df.columns:
            top_cat = df.groupby("Product Category")["Total Purchase Amount"].sum().idxmax()
            m4.metric("Top category", top_cat)
        st.divider()

    opps = st.session_state.opportunities
    if not opps:
        st.info("No opportunities yet. Run the pipeline on the **Pipeline** tab.")
    else:
        st.subheader(f"Ranked Opportunities  ({len(opps)} found)")
        for opp in sorted(opps, key=lambda x: x.get("rank", 99)):
            rank = opp.get("rank", "?")
            name = opp.get("opportunity", "Unknown")
            conf = opp.get("confidence", "low")
            badge = CONFIDENCE_BADGE.get(conf, conf)

            with st.expander(f"#{rank}  {name}  ·  {badge}", expanded=(rank == 1)):
                left, right = st.columns([2, 1])
                with left:
                    st.markdown(f"**{opp.get('description', '')}**")

                    evidence = opp.get("evidence") or []
                    if evidence:
                        st.markdown("**Evidence**")
                        for e in evidence:
                            st.markdown(f"- {e}")

                    lead_markets = opp.get("lead_markets") or []
                    if lead_markets:
                        st.markdown(f"**Lead markets:** {', '.join(lead_markets)} — trend appeared there before Switzerland")

                    st.markdown(f"**DACH Transferability:** {opp.get('transferability', '')}")
                    st.markdown(f"**Risks / gaps:** {opp.get('risks', '')}")
                with right:
                    st.markdown(f"**Confidence:** {badge}")
                    st.divider()
                    st.markdown("**Recommended action**")
                    st.info(opp.get("action", ""))


# ── Tab 3: Assortment Agent ──────────────────────────────────────────────────
with tab_agent:
    st.subheader("Assortment Agent")
    if not st.session_state.opportunities:
        st.warning("Run the pipeline first so the agent has opportunity context to work from.")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("Ask about your assortment — e.g. 'What should we prioritise for Q3?'"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        system = build_agent_system_prompt()
        history = st.session_state.messages[:-1]

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                reply = claude_client.chat(system, history, prompt)
            st.write(reply)

        st.session_state.messages.append({"role": "assistant", "content": reply})
