import re
import time
from datetime import datetime, timedelta, timezone
import requests as rq
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

# ===============================
# 🔹 Настройки Telegram
# ===============================
TOKEN = "8353200396:AAEYPs8RmdEUfsK6lG1U3kve3fjL-oAIR3I"
CHAT_ID = 293637253

def send_telegram_message(text):
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
    url = "https://www.zulubet.com/"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = rq.get(url, headers=headers, timeout=20)
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

            link = cells[1].find("a")
            if not link:
                continue
            match = link.text.strip()

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
# 🔹 Новый парсер Forebet (API + BeautifulSoup)
# ===============================
forebet_cache = []
last_update = None

def fetch_forebet():
    results = []
    urls = [
        ("today", "https://www.forebet.com/en/football-tips-and-predictions-for-today"),
        ("tomorrow", "https://www.forebet.com/en/football-tips-and-predictions-for-tomorrow")
    ]

    session = curl_requests.Session()

    for desc, main_url in urls:
        try:
            resp_main = session.get(main_url, impersonate="chrome110", timeout=20)
            resp_main.raise_for_status()
            soup = BeautifulSoup(resp_main.text, "html.parser")

            api_url = "https://www.forebet.com/scripts/getrs.php"
            date_str = datetime.now().strftime("%Y-%m-%d") if desc == "today" else (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            params = {
                "ln": "en",
                "tp": "1x2",
                "in": date_str,
                "ord": "0",
                "tz": "+60",
                "tzs": "0",
                "tze": "0"
            }

            resp_api = session.get(api_url, params=params, impersonate="chrome110", timeout=20)
            resp_api.raise_for_status()
            json_data = resp_api.json()

            if not json_data or not json_data[0]:
                print(f"{desc.capitalize()}: матчей не найдено")
                continue

            matches = json_data[0]
            score_divs = soup.find_all("div", class_="ex_sc tabonly")

            for i, match in enumerate(matches):
                date_time = match.get("DATE_BAH", "N/A").split(' ')
                date_match = date_time[0]
                time_match = date_time[1][:5] if len(date_time) > 1 else "N/A"

                host = match.get("HOST_NAME", "Неизвестно")
                guest = match.get("GUEST_NAME", "Неизвестно")

                p1 = int(match.get("Pred_1", 0))
                px = int(match.get("Pred_X", 0))
                p2 = int(match.get("Pred_2", 0))

                forecast_score = score_divs[i].get_text(strip=True) if i < len(score_divs) else ""

                results.append({
                    "time": f"{date_match} {time_match}",
                    "home": host,
                    "away": guest,
                    "p1": p1,
                    "px": px,
                    "p2": p2,
                    "score": forecast_score
                })

            print(f"✔ {desc.capitalize()}: собрано матчей {len(matches)}")

        except Exception as e:
            print(f"Ошибка парсинга Forebet ({desc}): {e}")
            continue

    return results

def update_forebet_cache(force=False):
    global forebet_cache, last_update
    now = datetime.now(timezone.utc)
    if not force and last_update is not None and (now - last_update) < timedelta(hours=4):
        return False
    print("Обновляю Forebet (новый парсер)...")
    items = fetch_forebet()
    if items:
        forebet_cache = items
        last_update = datetime.now(timezone.utc)
        print(f"Кеш Forebet обновлён: {len(items)} матчей (время {last_update})")
        return True
    else:
        print("Forebet-парсер вернул 0 матчей — кеш не обновлён.")
        return False

# ===============================
# 🔁 Основной цикл
# ===============================
print("Скрипт запущен. Forebet обновляется каждые 4 часа; сравнение — каждые 30 минут.\n")
update_forebet_cache(force=True)

while True:
    try:
        if last_update is None or (datetime.now(timezone.utc) - last_update) >= timedelta(hours=4):
            update_forebet_cache()

        zulubet_results = parse_zulubet()
        forebet_results = forebet_cache

        # 🔹 фильтр по вероятности ≥ 60
        forebet_results_filtered = [
            f for f in forebet_results if f['p1'] >= 60 or f['px'] >= 60 or f['p2'] >= 60
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
                        f"F1T:{f['time']} {f['home']} vs {f['away']}  {f['p1']}-{f['px']}-{f['p2']}  {f['score']}"
                    )
                for f in f2_matches:
                    combined_matches.append(
                        f"F2T:{f['time']} {f['home']} vs {f['away']}  {f['p1']}-{f['px']}-{f['p2']}  {f['score']}"
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

    print("\nОжидание 30 минут...\n")
    time.sleep(1800)

