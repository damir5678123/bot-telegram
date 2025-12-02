import sqlite3
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы для состояний ConversationHandler
ADD_TITLE, ADD_YEAR, ADD_DURATION, ADD_DESCRIPTION, ADD_GENRES = range(5)
UPDATE_CHOICE, UPDATE_FIELD, UPDATE_VALUE = range(5, 8)
DELETE_CONFIRM = 8
SEARCH_TYPE, SEARCH_VALUE = range(9, 11)


class FilmsDatabase:
    def __init__(self, db_name='films.db'):
        self.connection = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.connection.cursor()
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS genres (
            genre_id INTEGER PRIMARY KEY AUTOINCREMENT,
            genre_name TEXT UNIQUE NOT NULL
        )
        ''')

        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS films (
            film_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            duration_minutes INTEGER NOT NULL,
            release_year INTEGER NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS film_genres (
            film_id INTEGER,
            genre_id INTEGER,
            PRIMARY KEY (film_id, genre_id),
            FOREIGN KEY (film_id) REFERENCES films (film_id) ON DELETE CASCADE,
            FOREIGN KEY (genre_id) REFERENCES genres (genre_id) ON DELETE CASCADE
        )
        ''')

        # Добавляем жанры, если их нет
        default_genres = ['Боевик', 'Драма', 'Комедия', 'Фантастика', 'Триллер', 'Ужасы', 'Мелодрама', 'Детектив']
        for genre in default_genres:
            self.cursor.execute('INSERT OR IGNORE INTO genres (genre_name) VALUES (?)', (genre,))

        self.connection.commit()

    # ========== CRUD ОПЕРАЦИИ ==========

    # CREATE - Создание
    def add_film(self, title, year, duration, description=None):
        """Добавление нового фильма"""
        try:
            self.cursor.execute('''
            INSERT INTO films (title, release_year, duration_minutes, description)
            VALUES (?, ?, ?, ?)
            ''', (title, year, duration, description))
            film_id = self.cursor.lastrowid
            self.connection.commit()
            return film_id
        except Exception as e:
            logger.error(f"Error adding film: {e}")
            return None

    def add_genre_to_film(self, film_id, genre_id):
        """Добавление жанра к фильму"""
        try:
            self.cursor.execute('''
            INSERT OR IGNORE INTO film_genres (film_id, genre_id) VALUES (?, ?)
            ''', (film_id, genre_id))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding genre to film: {e}")
            return False

    # READ - Чтение
    def get_all_films(self, limit=50):
        """Получение всех фильмов"""
        self.cursor.execute('''
        SELECT f.*, GROUP_CONCAT(g.genre_name, ', ') as genres
        FROM films f
        LEFT JOIN film_genres fg ON f.film_id = fg.film_id
        LEFT JOIN genres g ON fg.genre_id = g.genre_id
        GROUP BY f.film_id
        ORDER BY f.release_year DESC
        LIMIT ?
        ''', (limit,))
        return self.cursor.fetchall()

    def get_film_by_id(self, film_id):
        """Получение фильма по ID"""
        self.cursor.execute('''
        SELECT f.*, GROUP_CONCAT(g.genre_name, ', ') as genres
        FROM films f
        LEFT JOIN film_genres fg ON f.film_id = fg.film_id
        LEFT JOIN genres g ON fg.genre_id = g.genre_id
        WHERE f.film_id = ?
        GROUP BY f.film_id
        ''', (film_id,))
        return self.cursor.fetchone()

    def search_films(self, search_type, value):
        """Поиск фильмов"""
        if search_type == 'title':
            self.cursor.execute('''
            SELECT f.*, GROUP_CONCAT(g.genre_name, ', ') as genres
            FROM films f
            LEFT JOIN film_genres fg ON f.film_id = fg.film_id
            LEFT JOIN genres g ON fg.genre_id = g.genre_id
            WHERE f.title LIKE ?
            GROUP BY f.film_id
            ORDER BY f.title
            ''', (f'%{value}%',))
        elif search_type == 'year':
            self.cursor.execute('''
            SELECT f.*, GROUP_CONCAT(g.genre_name, ', ') as genres
            FROM films f
            LEFT JOIN film_genres fg ON f.film_id = fg.film_id
            LEFT JOIN genres g ON fg.genre_id = g.genre_id
            WHERE f.release_year = ?
            GROUP BY f.film_id
            ORDER BY f.title
            ''', (int(value),))
        elif search_type == 'genre':
            self.cursor.execute('''
            SELECT f.*, GROUP_CONCAT(g2.genre_name, ', ') as genres
            FROM films f
            JOIN film_genres fg ON f.film_id = fg.film_id
            JOIN genres g ON fg.genre_id = g.genre_id
            LEFT JOIN film_genres fg2 ON f.film_id = fg2.film_id
            LEFT JOIN genres g2 ON fg2.genre_id = g2.genre_id
            WHERE g.genre_name LIKE ?
            GROUP BY f.film_id
            ORDER BY f.title
            ''', (f'%{value}%',))

        return self.cursor.fetchall()

    def get_all_genres(self):
        """Получение всех жанров"""
        self.cursor.execute('SELECT genre_id, genre_name FROM genres ORDER BY genre_name')
        return self.cursor.fetchall()

    # UPDATE - Обновление
    def update_film_field(self, film_id, field, value):
        """Обновление поля фильма"""
        allowed_fields = ['title', 'release_year', 'duration_minutes', 'description']
        if field not in allowed_fields:
            return False

        try:
            self.cursor.execute(f'''
            UPDATE films SET {field} = ? WHERE film_id = ?
            ''', (value, film_id))
            self.connection.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating film: {e}")
            return False

    # DELETE - Удаление
    def delete_film(self, film_id):
        """Удаление фильма"""
        try:
            self.cursor.execute('DELETE FROM films WHERE film_id = ?', (film_id,))
            self.connection.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting film: {e}")
            return False

    def close(self):
        """Закрытие соединения"""
        self.connection.close()


# Инициализация базы данных
db = FilmsDatabase()


# ========== КОМАНДЫ БОТА ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    welcome_text = f"""
🎬 Привет, {user.first_name}!

Я бот для управления базой данных фильмов.

Доступные команды:
/show - Показать все фильмы
/add - Добавить новый фильм
/search - Поиск фильмов
/update - Обновить информацию о фильме
/delete - Удалить фильм
/genres - Список жанров
/help - Справка
"""
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📚 Справка по командам:

/show - Показать все фильмы в базе
/add - Добавить новый фильм (после команды следуйте инструкциям)
/search - Найти фильм по названию, году или жанру
/update - Изменить информацию о фильме
/delete - Удалить фильм из базы
/genres - Посмотреть все доступные жанры
/cancel - Отменить текущую операцию
"""
    await update.message.reply_text(help_text)


async def show_films(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все фильмы"""
    films = db.get_all_films(limit=20)

    if not films:
        await update.message.reply_text("📭 База данных пуста. Добавьте первый фильм командой /add")
        return

    response = "🎬 *ВСЕ ФИЛЬМЫ В БАЗЕ:*\n\n"

    for film in films:
        film_id, title, duration, year, description, created_at, genres = film
        hours = duration // 60
        minutes = duration % 60
        duration_str = f"{hours}ч {minutes}мин" if hours > 0 else f"{minutes}мин"

        response += f"*{title}* ({year})\n"
        response += f"🆔 ID: `{film_id}`\n"
        response += f"⏱️ {duration_str}\n"
        if genres:
            response += f"🏷️ {genres}\n"
        if description:
            response += f"📝 {description[:100]}...\n" if len(description) > 100 else f"📝 {description}\n"
        response += "━" * 30 + "\n"

    # Разбиваем на части, если сообщение слишком длинное
    if len(response) > 4000:
        parts = [response[i:i + 4000] for i in range(0, len(response), 4000)]
        for part in parts:
            await update.message.reply_text(part, parse_mode='Markdown')
    else:
        await update.message.reply_text(response, parse_mode='Markdown')


async def show_genres(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все жанры"""
    genres = db.get_all_genres()

    if not genres:
        await update.message.reply_text("Жанры не найдены")
        return

    response = "🏷️ *ДОСТУПНЫЕ ЖАНРЫ:*\n\n"
    for genre_id, genre_name in genres:
        response += f"`{genre_id}`. {genre_name}\n"

    await update.message.reply_text(response, parse_mode='Markdown')


# ========== ДОБАВЛЕНИЕ ФИЛЬМА ==========

async def add_film_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления фильма"""
    await update.message.reply_text(
        "🎥 *ДОБАВЛЕНИЕ НОВОГО ФИЛЬМА*\n\n"
        "Введите название фильма:",
        parse_mode='Markdown'
    )
    return ADD_TITLE


async def add_film_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение названия фильма"""
    context.user_data['title'] = update.message.text
    await update.message.reply_text("Введите год выпуска:")
    return ADD_YEAR


async def add_film_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение года выпуска"""
    try:
        year = int(update.message.text)
        if year < 1888 or year > datetime.now().year + 5:
            await update.message.reply_text("❌ Неверный год. Введите корректный год:")
            return ADD_YEAR
        context.user_data['year'] = year
        await update.message.reply_text("Введите продолжительность в минутах:")
        return ADD_DURATION
    except ValueError:
        await update.message.reply_text("❌ Введите число (год):")
        return ADD_YEAR


async def add_film_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение продолжительности"""
    try:
        duration = int(update.message.text)
        if duration <= 0 or duration > 1000:
            await update.message.reply_text("❌ Неверная продолжительность. Введите число от 1 до 1000:")
            return ADD_DURATION
        context.user_data['duration'] = duration
        await update.message.reply_text("Введите описание фильма (можно пропустить, отправив /skip):")
        return ADD_DESCRIPTION
    except ValueError:
        await update.message.reply_text("❌ Введите число (продолжительность в минутах):")
        return ADD_DURATION


async def add_film_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение описания или пропуск"""
    if update.message.text != '/skip':
        context.user_data['description'] = update.message.text
    else:
        context.user_data['description'] = None

    # Показываем доступные жанры
    genres = db.get_all_genres()
    keyboard = []

    for i in range(0, len(genres), 2):
        row = []
        for j in range(2):
            if i + j < len(genres):
                genre_id, genre_name = genres[i + j]
                row.append(InlineKeyboardButton(genre_name, callback_data=f"genre_{genre_id}"))
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("✅ Завершить выбор", callback_data="genre_done")])

    await update.message.reply_text(
        "Выберите жанры для фильма (можно несколько):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    context.user_data['selected_genres'] = []
    return ADD_GENRES


async def add_film_genres(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора жанров"""
    query = update.callback_query
    await query.answer()

    if query.data == "genre_done":
        # Сохраняем фильм в базу
        title = context.user_data['title']
        year = context.user_data['year']
        duration = context.user_data['duration']
        description = context.user_data.get('description')

        film_id = db.add_film(title, year, duration, description)

        if film_id:
            # Добавляем выбранные жанры
            for genre_id in context.user_data['selected_genres']:
                db.add_genre_to_film(film_id, genre_id)

            await query.edit_message_text(
                f"✅ *Фильм успешно добавлен!*\n\n"
                f"*Название:* {title}\n"
                f"*Год:* {year}\n"
                f"*Продолжительность:* {duration} мин\n"
                f"*ID в базе:* `{film_id}`",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ Ошибка при добавлении фильма")

        # Очищаем временные данные
        context.user_data.clear()
        return ConversationHandler.END

    else:
        # Добавляем или удаляем жанр
        genre_id = int(query.data.split('_')[1])

        if genre_id in context.user_data['selected_genres']:
            context.user_data['selected_genres'].remove(genre_id)
            await query.answer("Жанр удален из выбора")
        else:
            context.user_data['selected_genres'].append(genre_id)
            await query.answer("Жанр добавлен к выбору")

        # Обновляем сообщение с текущим выбором
        selected = len(context.user_data['selected_genres'])
        await query.edit_message_text(
            f"Выберите жанры для фильма (можно несколько):\n"
            f"✅ Выбрано: {selected} жанр(ов)",
            reply_markup=query.message.reply_markup
        )

        return ADD_GENRES


# ========== ПОИСК ФИЛЬМОВ ==========

async def search_films_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало поиска"""
    keyboard = [
        [InlineKeyboardButton("🔤 По названию", callback_data="search_title")],
        [InlineKeyboardButton("📅 По году", callback_data="search_year")],
        [InlineKeyboardButton("🏷️ По жанру", callback_data="search_genre")]
    ]

    await update.message.reply_text(
        "🔍 *ПОИСК ФИЛЬМОВ*\n\nВыберите тип поиска:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SEARCH_TYPE


async def search_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора типа поиска"""
    query = update.callback_query
    await query.answer()

    search_type = query.data.split('_')[1]
    context.user_data['search_type'] = search_type

    if search_type == 'title':
        await query.edit_message_text("Введите название или часть названия:")
    elif search_type == 'year':
        await query.edit_message_text("Введите год выпуска:")
    elif search_type == 'genre':
        await query.edit_message_text("Введите название жанра:")

    return SEARCH_VALUE


async def search_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение поиска"""
    search_type = context.user_data['search_type']
    value = update.message.text

    films = db.search_films(search_type, value)

    if not films:
        await update.message.reply_text("😞 Фильмы не найдены")
        return ConversationHandler.END

    response = f"🔍 *РЕЗУЛЬТАТЫ ПОИСКА:*\n\n"

    for film in films[:10]:  # Ограничиваем 10 результатами
        film_id, title, duration, year, description, created_at, genres = film
        response += f"*{title}* ({year})\n"
        response += f"🆔 ID: `{film_id}`\n"
        response += f"⏱️ {duration} мин\n"
        if genres:
            response += f"🏷️ {genres}\n"
        response += "─" * 20 + "\n"

    if len(films) > 10:
        response += f"\n... и ещё {len(films) - 10} фильм(ов)"

    await update.message.reply_text(response, parse_mode='Markdown')
    return ConversationHandler.END


# ========== УДАЛЕНИЕ ФИЛЬМА ==========

async def delete_film_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало удаления фильма"""
    await update.message.reply_text(
        "🗑️ *УДАЛЕНИЕ ФИЛЬМА*\n\n"
        "Введите ID фильма, который хотите удалить:",
        parse_mode='Markdown'
    )
    return DELETE_CONFIRM


async def delete_film_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления"""
    try:
        film_id = int(update.message.text)
        film = db.get_film_by_id(film_id)

        if not film:
            await update.message.reply_text("❌ Фильм с таким ID не найден")
            return ConversationHandler.END

        # Показываем информацию о фильме
        _, title, duration, year, description, _, genres = film

        keyboard = [
            [InlineKeyboardButton("✅ Да, удалить", callback_data=f"delete_yes_{film_id}")],
            [InlineKeyboardButton("❌ Нет, отмена", callback_data="delete_no")]
        ]

        response = f"❗ *ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ*\n\n"
        response += f"Вы действительно хотите удалить фильм?\n\n"
        response += f"*{title}* ({year})\n"
        response += f"⏱️ {duration} мин\n"
        if genres:
            response += f"🏷️ {genres}\n"

        await update.message.reply_text(
            response,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    except ValueError:
        await update.message.reply_text("❌ Введите числовой ID фильма")
        return DELETE_CONFIRM


async def delete_film_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение удаления"""
    query = update.callback_query
    await query.answer()

    if query.data == "delete_no":
        await query.edit_message_text("❌ Удаление отменено")
        return ConversationHandler.END

    # Извлекаем ID фильма из callback_data
    film_id = int(query.data.split('_')[2])

    if db.delete_film(film_id):
        await query.edit_message_text("✅ Фильм успешно удален")
    else:
        await query.edit_message_text("❌ Ошибка при удалении фильма")

    return ConversationHandler.END


# ========== ОБНОВЛЕНИЕ ФИЛЬМА ==========

async def update_film_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало обновления фильма"""
    await update.message.reply_text(
        "✏️ *ОБНОВЛЕНИЕ ФИЛЬМА*\n\n"
        "Введите ID фильма, который хотите обновить:",
        parse_mode='Markdown'
    )
    return UPDATE_CHOICE


async def update_film_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор поля для обновления"""
    try:
        film_id = int(update.message.text)
        film = db.get_film_by_id(film_id)

        if not film:
            await update.message.reply_text("❌ Фильм с таким ID не найден")
            return ConversationHandler.END

        context.user_data['update_film_id'] = film_id

        # Показываем информацию о фильме
        _, title, duration, year, description, _, genres = film

        keyboard = [
            [InlineKeyboardButton("📝 Название", callback_data="update_title")],
            [InlineKeyboardButton("📅 Год", callback_data="update_year")],
            [InlineKeyboardButton("⏱️ Продолжительность", callback_data="update_duration")],
            [InlineKeyboardButton("📄 Описание", callback_data="update_description")]
        ]

        response = f"✏️ *ОБНОВЛЕНИЕ ФИЛЬМА*\n\n"
        response += f"*{title}* ({year})\n"
        response += f"⏱️ {duration} мин\n"
        if genres:
            response += f"🏷️ {genres}\n"
        if description:
            response += f"📄 {description[:100]}...\n" if len(description) > 100 else f"📄 {description}\n"

        response += "\nВыберите поле для обновления:"

        await update.message.reply_text(
            response,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

        return UPDATE_FIELD

    except ValueError:
        await update.message.reply_text("❌ Введите числовой ID фильма")
        return UPDATE_CHOICE


async def update_field_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора поля"""
    query = update.callback_query
    await query.answer()

    field = query.data.split('_')[1]
    context.user_data['update_field'] = field

    field_names = {
        'title': 'название',
        'year': 'год выпуска',
        'duration': 'продолжительность (в минутах)',
        'description': 'описание'
    }

    await query.edit_message_text(f"Введите новое значение для поля '{field_names[field]}':")
    return UPDATE_VALUE


async def update_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение обновления"""
    film_id = context.user_data['update_film_id']
    field = context.user_data['update_field']
    value = update.message.text

    # Валидация значений
    try:
        if field == 'year':
            value = int(value)
            if value < 1888 or value > datetime.now().year + 5:
                await update.message.reply_text("❌ Неверный год. Введите корректный год:")
                return UPDATE_VALUE
        elif field == 'duration':
            value = int(value)
            if value <= 0 or value > 1000:
                await update.message.reply_text("❌ Неверная продолжительность. Введите число от 1 до 1000:")
                return UPDATE_VALUE
    except ValueError:
        await update.message.reply_text(f"❌ Введите корректное значение для {field}:")
        return UPDATE_VALUE

    # Обновляем поле
    field_db_name = 'release_year' if field == 'year' else 'duration_minutes' if field == 'duration' else field

    if db.update_film_field(film_id, field_db_name, value):
        await update.message.reply_text("✅ Фильм успешно обновлен!")
    else:
        await update.message.reply_text("❌ Ошибка при обновлении фильма")

    return ConversationHandler.END


# ========== ОБРАБОТЧИК ОТМЕНЫ ==========

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена текущей операции"""
    await update.message.reply_text("❌ Операция отменена")
    context.user_data.clear()
    return ConversationHandler.END


# ========== ОСНОВНАЯ ФУНКЦИЯ ==========

def main():
    """Запуск бота"""
    # Импортируем токен из config.py
    try:
        from config import BOT_TOKEN
    except ImportError:
        print("❌ Создайте файл config.py с переменной BOT_TOKEN!")
        return

    # Создаем Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Обработчики простых команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("show", show_films))
    application.add_handler(CommandHandler("genres", show_genres))

    # ConversationHandler для добавления фильма
    add_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", add_film_start)],
        states={
            ADD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_film_title)],
            ADD_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_film_year)],
            ADD_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_film_duration)],
            ADD_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_film_description)],
            ADD_GENRES: [CallbackQueryHandler(add_film_genres)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # ConversationHandler для поиска
    search_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("search", search_films_start)],
        states={
            SEARCH_TYPE: [CallbackQueryHandler(search_type_selected)],
            SEARCH_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_execute)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # ConversationHandler для удаления
    delete_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("delete", delete_film_start)],
        states={
            DELETE_CONFIRM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, delete_film_confirm),
                CallbackQueryHandler(delete_film_execute)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # ConversationHandler для обновления
    update_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("update", update_film_start)],
        states={
            UPDATE_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_film_choice)],
            UPDATE_FIELD: [CallbackQueryHandler(update_field_selected)],
            UPDATE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_execute)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Добавляем все обработчики
    application.add_handler(add_conv_handler)
    application.add_handler(search_conv_handler)
    application.add_handler(delete_conv_handler)
    application.add_handler(update_conv_handler)

    # Запускаем бота
    print("🤖 Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()