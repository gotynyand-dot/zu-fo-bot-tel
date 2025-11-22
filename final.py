# ПОЛНАЯ ВЕРСИЯ СКРИПТА БЕЗ SELENIUM
# ====== БОТ ДЛЯ ZULUBET + FOREBET ======
# Работает на Render
# Использует requests + BeautifulSoup вместо Selenium

import requests
from bs4 import BeautifulSoup
import time
import datetime
import telebot
import threading
import os

# ====================
#    НАСТРОЙКИ БОТА
# ====================
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))

bot = telebot.TeleBot(TOKEN)

# ====================
#    ГЛОБАЛЬНЫЕ ДАННЫЕ
# ====================
forebet_cache = []
last_forebet_update = None

# ================================
#    FOREBET ПАРСЕР (requests)
# ================================
def load_forebet():
    global forebet_cache, last_forebet_update
    print("[Forebet] Обновляю данные...")

    url = "https://www.forebet.com/en/football-tips-and-predictions-for-today"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print("[Forebet] Ошибка загрузки страницы", response.status_code)
            return False

        soup = BeautifulSoup(response.text, "html.parser")
        matches = []

        # На Forebet таблица с матчами в <table class="table-tip">
        table = soup.find("table", {"class": "table-tip"})
        if not table:
            print("[Forebet] Таблица матчей не найдена")
            return False

        for row in table.find_all("tr")[1:]:  # пропускаем заголовок
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            try:
                teams = cols[0].text.strip()
                prediction = cols[1].text.strip()
                prob_text = cols[2].text.strip()
                prob = int(prob_text.replace("%", "")) if "%" in prob_text else 0

                matches.append({
                    "teams": teams,
                    "prediction": prediction,
                    "prob": prob
                })
            except Exception as e:
                continue

        forebet_cache = matches
        last_forebet_update = datetime.datetime.utcnow()
        print(f"[Forebet] Загружено матчей: {len(matches)}")
        return True

    except Exception as e:
        print("Forebet error:", e)
        return False

# ===================================================
#    ZULUBET ПАРСЕР (у тебя он уже был рабочий)
# ===================================================
def load_zulubet():
    url = "https://www.zulubet.com/tips"
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(response.text, "html.parser")

        matches = []
        for row in soup.select("table.tips > tr")[1:]:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            team1 = cols[0].text.strip()
            team2 = cols[1].text.strip()
            prediction = cols[2].text.strip()
            odd = cols[3].text.strip()

            matches.append({
                "teams": f"{team1} - {team2}",
                "prediction": prediction,
                "odd": odd
            })

        print(f"[Zulubet] Найдено матчей: {len(matches)}")
        return matches

    except Exception as e:
        print("Zulubet error:", e)
        return []

# ================================================
#         СРАВНЕНИЕ FOREBET + ZULUBET
# ================================================
def compare_matches():
    zulubet_matches = load_zulubet()
    results = []

    for z in zulubet_matches:
        for f in forebet_cache:
            if z["teams"].lower() == f["teams"].lower() and f["prob"] >= 60:
                results.append((z, f))

    return results

# ====================
#   ОСНОВНОЙ ЦИКЛ
# ====================
def loop_forebet():
    while True:
        load_forebet()
        time.sleep(4 * 3600)  # 4 часа

def loop_compare():
    while True:
        if not forebet_cache:
            print("[Loop] Forebet пуст — жду обновления...")
        else:
            matches = compare_matches()
            if matches:
                for z, f in matches:
                    text = (
                        "🔥 СОВПАДЕНИЕ НАЙДЕНО!🔥\n"
                        f"⚽ Матч: {z['teams']}\n"
                        f"🔵 Forebet: {f['prediction']} ({f['prob']}%)\n"
                        f"🟢 Zulubet: {z['prediction']} | Коэффициент: {z['odd']}"
                    )
                    bot.send_message(CHAT_ID, text)
            else:
                print("[Loop] Совпадений нет.")

        time.sleep(30 * 60)  # 30 минут

# ============================
#    СТАРТ БОТА НА RENDER
# ============================
@bot.message_handler(commands=["start"])
def start_command(message):
    bot.reply_to(message, "Бот работает на сервере Render!")

def start_threads():
    threading.Thread(target=loop_forebet, daemon=True).start()
    threading.Thread(target=loop_compare, daemon=True).start()
    threading.Thread(
        target=lambda: bot.infinity_polling(timeout=60, long_polling_timeout=60),
        daemon=True
    ).start()

if __name__ == "__main__":
    print("Бот запущен.")
    start_threads()
