import asyncio
import httpx
from fastapi import FastAPI
from telegram import Bot

# Replace with your actual bot token and chat ID
TELEGRAM_BOT_TOKEN = "7934074261:AAFtAdnwJKLh_iercRs-qtvqknTmLKG0vV4"
TELEGRAM_CHAT_ID = "7559598079"

app = FastAPI()
bot = Bot(token=TELEGRAM_BOT_TOKEN)

bybit_base_url = "https://api.bybit.com"

async def fetch_symbols(session):
    url = f"{bybit_base_url}/v5/market/instruments-info?category=linear"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }
    print("Fetching symbols...", flush=True)
    resp = await session.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    symbols = [
        i["symbol"] for i in data["result"]["list"]
        if "USDT" in i["symbol"] and i["symbol"].endswith("USDT")
    ]
    print(f"Fetched {len(symbols)} symbols", flush=True)
    return symbols

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

async def monitor():
    async with httpx.AsyncClient(timeout=10.0) as session:
        symbols = await fetch_symbols(session)
        for symbol in symbols:
            try:
                klines = await fetch_kline(session, symbol)
                if len(klines) < 32:
                    print(f"Not enough klines for {symbol}, skipping", flush=True)
                    continue

                vols = [float(k[5]) for k in klines[:-2]]  # exclude last 2 candles
                avg_vol = sum(vols[-30:]) / 30
                candle_x = klines[-3]  # candle X
                x_vol = float(candle_x[5])
                x_high = float(candle_x[3])
                x_low = float(candle_x[4])

                c1 = klines[-2]
                c2 = klines[-1]

                # Check if price stayed within candle_x range for last 2 candles
                for c in [c1, c2]:
                    high = float(c[3])
                    low = float(c[4])
                    if high > x_high or low < x_low:
                        # Price left range
                        break
                else:
                    # Price stayed within range
                    if x_vol >= 2 * avg_vol:
                        text = (f"\u26A1 Volume Spike on {symbol}\n"
                                f"Volume: {x_vol:.2f} (>{2*avg_vol:.2f} avg)\n"
                                f"Range held for 2 min: {x_low:.4f} - {x_high:.4f}")
                        print(f"Sending alert for {symbol}:\n{text}", flush=True)
                        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
            except Exception as e:
                print(f"Error processing {symbol}: {e}", flush=True)

@app.on_event("startup")
async def startup_event():
    print("App startup: launching monitor loop", flush=True)
    loop = asyncio.get_event_loop()
    loop.create_task(safe_monitor())

async def safe_monitor():
    while True:
        try:
            await monitor()
        except Exception as e:
            print("Error in monitor():", e, flush=True)
        await asyncio.sleep(60)  # Run every minute

@app.get("/")
async def root():
    return {"status": "running"}

@app.get("/test")
async def test_alert():
    print("Test endpoint hit: sending Telegram message", flush=True)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="\u2705 Telegram bot is working!")
    return {"status": "test message sent"}
