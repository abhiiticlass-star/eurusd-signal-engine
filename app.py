from flask import Flask, jsonify, render_template_string
import yfinance as yf
import pandas as pd
import numpy as np
import time

app = Flask(__name__)

SYMBOL = "EURUSD=X"

# ---------- CACHE ----------
cache = {"time": 0, "data": None}
CACHE_TIME = 60


# ---------- REAL DATA ----------
def get_data():
    try:
        if cache["data"] is not None and time.time() - cache["time"] < CACHE_TIME:
            return cache["data"]

        df = yf.download(SYMBOL, interval="5m", period="5d", progress=False)

        if df is None or df.empty:
            return "DATA_ERROR"

        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close"
        })

        df = df.dropna().reset_index()

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
        return {"signal": "DATA ERROR ❌", "strength": "NO DATA"}

    if df == "BACKEND_CRASH":
        return {"signal": "BACKEND CRASH ❌", "strength": "SERVER ISSUE"}

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

        # ---------- TREND FILTER (STRONG WEIGHT) ----------
        if ema9.iloc[-1] > ema21.iloc[-1] > ema50.iloc[-1]:
            score += 4
        elif ema9.iloc[-1] < ema21.iloc[-1] < ema50.iloc[-1]:
            score -= 4

        # ---------- RSI FILTER ----------
        if 50 < rsi_val < 65:
            score += 2
        elif 35 < rsi_val < 50:
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

        # ---------- VOLATILITY FILTER ----------
        if atr_val < close.mean() * 0.0004:
            return {"signal": "AVOID ⚠️", "strength": "LOW VOLATILITY"}

        # ---------- FINAL DECISION ----------
        if score >= 6:
            return {"signal": "CALL 📈", "strength": "HIGH CONFIDENCE"}

        elif score <= -6:
            return {"signal": "PUT 📉", "strength": "HIGH CONFIDENCE"}

        else:
            return {"signal": "AVOID ⚠️", "strength": "LOW CONFIDENCE"}

    except:
        return {"signal": "BACKEND CRASH ❌", "strength": "LOGIC ERROR"}
