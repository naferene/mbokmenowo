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
    page_title="🧭 Context Gate — OKX Futures",
    page_icon="🧭",
    layout="centered"
)

st.title("🧭 Context Gate — OKX Futures")
st.caption("Context-first • Pair-specific • Bukan sinyal entry")

# ==================================================
# EXPECTED JOURNAL SCHEMA (ANTI REGRESI)
# ==================================================
EXPECTED_COLUMNS = [
    "datetime_wib",
    "pair",
    "inst_id",
    "session",
    "rv_label",
    "rvol_label",
    "oi_label",
    "behavior",
    "verdict",
    "decision",
    "note"
]

# ==================================================
# INIT / VALIDATE JOURNAL
# ==================================================
if not os.path.exists(JOURNAL_FILE):
    pd.DataFrame(columns=EXPECTED_COLUMNS).to_csv(JOURNAL_FILE, index=False)
else:
    df_existing = pd.read_csv(JOURNAL_FILE)
    if list(df_existing.columns) != EXPECTED_COLUMNS:
        backup_name = JOURNAL_FILE.replace(
            ".csv",
            f"_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        df_existing.to_csv(backup_name, index=False)
        pd.DataFrame(columns=EXPECTED_COLUMNS).to_csv(JOURNAL_FILE, index=False)

# ==================================================
# LABEL TRANSLATION (UI ONLY)
# ==================================================
LABEL_ID = {
    "ABOVE_USUAL": "Volume di atas kebiasaan",
    "NORMAL": "Volume normal",
    "BELOW_USUAL": "Volume di bawah kebiasaan",

    "EXPANDING": "Range melebar",
    "COMPRESSED": "Range menyempit",
    "RANGE_NORMAL": "Range normal",

    "OI_BUILDING": "Posisi futures sedang dibangun",
    "OI_UNWINDING": "Posisi futures sedang ditutup",
    "OI_INERT": "Minat futures stagnan",

    "ACCUMULATION_LIKE": "Indikasi akumulasi",
    "HEALTHY_PARTICIPATION": "Partisipasi sehat",
    "EXIT_LIKE": "Indikasi distribusi / exit",
    "LOW_ENGAGEMENT": "Partisipasi rendah",
    "MIXED": "Perilaku campuran"
}

# ==================================================
# PAIR INPUT (DISERDERHANAKAN)
# ==================================================
base_asset = st.text_input(
    "Pair Futures (cukup simbol dasar, contoh: BTC, ETH, SOL)",
    value="BTC"
).upper().strip()

if not re.match(r"^[A-Z]{2,10}$", base_asset):
    st.error("Format pair tidak valid.")
    st.stop()

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
        params={"instId": inst, "period": "15m", "limit": limit},
        timeout=10
    ).json()
    return r["data"] if r.get("code") == "0" else []

# ==================================================
# INSTRUMENT FALLBACK LOGIC
# ==================================================
inst_candidates = [
    f"{base_asset}-USDT-SWAP",
    f"{base_asset}-USD-SWAP"
]

candles = ticker = oi_hist = None
inst_used = None

for inst in inst_candidates:
    c = get_candles(inst)
    t = get_ticker(inst)
    oi = get_oi_history(inst)

    if c and t and oi:
        candles, ticker, oi_hist = c, t, oi
        inst_used = inst
        break

if candles is None:
    st.error("❌ Data market tidak tersedia atau OI tidak lengkap untuk pair ini.")
    st.stop()

st.caption(f"Instrumen OKX yang digunakan: `{inst_used}`")

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
# RELATIVE VOLATILITY
# ==================================================
median_range = np.median(df["range"])
avg_range = df["range"].mean()
rvol_ratio = avg_range / median_range if median_range else 1.0

if rvol_ratio > 1.2:
    rvol_label = "EXPANDING"
elif rvol_ratio < 0.8:
    rvol_label = "COMPRESSED"
else:
    rvol_label = "RANGE_NORMAL"

# ==================================================
# RELATIVE VOLUME
# ==================================================
vol_24h = float(ticker["volCcy24h"])
median_vol = np.median(df["volQuote"]) * len(df)
rv_ratio = vol_24h / median_vol if median_vol else 1.0

if rv_ratio > 1.3:
    rv_label = "ABOVE_USUAL"
elif rv_ratio < 0.8:
    rv_label = "BELOW_USUAL"
else:
    rv_label = "NORMAL"

# ==================================================
# OPEN INTEREST MOMENTUM
# ==================================================
oi_df = pd.DataFrame(oi_hist)
oi_df["oi"] = oi_df["oi"].astype(float)

oi_delta = oi_df["oi"].iloc[0] - oi_df["oi"].iloc[-1]

if oi_delta > 0:
    oi_label = "OI_BUILDING"
elif oi_delta < 0:
    oi_label = "OI_UNWINDING"
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
# MARKET BEHAVIOR
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
st.subheader("📊 Kondisi Pasar Saat Ini")
st.markdown(f"""
**Pair** : {base_asset}  
**Instrumen** : {inst_used}  
**Session** : {session}  
**WIB** : {now_wib.strftime('%H:%M')}

• **Volume** : {LABEL_ID[rv_label]}  
• **Volatilitas** : {LABEL_ID[rvol_label]}  
• **Open Interest** : {LABEL_ID[oi_label]}
""")

st.subheader("🧠 Interpretasi Perilaku Pasar")
st.markdown(f"**{LABEL_ID[behavior]}**")

st.subheader("🎯 Sikap yang Disarankan")
st.markdown(f"### {verdict}")

# ==================================================
# JOURNAL INPUT
# ==================================================
st.divider()
st.subheader("📝 Jurnal Keputusan")

decision = st.radio("Keputusan", ["SKIPPED", "TAKEN"], horizontal=True)
note = st.text_input("Catatan (opsional)")

if st.button("💾 Simpan ke Jurnal"):
    dfj = pd.read_csv(JOURNAL_FILE)
    dfj.loc[len(dfj)] = [
        now_wib.strftime("%Y-%m-%d %H:%M"),
        base_asset,
        inst_used,
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
### Kondisi Pasar Saat Ini

**Volume di atas kebiasaan**  
Aktivitas transaksi lebih ramai dari kondisi normal pair tersebut.

**Volume normal**  
Aktivitas pasar berada pada tingkat wajar.

**Volume di bawah kebiasaan**  
Minat pasar rendah, rawan noise dan false move.

**Range melebar**  
Harga bergerak lebih luas dari biasanya, volatilitas meningkat.

**Range menyempit**  
Harga bergerak sempit, sering menandakan fase konsolidasi.

**Range normal**  
Pergerakan harga stabil dan proporsional.

**Posisi futures sedang dibangun**  
Open Interest meningkat → partisipan menambah posisi.

**Posisi futures sedang ditutup**  
Open Interest menurun → posisi lama dilepas.

**Minat futures stagnan**  
Tidak ada perubahan signifikan pada Open Interest.

---

### Interpretasi Perilaku Pasar

**Indikasi akumulasi**  
Volume tinggi + range menyempit + OI naik → posisi dibangun, belum dilepas.

**Partisipasi sehat**  
Volume dan volatilitas naik seimbang → pasar aktif dan responsif.

**Indikasi distribusi / exit**  
OI turun → rawan whipsaw dan fake move.

**Partisipasi rendah**  
Minat pasar kecil → edge rendah.

**Perilaku campuran**  
Tidak ada konteks dominan, tunggu kejelasan.
""")