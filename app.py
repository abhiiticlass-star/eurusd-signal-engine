from flask import Flask, jsonify, render_template_string
import requests
import pandas as pd
import numpy as np
import time
import os

app = Flask(__name__)

API_KEY = "DYASXHAJUXF7XLGN"
INTERVAL = "1min"

cache = {"time": 0, "data": None}
CACHE_TIME = 120  # 2 min cache (IMPORTANT FIX)


# ---------- DATA FETCH ----------
def get_data():
    try:
        if cache["data"] is not None and time.time() - cache["time"] < CACHE_TIME:
            return cache["data"]

        url = "https://www.alphavantage.co/query"

        params = {
            "function": "FX_INTRADAY",
            "from_symbol": "EUR",
            "to_symbol": "USD",
            "interval": INTERVAL,
            "apikey": API_KEY,
            "outputsize": "compact"
        }

        r = requests.get(url, params=params, timeout=10).json()

        # ❌ HARD FIX FOR LIMIT ERROR
        if "Note" in r:
            return "API_LIMIT"

        if "Time Series FX (1min)" not in r:
            return "DATA_ERROR"

        data = r["Time Series FX (1min)"]

        df = pd.DataFrame.from_dict(data, orient="index")
        df = df.rename(columns={
            "1. open": "open",
            "2. high": "high",
            "3. low": "low",
            "4. close": "close"
        })

        df = df.astype(float)
        df = df.sort_index().reset_index(drop=True)

        cache["data"] = df
        cache["time"] = time.time()

        return df

    except:
        return "BACKEND_CRASH"


# ---------- INDICATORS ----------
def ema(s, p): return s.ewm(span=p, adjust=False).mean()

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

def atr(df):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([
        h-l,
        abs(h-c.shift()),
        abs(l-c.shift())
    ], axis=1).max(axis=1)
    return tr.rolling(14).mean()


# ---------- SIGNAL ENGINE ----------
def generate_signal():
    df = get_data()

    if df == "API_LIMIT":
        return {"signal": "API LIMIT ⚠️", "strength": "WAIT 1-2 MIN"}

    if df == "DATA_ERROR":
        return {"signal": "DATA ERROR ❌", "strength": "NO DATA"}

    if df == "BACKEND_CRASH":
        return {"signal": "BACKEND ERROR ❌", "strength": "SERVER"}

    try:
        close = df["close"]

        e9 = ema(close, 9)
        e21 = ema(close, 21)
        e50 = ema(close, 50)

        r = rsi(close).iloc[-1]
        m, s = macd(close)
        a = atr(df).iloc[-1]

        if pd.isna(a):
            return {"signal": "AVOID ⚠️", "strength": "NO VOL DATA"}

        score = 0

        # TREND
        if e9.iloc[-1] > e21.iloc[-1] > e50.iloc[-1]:
            score += 3
        elif e9.iloc[-1] < e21.iloc[-1] < e50.iloc[-1]:
            score -= 3

        # RSI
        if 50 < r < 65:
            score += 2
        elif 35 < r < 50:
            score -= 2

        # MACD
        if m.iloc[-1] > s.iloc[-1]:
            score += 2
        else:
            score -= 2

        # MOMENTUM
        if close.iloc[-1] > close.iloc[-3]:
            score += 1

        # VOL FILTER
        if a < close.mean() * 0.0004:
            return {"signal": "AVOID ⚠️", "strength": "LOW VOL"}

        if score >= 5:
            return {"signal": "CALL 📈", "strength": "GOOD SETUP"}
        elif score <= -5:
            return {"signal": "PUT 📉", "strength": "GOOD SETUP"}
        else:
            return {"signal": "AVOID ⚠️", "strength": "NO TRADE"}

    except:
        return {"signal": "ERROR ❌", "strength": "LOGIC"}


# ---------- UI ----------
HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Pro Signal Engine</title>
<style>
body{background:#0f172a;color:white;text-align:center;font-family:Arial;padding-top:60px}
.box{background:#1e293b;width:350px;margin:auto;padding:20px;border-radius:12px}
.signal{margin-top:20px;background:#111827;padding:20px;border-radius:10px;font-size:20px}
button{margin-top:20px;padding:10px 20px;background:#22c55e;border:none;border-radius:8px;color:white}
</style>
</head>
<body>

<div class="box">
<h2>EUR/USD PRO ENGINE</h2>
<div class="signal" id="box">Loading...</div>
<button onclick="load()">Refresh</button>
</div>

<script>
async function load(){
let r=await fetch('/signal')
let d=await r.json()
document.getElementById("box").innerText=d.signal+" | "+d.strength
}
load()
setInterval(load,60000)
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
