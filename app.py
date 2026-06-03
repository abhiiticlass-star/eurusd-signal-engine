from flask import Flask, jsonify, render_template_string
import requests
import pandas as pd
import numpy as np

app = Flask(__name__)

API_KEY = "8e9f4f263cd044cdb3a0a6972179737a"
SYMBOL = "EUR/USD"
INTERVAL = "1min"


# ---------- DATA ----------
def get_data():
    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "outputsize": 100,
        "apikey": API_KEY
    }

    r = requests.get(url, params=params).json()

    if "values" not in r:
        return None

    df = pd.DataFrame(r["values"])
    df = df.astype(float)
    df = df.sort_index()

    return df


# ---------- INDICATORS ----------
def ema(series, period):
    return series.ewm(span=period).mean()


def rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    gain = pd.Series(gain).rolling(period).mean()
    loss = pd.Series(loss).rolling(period).mean()

    rs = gain / loss
    return 100 - (100 / (1 + rs))


def macd(series):
    ema12 = ema(series, 12)
    ema26 = ema(series, 26)

    macd_line = ema12 - ema26
    signal_line = ema(macd_line, 9)

    return macd_line, signal_line


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

    if df is None:
        return {"signal": "DATA ERROR", "strength": "LOW"}

    close = df["close"]

    ema9 = ema(close, 9)
    ema21 = ema(close, 21)
    ema50 = ema(close, 50)
    ema100 = ema(close, 100)

    rsi_val = rsi(close).iloc[-1]
    macd_line, macd_signal = macd(close)
    atr_val = atr(df).iloc[-1]

    score = 0

    # Trend
    if ema9.iloc[-1] > ema21.iloc[-1] > ema50.iloc[-1] > ema100.iloc[-1]:
        score += 3
    elif ema9.iloc[-1] < ema21.iloc[-1] < ema50.iloc[-1] < ema100.iloc[-1]:
        score -= 3

    # RSI
    if 55 <= rsi_val <= 70:
        score += 2
    elif 30 <= rsi_val <= 45:
        score -= 2

    # MACD
    if macd_line.iloc[-1] > macd_signal.iloc[-1]:
        score += 2
    else:
        score -= 2

    # Momentum
    if close.iloc[-1] > close.iloc[-2]:
        score += 1
    else:
        score -= 1

    # Volatility filter
    if atr_val < close.mean() * 0.0004:
        return {
            "signal": "AVOID ⚠️",
            "strength": "LOW"
        }

    # Final decision
    if score >= 5:
        return {
            "signal": "BUY 📈",
            "strength": "HIGH"
        }
    elif score <= -5:
        return {
            "signal": "SELL 📉",
            "strength": "HIGH"
        }
    else:
        return {
            "signal": "AVOID ⚠️",
            "strength": "LOW"
        }


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

        .row {
            margin-top: 10px;
            color: #cbd5e1;
        }

        .signal {
            margin-top: 20px;
            padding: 15px;
            background: #111827;
            border-radius: 10px;
            font-size: 20px;
        }

        button {
            margin-top: 20px;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            background: #22c55e;
            color: white;
            font-size: 16px;
            cursor: pointer;
        }

        button:hover {
            background: #16a34a;
        }
    </style>
</head>

<body>

<div class="box">

    <div class="title">Abhi's Signal Engine</div>

    <div class="row">EUR/USD | 1 Minute Timeframe</div>

    <div class="signal" id="signalBox">
        Click Get Signal
    </div>

    <button onclick="getSignal()">Get Signal</button>

</div>

<script>
async function getSignal() {
    const res = await fetch("/signal");
    const data = await res.json();

    let text = data.signal + " | " + data.strength + " Confidence";

    document.getElementById("signalBox").innerText = text;
}
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
