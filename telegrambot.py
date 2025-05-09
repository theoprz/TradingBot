import requests
import time

# Remplace par tes valeurs
BOT_TOKEN = '7658918436:AAH_KECUIv5r64zS000w5jWx4mBXnOXY0A8'
CHAT_ID = '-1002378082516'
ALERT_COOLDOWN = 60  # secondes

last_alert_time = {'buy': 0, 'sell': 0}

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': CHAT_ID,
        'text': message
    }
    try:
        requests.post(url, data=data)
        print(f"[ALERTE ENVOYÉE] {message}")
    except Exception as e:
        print(f"[ERREUR TELEGRAM] {e}")

def alert_if_proximity_high(buy_prox, sell_prox, threshold=90):
    global last_alert_time
    now = time.time()

    if buy_prox > threshold and now - last_alert_time['buy'] > ALERT_COOLDOWN:
        send_telegram_alert(f"📈 Signal BUY proche ({buy_prox:.0f}%) sur XAU/USD")
        last_alert_time['buy'] = now

    if sell_prox > threshold and now - last_alert_time['sell'] > ALERT_COOLDOWN:
        send_telegram_alert(f"📉 Signal SELL proche ({sell_prox:.0f}%) sur XAU/USD")
        last_alert_time['sell'] = now
