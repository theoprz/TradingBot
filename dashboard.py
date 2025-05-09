
import streamlit as st
import pandas as pd
import os
import time
import plotly.graph_objects as go
from ta.volatility import BollingerBands
from ta.momentum import RSIIndicator
from ta.trend import MACD

from scalping_bot_lstm_with_optimization import fetch_data, compute_indicators  # importer depuis ton script principal
from telegrambot import alert_if_proximity_high, send_telegram_alert

TRADE_LOG_FILE = "trade_history_XAUUSD.csv"
SIGNAL_LOG_FILE = "signal_log_XAUUSD.txt"
REFRESH_INTERVAL = 10  # secondes

st.set_page_config(page_title="XAUUSD Scalping Dashboard", layout="wide")
st.title("📈 Scalping Bot Dashboard (XAU/USD)")

# Rafraîchissement automatique
st_autorefresh = st.empty()
st_autorefresh.markdown(f"<meta http-equiv='refresh' content='{REFRESH_INTERVAL}'>", unsafe_allow_html=True)

# Proximité aux signaux BUY et SELL
st.subheader("📊 Proximité aux signaux")

df_indicators = fetch_data()
df_indicators = compute_indicators(df_indicators)
if not df_indicators.empty:
    latest = df_indicators.iloc[-1]

    # BUY
    rsi_buy = max(0, 1 - (latest['rsi'] - 30) / 20)
    bb_buy = max(0, 1 - (latest['close'] - latest['bb_bbl']) / (0.01 * latest['close']))
    macd_buy = 1 if latest['macd'] > latest['macd_signal'] else 0
    buy_proximity = (rsi_buy + bb_buy + macd_buy) / 3 * 100

    # SELL
    rsi_sell = max(0, 1 - (70 - latest['rsi']) / 20)
    bb_sell = max(0, 1 - (latest['bb_bbh'] - latest['close']) / (0.01 * latest['close']))
    macd_sell = 1 if latest['macd'] < latest['macd_signal'] else 0
    sell_proximity = (rsi_sell + bb_sell + macd_sell) / 3 * 100

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Proximité signal BUY", f"{buy_proximity:.0f} %")
    with col2:
        st.metric("Proximité signal SELL", f"{sell_proximity:.0f} %")
else:
    st.warning("Impossible de calculer la proximité aux signaux : données indisponibles.")

alert_if_proximity_high(buy_proximity, sell_proximity)

# Logs de signaux
if os.path.exists(SIGNAL_LOG_FILE):
    with open(SIGNAL_LOG_FILE, 'r') as f:
        logs = f.readlines()[-6:]
    st.subheader("📋 Derniers Signaux")
    for line in logs:
        st.text(line.strip())
else:
    st.info("Aucun signal enregistré pour l'instant.")

# Graphique TP/SL si trades disponibles
if os.path.exists(TRADE_LOG_FILE):
    df = pd.read_csv(TRADE_LOG_FILE)
    df['time'] = pd.to_datetime(df['time'])
    df = df.tail(7)
    st.subheader("📉 Visualisation des 7 derniers Trades")

    fig = go.Figure()

    for _, row in df.iterrows():
        x_time = row['time'].strftime('%Y-%m-%d %H:%M:%S')

        # Ligne entre TP et SL (non horizontale)
        fig.add_trace(go.Scatter(
            x=[x_time, x_time],
            y=[row['sl'], row['tp']],
            mode='lines',
            line=dict(color='gray', width=1),
            showlegend=False
        ))

        # Point d'entrée
        fig.add_trace(go.Scatter(
            x=[x_time],
            y=[row['entry_price']],
            mode='markers',
            marker=dict(color='blue', size=8),
            name='Entrée'
        ))

        # TP
        fig.add_trace(go.Scatter(
            x=[x_time],
            y=[row['tp']],
            mode='markers+text',
            marker=dict(color='green', size=6),
            text=[f"TP: {row['tp']:.2f}"],
            textposition="top right",
            name='Take Profit'
        ))

        # SL
        fig.add_trace(go.Scatter(
            x=[x_time],
            y=[row['sl']],
            mode='markers+text',
            marker=dict(color='red', size=6),
            text=[f"SL: {row['sl']:.2f}"],
            textposition="bottom right",
            name='Stop Loss'
        ))

    fig.update_layout(
        title="Courbe des 7 derniers ordres avec TP/SL",
        xaxis_title="Temps",
        yaxis_title="Prix",
        height=600,
        showlegend=True
    )

    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Aucun trade enregistré pour l’instant.")
