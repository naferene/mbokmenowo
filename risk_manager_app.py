import streamlit as st
import pandas as pd
from datetime import datetime, date
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
st.caption("Risk-first • Bias Filter • Context-aware • Multi-pair")

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

    st_autorefresh(interval=60 * 1000, key="timer")

    pin = st.text_input("🔐 PIN Quick Trade", type="password")
    if pin != PIN_CODE:
        st.stop()

    pair = st.text_input("Pair (BTCUSDT, SOLUSDT)").upper()
    equity = st.number_input("Equity (USD)", value=2500.0)
    risk_percent = st.number_input("Risk per Trade (%)", value=1.0)
    entry = st.number_input("Entry Price", format="%.4f")
    sl = st.number_input("Stop Loss Price", format="%.4f")
    leverage = st.number_input("Leverage (x)", min_value=1, value=5)

    # ==================================================
    # BIAS CHECKLIST (WITH EXPANDERS)
    # ==================================================
    st.markdown("### 🧠 Bias Checklist")

    c1 = st.checkbox("EMA searah")
    with st.expander("Penjelasan EMA searah", expanded=False):
        st.markdown("- EMA 21/55/89/144 rapi, tidak kusut")

    c2 = st.checkbox("Harga dijaga EMA")
    with st.expander("Penjelasan harga vs EMA", expanded=False):
        st.markdown("- Harga konsisten di satu sisi EMA utama")

    c3 = st.checkbox("Momentum ada")
    with st.expander("Penjelasan momentum", expanded=False):
        st.markdown("- RSI tidak flat / tenaga masih ada")

    c4 = st.checkbox("Market tidak choppy")
    with st.expander("Penjelasan choppy", expanded=False):
        st.markdown("- Tidak doji beruntun / whipsaw")

    bias_score = sum([c1, c2, c3, c4])
    if bias_score < 3:
        st.error("❌ NO TRADE — Bias belum cukup.")
        st.stop()

    # ==================================================
    # ENTRY
    # ==================================================
    if st.button("⚡ HITUNG & CATAT TRADE", use_container_width=True):

        trade_time = datetime.now().isoformat()
        context = get_latest_context(pair, trade_time)

        if context is not None:
            st.info(f"Context terakhir: {context['verdict']}")

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

            "time_eval_min": 30,
            "time_state": "ACTIVE",   # ACTIVE | MATURE | DONE

            "context_verdict": context["verdict"] if context is not None else None,

            "result_r": None,
            "exit_reason": None
        })

        save_journal()
        backup_journal()
        st.success("Trade dicatat.")

    # ==================================================
    # ACTIVE / MATURE TRADES PANEL
    # ==================================================
    st.divider()
    st.subheader("🟢 Trade Aktif")

    open_trades = [
        (i, t) for i, t in enumerate(st.session_state.journal)
        if t["time_state"] in ["ACTIVE", "MATURE"]
    ]

    active_count = sum(1 for _, t in open_trades if t["time_state"] == "ACTIVE")
    if active_count > 5:
        st.warning("⚠️ Lebih dari 5 trade ACTIVE. Perhatikan fokus.")

    for idx, trade in open_trades:
        elapsed = int((datetime.now() - datetime.fromisoformat(trade["timestamp"])).total_seconds() / 60)

        # Auto transition ACTIVE → MATURE
        if trade["time_state"] == "ACTIVE" and elapsed >= trade["time_eval_min"]:
            trade["time_state"] = "MATURE"
            save_journal()

        label = f"{trade['pair']} • {trade['direction']} • {elapsed} menit • {trade['time_state']}"
        with st.expander(label, expanded=(trade["time_state"] == "ACTIVE")):

            st.markdown(f"""
**Entry**: {trade['entry']}  
**SL**: {trade['sl']}  
**Context**: {trade['context_verdict']}
""")

            if trade["time_state"] == "MATURE":
                st.warning("⏳ Trade sudah melewati waktu evaluasi awal.")

            if st.button("⛔ Selesai Trade", key=f"done_{idx}"):
                trade["time_state"] = "DONE"
                save_journal()
                backup_journal()
                st.success("Trade ditandai selesai.")

    # ==================================================
    # UPDATE RESULT R (QUICK)
    # ==================================================
    st.divider()
    st.subheader("✏️ Update Hasil Trade (Quick)")

    pending = [
        i for i, t in enumerate(st.session_state.journal)
        if t["time_state"] == "DONE" and t["result_r"] is None
    ]

    if pending:
        idx = st.selectbox(
            "Pilih Trade",
            pending,
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
        st.info("Tidak ada trade menunggu evaluasi.")

# ==================================================
# NORMAL MODE
# ==================================================
else:
    if not st.session_state.journal:
        st.info("Belum ada trade.")
        st.stop()

    df = pd.DataFrame(st.session_state.journal)
    st.dataframe(df, use_container_width=True)

    st.divider()
    st.subheader("✏️ Update Result R (Normal Mode)")

    open_eval = df[df["result_r"].isna()].index.tolist()
    if open_eval:
        idx = st.selectbox(
            "Pilih Trade",
            open_eval,
            format_func=lambda i: f"{df.loc[i,'pair']} @ {df.loc[i,'timestamp']}"
        )
        r_val = st.selectbox("Result R", R_OPTIONS)
        reason = st.text_input("Alasan Exit")

        if st.button("💾 Update Trade"):
            st.session_state.journal[idx]["result_r"] = r_val
            st.session_state.journal[idx]["exit_reason"] = reason
            save_journal()
            backup_journal()
            st.success("Trade diperbarui.")
    else:
        st.success("Semua trade sudah dievaluasi.")

    st.divider()
    st.download_button(
        "⬇️ Download Journal CSV",
        df.to_csv(index=False).encode("utf-8"),
        "journal.csv",
        "text/csv"
    )
