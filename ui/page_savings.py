"""«Как сэкономить»: разделы из savings.sections() — тот же текст и цифры, что на сайте."""
import pandas as pd
import streamlit as st

import savings


@st.cache_data
def _data():
    return savings.compute()


def _md_cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def block(b):
    t = b["t"]
    if t == "p":
        st.markdown(b["text"])
    elif t == "list":
        st.markdown("\n".join(f"- {x}" for x in b["items"]))
    elif t == "steps":
        st.markdown("\n".join(f"{i}. **{x['title']}** — {x['text']}" for i, x in enumerate(b["items"], 1)))
    elif t == "table":
        if b.get("caption"):
            st.caption(b["caption"])
        head = "| " + " | ".join(_md_cell(h) for h in b["head"]) + " |"
        align = "|" + "|".join("---:" if i in b.get("num", []) else "---" for i in range(len(b["head"]))) + "|"
        rows = ["| " + " | ".join(_md_cell(c) for c in r) + " |" for r in b["rows"]]
        st.markdown("\n".join([head, align] + rows))
    elif t == "figures":
        cols = st.columns(len(b["items"]))
        for c, (label, value) in zip(cols, b["items"]):
            c.metric(label, value)
    elif t == "note":
        st.caption(b["text"])
    elif t == "warn":
        st.warning(b["text"])


def render():
    d = _data()
    st.title("Как сэкономить")
    secs = d["sections"]
    st.markdown("  \n".join(f"{i}. [{s['title']}](#{s['id']})" for i, s in enumerate(secs, 1)))
    for s in secs:
        st.header(s["title"], anchor=s["id"], divider="gray")
        for b in s["blocks"]:
            block(b)
    st.caption(d["footer"])


if __name__ == "__main__":   # быстрый просмотр текста без Streamlit
    print(pd.json_normalize(savings.compute()["sections"])[["id", "title"]])
