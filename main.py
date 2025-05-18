import time
import asyncio
import aiohttp
from datetime import datetime, timedelta
from telegram import Bot
from fastapi import FastAPI
import uvicorn

app = FastAPI()

TELEGRAM_BOT_TOKEN = 'your_telegram_bot_token'
TELEGRAM_CHAT_ID = 'your_chat_id'
bot = Bot(token=TELEGRAM_BOT_TOKEN)

BYBIT_BASE_URL = 'https://api.bybit.com'

HEADERS = {
    'User-Agent': 'volume-alert-bot'
}

CHECK_INTERVAL = 60  # seconds

async def fetch_symbols(session):
    url = f"{BYBIT_BASE_URL}/v5/market/instruments-info?category=linear"
    async with session.get(url, headers=HEADERS) as resp:
        data = await resp.json()
        return [item['symbol'] for item in data['result']['list'] if 'USDT' in item['symbol']]

async def fetch_candles(session, symbol):
    url = f"{BYBIT_BASE_URL}/v5/market/kline?category=linear&symbol={symbol}&interval=1&limit=35"
    async with session.get(url, headers=HEADERS) as resp:
        data = await resp.json()
        return data['result']['list']

async def check_volume_spike(session, symbol):
    try:
        candles = await fetch_candles(session, symbol)
        if len(candles) < 32:
            return

        last_candle = candles[-3]  # Candle X (3rd last)
        volume_x = float(last_candle[5])
        high_x = float(last_candle[3])
        low_x = float(last_candle[4])
        avg_volume = sum(float(c[5]) for c in candles[-33:-3]) / 30

        if volume_x >= 2 * avg_volume:
            price_1 = float(candles[-2][1])
            price_2 = float(candles[-1][1])
            if low_x <= price_1 <= high_x and low_x <= price_2 <= high_x:
                message = (
                    f"🔔 Volume Spike Alert on {symbol}\n"
                    f"Time: {datetime.utcfromtimestamp(int(last_candle[0]) / 1000)} UTC\n"
                    f"Volume: {volume_x:.2f} (avg: {avg_volume:.2f})\n"
                    f"Price Range: {low_x:.4f} - {high_x:.4f}"
                )
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as e:
        print(f"Error checking {symbol}: {e}")

async def monitor():
    while True:
        async with aiohttp.ClientSession() as session:
            symbols = await fetch_symbols(session)
            tasks = [check_volume_spike(session, symbol) for symbol in symbols]
            await asyncio.gather(*tasks)
        await asyncio.sleep(CHECK_INTERVAL)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(monitor())

@app.get("/")
def read_root():
    return {"status": "running"}

if __name__ == "__main__":
    uvicorn.run("bybit_volume_alert_bot:app", host="0.0.0.0", port=8000, reload=False)
