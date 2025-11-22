# ====== БОТ ДЛЯ ZULUBET + FOREBET С SELENIUM ======
# Работает на Render
# Selenium + Chrome (headless)

import os
import time
import datetime
import threading
import telebot
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import chromedriver_autoinstaller
import requests
from bs4 import BeautifulSoup

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
#    FOREBET ПАРСЕР (Selenium)
# ================================
def load_forebet():
    global forebet_cache, last_forebet_update
    print("[Forebet] Обновляю данные...")

    try:
        chromedriver_autoinstaller.install()

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--ignore-certificate-errors")

        driver = webdriver.Chrome(options=options)
        driver.get("https://www.forebet.com/en/football-tips")

        time.sleep(3)  # подождать загрузку страницы

        matches = []
        rows = driver.find_elements(By.CSS_SELECTOR, "div.rcnt")
        for row in rows:
            try:
                teams = row.find_element(By.CSS_SELECTOR, "span.homeTeam").text.strip() + " - " + \
                        row.find_element(By.CSS_SELECTOR, "span.awayTeam").text.strip()
                prediction = row.find_element(By.CSS_SELECTOR, "div.prediction div.value").text.strip()
                probability = row.find_element(By.CSS_SELECTOR, "div.prob span.value").text.strip()
                matches.append({
                    "teams": teams,
                    "prediction": prediction,
                    "prob": int(probability.replace("%", ""))
                })
            except:
                continue

        forebet_cache = matches
        last_forebet_update = datetime.datetime.utcnow()
        print(f"[Forebet] Загружено матчей: {len(matches)}")

        driver.quit()
        return True

    except Exception as e:
        print("Forebet error:", e)
        return False

# ===================================================
#    ZULUBET ПАРСЕР (requests)
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
    bot.infinity_polling()
