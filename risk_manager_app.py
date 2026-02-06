import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
import os

# ==================================================
# FILE PATH
# ==================================================
JOURNAL_FILE = "journal.csv"
CONTEXT_JOURNAL_FILE = "context_gate_journal.csv"
BACKUP_DIR = "backups"

# ==================================================
# CONFIG
# ==================================================
st.set_page_config(
    page_title="Scalping Risk Manager",
    page_icon="📊",
    layout="centered"
)

st.title("📊 Scalping Risk Manager")
st.caption("Risk-first • Bias Filter • Context-aware Futures")

# ==================================================
# SESSION STATE
# ==================================================
today = date.today().isoformat()

if "journal" not in st.session_state:
    st.session_state.journal = []

if "last_quick_trade_time" not in st.session_state:
    st.session_state.last_quick_trade_time = 0.0

if "active_trade_index" not in st.session_state:
    st.session_state.active_trade_index = None

# ==================================================
# LOAD JOURNAL
# ==================================================
if os.path.exists(JOURNAL_FILE) and not st.session_state.journal:
    st.session_state.journal = pd.read_csv(JOURNAL_FILE).to_dict("records")

# ==================================================
# SAVE & BACKUP
# ==================================================
def save_journal():
    pd.DataFrame(st.session_state.journal).to_csv(JOURNAL_FILE, index=False)

def backup_journal():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    path = f"{BACKUP_DIR}/journal_{today}.csv"
    if not os.path.exists(path):
        pd.DataFrame(st.session_state.journal).to_csv(path, index=False)

# ==================================================
# CONTEXT LINKING
# ==================================================
def get_latest_context(pair, trade_time, max_minutes=30):
    if not os.path.exists(CONTEXT_JOURNAL_FILE):
        return None

    df = pd.read_csv(CONTEXT_JOURNAL_FILE)
    if df.empty:
        return None

    df["datetime_wib"] = pd.to_datetime(df["datetime_wib"])
    trade_time = pd.to_datetime(trade_time)

    df = df[(df["pair"] == pair) & (df["datetime_wib"] <= trade_time)]
    if df.empty:
        return None

    df["delta_min"] = (trade_time - df["datetime_wib"]).dt.total_seconds() / 60
    df = df[df["delta_min"] <= max_minutes]
    if df.empty:
        return None

    return df.sort_values("delta_min").iloc[0]

# ==================================================
# CONSTANTS
# ==================================================
PIN_CODE = "1234"
COOLDOWN_SECONDS = 30
R_OPTIONS = [-1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0]

# ==================================================
# MODE
# ==================================================
mode = st.radio(
    "🎛️ Mode",
    ["📱 Quick Trade (Eksekusi)", "🧠 Normal / Analisis"],
    horizontal=True
)

st.divider()

# ==================================================
# QUICK TRADE MODE
# ==================================================
if mode == "📱 Quick Trade (Eksekusi)":

    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=60 * 1000, key="trade_timer")

    pin = st.text_input("🔐 PIN Quick Trade", type="password")
    if pin != PIN_CODE:
        st.stop()

    if time.time() - st.session_state.last_quick_trade_time < COOLDOWN_SECONDS:
        st.error("⏱️ Cooldown aktif.")
        st.stop()

    pair = st.text_input("Pair (BTCUSDT, SOLUSDT)").upper()
    equity = st.number_input("Equity (USD)", value=2500.0)
    risk_percent = st.number_input("Risk per Trade (%)", value=1.0)
    entry = st.number_input("Entry Price", format="%.4f")
    sl = st.number_input("Stop Loss Price", format="%.4f")
    leverage = st.number_input("Leverage (x)", min_value=1, value=5)

    st.markdown("### 🧠 Bias Checklist")
    c1 = st.checkbox("EMA searah")
    c2 = st.checkbox("Harga dijaga EMA")
    c3 = st.checkbox("Momentum ada")
    c4 = st.checkbox("Market tidak choppy")

    bias_score = sum([c1, c2, c3, c4])
    if bias_score < 3:
        st.error("❌ NO TRADE — Bias belum cukup.")
        st.stop()

    if st.button("⚡ HITUNG & CATAT TRADE", use_container_width=True):

        trade_time = datetime.now().isoformat()
        context = get_latest_context(pair, trade_time)

        # ===== CONTEXT WARNING (NON-BLOCKING) =====
        if context is not None:
            if context["verdict"].startswith("⛔"):
                st.warning("⚠️ Context terakhir menyarankan **TIDAK TRADE**.")
            elif context["verdict"].startswith("⚠️"):
                st.info("ℹ️ Context terakhir status **AMATI SAJA**.")

        risk_usd = equity * (risk_percent / 100)
        sl_dist = abs(entry - sl)
        position_size = (risk_usd * entry) / sl_dist
        margin = position_size / leverage
        direction = "LONG" if entry > sl else "SHORT"

        st.session_state.journal.append({
            "timestamp": trade_time,
            "pair": pair,
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "risk_percent": risk_percent,
            "bias_score": bias_score,
            "position_size": position_size,
            "margin": margin,

            # Context snapshot
            "context_verdict": context["verdict"] if context is not None else None,
            "context_behavior": context["behavior"] if context is not None else None,
            "context_gap_min": round(context["delta_min"], 1) if context is not None else None,

            # Countdown
            "time_eval_min": 30,
            "time_eval_done": False,
            "trade_status": "OPEN",

            "result_r": None,
            "exit_reason": None
        })

        st.session_state.active_trade_index = len(st.session_state.journal) - 1
        st.session_state.last_quick_trade_time = time.time()

        save_journal()
        backup_journal()
        st.success("Trade dicatat.")

    # Countdown
    idx = st.session_state.active_trade_index
    if idx is not None:
        trade = st.session_state.journal[idx]
        if trade["trade_status"] == "OPEN":
            elapsed = int((datetime.now() - datetime.fromisoformat(trade["timestamp"])).total_seconds() / 60)
            st.info(f"⏳ Trade berjalan: {elapsed} menit")

# ==================================================
# NORMAL MODE
# ==================================================
else:
    if not st.session_state.journal:
        st.info("Belum ada trade.")
        st.stop()

    df = pd.DataFrame(st.session_state.journal)
    st.dataframe(df, use_container_width=True)

    st.download_button(
        "⬇️ Download Journal",
        df.to_csv(index=False).encode(),
        "journal.csv",
        "text/csv"
    )
