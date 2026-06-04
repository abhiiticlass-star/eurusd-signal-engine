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
CACHE_TIME = 5


# ---------- BINANCE DATA ----------
def get_data():
    try:
        if cache["data"] is not None and time.time() - cache["time"] < CACHE_TIME:
            return cache["data"]

        url = "https://api.bybit.com/v5/market/kline"

        r = requests.get(
            url,
            params={
                "category": "linear",
                "symbol": SYMBOL,
                "interval": "1",
                "limit": 200
            },
            timeout=10
        ).json()

        if r.get("retCode") != 0:
            return None

        data = r["result"]["list"]

        df = pd.DataFrame(data, columns=[
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover"
        ])

        df = df[["open", "high", "low", "close"]].astype(float)

        # Bybit newest candle pehle deta hai
        df = df.iloc[::-1].reset_index(drop=True)

        cache["data"] = df
        cache["time"] = time.time()

        return df

    except Exception as e:
        print("ERROR:", e)
        return None

@app.route("/debug")
def debug():
    df = get_data()

    if df is None:
        return jsonify({"error": "No Data"})

    return jsonify({
        "rows": len(df),
        "columns": list(df.columns)
    })


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

    close = df["close"][:-1]

    e9 = ema(close, 9)
    e21 = ema(close, 21)
    e50 = ema(close, 50)

    r = rsi(close).iloc[-1]
    m, s = macd(close)

    score = 0

    # TREND
    if e9.iloc[-1] > e21.iloc[-1] > e50.iloc[-1]:
        score += 3
    elif e9.iloc[-1] < e21.iloc[-1] < e50.iloc[-1]:
        score -= 3

    # RSI
    if r > 55:
        score += 2
    elif r < 45:
        score -= 2

    # MACD
    if m.iloc[-1] > s.iloc[-1]:
        score += 2
    else:
        score -= 2

    # MOMENTUM
    if close.iloc[-1] > close.iloc[-3]:
        score += 2
    else:
        score -= 2

        confidence = min(95, max(20, int((abs(score) / 9) * 100)))

    if score >= 3:
        return {
            "signal": "CALL 📈",
            "strength": confidence,
            "type": "HIGH",
            "score": score,
            "rsi": round(r, 2)
        }

    elif score <= -3:
        return {
            "signal": "PUT 📉",
            "strength": confidence,
            "type": "HIGH",
            "score": score,
            "rsi": round(r, 2)
        }

    else:
        return {
            "signal": "AVOID ⚠️",
            "strength": confidence,
            "type": "LOW",
            "score": score,
            "rsi": round(r, 2)
        }

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

</div>

<script>

function getNextCandleTime(){
    let now = new Date();
    now.setSeconds(0);
    now.setMilliseconds(0);
    now.setMinutes(now.getMinutes() + 1);
    return now.getTime();
}

let nextCandle = getNextCandleTime();

function updateTimer(){
    let now = new Date().getTime();
    let diff = nextCandle - now;

    if(diff <= 0){
        load();
        nextCandle = getNextCandleTime();
        diff = 60000;
    }

    let sec = Math.floor(diff / 1000);

    document.getElementById("timer").innerText =
        "Next candle in: " + sec + " sec";
}

async function load(){
    let r = await fetch('/signal');
    let d = await r.json();

    let label = d.type === "HIGH"
        ? d.signal + " | " + d.strength + "% CONFIDENCE"
        : "AVOID ⚠️ | " + d.strength + "% CONFIDENCE";

    document.getElementById("box").innerText = label;
}

load();
setInterval(updateTimer, 1000);

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
