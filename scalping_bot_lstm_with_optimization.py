import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import datetime
from ta.volatility import BollingerBands
from ta.momentum import RSIIndicator
from ta.trend import MACD, ADXIndicator, EMAIndicator
import streamlit as st
import os

from telegrambot import send_telegram_alert

SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M1
LOT = 0.5
TP_SL_MULTIPLIER = 1.5
HISTORY_BARS = 1000
TRADE_LOG_FILE = f"trade_history_{SYMBOL}.csv"
SIGNAL_LOG_FILE = f"signal_log_{SYMBOL}.txt"

RISK_PERCENT = 1  # % du capital à risquer
SYMBOL = "XAUUSD"

def get_dynamic_lot(entry_price, sl_price):
    account_info = mt5.account_info()
    if account_info is None:
        print("[ERREUR] Impossible d'accéder aux infos du compte.")
        return LOT  # fallback

    equity = account_info.equity
    risk_amount = equity * (RISK_PERCENT / 100)

    stop_loss_pips = abs(entry_price - sl_price)
    if stop_loss_pips == 0:
        stop_loss_pips = 0.01  # éviter division par 0

    # Coefficient spécifique XAUUSD (10$ / lot pour 1 pip de mouvement = 0.1)
    pip_value = 10
    lot_size = risk_amount / (stop_loss_pips * pip_value)

    # Arrondi, avec bornes min/max
    return max(0.01, round(min(lot_size, 5.0), 2))


if not mt5.initialize():
    print("initialize() failed")
    mt5.shutdown()

def fetch_data(symbol=SYMBOL, bars=HISTORY_BARS):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, bars)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def compute_indicators(df):
    df['rsi'] = RSIIndicator(df['close']).rsi()
    bb = BollingerBands(df['close'])
    df['bb_bbm'] = bb.bollinger_mavg()
    df['bb_bbh'] = bb.bollinger_hband()
    df['bb_bbl'] = bb.bollinger_lband()
    macd = MACD(df['close'])
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['adx'] = ADXIndicator(df['high'], df['low'], df['close']).adx()
    df['ema_20'] = EMAIndicator(df['close'], window=20).ema_indicator()
    df = df.dropna()
    return df

def generate_signals(df):
    latest = df.iloc[-1]
    signal = None
    if latest['rsi'] < 30 and latest['close'] < latest['bb_bbl'] and latest['macd'] > latest['macd_signal']:
        signal = 'buy'
    elif latest['rsi'] > 70 and latest['close'] > latest['bb_bbh'] and latest['macd'] < latest['macd_signal']:
        signal = 'sell'
    with open(SIGNAL_LOG_FILE, 'a') as f:
        f.write(f"{datetime.datetime.now()} - Signal: {signal} | Price: {latest['close']:.2f}\n")
    return signal

def calculate_tp_sl(entry_price, atr, direction):
    tp = entry_price + atr * TP_SL_MULTIPLIER if direction == 'buy' else entry_price - atr * TP_SL_MULTIPLIER
    sl = entry_price - atr * TP_SL_MULTIPLIER if direction == 'buy' else entry_price + atr * TP_SL_MULTIPLIER
    return tp, sl

def place_order(signal, df):
    price = mt5.symbol_info_tick(SYMBOL).ask if signal == 'buy' else mt5.symbol_info_tick(SYMBOL).bid
    atr = df['high'].rolling(window=14).max().iloc[-1] - df['low'].rolling(window=14).min().iloc[-1]
    tp, sl = calculate_tp_sl(price, atr, signal)
    order_type = mt5.ORDER_TYPE_BUY if signal == 'buy' else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": get_dynamic_lot(entry_price=price, sl_price=sl),
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 42,
        "comment": "Scalping bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    print(f"Trade executed: {result}")
    return {
        'time': datetime.datetime.now(),
        'signal': signal,
        'entry_price': price,
        'tp': tp,
        'sl': sl
    }

def move_sl_to_breakeven(position, entry_price):
    # noinspection PyUnresolvedReferences
    result = mt5.order_modify(
        ticket=position.ticket,
        price=position.price_open,
        sl=entry_price,
        tp=position.tp,
        deviation=10,
        type_time=mt5.ORDER_TIME_GTC,
        type_filling=mt5.ORDER_FILLING_IOC
    )
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[SL MOVED TO BE] Position {position.ticket}")
        send_telegram_alert(f"🔔 SL déplacé en Break-Even pour la position {position.ticket} sur {SYMBOL}")
    else:
        print(f"[ERREUR SL BE] {result.retcode}: {result.comment}")

def check_positions_for_breakeven(atr_multiplier=0.5):
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None or len(positions) == 0:
        return

    df = fetch_data()
    df = compute_indicators(df)
    atr = df['high'].rolling(window=14).max().iloc[-1] - df['low'].rolling(window=14).min().iloc[-1]

    for pos in positions:
        entry = pos.price_open
        if pos.type == mt5.ORDER_TYPE_BUY:
            current = mt5.symbol_info_tick(SYMBOL).bid
            if current >= entry + atr * atr_multiplier and pos.sl < entry:
                move_sl_to_breakeven(pos, entry)
        elif pos.type == mt5.ORDER_TYPE_SELL:
            current = mt5.symbol_info_tick(SYMBOL).ask
            if current <= entry - atr * atr_multiplier and pos.sl > entry:
                move_sl_to_breakeven(pos, entry)

def run_bot():
    trade_log = []
    while True:
        df = fetch_data()
        if df.empty:
            continue
        df = compute_indicators(df)
        signal = generate_signals(df)
        if signal:
            trade = place_order(signal, df)
            trade_log.append(trade)
            pd.DataFrame(trade_log).to_csv(TRADE_LOG_FILE, index=False)
        check_positions_for_breakeven()
        time.sleep(15)

def optimize_parameters():
    results = []
    for tp_mult in np.arange(0.5, 3.1, 0.5):
        TP_SL_MULTIPLIER = tp_mult
        df = fetch_data()
        if df.empty:
            continue
        df = compute_indicators(df)
        win, loss = 0, 0
        for i in range(60, len(df) - 3):
            row = df.iloc[i]
            future = df.iloc[i + 3]
            signal = None
            if row['rsi'] < 30 and row['close'] < row['bb_bbl'] and row['macd'] > row['macd_signal']:
                signal = 'buy'
            elif row['rsi'] > 70 and row['close'] > row['bb_bbh'] and row['macd'] < row['macd_signal']:
                signal = 'sell'
            if signal:
                direction = 1 if signal == 'buy' else -1
                result = direction * (future['close'] - row['close'])
                if result > 0:
                    win += 1
                else:
                    loss += 1
        total = win + loss
        win_rate = (win / total * 100) if total > 0 else 0
        results.append({'tp_multiplier': tp_mult, 'win_rate': win_rate, 'total_trades': total})
    df_results = pd.DataFrame(results)
    df_results.to_csv("optimization_results.csv", index=False)
    print(df_results)
    return df_results

def show_dashboard():
    st.title("📈 Scalping Bot Dashboard (XAU/USD)")
    if os.path.exists(TRADE_LOG_FILE):
        df = pd.read_csv(TRADE_LOG_FILE)
        st.subheader("Historique des Trades")
        st.dataframe(df.tail(10))
        st.metric("Nombre total de trades", len(df))
    else:
        st.info("Aucun trade effectué pour l’instant.")
    if os.path.exists(SIGNAL_LOG_FILE):
        with open(SIGNAL_LOG_FILE, 'r') as f:
            logs = f.readlines()[-20:]
        st.subheader("📋 Derniers Signaux (avec prix)")
        for line in logs:
            st.text(line.strip())
