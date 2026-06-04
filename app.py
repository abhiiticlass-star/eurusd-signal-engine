from flask import Flask, jsonify, render_template_string
import requests
import pandas as pd
import numpy as np
import time
import os

app = Flask(__name__)

SYMBOL = "BTCUSDT"
INTERVAL = "1m"

cache = {"time": 0, "data": None}
CACHE_TIME = 30


# ---------- BINANCE DATA ----------
def get_data():
    try:
        if cache["data"] is not None and time.time() - cache["time"] < CACHE_TIME:
            return cache["data"]

        url = "https://api.binance.com/api/v3/klines"

        r = requests.get(url, params={
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "limit": 200
        }, timeout=10).json()

        df = pd.DataFrame(r, columns=[
            "time","open","high","low","close","volume",
            "c1","c2","c3","c4","c5","c6"
        ])

        df = df[["open","high","low","close"]].astype(float)

        cache["data"] = df
        cache["time"] = time.time()

        return df

    except:
        return None


# ---------- INDICATORS ----------
def ema(s, p):
    return s.ewm(span=p, adjust=False).mean()

def rsi(s, p=14):
    d = s.diff()
    g = (d.where(d > 0, 0)).rolling(p).mean()
    l = (-d.where(d < 0, 0)).rolling(p).mean()
    rs = g / l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def macd(s):
    m = ema(s, 12) - ema(s, 26)
    sig = ema(m, 9)
    return m, sig


# ---------- SIGNAL ENGINE ----------
def generate_signal():
    df = get_data()

    if df is None or len(df) < 60:
        return {"signal": "NO DATA", "strength": 0, "type": "AVOID"}

    close = df["close"]

    e9 = ema(close, 9)
    e21 = ema(close, 21)
    r = rsi(close).iloc[-1]
    m, s = macd(close)

    score = 0

    # TREND
    if e9.iloc[-1] > e21.iloc[-1]:
        score += 2
    else:
        score -= 2

    # RSI
    if 55 < r < 70:
        score += 2
    elif 30 < r < 45:
        score -= 2

    # MACD
    if m.iloc[-1] > s.iloc[-1]:
        score += 2
    else:
        score -= 2

    # MOMENTUM
    if close.iloc[-1] > close.iloc[-3]:
        score += 1

    # ---------- CONFIDENCE CALC ----------
    confidence = min(100, max(10, int((abs(score) / 6) * 100)))

    # ---------- FINAL ----------
    if score >= 4:
        return {"signal": "CALL 📈", "strength": confidence, "type": "HIGH"}
    elif score <= -4:
        return {"signal": "PUT 📉", "strength": confidence, "type": "HIGH"}
    else:
        return {"signal": "AVOID ⚠️", "strength": confidence, "type": "LOW"}


# ---------- UI ----------
HTML = """
<!DOCTYPE html>
<html>
<head>
<title>BTCUSDT PRO ENGINE</title>

<style>
body{
    background:#0f172a;
    color:white;
    text-align:center;
    font-family:Arial;
    padding-top:60px;
}

.box{
    background:#1e293b;
    width:360px;
    margin:auto;
    padding:20px;
    border-radius:12px;
}

.signal{
    margin-top:20px;
    background:#111827;
    padding:20px;
    border-radius:10px;
    font-size:20px;
}

.timer{
    margin-top:10px;
    font-size:14px;
    color:#22c55e;
}

button{
    margin-top:15px;
    padding:10px 20px;
    background:#22c55e;
    border:none;
    border-radius:8px;
    color:white;
}
</style>
</head>

<body>

<div class="box">
<h2>BTCUSDT LIVE ENGINE</h2>

<div class="timer" id="timer">Syncing...</div>

<div class="signal" id="box">Loading...</div>

<button onclick="load()">Refresh</button>
</div>

<script>

let seconds = 60;

function countdown(){
    seconds--;
    if(seconds <= 0){
        load();
        seconds = 60;
    }
    document.getElementById("timer").innerText =
        "Next update in: " + seconds + " sec";
}

async function load(){
    let r = await fetch('/signal');
    let d = await r.json();

    let label = d.type === "HIGH"
        ? d.signal + " | " + d.strength + "% CONFIDENCE"
        : "AVOID ⚠️ | " + d.strength + "% CONFIDENCE";

    document.getElementById("box").innerText = label;
    seconds = 60;
}

load();
setInterval(countdown, 1000);

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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
