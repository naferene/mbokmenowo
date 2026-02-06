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
st.caption("Filter konteks • Pair-specific • Bukan sinyal")

# ==================================================
# LABEL TERJEMAHAN
# ==================================================
LABEL_ID = {
    "ABOVE_USUAL": "Volume di atas kebiasaan",
    "NORMAL": "Normal",
    "BELOW_USUAL": "Volume di bawah kebiasaan",
    "EXPANDING": "Range melebar",
    "COMPRESSED": "Range menyempit",
    "BUILDING": "Posisi sedang dibangun",
    "INERT": "Minat stagnan",
    "UNWINDING": "Posisi ditutup",
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
        "datetime_wib","pair","rv_label","rvol_label",
        "oi_momentum","behavior","verdict","decision"
    ]).to_csv(JOURNAL_FILE, index=False)

# ==================================================
# INPUT PAIR
# ==================================================
pair_raw = st.text_input("Pair Futures (BTCUSDT, SOLUSDT)", "BTCUSDT").upper()
if not re.match(r"^[A-Z0-9]+USDT$", pair_raw):
    st.error("Format pair tidak valid.")
    st.stop()

inst_id = pair_raw.replace("USDT", "") + "-USDT-SWAP"

# ==================================================
# API FUNCTIONS
# ==================================================
@st.cache_data(ttl=60)
def get_candles(inst):
    r = requests.get(
        f"{BASE_URL}/api/v5/market/candles",
        params={"instId": inst, "bar": "15m", "limit": 96}
    ).json()
    return r["data"]

@st.cache_data(ttl=60)
def get_ticker(inst):
    r = requests.get(
        f"{BASE_URL}/api/v5/market/ticker",
        params={"instId": inst}
    ).json()
    return r["data"][0]

# ==================================================
# LOAD DATA
# ==================================================
candles = get_candles(inst_id)
ticker = get_ticker(inst_id)

df = pd.DataFrame(candles, columns=["ts","o","h","l","c","vol","volCcy","volQuote","confirm"])
df[["h","l","c","volQuote"]] = df[["h","l","c","volQuote"]].astype(float)
df["range"] = df["h"] - df["l"]

# ==================================================
# METRICS
# ==================================================
median_range = np.median(df["range"])
avg_range = df["range"].mean()
rvol = avg_range / median_range if median_range else 1

rvol_label = "EXPANDING" if rvol > 1.2 else "COMPRESSED" if rvol < 0.8 else "NORMAL"

vol_now = float(ticker["volCcy24h"])
median_vol = np.median(df["volQuote"]) * 96
rv = vol_now / median_vol if median_vol else 1

rv_label = "ABOVE_USUAL" if rv > 1.3 else "BELOW_USUAL" if rv < 0.8 else "NORMAL"

oi_momentum = "BUILDING" if rv > 1 and rvol < 1 else "INERT"

# ==================================================
# BEHAVIOR
# ==================================================
if rv_label == "ABOVE_USUAL" and rvol_label == "COMPRESSED":
    behavior = "ACCUMULATION_LIKE"
elif rv_label == "ABOVE_USUAL" and rvol_label == "EXPANDING":
    behavior = "HEALTHY_PARTICIPATION"
elif rv_label == "BELOW_USUAL":
    behavior = "LOW_ENGAGEMENT"
else:
    behavior = "MIXED"

# ==================================================
# VERDICT
# ==================================================
if behavior in ["LOW_ENGAGEMENT"]:
    verdict = "⛔ Tidak Layak Ditrade"
elif behavior == "ACCUMULATION_LIKE":
    verdict = "⚠️ Amati Saja"
else:
    verdict = "✅ Layak Dipantau"

# ==================================================
# TIME
# ==================================================
now_wib = datetime.now(pytz.timezone("Asia/Jakarta"))

# ==================================================
# DISPLAY
# ==================================================
st.subheader("📊 Snapshot Konteks")

st.markdown(f"""
**Pair**: {pair_raw}  
**Waktu (WIB)**: {now_wib.strftime('%H:%M')}

**Volume**: {LABEL_ID[rv_label]}  
**Volatilitas**: {LABEL_ID[rvol_label]}  
**Open Interest**: {LABEL_ID[oi_momentum]}  
**Perilaku Pasar**: {LABEL_ID[behavior]}
""")

st.markdown(f"## {verdict}")

# ==================================================
# JOURNAL
# ==================================================
decision = st.radio("Keputusan", ["SKIPPED", "TAKEN"], horizontal=True)

if st.button("💾 Simpan ke Jurnal"):
    dfj = pd.read_csv(JOURNAL_FILE)
    dfj.loc[len(dfj)] = [
        now_wib.strftime("%Y-%m-%d %H:%M"),
        pair_raw,
        rv_label,
        rvol_label,
        oi_momentum,
        behavior,
        verdict,
        decision
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
        file_name="context_gate_journal.csv"
    )

# ==================================================
# GLOSSARY
# ==================================================
with st.expander("📘 Daftar Istilah", expanded=False):
    st.markdown("""
**Indikasi akumulasi**  
Volume meningkat, range menyempit → posisi kemungkinan dibangun.

**Partisipasi sehat**  
Volume dan volatilitas berkembang seimbang.

**Partisipasi rendah**  
Minat pasar kecil, noise dominan.

**Amati saja**  
Belum saatnya masuk, tunggu konfirmasi.
""")
