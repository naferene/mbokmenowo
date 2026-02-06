import streamlit as st
import pandas as pd
import requests
import numpy as np
from datetime import datetime
import pytz
import os
import re

# ==================================================
# CONFIG
# ==================================================
BASE_URL = "https://www.okx.com"
JOURNAL_FILE = "context_gate_journal.csv"

st.set_page_config(
    page_title="Context Gate OKX Futures V2",
    page_icon="🧭",
    layout="centered"
)

st.title("🧭 Context Gate — OKX Futures")
st.caption("Context-first • Pair-specific • Bukan sinyal")

# ==================================================
# LABEL TERJEMAHAN (UI)
# ==================================================
LABEL_ID = {
    "ABOVE_USUAL": "Volume di atas kebiasaan",
    "NORMAL": "Normal",
    "BELOW_USUAL": "Volume di bawah kebiasaan",

    "EXPANDING": "Range melebar",
    "COMPRESSED": "Range menyempit",

    "OI_BUILDING": "Posisi sedang dibangun",
    "OI_UNWINDING": "Posisi sedang ditutup",
    "OI_INERT": "Minat stagnan",

    "ACCUMULATION_LIKE": "Indikasi akumulasi",
    "HEALTHY_PARTICIPATION": "Partisipasi sehat",
    "EXIT_LIKE": "Indikasi distribusi / exit",
    "LOW_ENGAGEMENT": "Partisipasi rendah",
    "MIXED": "Perilaku campuran"
}

# ==================================================
# INIT JOURNAL
# ==================================================
if not os.path.exists(JOURNAL_FILE):
    pd.DataFrame(columns=[
        "datetime_wib",
        "pair",
        "session",
        "rv_label",
        "rvol_label",
        "oi_label",
        "behavior",
        "verdict",
        "decision",
        "note"
    ]).to_csv(JOURNAL_FILE, index=False)

# ==================================================
# INPUT PAIR
# ==================================================
pair_raw = st.text_input(
    "Pair Futures (contoh: BTCUSDT, SOLUSDT)",
    value="BTCUSDT"
).upper().strip()

if not re.match(r"^[A-Z0-9]+USDT$", pair_raw):
    st.error("Format pair tidak valid.")
    st.stop()

inst_id = pair_raw.replace("USDT", "") + "-USDT-SWAP"
st.caption(f"Instrumen OKX: `{inst_id}`")

# ==================================================
# OKX API FUNCTIONS
# ==================================================
@st.cache_data(ttl=60)
def get_candles(inst, limit=96):
    r = requests.get(
        f"{BASE_URL}/api/v5/market/candles",
        params={"instId": inst, "bar": "15m", "limit": limit},
        timeout=10
    ).json()
    return r["data"] if r.get("code") == "0" else []

@st.cache_data(ttl=60)
def get_ticker(inst):
    r = requests.get(
        f"{BASE_URL}/api/v5/market/ticker",
        params={"instId": inst},
        timeout=10
    ).json()
    return r["data"][0] if r.get("code") == "0" else None

@st.cache_data(ttl=300)
def get_oi_history(inst, limit=6):
    r = requests.get(
        f"{BASE_URL}/api/v5/public/open-interest-history",
        params={
            "instType": "SWAP",
            "instId": inst,
            "period": "15m",
            "limit": limit
        },
        timeout=10
    ).json()
    if r.get("code") != "0":
        return []
    return r.get("data", [])

# ==================================================
# LOAD DATA
# ==================================================
candles = get_candles(inst_id)
ticker = get_ticker(inst_id)
oi_hist = get_oi_history(inst_id)

if not candles or ticker is None:
    st.error("Data harga tidak tersedia untuk pair ini.")
    st.stop()

# ==================================================
# BUILD CANDLE DF
# ==================================================
df = pd.DataFrame(
    candles,
    columns=["ts","o","h","l","c","vol","volCcy","volQuote","confirm"]
)
df[["h","l","c","volQuote"]] = df[["h","l","c","volQuote"]].astype(float)
df["range"] = df["h"] - df["l"]

# ==================================================
# RELATIVE VOLATILITY (REFINED)
# ==================================================
median_range = np.median(df["range"])
avg_range = df["range"].mean()
rvol = avg_range / median_range if median_range else 1

if rvol > 1.15:
    rvol_label = "EXPANDING"
elif rvol < 0.85:
    rvol_label = "COMPRESSED"
else:
    rvol_label = "NORMAL"

# ==================================================
# RELATIVE VOLUME (REFINED)
# ==================================================
vol_now = float(ticker["volCcy24h"])
median_vol = np.median(df["volQuote"]) * len(df)
rv = vol_now / median_vol if median_vol else 1

if rv > 1.25:
    rv_label = "ABOVE_USUAL"
elif rv < 0.75:
    rv_label = "BELOW_USUAL"
else:
    rv_label = "NORMAL"

# ==================================================
# OI MOMENTUM (DEFENSIVE)
# ==================================================
if oi_hist:
    oi_df = pd.DataFrame(oi_hist)
    oi_df["oi"] = oi_df["oi"].astype(float)
    oi_delta = oi_df["oi"].iloc[0] - oi_df["oi"].iloc[-1]

    if oi_delta > 0:
        oi_label = "OI_BUILDING"
    elif oi_delta < 0:
        oi_label = "OI_UNWINDING"
    else:
        oi_label = "OI_INERT"
else:
    oi_label = "OI_INERT"

# ==================================================
# TIME CONTEXT
# ==================================================
wib = pytz.timezone("Asia/Jakarta")
now_wib = datetime.now(wib)
hour = now_wib.hour

if 7 <= hour < 14:
    session = "Asia"
elif 14 <= hour < 19:
    session = "London"
elif 19 <= hour < 23:
    session = "New York"
else:
    session = "Off-hours"

# ==================================================
# MARKET BEHAVIOR + SANITY CHECK
# ==================================================
if rv_label == "ABOVE_USUAL" and rvol_label == "COMPRESSED" and oi_label == "OI_BUILDING":
    behavior = "ACCUMULATION_LIKE"
elif rv_label == "ABOVE_USUAL" and rvol_label == "EXPANDING" and oi_label == "OI_BUILDING":
    behavior = "HEALTHY_PARTICIPATION"
elif oi_label == "OI_UNWINDING":
    behavior = "EXIT_LIKE"
elif rv_label == "BELOW_USUAL":
    behavior = "LOW_ENGAGEMENT"
else:
    behavior = "MIXED"

# Sanity check: akumulasi tapi range terlalu kecil & OI inert
if behavior == "ACCUMULATION_LIKE" and oi_label == "OI_INERT":
    behavior = "MIXED"

# ==================================================
# VERDICT
# ==================================================
if behavior in ["LOW_ENGAGEMENT", "EXIT_LIKE"]:
    verdict = "⛔ Tidak Layak Ditrade"
elif behavior == "ACCUMULATION_LIKE":
    verdict = "⚠️ Amati Saja"
else:
    verdict = "✅ Layak Dipantau"

# ==================================================
# DISPLAY
# ==================================================
st.subheader("📊 Snapshot Konteks")

st.markdown(f"""
**Pair**: {pair_raw}  
**Session**: {session}  
**Waktu (WIB)**: {now_wib.strftime('%H:%M')}

**Volume**: {LABEL_ID[rv_label]}  
**Volatilitas**: {LABEL_ID[rvol_label]}  
**Open Interest**: {LABEL_ID[oi_label]}  
**Perilaku Pasar**: {LABEL_ID[behavior]}
""")

st.markdown(f"## {verdict}")

# ==================================================
# JOURNAL INPUT
# ==================================================
st.divider()
decision = st.radio("Keputusan", ["SKIPPED", "TAKEN"], horizontal=True)
note = st.text_input("Catatan (opsional)")

if st.button("💾 Simpan ke Jurnal"):
    dfj = pd.read_csv(JOURNAL_FILE)
    dfj.loc[len(dfj)] = [
        now_wib.strftime("%Y-%m-%d %H:%M"),
        pair_raw,
        session,
        rv_label,
        rvol_label,
        oi_label,
        behavior,
        verdict,
        decision,
        note
    ]
    dfj.to_csv(JOURNAL_FILE, index=False)
    st.success("Jurnal tersimpan.")

# ==================================================
# EXPORT
# ==================================================
st.divider()
with open(JOURNAL_FILE, "rb") as f:
    st.download_button(
        "📤 Download context_gate_journal.csv",
        f,
        file_name="context_gate_journal.csv",
        mime="text/csv"
    )

# ==================================================
# GLOSSARY
# ==================================================
with st.expander("📘 Daftar Istilah Context Gate", expanded=False):
    st.markdown("""
**Indikasi akumulasi**  
Volume relatif tinggi, range menyempit, dan Open Interest bertambah → posisi kemungkinan sedang dibangun.

**Partisipasi sehat**  
Volume dan volatilitas berkembang seimbang, pasar aktif dan responsif.

**Partisipasi rendah**  
Minat pasar kecil, pergerakan didominasi noise.

**Indikasi distribusi / exit**  
Open Interest menurun → posisi futures mulai ditutup.

**Amati saja**  
Konteks menarik, tetapi belum ada alasan kuat untuk masuk.
""")
