from flask import Flask, jsonify
import requests
import pandas as pd
import numpy as np
import time
import os

app = Flask(__name__)

API_KEY = "DYASXHAJUXF7XLGN"
SYMBOL = "EURUSD"
INTERVAL = "1min"

cache = {"time": 0, "data": None}
CACHE_TIME = 60


# ---------- DATA FETCH (ALPHA VANTAGE) ----------
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

        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col])

        df = df.sort_index()
        df = df.reset_index(drop=True)

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

    if df == "DATA_ERROR":
        return {"signal": "API LIMIT / NO DATA ❌", "strength": "CHECK ALPHA VANTAGE LIMIT"}

    if df == "BACKEND_CRASH":
        return {"signal": "BACKEND CRASH ❌", "strength": "SERVER ERROR"}

    try:
        close = df["close"]

        ema9 = ema(close, 9)
        ema21 = ema(close, 21)
        ema50 = ema(close, 50)

        rsi_val = rsi(close).iloc[-1]
        macd_line, macd_signal = macd(close)
        atr_val = atr(df).iloc[-1]

        if pd.isna(atr_val) or pd.isna(rsi_val):
            return {"signal": "AVOID ⚠️", "strength": "INSUFFICIENT DATA"}

        score = 0

        # TREND
        if ema9.iloc[-1] > ema21.iloc[-1] > ema50.iloc[-1]:
            score += 4
        elif ema9.iloc[-1] < ema21.iloc[-1] < ema50.iloc[-1]:
            score -= 4

        # RSI
        if 50 < rsi_val < 65:
            score += 2
        elif 35 < rsi_val < 50:
            score -= 2

        # MACD
        if macd_line.iloc[-1] > macd_signal.iloc[-1]:
            score += 3
        else:
            score -= 3

        # MOMENTUM
        if close.iloc[-1] > close.iloc[-3]:
            score += 1
        else:
            score -= 1

        # VOLATILITY FILTER
        if atr_val < close.mean() * 0.0004:
            return {"signal": "AVOID ⚠️", "strength": "LOW VOLATILITY"}

        # FINAL DECISION
        if score >= 6:
            return {"signal": "CALL 📈", "strength": "HIGH CONFIDENCE"}
        elif score <= -6:
            return {"signal": "PUT 📉", "strength": "HIGH CONFIDENCE"}
        else:
            return {"signal": "AVOID ⚠️", "strength": "LOW CONFIDENCE"}

    except:
        return {"signal": "BACKEND CRASH ❌", "strength": "LOGIC ERROR"}


# ---------- ROUTES ----------
@app.route("/")
def home():
    return "<h2>EUR/USD Signal Engine (Alpha Vantage) ✅</h2>"


@app.route("/signal")
def signal():
    return jsonify(generate_signal())


# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
