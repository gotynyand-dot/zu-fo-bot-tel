#!/usr/bin/env python3
# coding: utf-8
"""
final.py
Playwright-версия парсера Forebet + Zulubet + Telegram отправка.
Заменена только часть, связанная с Selenium -> Playwright.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import time
import os
import sys
import traceback

# Playwright
from playwright.sync_api import sync_playwright

# ===============================
# 🔹 Настройки Telegram (через env переменные — безопасно)
# ===============================
# Рекомендую настроить эти переменные в Render (Dashboard -> Environment)
TOKEN = os.environ.get("TG_BOT_TOKEN") or "8353200396:AAEYPs8RmdEUfsK6lG1U3kve3fjL-oAIR3I"
CHAT_ID = int(os.environ.get("TG_CHAT_ID") or "293637253")

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
    """Очищает название команды и убирает служебные слова"""
    name = re.sub(r'[^a-zA-Z0-9\s\-]', '', str(name)).lower()
    words = name.split()
    ignore = {
        'town', 'city', 'county', 'borough', 'united', 'district', 'state',
        'fc', 'afc', 'cf', 'sc', 'ac', 'bc', 'rc', 'cd', 'sd', 'ud',
        'fk', 'nk', 'ks',
        'u17', 'u18', 'u19', 'u20', 'u21', 'u23',
        'b', 'ii', 'reserve', 'reserves',
        'club', 'team', 'sporting',
        'sv', 'tsv', 'vfb', 'vfl', 'sg', 'spvgg'
    }
    return [w for w in words if w not in ignore and len(w) > 2]

def teams_match(z_team: str, f_team: str) -> bool:
    """Проверяет, есть ли совпадение по хотя бы одному слову"""
    z_words = normalize_team_name(z_team)
    f_words = normalize_team_name(f_team)
    return any(zw in f_words for zw in z_words)

# ===============================
# 🔹 Парсинг Zulubet (оставил как было)
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
                script_tag.string.strip()
                .replace("mf_usertime('", "")
                .replace("');", "")
                if script_tag else "?"
            )

            try:
                dt = datetime.strptime(raw_time, "%m/%d/%Y, %H:%M") + timedelta(hours=1)
                time_str = dt.strftime("%d/%m %H:%M")
            except:
                time_str = raw_time

            match = cells[1].find("a").text.strip()

            def extract_percent(text):
                return int(text.split(":")[1].replace("%", "").strip())

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
# 🔹 Парсер Forebet (Playwright)
# ===============================
def fetch_forebet_via_playwright():
    results = []

    urls = [
        "https://www.forebet.com/en/football-tips-and-predictions-for-today",
        "https://www.forebet.com/en/football-tips-and-predictions-for-tomorrow"
    ]

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            for url in urls:
                try:
                    print(f"\n===== Парсинг сайта: {url} =====\n")
                    page.goto(url, timeout=60000, wait_until="domcontentloaded")
                except Exception as e:
                    print("Ошибка загрузки страницы Forebet:", e)
                    continue

                # Закрываем cookies если есть (адаптируй селектор при необходимости)
                try:
                    # разные сайты могут иметь разные селекторы; пробуем несколько
                    page.click(".fc-button.fc-cta-consent", timeout=3000)
                    print("Нажал 'Соглашаюсь' (селектор .fc-button.fc-cta-consent)")
                except:
                    try:
                        page.click(".fc-button-label", timeout=3000)
                        print("Нажал 'Соглашаюсь' (селектор .fc-button-label)")
                    except:
                        print("Кнопка 'Соглашаюсь' не найдена.")

                # Жмём кнопку More, если есть
                try:
                    page.click("xpath=//span[contains(@onclick, 'ltodrows')]", timeout=4000)
                    page.wait_for_timeout(3000)
                except:
                    print("Кнопка MORE не найдена или не кликабельна.")

                rows = page.locator(".rcnt")
                try:
                    count = rows.count()
                except Exception:
                    count = 0
                print(f"Найдено матчей: {count}")

                for i in range(count):
                    try:
                        row = rows.nth(i)
                        try:
                            date = row.locator("time .date_bah").inner_text().strip()
                        except:
                            date = ""

                        try:
                            home = row.locator(".homeTeam span").inner_text().strip()
                            away = row.locator(".awayTeam span").inner_text().strip()
                        except:
                            # если не смогли получить команды — пропускаем
                            continue

                        probs = row.locator(".fprc span")
                        def get_prob(j):
                            try:
                                return probs.nth(j).inner_text().strip()
                            except:
                                return ""

                        prob1 = get_prob(0)
                        probX = get_prob(1)
                        prob2 = get_prob(2)

                        try:
                            ex_score = row.locator(".ex_sc").inner_text().strip()
                        except:
                            ex_score = ""

                        def to_int_percent(s):
                            s = str(s).replace("%", "").strip()
                            try:
                                return int(s) if s != '' else 0
                            except:
                                return 0

                        results.append({
                            "time": date,
                            "home": home,
                            "away": away,
                            "p1": to_int_percent(prob1),
                            "px": to_int_percent(probX),
                            "p2": to_int_percent(prob2),
                            "score": ex_score
                        })

                    except Exception:
                        # не останавливаем парсер из-за одного row
                        continue

            browser.close()

    except Exception as e:
        print("Ошибка парсинга Forebet (playwright):", e)
        traceback.print_exc()

    print(f"✔ Forebet собрано матчей: {len(results)}")
    return results

# ===============================
# 🔹 In-memory cache для Forebet
# ===============================
forebet_cache = []
last_update = None

def update_forebet_cache(force=False):
    global forebet_cache, last_update
    now = datetime.utcnow()
    if not force and last_update is not None and (now - last_update) < timedelta(hours=4):
        return False
    print("Обновляю Forebet (Playwright)...")
    items = fetch_forebet_via_playwright()
    if items:
        forebet_cache = items
        last_update = datetime.utcnow()
        print(f"Кеш Forebet обновлён: {len(items)} матчей (время {last_update})")
        return True
    else:
        print("Forebet-парсер вернул 0 матчей — кеш не обновлён.")
        return False

# ===============================
# 🔁 Основной цикл
# ===============================
def main_loop():
    print("Скрипт запущен. Forebet обновляется каждые 4 часа; сравнение — каждые 30 минут.\n")
    update_forebet_cache(force=True)

    while True:
        try:
            if last_update is None or (datetime.utcnow() - last_update) >= timedelta(hours=4):
                update_forebet_cache()

            zulubet_results = parse_zulubet()
            forebet_results = forebet_cache

            # 🔹 фильтр по вероятности ≥ 60
            forebet_results_filtered = [
                f for f in forebet_results if f.get('p1',0) >= 60 or f.get('px',0) >= 60 or f.get('p2',0) >= 60
            ]

            print(f"Zulubet: найдено {len(zulubet_results)} подходящих матчей (по порогу).")
            print(f"Forebet после фильтрации по вероятности ≥60: {len(forebet_results_filtered)} матчей")

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
                    combined_matches.append("")  # разделитель между блоками

            if combined_matches:
                final_message = "\n".join(combined_matches)
                send_telegram_message(final_message)
                print("✅ Совпадения найдены и отправлены.")
            else:
                print("— Совпадений нет.")

        except Exception as e:
            print("ОШИБКА В ОСНОВНОМ ЦИКЛЕ:", e)
            traceback.print_exc()

        print("\nОжидание 30 минут...\n")
        time.sleep(1800)


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("Завершение по Ctrl+C")
        sys.exit(0)
    except Exception as e:
        print("Критическая ошибка, выхожу.", e)
        traceback.print_exc()
        sys.exit(1)
