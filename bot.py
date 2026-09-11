import telebot
import requests
import json
import os
import base64
import html
import time
from dotenv import load_dotenv

# Загружаем ключи из нашего сейфа
load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
# Читаем список пользователей. Если вдруг ты забыл обновить .env, 
# бот не сломается и попытается загрузить старый ADMIN_ID
env_users = os.getenv('ALLOWED_USERS', os.getenv('ADMIN_ID', '0'))
ALLOWED_USERS = [int(x.strip()) for x in env_users.split(',') if x.strip()]

DB_FILE = "movies.json" # <-- Та самая потерянная ссылка на базу!

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Словарь current_mode = {} мы удалили, он больше не нужен

# --- МЕНЮ КНОПОК ---
BTN_MOVE = "➡️ Перенести в любимое"
BTN_BACKUP = "📦 Скачать бэкап"

BTN_DEL = "🗑 Удалить"
BTN_SYNC = "🔄 Синхронизировать"
BTN_UPD = "⚡ Обновить HTML"
BTN_REP = "🔧 Отремонтировать"

# Оставили только сервисные кнопки
MENU_COMMANDS = [BTN_MOVE, BTN_BACKUP, BTN_DEL, BTN_SYNC, BTN_UPD, BTN_REP]

def get_main_menu():
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # Удалили строку markup.add(BTN_FAV, BTN_PLAN)
    markup.add(BTN_MOVE, BTN_BACKUP)
    markup.add(BTN_DEL, BTN_SYNC)
    markup.add(BTN_UPD, BTN_REP)
    return markup

def generate_html():
    if not os.path.exists(DB_FILE):
        return
        
    with open(DB_FILE, "r", encoding="utf-8") as file:
        items = json.load(file)

    all_genres, all_directors, all_actors = set(), set(), set()
    cards_html = ""

    for item in reversed(items): 
        display_title = item.get('title', item.get('name', 'Без названия'))
        safe_title = html.escape(display_title.lower())
        safe_orig_title = html.escape(item.get('original_title', '').lower())
        item_type = item.get('type', 'movie')
        genres = item.get('genres', [])
        director = item.get('director', 'Неизвестно')
        actors = item.get('cast', [])
        lang = item.get('original_language', '')
        
        status = item.get('status', 'favorite') 

        genres_lower = [g.lower() for g in genres]
        is_animation = any("мульт" in g or "анимац" in g or "anim" in g for g in genres_lower)
        is_anime = (is_animation and lang == 'ja') or any("аниме" in g for g in genres_lower)
        
        # --- ОПРЕДЕЛЯЕМ СОВЕТСКИЕ ФИЛЬМЫ И МУЛЬТФИЛЬМЫ ---
        try:
            # Оборачиваем в str(), чтобы защититься от пустых значений и чисел
            year_int = int(str(item.get('year', '0'))[:4])
        except (ValueError, TypeError):
            year_int = 0
            
        is_soviet = (lang == 'ru' and 0 < year_int <= 1991)
        # -------------------------------------------------
        
        subtype = item_type
        if is_anime: 
            subtype = "anime"
        elif is_soviet:
            subtype = "soviet"  # Отправляем в новую подкатегорию
        elif is_animation: 
            subtype = "cartoon"

        for g in genres: all_genres.add(g)
        if director != "Неизвестно": all_directors.add(director)
        for a in actors: all_actors.add(a)

        genres_json = html.escape(json.dumps(genres, ensure_ascii=False))
        actors_json = html.escape(json.dumps(actors, ensure_ascii=False))
        safe_director = html.escape(director)

        type_badge = '<span class="badge tv">СЕРИАЛ</span>' if item_type == 'tv' else ''
        seasons_info = f"<p><strong>Сезонов:</strong> {item.get('seasons', 1)}</p>" if item_type == 'tv' else ""

        # --- ДЕЛАЕМ АКТЕРОВ И МЕТКИ КЛИКАБЕЛЬНЫМИ ---
        actors_links = [f'<span onclick="setFilter(\'actor\', this)" class="clickable-tag">{html.escape(a)}</span>' for a in actors[:3]]
            
        # Делаем студии кликабельными
        studios_links = [f'<span onclick="setFilter(\'studio\', this)" class="clickable-tag">{html.escape(s)}</span>' for s in item.get("studios", [])]
        studios_info = f'<p class="studios" style="font-size: 12px; color: #888; margin-top: 8px;">🎬 {", ".join(studios_links)}</p>' if studios_links else ""
            
        collection_info = f'<p onclick="setFilter(\'collection\', this)" class="collection clickable-tag" style="font-size: 12px; color: #d4af37; font-weight: bold; margin-top: 4px;">📚 {item.get("collection")}</p>' if item.get("collection") else ""
        # --------------------------------------------

        # Добавили параметры data-year и data-rating для сортировки
        cards_html += f"""
        <div class="card" 
             data-type="{item_type}" 
             data-subtype="{subtype}"
             data-status="{status}" 
             data-title="{safe_title}" 
             data-orig-title="{safe_orig_title}"
             data-genres="{genres_json}"
             data-director="{safe_director.lower()}"
             data-actors="{actors_json.lower()}"
             data-year="{item['year']}"
             data-rating="{item['rating']}"
             data-collection="{html.escape(item.get('collection', ''))}"
             data-studios="{html.escape(', '.join(item.get('studios', [])))}">
            <img src="{item.get('poster_path', '')}" alt="{html.escape(display_title)}" loading="lazy">
            <div class="info">
                <h3>{display_title} {type_badge}</h3>
                <p style="margin-bottom: 5px;"><strong>Режиссер:</strong> <span onclick="setFilter('director', this)" class="clickable-tag">{safe_director}</span></p>
                <p><strong>В ролях:</strong> {', '.join(actors_links)}</p>
                {seasons_info}
                {studios_info}
                {collection_info}
                <div class="meta-small">{item['year']} | ⭐ {item['rating']}</div>
            </div>
        </div>
        """

    def build_datalist(id, items_set):
        options = "".join([f'<option value="{html.escape(i)}">' for i in sorted(list(items_set))])
        return f'<datalist id="{id}">{options}</datalist>'

    html_template = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🎬</text></svg>">
    <title>Мой Кинокаталог</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background-color: #141414; color: #ffffff; padding: 20px; margin: 0; }}
        h1 {{ text-align: center; margin-bottom: 30px; font-size: 2.5em; }}
        .controls {{ max-width: 1200px; margin: 0 auto 30px auto; display: flex; flex-direction: column; gap: 20px; }}
        .tabs {{ display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }}
        .tab-btn {{ background-color: #333; color: #fff; border: none; padding: 10px 25px; border-radius: 20px; cursor: pointer; font-weight: bold; transition: 0.3s; }}
        .tab-btn.active {{ background-color: #e50914; }}
        .tab-btn.planned-tab {{ background-color: #555; border: 1px solid #777; }}
        .tab-btn.planned-tab.active {{ background-color: #e50914; border-color: #e50914; }}
        .selectors {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; }}
        input, select {{ background-color: #333; color: white; border: 1px solid #444; padding: 12px; border-radius: 10px; outline: none; width: 100%; box-sizing: border-box; font-family: inherit; }}
        input:focus, select:focus {{ border-color: #e50914; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 25px; max-width: 1200px; margin: 0 auto; }}
        .card {{ background-color: #222; border-radius: 10px; overflow: hidden; transition: 0.3s; box-shadow: 0 4px 6px rgba(0,0,0,0.5); display: grid; grid-template-rows: auto 1fr; height: 100%; }}
        .card img {{ width: 100%; height: auto; display: block; min-height: 330px; background-color: #333; }}
        .info {{ padding: 15px; display: flex; flex-direction: column; }}
        .info h3 {{ margin: 0 0 10px 0; font-size: 1.1em; color: #fff; line-height: 1.2; }}
        .genres {{ color: #e50914; font-size: 0.75em; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; }}
        .info p {{ font-size: 0.85em; color: #bbb; margin: 4px 0; }}
        .meta-small {{ font-size: 0.75em; color: #666; margin-top: auto; border-top: 1px solid #333; padding-top: 5px; }}
        .badge.tv {{ background-color: #4a90e2; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.6em; vertical-align: middle; margin-left: 5px; }}
        .clickable-tag {{ cursor: pointer; transition: 0.2s; }}
        .clickable-tag:hover {{ color: #fff; text-decoration: underline; }}
        input[type="search"]::-webkit-search-cancel-button {{
            display: none !important;
            -webkit-appearance: none !important;
        }}
    </style>
</head>
<body>
    <h1>Моя Коллекция</h1>
    <div class="controls">
        <div class="tabs">
            <button class="tab-btn active" data-type="all">Всё</button>
            <button class="tab-btn" data-type="movie">Фильмы</button>
            <button class="tab-btn" data-type="tv">Сериалы</button>
            <button class="tab-btn" data-type="cartoon">Мультфильмы</button>
            <button class="tab-btn" data-type="anime">Аниме</button>
            <button class="tab-btn" data-type="soviet">Советское</button>
            <button class="tab-btn planned-tab" data-type="planned">⏳ В планах</button>
            <button id="random-btn" class="tab-btn" style="background-color: #555;">🎲 Случайно</button>
        </div>
        <div class="selectors">
            <input type="search" placeholder="Поиск по названию..." id="searchInput">
            <input type="search" id="genreFilter" list="genre-list" placeholder="Жанр...">
            <input type="search" id="directorFilter" list="director-list" placeholder="Режиссер...">
            <input type="search" id="actorFilter" list="actor-list" placeholder="Актер...">
            
            <select id="sortSelect">
                <option value="default">Сортировка: Последние добавленные</option>
                <option value="title_asc">По алфавиту (А-Я)</option>
                <option value="year_desc">Сначала новые (по году)</option>
                <option value="rating_desc">Сначала с высоким рейтингом</option>
            </select>
        </div>
    </div>
    {build_datalist('genre-list', all_genres)}
    {build_datalist('director-list', all_directors)}
    {build_datalist('actor-list', all_actors)}
    <div class="grid" id="movieGrid">{cards_html}</div>
    
    <script>
        const cards = Array.from(document.querySelectorAll('.card'));
        const movieGrid = document.getElementById('movieGrid');
        const filters = {{
            search: document.getElementById('searchInput'),
            genre: document.getElementById('genreFilter'),
            director: document.getElementById('directorFilter'),
            actor: document.getElementById('actorFilter')
        }};
        const sortSelect = document.getElementById('sortSelect');
        const tabBtns = document.querySelectorAll('.tab-btn');
        
        let activeTab = 'all';

        function applyFiltersAndSort() {{
            try {{
                const fVal = {{
                    search: (filters.search.value || '').toLowerCase().trim(),
                    genre: (filters.genre.value || '').toLowerCase().trim(),
                    director: (filters.director.value || '').toLowerCase().trim(),
                    actor: (filters.actor.value || '').toLowerCase().trim()
                }};

                // 1. Фильтрация
                cards.forEach(card => {{
                    const subtype = card.getAttribute('data-subtype') || '';
                    const status = card.getAttribute('data-status') || '';
                    const title = (card.getAttribute('data-title') || '').toLowerCase();
                    const cOrigTitle = (card.getAttribute('data-orig-title') || '').toLowerCase();
                    const cDirector = (card.getAttribute('data-director') || '').toLowerCase();
                    
                    let cGenres = [];
                    let cActors = [];
                    try {{ cGenres = JSON.parse(card.getAttribute('data-genres') || '[]').map(g => g.toLowerCase()); }} catch(e) {{}}
                    try {{ cActors = JSON.parse(card.getAttribute('data-actors') || '[]').map(a => a.toLowerCase()); }} catch(e) {{}}
                    
                    const cCollection = (card.getAttribute('data-collection') || '').toLowerCase();
                    const cStudios = (card.getAttribute('data-studios') || '').toLowerCase();

                    // --- УМНАЯ ЛОГИКА ВКЛАДОК ---
                    const cType = card.getAttribute('data-type') || '';
                    const isCartoon = cGenres.some(g => g.includes('мульт') || g.includes('анима'));
                    
                    let matchesTabAndStatus = false;
                    if (activeTab === 'planned') {{
                        matchesTabAndStatus = (status === 'planned');
                    }} else if (activeTab === 'all') {{
                        matchesTabAndStatus = (status === 'favorite');
                    }} else if (activeTab === 'movie' || activeTab === 'tv') {{
                        // В Фильмах/Сериалах показываем всё, кроме мультиков и аниме (советское кино вернется)
                        matchesTabAndStatus = (status === 'favorite') && (cType === activeTab) && !isCartoon && (subtype !== 'anime');
                    }} else if (activeTab === 'cartoon') {{
                        // В Мультиках показываем все мультики, включая советские
                        matchesTabAndStatus = (status === 'favorite') && isCartoon && (subtype !== 'anime');
                    }} else {{
                        // Для Аниме и Советского строгий фильтр
                        matchesTabAndStatus = (status === 'favorite') && (activeTab === subtype);
                    }}

                    const matchesSearch = title.includes(fVal.search) || 
                                        cOrigTitle.includes(fVal.search) ||
                                        cCollection.includes(fVal.search) || 
                                        cStudios.includes(fVal.search);

                    const matchesGenre = !fVal.genre || cGenres.some(g => g.includes(fVal.genre));
                    const matchesDirector = !fVal.director || cDirector.includes(fVal.director);
                    const matchesActor = !fVal.actor || cActors.some(a => a.includes(fVal.actor));

                    card.style.display = (matchesTabAndStatus && matchesSearch && matchesGenre && matchesDirector && matchesActor) ? 'grid' : 'none';
                }});

                // 2. Сортировка (безопасная, через CSS order)
                const sortValue = sortSelect.value;

                if (sortValue === 'default') {{
                    // Сбрасываем порядок на изначальный
                    cards.forEach(card => card.style.order = '');
                }} else {{
                    let visibleCards = cards.filter(card => card.style.display !== 'none');
                    visibleCards.sort((a, b) => {{
                        if (sortValue === 'title_asc') {{
                            return (a.getAttribute('data-title') || '').localeCompare(b.getAttribute('data-title') || '');
                        }} else if (sortValue === 'year_desc') {{
                            let yA = parseInt(a.getAttribute('data-year')) || 0;
                            let yB = parseInt(b.getAttribute('data-year')) || 0;
                            return yB - yA;
                        }} else if (sortValue === 'rating_desc') {{
                            let rA = parseFloat(a.getAttribute('data-rating')) || 0;
                            let rB = parseFloat(b.getAttribute('data-rating')) || 0;
                            return rB - rA;
                        }}
                        return 0;
                    }});
                    
                    // Раздаем порядковые номера (browser сам всё переставит)
                    visibleCards.forEach((card, index) => {{
                        card.style.order = index + 1;
                    }});
                }}
            }} catch (error) {{
                console.error("Ошибка при фильтрации:", error);
            }}
        }}

        tabBtns.forEach(btn => {{
            btn.addEventListener('click', () => {{
                // ЩИТ: Если у кнопки нет атрибута data-type, значит это Очистить или Случайно - игнорируем!
                if (!btn.getAttribute('data-type')) return; 

                tabBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                activeTab = btn.getAttribute('data-type');
                sortSelect.value = 'default'; 
                applyFiltersAndSort();
            }});
        }});
        
        Object.values(filters).forEach(el => el.addEventListener('input', applyFiltersAndSort));
        sortSelect.addEventListener('change', applyFiltersAndSort);
        
        applyFiltersAndSort();

        // --- ФУНКЦИЯ ДЛЯ КЛИКАБЕЛЬНЫХ МЕТОК ---
        function setFilter(type, element) {{
            let value = element.textContent.trim();
            let input;

            if (type === 'actor') {{
                input = document.querySelector('input[placeholder="Актер..."]');
            }} else if (type === 'collection') {{
                value = value.replace('📚', '').trim();
                input = document.querySelector('input[placeholder="Поиск по названию..."]');
            }} else if (type === 'studio') {{
                // Студии тоже отправляем в общее поле поиска
                input = document.querySelector('input[placeholder="Поиск по названию..."]');
            }} else if (type === 'director') {{
                input = document.querySelector('input[placeholder="Режиссер..."]');
            }}

            if (input) {{
                input.value = value;
                input.dispatchEvent(new Event('input'));
                window.scrollTo({{ top: 0, behavior: 'smooth' }});
            }}
        }}

        // --- НЕУБИВАЕМАЯ РУЛЕТКА ---
        document.getElementById('random-btn').addEventListener('click', function() {{
            // Создаем копию карточек, перемешиваем и выкладываем обратно
            let shuffled = [...cards].sort(() => Math.random() - 0.5);
            shuffled.forEach(card => movieGrid.appendChild(card));
            // Сбрасываем селект, чтобы не сбивать с толку
            sortSelect.value = 'default';
        }});
        
        // --- 100% РАБОЧИЕ КРЕСТИКИ (КАСТОМНЫЕ) ---
        Object.values(filters).forEach(input => {{
            if (!input) return;
            
            // 1. Создаем невидимую обертку вокруг поля
            let wrapper = document.createElement('div');
            wrapper.style.position = 'relative';
            wrapper.style.width = '100%';
            
            // Аккуратно вставляем обертку в сетку, а поле кладем внутрь
            input.parentNode.insertBefore(wrapper, input);
            wrapper.appendChild(input);
            
            // 2. Рисуем красивый крестик
            let clearBtn = document.createElement('span');
            clearBtn.innerHTML = '✖'; // Значок крестика
            clearBtn.style.position = 'absolute';
            clearBtn.style.right = '12px';
            clearBtn.style.top = '50%';
            clearBtn.style.transform = 'translateY(-50%)';
            clearBtn.style.color = '#bbb';
            clearBtn.style.cursor = 'pointer';
            clearBtn.style.fontSize = '14px';
            clearBtn.style.display = 'none'; // Скрыт, пока поле пустое
            clearBtn.style.transition = '0.2s';
            
            // Анимация при наведении (светится белым)
            clearBtn.onmouseover = () => clearBtn.style.color = '#fff';
            clearBtn.onmouseout = () => clearBtn.style.color = '#bbb';
            
            wrapper.appendChild(clearBtn);
            
            // 3. Заставляем крестик работать
            // Появляется только когда есть текст
            input.addEventListener('input', () => {{
                clearBtn.style.display = input.value.trim() !== '' ? 'block' : 'none';
            }});
            
            // При клике: стираем текст, прячем крестик, обновляем сетку фильмов
            clearBtn.addEventListener('click', () => {{
                input.value = '';
                clearBtn.style.display = 'none';
                input.dispatchEvent(new Event('input')); // Сигнал для сортировки
                input.focus(); // Возвращаем мигающий курсор в поле
            }});
        }});
    </script>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as file:
        file.write(html_template)

# --- КАПИТАЛЬНЫЙ РЕМОНТ БАЗЫ (ПОЛНОЕ ОБНОВЛЕНИЕ ДАННЫХ) ---
def repair_database(chat_id):
    if not os.path.exists(DB_FILE):
        return
        
    with open(DB_FILE, "r", encoding="utf-8") as f:
        database = json.load(f)

    msg = bot.send_message(chat_id, "🏗 Начинаю капитальную реставрацию базы...")

    # --- БЛОК ОЧИСТКИ ОТ ДУБЛИКАТОВ (БЕЗОПАСНЫЙ) ---
    unique_db = []
    seen = set()
    duplicates_removed = 0

    # Идем с конца списка в начало
    for item in reversed(database):
        item_id = item.get('id')
        
        # 1. ЗАЩИТА: Если у записи вообще нет ID, мы её не трогаем и не считаем дубликатом
        if not item_id:
            unique_db.append(item)
            continue
            
        # 2. ЗАЩИТА: Строго приводим к строке и отрезаем случайные пробелы (как ты и просил)
        item_id_str = str(item_id).strip()
        item_type = item.get('type', 'movie')
        
        identifier = f"{item_id_str}_{item_type}"
        
        if identifier not in seen:
            seen.add(identifier)
            unique_db.append(item)
        else:
            duplicates_removed += 1

    # Разворачиваем базу обратно в нормальный хронологический порядок
    database = list(reversed(unique_db))
    
    if duplicates_removed > 0:
        bot.send_message(chat_id, f"🧹 Найдено и удалено настоящих дубликатов: {duplicates_removed}")
    # -----------------------------------

    total = len(database)
    updated_count = 0

    for i, item in enumerate(database):
        try:
            # Запрашиваем свежие данные из TMDB по ID
            item_id = item.get('id')
            media_type = item.get('type', 'movie')
            
            # Стучимся за полным пакетом данных (включая актеров)
            res = requests.get(
                f"https://api.themoviedb.org/3/{media_type}/{item_id}",
                params={
                    "api_key": TMDB_API_KEY, 
                    "language": "ru-RU", 
                    "append_to_response": "credits,aggregate_credits"
                },
                timeout=10
            ).json()

            if 'id' not in res: continue # Пропускаем, если TMDB не ответил

            # 1. ОБНОВЛЯЕМ БАЗОВЫЕ ДАННЫЕ
            item['title'] = res.get('title') if media_type == 'movie' else res.get('name')
            item['original_title'] = res.get('original_title') if media_type == 'movie' else res.get('original_name')
            item['rating'] = round(res.get('vote_average', 0.0), 1)
            item['year'] = str(res.get('release_date') or res.get('first_air_date'))[:4]
            item['original_language'] = res.get('original_language', 'en')
            item['genres'] = [g["name"] for g in res.get("genres", [])]

            # --- НОВЫЙ БЛОК: СТУДИИ И КОЛЛЕКЦИИ ---
            collection_data = res.get('belongs_to_collection')
            item['collection'] = collection_data.get('name') if collection_data else ""
            item['studios'] = [c['name'] for c in res.get('production_companies', [])[:2]]
            # ------------------------------------

            # 2. ПРИМЕНЯЕМ ГИБРИДНЫЙ ФИЛЬТР АКТЕРОВ
            if media_type == 'tv' and "aggregate_credits" in res:
                full_cast = res.get("aggregate_credits", {}).get("cast", [])
                raw_cast = sorted(full_cast, key=lambda x: x.get('total_episode_count', 0), reverse=True)
            else:
                raw_cast = res.get("credits", {}).get("cast", [])
            
            leads = raw_cast[:3]
            supporting = raw_cast[3:25]
            popular_supporting = sorted(supporting, key=lambda x: x.get('popularity', 0.0), reverse=True)[:7]
            
            final_cast = leads + popular_supporting
            item['cast'] = [actor["name"] for actor in final_cast]

            # 3. ОБНОВЛЯЕМ РЕЖИССЕРА
            if media_type == 'tv' and res.get('created_by'):
                item['director'] = res['created_by'][0]['name']
            else:
                item['director'] = "Неизвестно"
                for p in res.get("credits", {}).get("crew", []):
                    if p["job"] == "Director":
                        item['director'] = p["name"]
                        break
            
            # Проставляем статус, если его вдруг нет
            if 'status' not in item:
                item['status'] = 'favorite'

            updated_count += 1
            
            # Показываем прогресс каждые 5 фильмов, чтобы не спамить в Телеграм
            if i % 5 == 0 or i == total - 1:
                bot.edit_message_text(f"🚧 Обновлено {i+1} из {total} фильмов...", chat_id, msg.message_id)
            
            # Анти-спам пауза для API (0.2 секунды между запросами)
            time.sleep(0.2)

        except Exception as e:
            print(f"Ошибка при ремонте {item.get('title')}: {e}")
            continue

    # Сохраняем обновленную базу и пересобираем сайт
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4, ensure_ascii=False)
    
    generate_html()
    bot.edit_message_text(f"✅ Реставрация завершена! Обновлено {updated_count} позиций.", chat_id, msg.message_id)

# --- ДОБАВЛЕНИЕ ---
def process_and_add_item(item_id, chat_id, media_type, target_status, message_id_to_edit=None):
    try:
        if message_id_to_edit: 
            bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text="⏳ Загружаю данные...")
        else: 
            msg = bot.send_message(chat_id, "🎯 Загружаю...")
            message_id_to_edit = msg.message_id

        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as file: database = json.load(file)
        else: database = []
        
        # --- УМНАЯ ПРОВЕРКА: ДУБЛИКАТЫ ИЛИ ПЕРЕНОС ---
        for m in database: # <-- Сдвинули влево на 4 пробела!
            if str(m.get('id')) == str(item_id) and m.get('type', 'movie') == media_type:
                if m.get('status', 'favorite') == target_status:
                    bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text="⚠️ Этот проект уже есть в этом разделе!")
                    return
                else:
                    # Фильм найден, но в другом разделе -> мгновенно переносим!
                    m['status'] = target_status
                    with open(DB_FILE, "w", encoding="utf-8") as file: 
                        json.dump(database, file, indent=4, ensure_ascii=False)
                    generate_html()
                    status_name = 'Любимое ⭐' if target_status == 'favorite' else 'Планы ⏳'
                    bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, text=f"✅ «{m.get('title')}» перенесен в {status_name}!")
                    return
        # ---------------------------------------------
            
        details = requests.get(f"https://api.themoviedb.org/3/{media_type}/{item_id}", 
                               params={"api_key": TMDB_API_KEY, "language": "ru-RU", "append_to_response": "credits,aggregate_credits"},
                               timeout=10).json()
        
        genres = [g["name"] for g in details.get("genres", [])]
        director = "Неизвестно"
        if media_type == 'tv' and details.get('created_by'): director = details['created_by'][0]['name']
        else:
            for p in details.get("credits", {}).get("crew", []):
                if p["job"] == "Director": director = p["name"]; break 
                
        # --- ГИБРИДНЫЙ ФИЛЬТР АКТЕРОВ ---
        if media_type == 'tv' and "aggregate_credits" in details:
            full_cast = details.get("aggregate_credits", {}).get("cast", [])
            raw_cast = sorted(full_cast, key=lambda x: x.get('total_episode_count', 0), reverse=True)
        else:
            raw_cast = details.get("credits", {}).get("cast", [])
        
        leads = raw_cast[:3]
        supporting = raw_cast[3:25]
        popular_supporting = sorted(supporting, key=lambda x: x.get('popularity', 0.0), reverse=True)[:7]
        
        final_cast = leads + popular_supporting
        cast = [actor["name"] for actor in final_cast]
        # --------------------------------
        
        poster_path = ""
        if details.get("poster_path"):
            if not os.path.exists("covers"): os.makedirs("covers")
            img = requests.get(f"https://image.tmdb.org/t/p/w500{details['poster_path']}").content
            poster_path = f"covers/{media_type}_{item_id}.jpg"
            with open(poster_path, 'wb') as h: h.write(img)

        title = details.get("title") if media_type == 'movie' else details.get("name")
        year = str(details.get("release_date") or details.get("first_air_date"))[:4]
        status = target_status
        
        # --- СБОР МЕТОК ДЛЯ НОВЫХ ФИЛЬМОВ ---
        collection_data = details.get('belongs_to_collection')
        collection_name = collection_data.get('name') if collection_data else ""
        studios = [c['name'] for c in details.get('production_companies', [])[:2]]
        # ------------------------------------

        item_data = {
            "id": item_id, "type": media_type,
            "title": title,
            "original_title": details.get("original_title") if media_type == 'movie' else details.get("original_name"),
            "year": year if year else "----",
            "genres": genres, "director": director, "cast": cast,
            "rating": round(details.get("vote_average", 0), 1), "poster_path": poster_path,
            "original_language": details.get("original_language", "en"),
            "status": status,
            "collection": collection_name,  # Добавили коллекцию
            "studios": studios              # Добавили студии
        }
        if media_type == 'tv': item_data["seasons"] = details.get("number_of_seasons", 1)
        
        database.append(item_data)
        with open(DB_FILE, "w", encoding="utf-8") as file: json.dump(database, file, indent=4, ensure_ascii=False) 
        generate_html()
        
        bot.edit_message_text(chat_id=chat_id, message_id=message_id_to_edit, 
                              text=f"✅ <b>{html.escape(title)} ({item_data['year']})</b> успешно добавлен!", 
                              parse_mode="HTML")
    except Exception as e: 
        bot.send_message(chat_id, f"❌ Ошибка: {e}")
        print(f"Ошибка добавления: {e}")

# --- ФУНКЦИЯ ПОИСКА ---
def perform_search(raw_text, chat_id, forced_type=None):
    m_type = forced_type
    q = raw_text.strip()
    
    if not m_type:
        m_type = 'tv' if q.lower().startswith('сериал ') else 'movie'
        if m_type == 'tv': q = q[7:].strip()
        
    try:
        # Добавили timeout=10
        res = requests.get(f"https://api.themoviedb.org/3/search/{m_type}", 
                           params={"api_key": TMDB_API_KEY, "query": q, "language": "ru-RU"},
                           timeout=10).json().get("results", [])
        if not res: 
            bot.send_message(chat_id, "Ничего не нашел.")
            return
            
        new_items = res[:5]
        
        markup = telebot.types.InlineKeyboardMarkup(row_width=1)
        for r in new_items:
            t = r.get("title") or r.get("name", "Без названия")
            orig_t = r.get("original_title") or r.get("original_name", "")
            y_raw = r.get("release_date") or r.get("first_air_date")
            y = str(y_raw)[:4] if y_raw else "----"
            
            # Красиво склеиваем названия, если оригинальное отличается от русского
            if orig_t and orig_t.lower() != t.lower():
                btn_text = f"🎬 {t} / {orig_t} ({y})"
            else:
                btn_text = f"🎬 {t} ({y})"
                
            if len(btn_text) > 60:
                btn_text = btn_text[:57] + "..."
                
            markup.add(telebot.types.InlineKeyboardButton(text=btn_text, callback_data=f"select_{m_type}_{r['id']}"))
            
        bot.send_message(chat_id, "Выбери совпадение:", reply_markup=markup)
    except Exception as e: 
        bot.send_message(chat_id, f"❌ Ошибка поиска: {e}")
        print(e)

# --- КОМАНДЫ И МЕНЮ ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if message.from_user.id not in ALLOWED_USERS:
        return 
    bot.send_message(message.chat.id, "Привет! Выбери действие на панели меню ниже 👇", reply_markup=get_main_menu())

@bot.message_handler(func=lambda m: m.text in MENU_COMMANDS)
def handle_menu(message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    
    txt = message.text
    if txt == BTN_MOVE:
        request_move(message)
    elif txt == BTN_BACKUP:
        send_backup(message) 
    elif txt == BTN_DEL:
        request_delete(message)
    elif txt == BTN_SYNC:
        sync_to_github(message)
    elif txt == BTN_UPD:
        generate_html()
        bot.send_message(message.chat.id, "✅ Интерфейс HTML обновлен!")
    elif txt == BTN_REP:
        repair_database(message.chat.id)

# --- ПЕРЕНОС ИЗ ПЛАНОВ В ЛЮБИМОЕ ---
def request_move(message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    if not os.path.exists(DB_FILE): return
    with open(DB_FILE, "r", encoding="utf-8") as f: movies = json.load(f)
    
    # Ищем только те фильмы, у которых статус "в планах"
    planned_movies = [m for m in movies if m.get('status') == 'planned']
    
    if not planned_movies:
        bot.send_message(message.chat.id, "🤷‍♂️ У вас нет фильмов в планах для переноса.")
        return

    markup = telebot.types.InlineKeyboardMarkup()
    for m in planned_movies[:15]: # Показываем последние 15
        markup.add(telebot.types.InlineKeyboardButton(text=f"➡️ {m.get('title')}", callback_data=f"move_{m.get('type','movie')}_{m['id']}"))
    bot.send_message(message.chat.id, "Что переносим в ⭐ ЛЮБИМОЕ?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('move_'))
def handle_move(call):
    if call.from_user.id not in ALLOWED_USERS:
        return
    bot.answer_callback_query(call.id) # Мгновенно гасим моргание кнопки
    p = call.data.split('_')
    
    with open(DB_FILE, "r", encoding="utf-8") as f: db = json.load(f)
    moved_title = ""
    
    for m in db:
        if m['id'] == int(p[2]) and m.get('type','movie') == p[1]:
            m['status'] = 'favorite' # Меняем бирку!
            moved_title = m.get('title', 'Без названия')
            break
            
    with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4, ensure_ascii=False)
    generate_html()
    bot.edit_message_text(f"✅ «{moved_title}» перенесен в Любимое!", call.message.chat.id, call.message.message_id)

def send_backup(message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'rb') as f:
            bot.send_document(message.chat.id, f, caption="📦 Вот свежая копия базы данных!")
    else:
        bot.send_message(message.chat.id, "База данных пока пуста, нечего скачивать.")

@bot.message_handler(commands=['sync'])
def sync_to_github(message):
    if message.from_user.id not in ALLOWED_USERS:
        return

    bot.send_message(message.chat.id, "🔄 Начинаю синхронизацию с GitHub...")
    try:
        # 1. Выдаем серверу "паспорт", чтобы он мог делать коммиты
        os.system('git config user.name "MovieBot"')
        os.system('git config user.email "bot@example.com"')
        
        os.system('git add .')
        os.system('git commit -m "Обновление базы через бота"')
        
        # 2. Используем ваш токен из сейфа для открытия двери GitHub
        repo_url = f"https://{GITHUB_TOKEN}@github.com/timtimohin/movies.git"
        push_result = os.system(f'git push {repo_url} main')
        
        # 3. Честно проверяем, дошел ли груз
        if push_result == 0:
            bot.send_message(message.chat.id, "✅ Синхронизация успешна!\nИзменения появятся на сайте через 1-2 минуты.\nСсылка: https://timtimohin.github.io/movies/")
        else:
            bot.send_message(message.chat.id, "❌ Ошибка: GitHub отклонил файлы. Проверьте, правильный ли GITHUB_TOKEN в вашем файле .env.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Системная ошибка: {e}")

@bot.message_handler(commands=['delete'])
def request_delete(message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    if not os.path.exists(DB_FILE): return
    with open(DB_FILE, "r", encoding="utf-8") as f: movies = json.load(f)
    
    command_parts = message.text.split(maxsplit=1)
    search_query = command_parts[1].lower() if len(command_parts) > 1 and not message.text.startswith("🗑") else ""
    
    if search_query:
        # --- УЛЬТРА-ПРОЩАЮЩИЙ ПОИСК ---
        # Очищаем запрос от любых знаков препинания
        clean_query = search_query.replace('-', ' ').replace(':', ' ').replace('.', ' ').replace(',', ' ')
        query_words = clean_query.split()
        
        filtered = []
        for m in movies:
            # Очищаем названия из базы тем же способом
            t = m.get('title', '').lower().replace('-', ' ').replace(':', ' ').replace('.', ' ').replace(',', ' ')
            orig_t = m.get('original_title', '').lower().replace('-', ' ').replace(':', ' ').replace('.', ' ').replace(',', ' ')
            
            # 1. Проверка на полное совпадение (спасет запросы вроде "Charlie St Cloud" без точки)
            if clean_query in t or clean_query in orig_t:
                if m not in filtered: filtered.append(m)
                continue
                
            # 2. Умная проверка по отдельным словам (спасет от опечаток и падежей)
            # Считаем, сколько слов из твоего запроса нашлось в названии
            match_count = sum(1 for w in query_words if w in t or w in orig_t)
            
            # Пропускаем, если совпало хотя бы 70% слов (прощает 1 ошибку в названии из 4-5 слов)
            if len(query_words) > 0 and match_count >= len(query_words) * 0.7:
                if m not in filtered: filtered.append(m)
        # -------------------------------
        text_response = f"🔍 Поиск для удаления: «{search_query}»"
    else:
        filtered = list(reversed(movies))[:10]
        text_response = "🗑 Последние добавленные (чтобы найти конкретный, напиши /delete название):"

    if not filtered:
        bot.send_message(message.chat.id, "Ничего не найдено.")
        return

    # row_width=1 ставим, чтобы кнопки шли красиво списком вниз
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    
    # Ограничиваем выдачу до 15 результатов, чтобы клавиатура не была гигантской
    for m in filtered[:15]: 
        markup.add(telebot.types.InlineKeyboardButton(text=f"❌ {m.get('title')}", callback_data=f"del_{m.get('type','movie')}_{m['id']}"))
    bot.send_message(message.chat.id, text_response, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def handle_del(call):
    if call.from_user.id not in ALLOWED_USERS:
        return
    bot.answer_callback_query(call.id) 
    p = call.data.split('_')
    target_id = int(p[2])
    target_type = p[1]
    
    with open(DB_FILE, "r", encoding="utf-8") as f: db = json.load(f)
    
    # Находим и удаляем только ОДИН элемент с таким ID и типом, не трогая копии
    for m in db:
        if int(m.get('id', 0)) == target_id and m.get('type', 'movie') == target_type:
            db.remove(m)
            break # Удаляем ровно одну запись и мгновенно останавливаемся!
            
    with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4, ensure_ascii=False)
    generate_html()
    bot.edit_message_text("🗑 Удалено", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.text not in MENU_COMMANDS and not m.text.startswith('/'))
def handle_text_search(message):
    if message.from_user.id not in ALLOWED_USERS:
        return
    perform_search(message.text, message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('select_'))
def handle_select(call):
    if call.from_user.id not in ALLOWED_USERS: return
    p = call.data.split('_')
    m_type, item_id = p[1], p[2]
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f: db = json.load(f)
    else: db = []
        
    existing = next((m for m in db if str(m.get('id')) == item_id and m.get('type', 'movie') == m_type), None)
    
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    if existing:
        if existing.get('status') == 'planned':
            markup.add(
                telebot.types.InlineKeyboardButton("➡️ Перенести в Любимое", callback_data=f"save_{m_type}_{item_id}_favorite"),
                telebot.types.InlineKeyboardButton("🔄 Обновить (Точечный ремонт)", callback_data=f"upditem_{m_type}_{item_id}")
            )
            bot.edit_message_text(f"«{existing.get('title')}» сейчас в планах.", call.message.chat.id, call.message.message_id, reply_markup=markup)
        else:
            # Раньше тут был просто Alert, а теперь мы даем возможность отремонтировать карточку!
            markup.add(telebot.types.InlineKeyboardButton("🔄 Обновить (Точечный ремонт)", callback_data=f"upditem_{m_type}_{item_id}"))
            bot.edit_message_text(f"«{existing.get('title')}» уже в Любимом ⭐", call.message.chat.id, call.message.message_id, reply_markup=markup)
    else:
        markup.add(
            telebot.types.InlineKeyboardButton("⭐ В любимое", callback_data=f"save_{m_type}_{item_id}_favorite"),
            telebot.types.InlineKeyboardButton("⏳ В планы", callback_data=f"save_{m_type}_{item_id}_planned")
        )
        bot.edit_message_text("Куда добавить?", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('save_'))
def handle_save(call):
    if call.from_user.id not in ALLOWED_USERS: return
    bot.answer_callback_query(call.id)
    p = call.data.split('_')
    m_type, item_id, target_status = p[1], p[2], p[3]
    # Передаем статус напрямую, забыв про current_mode
    process_and_add_item(item_id, call.message.chat.id, m_type, target_status, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('upditem_'))
def handle_update_single_item(call):
    if call.from_user.id not in ALLOWED_USERS: return
    
    p = call.data.split('_')
    m_type, item_id = p[1], p[2]
    
    bot.edit_message_text("⏳ Загружаю свежие данные с TMDB...", call.message.chat.id, call.message.message_id)
    
    with open(DB_FILE, "r", encoding="utf-8") as f: db = json.load(f)
    
    # Находим нашу карточку в базе
    target_item = next((m for m in db if str(m.get('id')) == item_id and m.get('type', 'movie') == m_type), None)
    
    if not target_item:
        bot.edit_message_text("❌ Ошибка: Фильм не найден в локальной базе.", call.message.chat.id, call.message.message_id)
        return
        
    try:
        # Тянем свежие данные с API (с расширенными титрами)
        res = requests.get(
            f"https://api.themoviedb.org/3/{m_type}/{item_id}",
            params={"api_key": TMDB_API_KEY, "language": "ru-RU", "append_to_response": "credits,aggregate_credits"},
            timeout=10
        ).json()
        
        if 'id' not in res:
            bot.edit_message_text("❌ Ошибка: TMDB не отдал данные.", call.message.chat.id, call.message.message_id)
            return
            
        # Обновляем текстовые данные
        target_item['title'] = res.get('title') if m_type == 'movie' else res.get('name')
        target_item['original_title'] = res.get('original_title') if m_type == 'movie' else res.get('original_name')
        target_item['rating'] = round(res.get('vote_average', 0.0), 1)
        target_item['year'] = str(res.get('release_date') or res.get('first_air_date'))[:4]
        target_item['original_language'] = res.get('original_language', 'en')
        target_item['genres'] = [g["name"] for g in res.get("genres", [])]
        
        collection_data = res.get('belongs_to_collection')
        target_item['collection'] = collection_data.get('name') if collection_data else ""
        target_item['studios'] = [c['name'] for c in res.get('production_companies', [])[:2]]
        
        # Обновляем актеров (УМНЫЙ АЛГОРИТМ ДЛЯ СЕРИАЛОВ)
        if m_type == 'tv' and "aggregate_credits" in res:
            full_cast = res.get("aggregate_credits", {}).get("cast", [])
            raw_cast = sorted(full_cast, key=lambda x: x.get('total_episode_count', 0), reverse=True)
        else:
            raw_cast = res.get("credits", {}).get("cast", [])
            
        leads = raw_cast[:3]
        supporting = raw_cast[3:25]
        popular_supporting = sorted(supporting, key=lambda x: x.get('popularity', 0.0), reverse=True)[:7]
        target_item['cast'] = [actor["name"] for actor in (leads + popular_supporting)]
        
        # Обновляем режиссера
        if m_type == 'tv' and res.get('created_by'):
            target_item['director'] = res['created_by'][0]['name']
        else:
            target_item['director'] = "Неизвестно"
            for p_crew in res.get("credits", {}).get("crew", []):
                if p_crew["job"] == "Director":
                    target_item['director'] = p_crew["name"]
                    break
                    
        # Проверяем и чиним постер (если его не было или стояла веб-ссылка)
        current_poster = target_item.get('poster_path', '')
        if not current_poster.startswith('covers/') and res.get('poster_path'):
            tmdb_url = f"https://image.tmdb.org/t/p/w500{res['poster_path']}"
            try:
                img_resp = requests.get(tmdb_url, timeout=10)
                img_resp.raise_for_status()
                if not os.path.exists("covers"): os.makedirs("covers")
                new_poster_path = f"covers/{m_type}_{item_id}.jpg"
                with open(new_poster_path, 'wb') as h: h.write(img_resp.content)
                target_item['poster_path'] = new_poster_path
            except Exception:
                target_item['poster_path'] = tmdb_url # Фолбек на прямую ссылку
        
        # Сохраняем файл и пересобираем сайт
        with open(DB_FILE, "w", encoding="utf-8") as f: json.dump(db, f, indent=4, ensure_ascii=False)
        generate_html()
        
        bot.edit_message_text(f"✅ Карточка «{target_item['title']}» успешно обновлена!", call.message.chat.id, call.message.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ Сбой при точечном обновлении: {e}", call.message.chat.id, call.message.message_id)

print("🤖 Бот запущен (v.26.05.17)")

while True:
    try:
        # Пытаемся запустить бота
        bot.polling(none_stop=True)
    except Exception as e:
        # Если Telegram отвалился или интернет моргнул, бот не умрет
        print(f"Сбой связи с Telegram: {e}")
        print("Перезапуск через 5 секунд...")
        time.sleep(5) # Ждем 5 секунд, пока интернет придет в норму, и пробуем снова
