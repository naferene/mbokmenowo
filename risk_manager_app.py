import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
import os
from streamlit_autorefresh import st_autorefresh

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
st.caption("Risk-first • Bias Filter • Context-aware • Multi Active Trade")

# ==================================================
# SESSION STATE
# ==================================================
today = date.today().isoformat()

if "journal" not in st.session_state:
    st.session_state.journal = []

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

    st_autorefresh(interval=60 * 1000, key="trade_timer")

    pin = st.text_input("🔐 PIN Quick Trade", type="password")
    if pin != PIN_CODE:
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

    # ================= ENTRY =================
    if st.button("⚡ HITUNG & CATAT TRADE", use_container_width=True):

        trade_time = datetime.now().isoformat()
        context = get_latest_context(pair, trade_time)

        if context is not None:
            if context["verdict"].startswith("⛔"):
                st.warning("⚠️ Context terakhir: **TIDAK LAYAK DITRADE**")
            elif context["verdict"].startswith("⚠️"):
                st.info("ℹ️ Context terakhir: **AMATI SAJA**")

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

            "context_verdict": context["verdict"] if context is not None else None,
            "context_behavior": context["behavior"] if context is not None else None,
            "context_gap_min": round(context["delta_min"], 1) if context is not None else None,

            "time_eval_min": 30,
            "time_eval_done": False,
            "trade_status": "OPEN",

            "result_r": None,
            "exit_reason": None
        })

        save_journal()
        backup_journal()
        st.success("Trade dicatat.")

    # ================= ACTIVE TRADES PANEL =================
    st.divider()
    st.subheader("🟢 Trade Aktif (Maks. 5)")

    open_trades = [
        (i, t) for i, t in enumerate(st.session_state.journal)
        if t["trade_status"] == "OPEN"
    ][:5]

    if not open_trades:
        st.info("Tidak ada trade aktif.")
    else:
        for idx, trade in open_trades:
            elapsed = int((datetime.now() - datetime.fromisoformat(trade["timestamp"])).total_seconds() / 60)

            with st.expander(f"{trade['pair']} • {trade['direction']} • {elapsed} menit", expanded=True):
                st.markdown(f"""
**Entry**: {trade['entry']}  
**SL**: {trade['sl']}  
**Context**: {trade['context_verdict']}  
**Berjalan**: {elapsed} menit
""")

                if elapsed >= trade["time_eval_min"] and not trade["time_eval_done"]:
                    st.warning("⏳ Waktu evaluasi tercapai")

                if st.button("⛔ Selesai Trade", key=f"close_{idx}"):
                    trade["trade_status"] = "CLOSED"
                    trade["exit_reason"] = "MANUAL_CLOSE"
                    save_journal()
                    backup_journal()
                    st.success("Trade ditandai selesai.")

    # ================= UPDATE RESULT R =================
    st.divider()
    st.subheader("✏️ Update Hasil Trade")

    open_eval = [
        i for i, t in enumerate(st.session_state.journal)
        if t["result_r"] is None and t["trade_status"] == "CLOSED"
    ]

    if open_eval:
        idx = st.selectbox(
            "Pilih Trade",
            open_eval,
            format_func=lambda i: f"{st.session_state.journal[i]['pair']} @ {st.session_state.journal[i]['timestamp']}"
        )
        r_val = st.selectbox("Result R", R_OPTIONS)
        reason = st.text_input("Alasan Exit")

        if st.button("💾 Simpan Result"):
            st.session_state.journal[idx]["result_r"] = r_val
            st.session_state.journal[idx]["exit_reason"] = reason
            save_journal()
            backup_journal()
            st.success("Result disimpan.")
    else:
        st.info("Tidak ada trade yang menunggu evaluasi.")

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
        df.to_csv(index=False).encode("utf-8"),
        "journal.csv",
        "text/csv"
    )
