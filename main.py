import asyncio
import httpx
from fastapi import FastAPI
from telegram import Bot

# Your bot token and chat ID
TELEGRAM_BOT_TOKEN = "7934074261:AAFtAdnwJKLh_iercRs-qtvqknTmLKG0vV4"
TELEGRAM_CHAT_ID = "7559598079"

app = FastAPI()
bot = Bot(token=TELEGRAM_BOT_TOKEN)

bybit_base_url = "https://api.bybit.com"
binance_base_url = "https://fapi.binance.com"

async def fetch_bybit_symbols(session):
    url = f"{bybit_base_url}/v5/market/instruments-info?category=linear"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Referer": "https://www.bybit.com/",
    }
    try:
        resp = await session.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        symbols = [
            i["symbol"] for i in data["result"]["list"]
            if "USDT" in i["symbol"] and i["symbol"].endswith("USDT")
        ]
        print(f"[Bybit] Fetched {len(symbols)} symbols")
        return symbols
    except httpx.HTTPStatusError as exc:
        text = f"[Bybit] HTTP error {exc.response.status_code}: {exc.response.text}"
        print(text)
        return None
    except Exception as e:
        print(f"[Bybit] Exception fetching symbols: {e}")
        return None

async def fetch_bybit_klines(session, symbol):
    url = f"{bybit_base_url}/v5/market/kline?category=linear&symbol={symbol}&interval=1&limit=32"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Referer": "https://www.bybit.com/",
    }
    try:
        resp = await session.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["result"]["list"]
    except Exception as e:
        print(f"[Bybit] Exception fetching klines for {symbol}: {e}")
        return None

# Fallback Binance Futures symbol fetcher
async def fetch_binance_symbols(session):
    url = f"{binance_base_url}/fapi/v1/exchangeInfo"
    try:
        resp = await session.get(url)
        resp.raise_for_status()
        data = resp.json()
        symbols = [item["symbol"] for item in data["symbols"] if item["contractType"] == "PERPETUAL" and item["quoteAsset"] == "USDT"]
        print(f"[Binance] Fetched {len(symbols)} symbols")
        return symbols
    except Exception as e:
        print(f"[Binance] Exception fetching symbols: {e}")
        return None

async def fetch_binance_klines(session, symbol):
    url = f"{binance_base_url}/fapi/v1/klines?symbol={symbol}&interval=1m&limit=32"
    try:
        resp = await session.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data
    except Exception as e:
        print(f"[Binance] Exception fetching klines for {symbol}: {e}")
        return None

async def monitor():
    async with httpx.AsyncClient(timeout=10.0) as session:
        # Try Bybit first
        symbols = await fetch_bybit_symbols(session)
        use_binance = False
        if not symbols:
            print("[Monitor] Bybit symbols fetch failed, switching to Binance")
            symbols = await fetch_binance_symbols(session)
            use_binance = True

        if not symbols:
            print("[Monitor] No symbols to process, skipping cycle")
            return

        print(f"[Monitor] Checking {len(symbols)} symbols")

        for symbol in symbols:
            try:
                klines = None
                if use_binance:
                    klines = await fetch_binance_klines(session, symbol)
                    if klines is None or len(klines) < 32:
                        continue
                    vols = [float(k[5]) for k in klines[:-2]]  # volume index 5 in Binance data
                    avg_vol = sum(vols[-30:]) / 30
                    candle_x = klines[-3]
                    x_vol = float(candle_x[5])
                    x_high = float(candle_x[2])
                    x_low = float(candle_x[3])

                    c1 = klines[-2]
                    c2 = klines[-1]

                    # price stays in candle x range for last 2 candles
                    if all(float(c[2]) <= x_high and float(c[3]) >= x_low for c in [c1, c2]):
                        if x_vol >= 2 * avg_vol:
                            text = f"⚡ Binance Volume Spike on {symbol}\n" \
                                   f"Volume: {x_vol:.2f} (> {2*avg_vol:.2f} avg)\n" \
                                   f"Range held for 2 min: {x_low:.4f} - {x_high:.4f}"
                            print(text)
                            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)

                else:
                    klines = await fetch_bybit_klines(session, symbol)
                    if klines is None or len(klines) < 32:
                        continue
                    vols = [float(k[5]) for k in klines[:-2]]  # volume at index 5 for Bybit
                    avg_vol = sum(vols[-30:]) / 30
                    candle_x = klines[-3]
                    x_vol = float(candle_x[5])
                    x_high = float(candle_x[3])
                    x_low = float(candle_x[4])

                    c1 = klines[-2]
                    c2 = klines[-1]

                    # price stays in candle x range for last 2 candles
                    if all(float(c[3]) <= x_high and float(c[4]) >= x_low for c in [c1, c2]):
                        if x_vol >= 2 * avg_vol:
                            text = f"⚡ Bybit Volume Spike on {symbol}\n" \
                                   f"Volume: {x_vol:.2f} (> {2*avg_vol:.2f} avg)\n" \
                                   f"Range held for 2 min: {x_low:.4f} - {x_high:.4f}"
                            print(text)
                            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
            except Exception as e:
                print(f"[Monitor] Error processing {symbol}: {e}")

@app.on_event("startup")
async def startup_event():
    print("[Startup] Starting monitoring loop...")
    loop = asyncio.get_event_loop()
    loop.create_task(safe_monitor())

async def safe_monitor():
    cycle = 0
    while True:
        cycle += 1
        print(f"[Monitor] Starting cycle {cycle}...")
        try:
            await monitor()
        except Exception as e:
            print(f"[Monitor] Exception in monitor: {e}")
        await asyncio.sleep(60)

@app.get("/")
async def root():
    return {"status": "running"}

@app.get("/test")
async def test_alert():
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="✅ Telegram bot is working!")
    return {"status": "test message sent"}
