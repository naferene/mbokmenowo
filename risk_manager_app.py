import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
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
st.caption("Risk-first • Bias-first • Context-aware • Futures")

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
# CONTEXT GATE INTEGRATION (TIMEZONE SAFE)
# ==================================================
def get_context_gate_pairs(max_hours=4, limit=5):
    """
    Ambil pair TAKEN dari Context Gate
    - Timezone: WIB
    - Filter waktu: max_hours terakhir
    - Anti regresi schema
    """
    if not os.path.exists(CONTEXT_JOURNAL_FILE):
        return []

    df = pd.read_csv(CONTEXT_JOURNAL_FILE)

    REQUIRED_COLS = {"pair", "decision", "datetime_wib"}
    if not REQUIRED_COLS.issubset(df.columns):
        st.warning("⚠️ Schema Context Gate tidak cocok.")
        return []

    df = df[df["decision"] == "TAKEN"]
    if df.empty:
        return []

    # Parse datetime_wib secara eksplisit
    df["datetime_wib"] = pd.to_datetime(
        df["datetime_wib"],
        format="%Y-%m-%d %H:%M",
        errors="coerce"
    )

    df = df.dropna(subset=["datetime_wib"])
    if df.empty:
        return []

    # Gunakan WIB (UTC+7) secara konsisten
    now_wib = datetime.utcnow() + timedelta(hours=7)

    df["age_hours"] = (
        now_wib - df["datetime_wib"]
    ).dt.total_seconds() / 3600

    df = df[df["age_hours"] <= max_hours]
    if df.empty:
        return []

    # Urutkan terbaru & ambil pair unik
    df = df.sort_values("datetime_wib", ascending=False)

    pairs = []
    for p in df["pair"]:
        if p not in pairs:
            pairs.append(p)
        if len(pairs) >= limit:
            break

    return pairs

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

    # ---------- STEP 0: PIN ----------
    pin = st.text_input("🔐 PIN Eksekusi", type="password")
    if pin != PIN_CODE:
        st.stop()

    # ---------- STEP 1: PAIR SELECTION ----------
    st.markdown("### 🧩 Pilih Pair")

    context_pairs = get_context_gate_pairs(max_hours=4, limit=5)

    use_context = False

    if context_pairs:
        pair = st.selectbox(
            "Pair dari Context Gate (TAKEN • ≤ 4 jam)",
            context_pairs
        )
        st.caption("Pair ini lolos Context Gate. Tetap wajib lolos Bias Checklist.")
        use_context = True

        if st.checkbox("Input pair manual"):
            pair = st.text_input("Pair (manual)", "").upper().strip()
            use_context = False
    else:
        pair = st.text_input(
            "Pair (manual)",
            help="Tidak ada pair TAKEN dari Context Gate dalam 4 jam terakhir."
        ).upper().strip()

    if not pair:
        st.stop()

    # ---------- STEP 2: BIAS CHECKLIST ----------
    st.markdown("### 🧠 Validasi Ide (Bias Checklist)")

    c1 = st.checkbox("EMA searah (struktur rapi)")
    with st.expander("Penjelasan EMA searah", expanded=False):
        st.markdown("""
- EMA 21 / 55 / 89 / 144 berurutan rapi
- Tidak saling silang
- Sudut EMA jelas
- EMA kusut = CHOPPY = NO TRADE
""")

    c2 = st.checkbox("Harga dijaga di satu sisi EMA")
    with st.expander("Penjelasan harga vs EMA", expanded=False):
        st.markdown("""
- Harga dijaga di atas EMA 21 & 55 (bullish)
- Atau di bawah EMA 21 & 55 (bearish)
- Pullback → mantul
- Bolak-balik EMA = arah tidak dijaga
""")

    c3 = st.checkbox("Momentum ada (RSI tidak flat)")
    with st.expander("Penjelasan momentum RSI", expanded=False):
        st.markdown("""
- RSI dominan:
  - ≥ 55 → bullish
  - ≤ 45 → bearish
- RSI 45–55 bolak-balik = tenaga habis
""")

    c4 = st.checkbox("Market tidak choppy")
    with st.expander("Penjelasan market choppy", expanded=False):
        st.markdown("""
- Banyak doji
- Sumbu panjang
- Arah cepat berubah
- Ragu = anggap choppy
""")

    bias_score = sum([c1, c2, c3, c4])
    if bias_score < 3:
        st.error("❌ NO TRADE — Ide belum valid.")
        st.stop()

    st.success("✅ Ide valid. Lanjut ke perhitungan risiko.")

    # ---------- STEP 3: RISK INPUT ----------
    equity = st.number_input("Equity (USD)", value=2500.0)
    risk_percent = st.number_input("Risk per Trade (%)", value=1.0)

    sl = st.number_input("Stop Loss Price", format="%.4f")
    entry = st.number_input("Entry Price", format="%.4f")
    leverage = st.number_input("Leverage (x)", min_value=1, value=5)

    if entry == sl:
        st.warning("Entry dan SL tidak boleh sama.")
        st.stop()

    # ---------- STEP 4: RISK OUTPUT ----------
    risk_usd = equity * (risk_percent / 100)
    sl_dist = abs(entry - sl)
    position_size = (risk_usd * entry) / sl_dist
    margin = position_size / leverage
    direction = "LONG" if entry > sl else "SHORT"

    st.subheader("📊 Ringkasan Risiko")
    st.markdown(f"""
**Pair** : {pair}  
**Sumber Pair** : {"Context Gate" if use_context else "Manual"}  
**Arah** : **{direction}**

**1R** : ${risk_usd:,.2f}  
**Position Size** : ${position_size:,.2f}  
**Margin Digunakan** : **${margin:,.2f}**
""")

    # ---------- STEP 5: SAVE TRADE ----------
    if st.button("💾 Catat Trade & Eksekusi", use_container_width=True):
        st.session_state.journal.append({
            "timestamp": datetime.utcnow().isoformat(),
            "pair": pair,
            "pair_source": "CONTEXT_GATE" if use_context else "MANUAL",
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "risk_percent": risk_percent,
            "bias_score": bias_score,
            "position_size": position_size,
            "margin": margin,
            "trade_status": "OPEN",
            "result_r": None,
            "exit_reason": None
        })
        save_journal()
        backup_journal()
        st.success("Trade dicatat. Lanjut eksekusi di exchange.")

# ==================================================
# NORMAL MODE (UNCHANGED)
# ==================================================
else:
    st_autorefresh(interval=60 * 1000, key="monitor_timer")

    st.subheader("🟢 Trade Aktif")

    open_trades = [
        (i, t) for i, t in enumerate(st.session_state.journal)
        if t["trade_status"] == "OPEN"
    ]

    if not open_trades:
        st.info("Tidak ada trade aktif.")
    else:
        for idx, trade in open_trades:
            elapsed = int(
                (datetime.utcnow() - datetime.fromisoformat(trade["timestamp"]))
                .total_seconds() / 60
            )

            with st.expander(
                f"{trade['pair']} • {trade['direction']} • {elapsed} menit",
                expanded=True
            ):
                st.markdown(f"""
**Entry** : {trade['entry']}  
**SL** : {trade['sl']}  
**Margin** : ${trade['margin']:,.2f}
""")

                if st.button("⛔ Selesai Trade", key=f"close_{idx}"):
                    trade["trade_status"] = "CLOSED"
                    save_journal()
                    backup_journal()
                    st.success("Trade ditandai selesai.")

    st.divider()
    st.subheader("✏️ Update Result R")

    pending = [
        i for i, t in enumerate(st.session_state.journal)
        if t["trade_status"] == "CLOSED" and t["result_r"] is None
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

    st.divider()
    df = pd.DataFrame(st.session_state.journal)
    st.dataframe(df, use_container_width=True)
