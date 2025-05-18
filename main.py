import asyncio
import httpx
from fastapi import FastAPI
from telegram import Bot
import os

TELEGRAM_BOT_TOKEN = "7934074261:AAFtAdnwJKLh_iercRs-qtvqknTmLKG0vV4"
TELEGRAM_CHAT_ID = "7559598079"

app = FastAPI()
bot = Bot(token=TELEGRAM_BOT_TOKEN)

bybit_base_url = "https://api.bybit.com"

# Fetch all USDT perp futures symbols
async def fetch_symbols(session):
    url = f"{bybit_base_url}/v5/market/instruments-info?category=linear"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }
    resp = await session.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    symbols = [
        i["symbol"] for i in data["result"]["list"]
        if "USDT" in i["symbol"] and i["symbol"].endswith("USDT")
    ]
    return symbols

# Fetch recent kline data for a symbol
async def fetch_kline(session, symbol):
    url = f"{bybit_base_url}/v5/market/kline?category=linear&symbol={symbol}&interval=1&limit=32"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }
    resp = await session.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    return data["result"]["list"]

# Core monitoring logic
async def monitor(cycle_counter):
    print("Starting a new monitoring cycle...", flush=True)
    async with httpx.AsyncClient(timeout=10.0) as session:
        symbols = await fetch_symbols(session)

        print(f"Checking {len(symbols)} symbols", flush=True)
        for symbol in symbols:
            print(f"Checking symbol: {symbol}", flush=True)
            try:
                klines = await fetch_kline(session, symbol)
                if len(klines) < 32:
                    continue

                vols = [float(k[5]) for k in klines[:-2]]  # exclude last 2 candles
                avg_vol = sum(vols[-30:]) / 30
                candle_x = klines[-3]  # the one before last 2 candles
                x_vol = float(candle_x[5])
                x_high = float(candle_x[3])
                x_low = float(candle_x[4])

                c1 = klines[-2]
                c2 = klines[-1]
                for c in [c1, c2]:
                    high = float(c[3])
                    low = float(c[4])
                    if high > x_high or low < x_low:
                        break  # price left the range
                else:
                    if x_vol >= 2 * avg_vol:
                        text = f"\u26a1 Volume Spike on {symbol}\n" \
                               f"Volume: {x_vol:.2f} (>{2*avg_vol:.2f} avg)\n" \
                               f"Range held for 2 min: {x_low:.4f} - {x_high:.4f}"
                        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
            except Exception as e:
                print(f"Error processing {symbol}: {e}", flush=True)

    # Send heartbeat Telegram message every 10 cycles
    if cycle_counter % 10 == 0:
        try:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"✅ Bot is alive. Completed {cycle_counter} monitoring cycles.")
        except Exception as e:
            print(f"Failed to send heartbeat message: {e}", flush=True)


@app.on_event("startup")
async def startup_event():
    loop = asyncio.get_event_loop()
    loop.create_task(safe_monitor())

async def safe_monitor():
    cycle_counter = 1
    while True:
        print(f"Running monitor cycle {cycle_counter}...", flush=True)
        try:
            await monitor(cycle_counter)
        except Exception as e:
            print("Error in monitor():", e, flush=True)
        cycle_counter += 1
        await asyncio.sleep(60)

@app.get("/")
async def root():
    return {"status": "running"}

@app.get("/test")
async def test_alert():
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="\u2705 Telegram bot is working!")
    return {"status": "test message sent"}
