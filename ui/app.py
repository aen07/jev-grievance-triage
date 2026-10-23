"""Streamlit front end for live runs. Talks to the FastAPI service only (ED-035).

Run:  streamlit run ui/app.py      (API_URL defaults to http://127.0.0.1:8000)
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

import altair as alt
import httpx
import pandas as pd
import streamlit as st

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")
CHANNELS = ["web_form", "email", "hotline_transcript", "letter_ocr"]
GROUPS = {
    "Project": "project_",
    "Issues": "issue_",
    "Safety flags": "flag_",
    "Eligibility": "harm_alleged",
    "Robustness": ("contains_instructions_to_system", "text_is_coherent", "is_english"),
}

st.set_page_config(page_title="Grievance triage", layout="wide")


# ---------------------------------------------------------------- API helpers

def api(method: str, path: str, **kw: Any) -> Any:
    try:
        r = httpx.request(method, f"{API_URL}{path}", timeout=120, **kw)
    except httpx.HTTPError as e:
        st.error(f"Cannot reach the API at {API_URL}: {e}")
        st.stop()
    if r.status_code >= 400:
        st.error(f"API error {r.status_code}: {r.text}")
        st.stop()
    return r.json()


@st.cache_data(ttl=60)
def samples() -> list[dict[str, Any]]:
    return api("GET", "/samples")


def compare(expected: dict[str, Any], out: dict[str, Any]) -> pd.DataFrame:
    """Same conventions as eval/run_eval.py: list = any of, *_include = subset."""
    def ok(e: Any, a: Any) -> bool:
        return a in e if isinstance(e, list) else a == e

    rows = []
    if "status" in expected:
        rows.append(("eligibility.status", expected["status"], out["eligibility"]["status"], ok(expected["status"], out["eligibility"]["status"])))
    if "project_id" in expected:
        rows.append(("eligibility.project_id", expected["project_id"], out["eligibility"]["project_id"], expected["project_id"] == out["eligibility"]["project_id"]))
    if "reasons_include" in expected:
        rows.append(("eligibility.reasons", f"includes {expected['reasons_include']}", out["eligibility"]["reasons"], set(expected["reasons_include"]) <= set(out["eligibility"]["reasons"])))
    if "issues" in expected:
        rows.append(("issues", expected["issues"], out["issues"], set(expected["issues"]) == set(out["issues"])))
    elif "issues_include" in expected:
        rows.append(("issues", f"includes {expected['issues_include']}", out["issues"], set(expected["issues_include"]) <= set(out["issues"])))
    for f, want in expected.get("flags", {}).items():
        rows.append((f"flags.{f}", want, out["flags"][f], out["flags"][f] == want))
    for key in ("urgency", "route_to"):
        if key in expected:
            rows.append((key, expected[key], out[key], ok(expected[key], out[key])))
    if "also_notify" in expected:
        rows.append(("also_notify", expected["also_notify"], out["also_notify"], set(expected["also_notify"]) == set(out["also_notify"])))
    elif "also_notify_include" in expected:
        rows.append(("also_notify", f"includes {expected['also_notify_include']}", out["also_notify"], set(expected["also_notify_include"]) <= set(out["also_notify"])))
    for key in ("redact_identity", "action"):
        if key in expected:
            rows.append((key, expected[key], out[key], out[key] == expected[key]))
    if "review_reasons_include" in expected:
        rows.append(("review_reasons", f"includes {expected['review_reasons_include']}", out["review_reasons"], set(expected["review_reasons_include"]) <= set(out["review_reasons"])))
    df = pd.DataFrame(rows, columns=["field", "expected", "got", "match"])
    df["expected"] = df["expected"].astype(str)
    df["got"] = df["got"].astype(str)
    return df


def noul_table(answers: dict[str, Any], th: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for qid, a in answers.items():
        if a.get("type") != "noul":
            continue
        group = next((g for g, pre in GROUPS.items() if (qid in pre if isinstance(pre, tuple) else qid.startswith(pre))), "Other")
        rows.append({"group": group, "question": qid, "p_yes": a["noul"]})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- sidebar

health = api("GET", "/health")
with st.sidebar:
    st.subheader("Service")
    if health["jev_ready"]:
        st.success(f"API OK · Jev ready ({health['cache_mode']} mode)")
    else:
        st.error(f"Jev not ready: {health['error']}")
    st.caption(API_URL)
    st.markdown(
        f"- Model pinned: `{health['model_pinned']}`\n"
        f"- Policy: `{health['policy_version']}`\n"
        f"- Thresholds: `{health['thresholds_version']}`\n"
        f"- Questions: `{health['questions_version']}` ({health['n_questions']} per request)"
    )
    if st.button("Reload thresholds.yaml"):
        res = api("POST", "/admin/reload-thresholds")
        st.toast(f"Thresholds now {res['thresholds_version']}")
        st.rerun()
    with st.expander("Project registry"):
        st.dataframe(pd.DataFrame(api("GET", "/config")["registry"]), hide_index=True)

st.title("Grievance triage")
st.caption("Jev answers typed questions as probabilities; policy code (P1–P8) makes every decision. No LLM can change the outcome.")

single, batch = st.tabs(["Single grievance", "Batch"])

# ---------------------------------------------------------------- single

with single:
    cases = samples()
    labels = ["Custom"] + [f"{c['input']['grievance_id']} · {', '.join(c['tags'][:3])}" for c in cases]
    # deep link: ?case=<grievance_id>&run=1 preselects a test case and runs it (demos, README screenshots)
    qp = st.query_params
    ids = [c["input"]["grievance_id"] for c in cases]
    default = ids.index(qp["case"]) + 1 if qp.get("case") in ids else 1
    pick = st.selectbox("Start from a labelled test case, or write your own", labels, index=default)
    case = cases[labels.index(pick) - 1] if pick != "Custom" else None
    src = case["input"] if case else {"grievance_id": "G-LIVE-0001", "received_at": date.today().isoformat(), "channel": "web_form", "text": ""}

    c1, c2, c3 = st.columns([2, 1, 1])
    gid = c1.text_input("grievance_id", src["grievance_id"], key=f"gid-{pick}")
    received = c2.date_input("received_at", date.fromisoformat(src["received_at"]), key=f"rec-{pick}")
    channel = c3.selectbox("channel", CHANNELS, index=CHANNELS.index(src["channel"]), key=f"ch-{pick}")
    text = st.text_area("text", src["text"], height=160, key=f"txt-{pick}")
    if case and case.get("note"):
        st.caption(f"Test-case note: {case['note']}")
    with_llm = st.checkbox("Add LLM acknowledgment letter / reviewer summary (labelled, after the decision)")

    auto = qp.get("run") == "1" and st.session_state.get("auto_ran") != pick
    if st.button("Run triage", type="primary") or auto:
        st.session_state["auto_ran"] = pick
        payload = {"grievance_id": gid, "received_at": received.isoformat(), "channel": channel, "text": text}
        with st.spinner("Asking Jev…"):
            st.session_state["result"] = api("POST", "/triage", json=payload, params={"with_llm": with_llm})
            st.session_state["result_case"] = case if case and text == case["input"]["text"] else None

    out = st.session_state.get("result")
    if out:
        st.divider()
        if out["action"] == "human_review":
            st.warning(f"**HUMAN REVIEW** → {out['route_to']}  ·  reasons: {', '.join(out['review_reasons'])}")
        else:
            st.success(f"**AUTO ROUTE** → {out['route_to']}")

        m = st.columns(4)
        m[0].metric("Eligibility", out["eligibility"]["status"])
        m[1].metric("Project", out["eligibility"]["project_id"] or "—")
        m[2].metric("Urgency", out["urgency"])
        m[3].metric("Redact identity", "yes" if out["redact_identity"] else "no")
        st.markdown(f"**Route to:** `{out['route_to']}`")

        l, r = st.columns(2)
        with l:
            st.markdown("**Issues:** " + (", ".join(f"`{i}`" for i in out["issues"]) or "—"))
            st.markdown("**Also notify:** " + (", ".join(f"`{u}`" for u in out["also_notify"]) or "—"))
            st.markdown("**Eligibility reasons:** " + (", ".join(f"`{x}`" for x in out["eligibility"]["reasons"]) or "—"))
        with r:
            st.markdown("**Flags:** " + "  ".join(f"{'🔴' if v else '⚪'} `{k}`" for k, v in out["flags"].items()))
            a = out["audit"]
            st.caption(f"model `{a['model']}` · {a['latency_ms']} ms · {a['input_tokens']} input tokens · "
                       f"attempts {a['jev_attempts']} · cache {'hit' if a['cache_hit'] else 'miss'}")

        exp_case = st.session_state.get("result_case")
        if exp_case:
            df = compare(exp_case["expected"], out)
            n_ok = int(df["match"].sum())
            st.subheader(f"Expected vs got: {n_ok}/{len(df)} fields match")
            st.dataframe(df, hide_index=True, use_container_width=True)

        answers = out["audit"]["jev_answers"]
        if answers:
            st.subheader("Raw Jev answers")
            th = out["audit"]["thresholds"]
            lines = {  # decision thresholds drawn on each chart (see config/thresholds.yaml)
                "Project": [th["project"]["match"]],
                "Issues": [th["issue"]["no_at"], th["issue"]["yes_at"]],
                "Safety flags": [th["safety"]["sea_sh"]["review_low"], th["safety"]["sea_sh"]["flag_at"]],
                "Eligibility": [th["harm_alleged"]["no_at"], th["harm_alleged"]["yes_at"]],
                "Robustness": [0.5],
            }
            st.caption("Fixed 0–1 scale. Dashed lines = decision thresholds (between two lines = uncertain band → review).")
            nt = noul_table(answers, th)
            for group in GROUPS:
                sub = nt[nt["group"] == group]
                if sub.empty:
                    continue
                bars = alt.Chart(sub).mark_bar(size=16).encode(
                    x=alt.X("p_yes:Q", scale=alt.Scale(domain=[0, 1]), title="p(yes)"),
                    y=alt.Y("question:N", sort=None, title=None, axis=alt.Axis(labelOverlap=False, labelLimit=260)),
                    tooltip=["question", alt.Tooltip("p_yes:Q", format=".2f")],
                )
                labels = bars.mark_text(align="left", dx=3).encode(text=alt.Text("p_yes:Q", format=".2f"))
                rules = alt.Chart(pd.DataFrame({"t": lines[group]})).mark_rule(strokeDash=[4, 3], color="gray").encode(x="t:Q")
                st.caption(group)
                st.altair_chart((bars + labels + rules).properties(height={"step": 28}), use_container_width=True)
            u = answers["urgency"]
            levels = [u["legend"][k].split(":")[0] for k in sorted(u["probabilities"], key=int)]
            udf = pd.DataFrame({"level": levels, "p": [u["probabilities"][k] for k in sorted(u["probabilities"], key=int)]})
            st.caption(f"Urgency score (confidence {u['confidence']:.2f}; floors from P4 applied in code afterwards)")
            st.altair_chart(alt.Chart(udf).mark_bar().encode(
                x=alt.X("level:N", sort=levels, title=None), y=alt.Y("p:Q", scale=alt.Scale(domain=[0, 1]))
            ).properties(height=180), use_container_width=True)

        if out.get("llm_outputs"):
            with st.expander("LLM outputs (labelled; not used in the decision)", expanded=True):
                st.json(out["llm_outputs"])
        with st.expander("Full JSON output"):
            st.code(json.dumps(out, indent=2), language="json")

# ---------------------------------------------------------------- batch

with batch:
    st.write("Run the whole labelled test set, or upload your own JSONL (one grievance per line).")
    up = st.file_uploader("JSONL file", type=["jsonl", "txt"])
    run_all = st.button("Run full test set") or (qp.get("batch") == "1" and not st.session_state.get("batch_auto"))
    if run_all:
        st.session_state["batch_auto"] = True
    rows: list[dict[str, Any]] | None = None
    expected: dict[str, dict] = {}
    if run_all:
        cs = samples()
        rows = [c["input"] for c in cs]
        expected = {c["input"]["grievance_id"]: c["expected"] for c in cs}
    elif up is not None and st.button("Run uploaded file"):
        rows = [json.loads(l) for l in up.getvalue().decode("utf-8").splitlines() if l.strip()]

    if rows:
        with st.spinner(f"Triaging {len(rows)} grievances…"):
            outs = api("POST", "/triage/batch", json=rows)
        table = pd.DataFrame([{
            "id": o["grievance_id"], "action": o["action"], "status": o["eligibility"]["status"],
            "project": o["eligibility"]["project_id"], "urgency": o["urgency"], "route_to": o["route_to"],
            "flags": ", ".join(k for k, v in o["flags"].items() if v), "review_reasons": ", ".join(o["review_reasons"]),
            "all_expected_match": bool(compare(expected[o["grievance_id"]], o)["match"].all()) if o["grievance_id"] in expected else None,
            "latency_ms": o["audit"]["latency_ms"],
        } for o in outs])
        k = st.columns(4)
        k[0].metric("Grievances", len(outs))
        k[1].metric("Human review", f"{(table['action'] == 'human_review').mean():.0%}")
        if expected:
            k[2].metric("All fields match", f"{table['all_expected_match'].mean():.0%}")
        k[3].metric("p50 latency", f"{table['latency_ms'].median():.0f} ms")
        st.dataframe(table, hide_index=True, use_container_width=True)
        st.download_button("Download outputs (JSONL)", "\n".join(json.dumps(o) for o in outs), "triage_outputs.jsonl")
