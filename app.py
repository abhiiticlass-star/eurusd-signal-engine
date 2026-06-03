from flask import Flask, jsonify, render_template_string
import pandas as pd
import numpy as np
import time
import random

app = Flask(__name__)

# ---------- CACHE ----------
cache = {
    "time": 0,
    "data": None
}

CACHE_TIME = 60


# ---------- FAKE MARKET DATA GENERATOR ----------
def generate_fake_data():
    base = 1.0850
    rows = []

    for i in range(200):
        change = random.uniform(-0.0005, 0.0005)
        base += change

        open_p = base
        high = base + random.uniform(0, 0.0003)
        low = base - random.uniform(0, 0.0003)
        close = base + random.uniform(-0.0002, 0.0002)

        rows.append([open_p, high, low, close])

    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    return df


# ---------- DATA FETCH (CACHED) ----------
def get_data():
    try:
        if cache["data"] is not None and time.time() - cache["time"] < CACHE_TIME:
            return cache["data"]

        df = generate_fake_data()

        cache["data"] = df
        cache["time"] = time.time()

        return df

    except:
        return "BACKEND_CRASH"


# ---------- INDICATORS ----------
def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series):
    ema12 = ema(series, 12)
    ema26 = ema(series, 26)
    macd_line = ema12 - ema26
    signal = ema(macd_line, 9)
    return macd_line, signal


def atr(df):
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr = pd.concat([
        high - low,
        abs(high - close.shift()),
        abs(low - close.shift())
    ], axis=1).max(axis=1)

    return tr.rolling(14).mean()


# ---------- SIGNAL ENGINE ----------
def generate_signal():
    df = get_data()

    if df == "BACKEND_CRASH":
        return {"signal": "BACKEND CRASH ❌", "strength": "ERROR"}

    if df is None or len(df) < 60:
        return {"signal": "AVOID ⚠️", "strength": "LOW"}

    try:
        close = df["close"]

        ema9 = ema(close, 9)
        ema21 = ema(close, 21)
        ema50 = ema(close, 50)
        ema100 = ema(close, 100)

        rsi_val = rsi(close).iloc[-1]
        macd_line, macd_signal = macd(close)
        atr_val = atr(df).iloc[-1]

        score = 0

        # ---------- TREND ----------
        if ema9.iloc[-1] > ema21.iloc[-1] > ema50.iloc[-1] > ema100.iloc[-1]:
            score += 4
        elif ema9.iloc[-1] < ema21.iloc[-1] < ema50.iloc[-1] < ema100.iloc[-1]:
            score -= 4

        # ---------- RSI ----------
        if 55 <= rsi_val <= 65:
            score += 2
        elif 35 <= rsi_val <= 45:
            score -= 2

        # ---------- MACD ----------
        if macd_line.iloc[-1] > macd_signal.iloc[-1]:
            score += 3
        else:
            score -= 3

        # ---------- MOMENTUM ----------
        if close.iloc[-1] > close.iloc[-3]:
            score += 1
        else:
            score -= 1

        # ---------- VOLATILITY ----------
        avg_price = close.mean()

        if atr_val < avg_price * 0.0005:
            return {"signal": "AVOID ⚠️", "strength": "LOW"}

        # ---------- FINAL ----------
        if score >= 6:
            return {"signal": "CALL 📈", "strength": "HIGH"}
        elif score <= -6:
            return {"signal": "PUT 📉", "strength": "HIGH"}
        else:
            return {"signal": "AVOID ⚠️", "strength": "LOW"}

    except:
        return {"signal": "BACKEND CRASH ❌", "strength": "LOGIC ERROR"}


# ---------- UI ----------
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Signal Engine</title>
    <style>
        body { font-family: Arial; background:#0f172a; color:white; text-align:center; padding-top:60px; }
        .box { background:#1e293b; padding:20px; width:320px; margin:auto; border-radius:12px; }
        .title { font-size:22px; font-weight:bold; }
        .signal { margin-top:20px; padding:20px; background:#111827; border-radius:10px; font-size:20px; }
        button { margin-top:20px; padding:10px 20px; background:#22c55e; border:none; border-radius:8px; color:white; }
    </style>
</head>
<body>

<div class="box">
    <div class="title">EUR/USD Signal Engine</div>
    <div>Simulated Market (Stable Mode)</div>

    <div class="signal" id="box">Loading...</div>

    <button onclick="load()">Get Signal</button>
</div>

<script>
async function load(){
    try{
        let res = await fetch("/signal");
        let data = await res.json();

        document.getElementById("box").innerText =
            data.signal + " | " + data.strength;

    }catch(e){
        document.getElementById("box").innerText = "BACKEND CRASH ❌";
    }
}

load();
setInterval(load, 60000);
</script>

</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(HTML)


@app.route("/signal")
def signal():
    return jsonify(generate_signal())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
