import re
import time
from datetime import datetime, timedelta, UTC
import requests as rq
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests # Используется для обхода защиты Forebet

# ===============================
# 🔹 Настройки Telegram
# ===============================
TOKEN = "8353200396:AAEYPs8RmdEUfsK6lG1U3kve3fjL-oAIR3I"
CHAT_ID = 293637253

def send_telegram_message(text):
    """Отправляет сообщение в Telegram с HTML-форматированием."""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        response = rq.post(url, data=payload, timeout=20)
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
# 🔹 Парсинг Zulubet
# ===============================
def parse_zulubet():
    """Парсит матчи с Zulubet, фильтруя по вероятности >= 60%."""
    url = "https://www.zulubet.com/"
    headers = {"User-Agent": "Mozilla/5.0"}
    results = []
    
    try:
        response = rq.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"Ошибка при загрузке Zulubet: {e}")
        return []

    main_table = soup.select_one("table.content_tables.main_table")
    if not main_table:
        print("Не удалось найти таблицу матчей на Zulubet.")
        return []

    rows = main_table.find_all("tr")[2:]

    for row in rows:
        try:
            cells = row.find_all("td")
            if len(cells) < 6:
                continue

            # 1. Время
            script_tag = cells[0].find("script")
            raw_time = (
                script_tag.string.strip()
                .replace("mf_usertime('", "")
                .replace("');", "")
                if script_tag else "?"
            )
            try:
                # В Zulubet время может быть в UTC-1 (поправка на час)
                dt = datetime.strptime(raw_time, "%m/%d/%Y, %H:%M") + timedelta(hours=1)
                time_str = dt.strftime("%d/%m %H:%M")
            except:
                time_str = raw_time

            # 2. Матч (команды)
            match_a = cells[1].find("a")
            match = match_a.text.strip() if match_a else "?"

            # 3. Вероятности
            def extract_percent(text):
                return int(text.split(":")[1].replace("%", "").strip())
                
            p1 = extract_percent(cells[3].text)
            px = extract_percent(cells[4].text)
            p2 = extract_percent(cells[5].text)

            # Фильтрация
            if p1 >= 60 or px >= 60 or p2 >= 60:
                parts = re.split(r'\s*-\s*', match)
                home = parts[0].strip()
                away = parts[1].strip() if len(parts) > 1 else "?"
                results.append({
                    "time": time_str,
                    "home": home,
                    "away": away,
                    "text": f"{time_str} ⚽️ {match}  {p1}-{px}-{p2}"
                })

        except Exception as e:
            print(f"Ошибка при обработке строки Zulubet: {e}") 
            continue

    return results

# ===============================
# 🔹 Парсер Forebet
# ===============================
def fetch_forebet():
    """Парсит матчи Forebet за сегодня и завтра с использованием API и HTML."""
    results = []
    urls = [
        ("today", "https://www.forebet.com/en/football-tips-and-predictions-for-today"),
        ("tomorrow", "https://www.forebet.com/en/football-tips-and-predictions-for-tomorrow")
    ]

    session = curl_requests.Session()

    for desc, main_url in urls:
        try:
            # 1. Получаем HTML для предполагаемых счетов (BeautifulSoup)
            resp_main = session.get(main_url, impersonate="chrome110", timeout=20)
            resp_main.raise_for_status()
            soup = BeautifulSoup(resp_main.text, "html.parser")
            score_divs = soup.find_all("div", class_="ex_sc tabonly")

            # 2. Получаем данные о матчах и процентах (API)
            api_url = "https://www.forebet.com/scripts/getrs.php"
            
            if desc == "today":
                date_str = datetime.now(UTC).strftime("%Y-%m-%d")
            else:
                date_str = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")

            params = {
                "ln": "en", "tp": "1x2", "in": date_str,
                "ord": "0", "tz": "+60", "tzs": "0", "tze": "0"
            }

            resp_api = session.get(api_url, params=params, impersonate="chrome110", timeout=20)
            resp_api.raise_for_status()
            json_data = resp_api.json()

            if not json_data or not json_data[0]:
                print(f"{desc.capitalize()}: матчей не найдено")
                continue

            matches = json_data[0]

            for i, match in enumerate(matches):
                # Извлечение времени
                date_time = match.get("DATE_BAH", "N/A").split(' ')
                date_match = date_time[0]
                time_match = date_time[1][:5] if len(date_time) > 1 else "N/A"

                # Извлечение команд и вероятностей
                host = match.get("HOST_NAME", "Неизвестно")
                guest = match.get("GUEST_NAME", "Неизвестно")
                p1 = int(match.get("Pred_1", 0))
                px = int(match.get("Pred_X", 0))
                p2 = int(match.get("Pred_2", 0))

                # Извлечение прогнозируемого счета
                forecast_score = score_divs[i].get_text(strip=True) if i < len(score_divs) else ""

                results.append({
                    "time": f"{date_match} {time_match}",
                    "home": host,
                    "away": guest,
                    "p1": p1, "px": px, "p2": p2,
                    "score": forecast_score
                })

            print(f"✔ {desc.capitalize()}: собрано матчей {len(matches)}")

        except Exception as e:
            print(f"Ошибка парсинга Forebet ({desc}): {e}")
            continue

    return results

# ===============================
# 🔁 Основной цикл Worker
# ===============================
print("Скрипт запущен в режиме Worker. Сравнение — каждые 30 минут.\n")

while True:
    try:
        # Каждый цикл мы заново получаем свежие данные
        forebet_results = fetch_forebet()
        zulubet_results = parse_zulubet()

        # 🔹 Фильтр Forebet по вероятности ≥ 60
        forebet_results_filtered = [
            f for f in forebet_results if f['p1'] >= 60 or f['px'] >= 60 or f['p2'] >= 60
        ]

        print(f"\nZulubet: найдено {len(zulubet_results)} подходящих матчей (по порогу).")
        print(f"Forebet после фильтрации по вероятности ≥60: {len(forebet_results_filtered)} матчей")

        combined_matches = []
        
        # Сравнение
        for z in zulubet_results:
            # Ищем совпадения по командам
            f_matches = [
                f for f in forebet_results_filtered 
                if teams_match(z["home"], f["home"]) or teams_match(z["away"], f["away"])
            ]
            
            if f_matches:
                # Заголовок блока с матчем Zulubet
                z_text_html = f"<b>ZULUBET: {z['text']}</b>"
                combined_matches.append(z_text_html)
                
                # Добавляем все совпавшие матчи Forebet
                for f in f_matches:
                    line = (
                        f"FOR: {f['time']} {f['home']} vs {f['away']}  "
                        f"P: {f['p1']}-{f['px']}-{f['p2']}  "
                        f"Счет: {f['score']}"
                    )
                    # Проверка на полное совпадение для выделения
                    is_full_match = teams_match(z["home"], f["home"]) and teams_match(z["away"], f["away"])
                    
                    if is_full_match:
                        combined_matches.append(f"🔥 {line}")
                    else:
                        combined_matches.append(line)
                
                combined_matches.append("")  # разделитель между блоками

        if combined_matches:
            final_message = "\n".join(combined_matches)
            send_telegram_message("🔔 Найдено совпадений! 🔔\n\n" + final_message)
            print("✅ Совпадения найдены и отправлены.")
        else:
            print("— Совпадений нет.")

    except Exception as e:
        print(f"ОШИБКА В ОСНОВНОМ ЦИКЛЕ: {e}")

    # Ждём 30 минут перед следующим циклом
    print("\nОжидание 30 минут...\n")
    time.sleep(1800)
