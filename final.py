#!/usr/bin/env python3
# coding: utf-8
"""
final.py
Парсер Zulubet + Forebet через Scrape.do + отправка в Telegram.
Forebet парсится через Scrape.do (HTTP запрос + HTML), без Selenium/Playwright.
"""

import os
import re
import time
import traceback
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

# ===============================
# 🔹 Настройки Telegram и Scrape.do
# ===============================
TOKEN = os.environ.get("TG_BOT_TOKEN") or "8353200396:AAEYPs8RmdEUfsK6lG1U3kve3fjL-oAIR3I"
CHAT_ID = int(os.environ.get("TG_CHAT_ID") or "293637253")
SCRAPE_DO_API_KEY = os.environ.get("SCRAPE_DO_API_KEY") or "83fd56a86b214950b688fa0adbf06682ee7310b61e2"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, data=payload, timeout=20)
        if not response.ok:
            print("Ошибка при отправке в Telegram:", response.text)
    except Exception as e:
        print("Ошибка HTTP при отправке в Telegram:", e)


# ===============================
# 🔹 Вспомогательные функции
# ===============================
def normalize_team_name(name: str):
    name = re.sub(r'[^a-zA-Z0-9\s\-]', '', str(name)).lower()
    words = name.split()
    ignore = {
        'town','city','county','borough','united','district','state',
        'fc','afc','cf','sc','ac','bc','rc','cd','sd','ud',
        'fk','nk','ks',
        'u17','u18','u19','u20','u21','u23',
        'b','ii','reserve','reserves',
        'club','team','sporting',
        'sv','tsv','vfb','vfl','sg','spvgg'
    }
    return [w for w in words if w not in ignore and len(w) > 2]

def teams_match(z_team: str, f_team: str) -> bool:
    z_words = normalize_team_name(z_team)
    f_words = normalize_team_name(f_team)
    return any(zw in f_words for zw in z_words)


# ===============================
# 🔹 Парсинг Zulubet
# ===============================
def parse_zulubet():
    url = "https://www.zulubet.com/"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print("Ошибка при загрузке Zulubet:", e)
        return []

    main_table = soup.select_one("table.content_tables.main_table")
    if not main_table:
        print("Не удалось найти таблицу матчей на Zulubet.")
        return []

    rows = main_table.find_all("tr")[2:]
    results = []

    for row in rows:
        try:
            cells = row.find_all("td")
            if len(cells) < 6:
                continue

            script_tag = cells[0].find("script")
            raw_time = (
                script_tag.string.strip().replace("mf_usertime('","").replace("');","")
                if script_tag else "?"
            )

            try:
                dt = datetime.strptime(raw_time, "%m/%d/%Y, %H:%M") + timedelta(hours=1)
                time_str = dt.strftime("%d/%m %H:%M")
            except:
                time_str = raw_time

            match = cells[1].find("a").text.strip()

            def extract_percent(text):
                return int(text.split(":")[1].replace("%","").strip())

            p1 = extract_percent(cells[3].text)
            px = extract_percent(cells[4].text)
            p2 = extract_percent(cells[5].text)

            if p1 >= 60 or px >= 60 or p2 >= 60:
                parts = re.split(r'\s*-\s*', match)
                home = parts[0].strip()
                away = parts[1].strip() if len(parts) > 1 else "?"
                results.append({
                    "time": time_str,
                    "home": home,
                    "away": away,
                    "text": f"{time_str} ⚽️ {match}  {p1}-{px}-{p2}"
                })
        except Exception as e:
            print("Ошибка в Zulubet:", e)

    return results


# ===============================
# 🔹 Парсинг Forebet через Scrape.do
# ===============================
def fetch_forebet_via_scrape_do(page="today"):
    url = f"https://www.forebet.com/en/football-tips-and-predictions-for-{page}"
    api_url = f"https://api.scrape.do/?token={SCRAPE_DO_API_KEY}&url={url}&render=true"
    try:
        r = requests.get(api_url, timeout=30)
        if r.status_code != 200:
            print("Scrape.do вернул статус:", r.status_code)
            return []
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print("Ошибка Scrape.do:", e)
        return []

    results = []
    rows = soup.select(".rcnt")
    for row in rows:
        try:
            home = row.select_one(".homeTeam span").text.strip()
            away = row.select_one(".awayTeam span").text.strip()
            probs = row.select(".fprc span")
            p1 = int(probs[0].text.replace("%",""))
            px = int(probs[1].text.replace("%",""))
            p2 = int(probs[2].text.replace("%",""))
            ex_score = row.select_one(".ex_sc").text.strip() if row.select_one(".ex_sc") else ""
            date = row.select_one("time .date_bah").text.strip() if row.select_one("time .date_bah") else ""
            results.append({
                "time": date,
                "home": home,
                "away": away,
                "p1": p1,
                "px": px,
                "p2": p2,
                "score": ex_score
            })
        except:
            continue
    return results


# ===============================
# 🔹 In-memory cache Forebet (30 min)
# ===============================
forebet_cache = []
last_update = None
FOREBET_UPDATE_INTERVAL = timedelta(minutes=30)

def update_forebet_cache(force=False):
    global forebet_cache, last_update
    now = datetime.utcnow()

    if not force and last_update is not None and (now - last_update) < FOREBET_UPDATE_INTERVAL:
        return False

    print("Обновляю Forebet (Scrape.do)...")
    items = fetch_forebet_via_scrape_do("today") + fetch_forebet_via_scrape_do("tomorrow")

    if items:
        forebet_cache = items
        last_update = datetime.utcnow()
        print(f"Кеш Forebet обновлён: {len(items)} матчей (время {last_update})")
        return True
    else:
        print("Forebet-парсер вернул 0 матчей — кеш НЕ обновлён.")
        return False


# ===============================
# 🔁 Основной цикл
# ===============================
def main_loop():
    print("Скрипт запущен. Forebet обновляется каждые 30 минут; сравнение — каждые 30 минут.\n")
    update_forebet_cache(force=True)

    while True:
        try:
            update_forebet_cache()  # теперь проверяется каждые 30 минут автоматически

            zulubet_results = parse_zulubet()
            forebet_results = forebet_cache

            forebet_results_filtered = [
                f for f in forebet_results if f.get('p1',0) >= 60 or f.get('px',0) >= 60 or f.get('p2',0) >= 60
            ]

            print(f"Zulubet: найдено {len(zulubet_results)} матчей")
            print(f"Forebet ≥60%: {len(forebet_results_filtered)} матчей")

            combined_matches = []

            for z in zulubet_results:
                f1_matches = [f for f in forebet_results_filtered if teams_match(z["home"], f["home"])]
                f2_matches = [f for f in forebet_results_filtered if teams_match(z["away"], f["away"])]

                if f1_matches or f2_matches:
                    combined_matches.append(f"Z:{z['text']}")
                    for f in f1_matches:
                        combined_matches.append(
                            f"F1T:{f['time']} {f['home']} vs {f['away']}  {f['p1']}-{f['px']}-{f['p2']}  {f.get('score','')}"
                        )
                    for f in f2_matches:
                        combined_matches.append(
                            f"F2T:{f['time']} {f['home']} vs {f['away']}  {f['p1']}-{f['px']}-{f['p2']}  {f.get('score','')}"
                        )
                    if f1_matches and f2_matches:
                        combined_matches.append("🔥 Полное совпадение по обеим командам!")
                    combined_matches.append("")

            if combined_matches:
                send_telegram_message("\n".join(combined_matches))
                print("✅ Совпадения найдены и отправлены.")
            else:
                print("— Совпадений нет.")

        except Exception as e:
            print("Ошибка в основном цикле:", e)
            traceback.print_exc()

        print("\nОжидание 30 минут...\n")
        time.sleep(1800)


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("Завершение по Ctrl+C")
    except Exception as e:
        print("Критическая ошибка:", e)
        traceback.print_exc()
