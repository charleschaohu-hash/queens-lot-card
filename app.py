"""Streamlit front end for the Queens lot card generator.

Run locally:  streamlit run app.py
Everything comes from free NYC Open Data endpoints — no API keys, no LLM calls.
"""
import sys
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import lot_card as lc  # noqa: E402

EXAMPLES = [
    "17-08 149th St, Queens, NY",
    "17-16 149th St, Queens, NY",
    "11 Center Dr, Queens, NY",
    "133-25 37th Ave, Queens, NY",
]
REPO = "https://github.com/charleschaohu-hash/queens-lot-card"

st.set_page_config(page_title="Queens Lot Card", page_icon="🏠", layout="centered")

st.title("Queens Lot Card")
st.caption(
    "Type a Queens address and get a one-page investment profile — zoning, buildable "
    "area, subdivision feasibility, ACRIS sales & mortgages, DOB permits, ownership. "
    "Built on free NYC Open Data; every figure links back to its official source. "
    f"[Source code]({REPO})"
)

# ---------- state ----------
ss = st.session_state
ss.setdefault("address", EXAMPLES[0])
ss.setdefault("choice_bbl", None)
ss.setdefault("candidates", None)
ss.setdefault("card", None)        # (address, context)


def _pick_example():
    ss.address = ss.example
    ss.choice_bbl = None
    ss.candidates = None
    ss.card = None


# ---------- input ----------
st.selectbox("Try an example", EXAMPLES, key="example", on_change=_pick_example)
address = st.text_input(
    "Address", key="address",
    help='Queens hyphenated house numbers work as-is, e.g. "17-08 149th St". '
         'Use "Queens, NY" rather than the neighborhood name for fewer ambiguities.',
)
col_run, col_fresh = st.columns([1, 2])
run = col_run.button("Generate card", type="primary", use_container_width=True)
fresh = col_fresh.checkbox("Bypass cache (re-fetch from NYC Open Data)", value=False)

if run:
    ss.choice_bbl = None
    ss.candidates = None
    ss.card = None

# ---------- ambiguity resolver ----------
if ss.candidates:
    st.warning("This address matches several lots with equal confidence. Pick one:")
    labels = [f"BBL {b} — {label}" for b, label in ss.candidates]
    idx = st.radio("Candidates", range(len(labels)), format_func=lambda i: labels[i])
    if st.button("Use this lot"):
        ss.choice_bbl = ss.candidates[idx][0]
        ss.candidates = None
        run = True

# ---------- run pipeline ----------
if run or (ss.choice_bbl and ss.card is None):
    if not address.strip():
        st.error("Enter an address first.")
    else:
        with st.spinner("Querying GeoSearch → MapPLUTO → ACRIS → DOB … (10–40 s)"):
            try:
                c = lc.build_card(address.strip(), fresh=fresh, choice_bbl=ss.choice_bbl)
                ss.card = (address.strip(), c)
            except lc.AmbiguousAddress as e:
                ss.candidates = e.candidates
                st.rerun()
            except lc.LotCardError as e:
                st.error(str(e))
            except requests.RequestException as e:
                st.error(f"NYC Open Data request failed: {e}")

# ---------- output ----------
if ss.card:
    addr, c = ss.card
    html = lc.render_html(c)
    md = lc.render_md(c)
    slug = f"{c['bbl']}_{lc.slugify(addr)}"

    d1, d2 = st.columns(2)
    d1.download_button("Download HTML", html, file_name=f"{slug}.html",
                       mime="text/html", use_container_width=True)
    d2.download_button("Download Markdown", md, file_name=f"{slug}.md",
                       mime="text/markdown", use_container_width=True)

    components.html(html, height=2400, scrolling=True)

    st.caption(
        "Not investment advice. MapPLUTO is a periodic snapshot; ACRIS and DOB update daily. "
        "Zoning rules cover residential R-districts; C/M districts get a flagged, partial card."
    )
