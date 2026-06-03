from flask import Flask, jsonify, render_template_string
import requests
import pandas as pd
import numpy as np

app = Flask(__name__)

API_KEY = "ebb5cf7870004709a1c668a9ee35b886"
SYMBOL = "EUR/USD"
INTERVAL = "1min"


# ---------- SAFE DATA FETCH ----------
def get_data():
    try:
        url = "https://api.twelvedata.com/time_series"

        params = {
            "symbol": SYMBOL,
            "interval": INTERVAL,
            "outputsize": 120,
            "apikey": API_KEY
        }

        r = requests.get(url, timeout=10).json()

        # ❌ API issue detect
        if "values" not in r:
            return "API_CRASH"

        df = pd.DataFrame(r["values"])

        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna()
        df = df.iloc[::-1].reset_index(drop=True)

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

    # ---------- ERROR HANDLING ----------
    if df == "API_CRASH":
        return {"signal": "API CRASH ❌", "strength": "CHECK API KEY / LIMIT"}

    if df == "BACKEND_CRASH":
        return {"signal": "BACKEND CRASH ❌", "strength": "SERVER ERROR"}

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

        if atr_val < avg_price * 0.00035:
            return {"signal": "AVOID ⚠️", "strength": "LOW"}

        # ---------- FINAL DECISION ----------
        if score >= 6:
            # bullish → CALL
            return {"signal": "CALL 📈", "strength": "HIGH"}

        elif score <= -6:
            # bearish → PUT
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
    <title>EUR/USD Signal Engine</title>

    <style>
        body {
            font-family: Arial;
            background: #0f172a;
            color: white;
            text-align: center;
            padding-top: 60px;
        }

        .box {
            background: #1e293b;
            padding: 20px;
            margin: auto;
            width: 320px;
            border-radius: 12px;
        }

        .title {
            font-size: 22px;
            font-weight: bold;
        }

        .signal {
            margin-top: 20px;
            padding: 20px;
            background: #111827;
            border-radius: 10px;
            font-size: 20px;
            min-height: 60px;
        }

        button {
            margin-top: 20px;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            background: #22c55e;
            color: white;
            font-size: 16px;
        }
    </style>
</head>

<body>

<div class="box">

    <div class="title">EUR/USD Signal Engine</div>

    <div>1 Minute Timeframe</div>

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
