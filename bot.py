import logging
import random
from flask import Flask, request
import telebot
from typing import Dict, Set, List, Optional
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# Настройки бота
TOKEN = "7991880472:AAFEbXe_hQzPC_KIqxiRnpwIQ30KnQ5P_JQ"
ADMIN_IDS = {7225179442}  # Используем множество для быстрого поиска

# Типы данных для аннотаций
UserData = Dict[str, any]
UsersDB = Dict[int, UserData]

# База данных
users_db: UsersDB = {}
used_ids: Set[int] = set()
blacklist: Set[int] = set()  # Черный список Telegram ID
supports: Set[int] = set()  # Множество для хранения support-пользователей

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def generate_unique_id() -> int:
    """Генерирует уникальный 5-значный ID для пользователя"""
    while True:
        new_id = random.randint(10000, 99999)
        if new_id not in used_ids:
            used_ids.add(new_id)
            return new_id


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return user_id in ADMIN_IDS


def is_support(user_id: int) -> bool:
    """Проверяет, является ли пользователь support-пользователем"""
    return user_id in supports


def has_admin_rights(user_id: int) -> bool:
    """Проверяет, есть ли у пользователя права администратора или support"""
    return is_admin(user_id) or is_support(user_id)


async def check_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет наличие профиля и блокировку пользователя"""
    user = update.effective_user

    if user.id in blacklist:
        await update.message.reply_text("❌ Вы заблокированы и не можете пользоваться ботом!")
        return False

    if user.id not in users_db or "login" not in users_db[user.id]:
        await update.message.reply_text(
            "❌ У вас нет профиля. Пожалуйста, создайте профиль командой /login ваш_логин ваш_пароль"
        )
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user

    if user.id in blacklist:
        await update.message.reply_text("❌ Вы заблокированы и не можете пользоваться ботом!")
        return

    # Инициализация данных для нового пользователя
    if user.id not in users_db:
        users_db[user.id] = {
            "cn_friends": [],
            "telegram_name": user.full_name,
            "telegram_id": user.id,
        }

    # Проверка наличия профиля
    if "login" not in users_db[user.id]:
        await update.message.reply_text(
            "👋 Добро пожаловать! Пожалуйста, создайте профиль командой:\n"
            "/login ваш_логин ваш_пароль\n\n"
            "Пример: /login user123 mypassword"
        )
        return

    # Создаем клавиатуру в зависимости от прав пользователя
    if has_admin_rights(user.id):
        reply_keyboard = [
            [KeyboardButton("👤 Профиль"), KeyboardButton("👑 Админ-панель")],
            [KeyboardButton("📊 Cn Friends"), KeyboardButton("📚 Instructions")],
        ]
    else:
        reply_keyboard = [
            [KeyboardButton("👤 Профиль"), KeyboardButton("📊 Cn Friends")],
            [KeyboardButton("📚 Instructions")],
        ]

    await update.message.reply_text(
        "👋 Главное меню",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, resize_keyboard=True, one_time_keyboard=False
        ),
    )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает панель администратора"""
    if not await check_profile(update, context):
        return
    if not has_admin_rights(update.effective_user.id):
        await update.message.reply_text("❌ Доступ запрещен!")
        return

    keyboard = [
        [InlineKeyboardButton("Все пользователи", callback_data="all_users")],
        [InlineKeyboardButton("Отправить сообщение", callback_data="send_message")],
        [InlineKeyboardButton("Управление Cn Friends", callback_data="manage_cn_friends")],
        [InlineKeyboardButton("Черный список", callback_data="manage_blacklist")],
    ]

    # Только админ может назначать support
    if is_admin(update.effective_user.id):
        keyboard.append([InlineKeyboardButton("Назначить Support", callback_data="assign_support")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👑 Админ-панель", reply_markup=reply_markup)


async def show_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает инструкции по использованию бота"""
    instructions = (
        "📚 Инструкции по использованию бота:\n\n"
        "1. Для создания профиля используйте команду /login ваш_логин ваш_пароль\n"
        "2. В разделе 'Профиль' вы можете посмотреть свои данные\n"
        "3. В разделе 'Cn Friends' вы можете управлять своими записями\n"
        "4. Для помощи обращайтесь к администратору"
    )
    await update.message.reply_text(instructions)


async def assign_support_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Меню для назначения прав Support"""
    query = update.callback_query
    await query.answer()

    if not users_db:
        await query.edit_message_text("📭 Нет зарегистрированных пользователей")
        return

    keyboard = []
    for user_id, data in users_db.items():
        if "personal_id" in data and not is_admin(user_id):
            status = "🟢 Support" if user_id in supports else "🔵 Обычный"
            btn_text = f"{data['telegram_name']} (ID: {data['personal_id']}) - {status}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"toggle_support_{user_id}")])

    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_admin")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "👥 Выберите пользователя для назначения/снятия прав Support:",
        reply_markup=reply_markup,
    )


async def toggle_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Переключает статус Support для пользователя"""
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.split("_")[-1])
    user_data = users_db[user_id]

    if user_id in supports:
        supports.remove(user_id)
        action = "лишён прав Support"
    else:
        supports.add(user_id)
        action = "назначен Support"

    keyboard = [
        [InlineKeyboardButton("Назад к списку", callback_data="assign_support")],
        [InlineKeyboardButton("В админ-панель", callback_data="back_to_admin")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✅ Пользователь {user_data['telegram_name']} {action}!",
        reply_markup=reply_markup,
    )


async def select_user_for_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выбор пользователя для отправки сообщения"""
    query = update.callback_query
    await query.answer()

    if not users_db:
        await query.edit_message_text("📭 Нет зарегистрированных пользователей")
        return

    keyboard = []
    for user_id, data in users_db.items():
        if "personal_id" in data:
            btn_text = f"{data['telegram_name']} (ID: {data['personal_id']})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"send_to_user_{user_id}")])

    keyboard.append([InlineKeyboardButton("Отправить всем", callback_data="send_to_all")])
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_admin")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "👥 Выберите пользователя для отправки сообщения:",
        reply_markup=reply_markup,
    )


async def prepare_message_for_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подготовка сообщения для конкретного пользователя"""
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.split("_")[-1])
    context.user_data["message_target"] = user_id
    await query.edit_message_text("✉ Введите текст сообщения для этого пользователя:")


async def prepare_message_for_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Подготовка сообщения для всех пользователей"""
    query = update.callback_query
    await query.answer()

    context.user_data["message_target"] = "all"
    await query.edit_message_text("✉ Введите текст сообщения для всех пользователей:")


async def send_individual_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправка сообщения конкретному пользователю"""
    if "message_target" not in context.user_data:
        return

    target_id = context.user_data["message_target"]
    message_text = update.message.text

    try:
        await context.bot.send_message(
            target_id, f"📨 Сообщение от администратора:\n\n{message_text}"
        )
        await update.message.reply_text(
            f"✅ Сообщение отправлено пользователю {users_db[target_id]['telegram_name']}"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        await update.message.reply_text(f"❌ Не удалось отправить сообщение: {e}")

    del context.user_data["message_target"]


async def send_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Рассылка сообщения всем пользователям"""
    if "message_target" not in context.user_data or context.user_data["message_target"] != "all":
        return

    message_text = update.message.text
    success_count = 0
    fail_count = 0

    for user_id, data in users_db.items():
        try:
            await context.bot.send_message(
                user_id, f"📨 Сообщение от администратора (рассылка):\n\n{message_text}"
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
            fail_count += 1

    await update.message.reply_text(
        f"✅ Рассылка завершена!\nУспешно отправлено: {success_count}\nНе удалось отправить: {fail_count}"
    )

    del context.user_data["message_target"]


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает профиль пользователя"""
    if not await check_profile(update, context):
        return

    user = update.effective_user
    user_data = users_db[user.id]

    profile_info = (
        f"📌 Ваш профиль:\n"
        f"👤 Имя: {user_data['telegram_name']}\n"
        f"🔑 Логин: {user_data['login']}\n"
        f"🆔 ID: {user_data['personal_id']}\n"
    )

    if has_admin_rights(user.id):
        profile_info += f"📝 Telegram ID: {user_data['telegram_id']}\n"
        profile_info += f"👑 Статус: {'Admin' if is_admin(user.id) else 'Support'}\n"

    if user.id in blacklist:
        profile_info += "🚫 Статус: Заблокирован\n"

    await update.message.reply_text(profile_info)


async def show_cn_friends(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает список Cn Friends пользователя"""
    if not await check_profile(update, context):
        return

    user = update.effective_user
    user_data = users_db[user.id]
    cn_friends = user_data.get("cn_friends", [])

    if not cn_friends:
        await update.message.reply_text("📊 У вас пока нет записей Cn Friends")
        return

    response = "📊 Ваши Cn Friends:\n\n"
    for i, friend in enumerate(cn_friends, 1):
        response += (
            f"{i}. Login: {friend.get('login', 'N/A')}\n"
            f"   Статус: {friend.get('status', 'Не установлен')}\n"
            f"   Кем взят: {friend.get('taken_by', 'Не указано')}\n\n"
        )

    await update.message.reply_text(response)


async def manage_cn_friends_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Меню управления Cn Friends"""
    query = update.callback_query
    await query.answer()

    if not users_db:
        await query.edit_message_text("📭 Нет зарегистрированных пользователей")
        return

    keyboard = []
    for user_id, data in users_db.items():
        if "personal_id" in data:
            btn_text = f"{data['telegram_name']} (ID: {data['personal_id']})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"user_cn_friends_{user_id}")])

    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_admin")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "👥 Выберите пользователя для управления Cn Friends:",
        reply_markup=reply_markup,
    )


async def show_user_cn_friends(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает Cn Friends конкретного пользователя"""
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.split("_")[-1])
    user_data = users_db[user_id]

    context.user_data["editing_user"] = user_id

    keyboard = [
        [InlineKeyboardButton("Добавить запись", callback_data=f"add_cn_friend_{user_id}")],
        [InlineKeyboardButton("Редактировать записи", callback_data=f"edit_cn_friends_{user_id}")],
        [InlineKeyboardButton("Назад", callback_data="manage_cn_friends")],
    ]

    cn_friends = user_data.get("cn_friends", [])
    cn_friends_text = (
        f"У пользователя {len(cn_friends)} записей Cn Friends"
        if cn_friends
        else "У пользователя нет записей Cn Friends"
    )

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"📊 Cn Friends пользователя {user_data['telegram_name']}:\n\n{cn_friends_text}",
        reply_markup=reply_markup,
    )


async def add_cn_friend_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Меню добавления нового Cn Friend"""
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.split("_")[-1])
    context.user_data["adding_cn_friend_for"] = user_id
    context.user_data["cn_friend_stage"] = "login"

    await query.edit_message_text("Введите login для новой записи Cn Friend:")


async def process_cn_friend_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ввода login для нового Cn Friend"""
    user_id = context.user_data["adding_cn_friend_for"]
    login = update.message.text

    context.user_data["new_cn_friend"] = {"login": login}
    context.user_data["cn_friend_stage"] = "status"

    await update.message.reply_text("Введите статус для этой записи:")


async def process_cn_friend_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ввода status для нового Cn Friend"""
    status = update.message.text
    context.user_data["new_cn_friend"]["status"] = status
    context.user_data["cn_friend_stage"] = "taken_by"

    await update.message.reply_text("Введите кем взят (никнейм администратора):")


async def process_cn_friend_taken_by(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка ввода taken_by для нового Cn Friend и сохранение записи"""
    taken_by = update.message.text
    user_id = context.user_data["adding_cn_friend_for"]
    new_cn_friend = context.user_data["new_cn_friend"]
    new_cn_friend["taken_by"] = taken_by

    if "cn_friends" not in users_db[user_id]:
        users_db[user_id]["cn_friends"] = []

    users_db[user_id]["cn_friends"].append(new_cn_friend)

    # Очищаем состояние
    del context.user_data["adding_cn_friend_for"]
    del context.user_data["new_cn_friend"]
    del context.user_data["cn_friend_stage"]

    await update.message.reply_text(
        f"✅ Новая запись Cn Friend добавлена для пользователя {users_db[user_id]['telegram_name']}!"
    )
    await show_user_cn_friends(update, context)


async def edit_cn_friends_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Меню редактирования записей Cn Friends"""
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.split("_")[-1])
    user_data = users_db[user_id]
    cn_friends = user_data.get("cn_friends", [])

    if not cn_friends:
        await query.answer("У пользователя нет записей Cn Friends")
        return

    keyboard = []
    for i, friend in enumerate(cn_friends, 1):
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"Запись #{i}: {friend.get('login', 'N/A')}",
                    callback_data=f"edit_cn_friend_{user_id}_{i - 1}",
                )
            ]
        )
    keyboard.append([InlineKeyboardButton("Назад", callback_data=f"user_cn_friends_{user_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "Выберите запись для редактирования:",
        reply_markup=reply_markup,
    )


async def edit_cn_friend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Меню редактирования конкретной записи Cn Friend"""
    query = update.callback_query
    await query.answer()

    _, user_id, friend_index = query.data.split("_")
    user_id = int(user_id)
    friend_index = int(friend_index)

    context.user_data["editing_cn_friend"] = {
        "user_id": user_id,
        "friend_index": friend_index,
    }

    keyboard = [
        [
            InlineKeyboardButton(
                "Изменить login",
                callback_data=f"change_login_{user_id}_{friend_index}",
            )
        ],
        [
            InlineKeyboardButton(
                "Изменить статус",
                callback_data=f"change_status_{user_id}_{friend_index}",
            )
        ],
        [
            InlineKeyboardButton(
                "Изменить 'Кем взят'",
                callback_data=f"change_taken_by_{user_id}_{friend_index}",
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Удалить запись",
                callback_data=f"delete_cn_friend_{user_id}_{friend_index}",
            )
        ],
        [
            InlineKeyboardButton(
                "Назад",
                callback_data=f"edit_cn_friends_{user_id}",
            )
        ],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "Выберите параметр для изменения:",
        reply_markup=reply_markup,
    )


async def change_cn_friend_param(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запрос на изменение параметра Cn Friend"""
    query = update.callback_query
    await query.answer()

    action, user_id, friend_index = query.data.split("_")[:3]
    user_id = int(user_id)
    friend_index = int(friend_index)

    param_map = {
        "change_login": "login",
        "change_status": "status",
        "change_taken_by": "taken_by",
    }

    param = param_map.get(action)
    if not param:
        return

    context.user_data["editing_cn_param"] = {
        "user_id": user_id,
        "friend_index": friend_index,
        "param": param,
    }

    await query.edit_message_text(f"Введите новое значение для {param}:")


async def save_cn_friend_param(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сохранение измененного параметра Cn Friend"""
    if "editing_cn_param" not in context.user_data:
        return

    editing_data = context.user_data["editing_cn_param"]
    user_id = editing_data["user_id"]
    friend_index = editing_data["friend_index"]
    param = editing_data["param"]
    new_value = update.message.text

    users_db[user_id]["cn_friends"][friend_index][param] = new_value

    del context.user_data["editing_cn_param"]
    await update.message.reply_text("✅ Изменения сохранены!")
    await edit_cn_friend(update, context)


async def delete_cn_friend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удаление записи Cn Friend"""
    query = update.callback_query
    await query.answer()

    _, user_id, friend_index = query.data.split("_")
    user_id = int(user_id)
    friend_index = int(friend_index)

    try:
        deleted_friend = users_db[user_id]["cn_friends"].pop(friend_index)
        await query.edit_message_text(
            f"✅ Запись удалена: {deleted_friend.get('login', 'N/A')}"
        )
        await edit_cn_friends_menu(update, context)
    except (IndexError, KeyError):
        await query.answer("Ошибка при удалении записи")


async def login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /login"""
    user = update.effective_user

    # Проверка на черный список
    if user.id in blacklist:
        await update.message.reply_text("❌ Вы заблокированы и не можете пользоваться ботом!")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Неверный формат. Используйте: /login логин пароль")
        return

    login, password = context.args[0], " ".join(context.args[1:])

    if len(login) < 3 or len(password) < 4:
        await update.message.reply_text("⚠ Логин должен быть от 3 символов, пароль - от 4")
        return

    personal_id = generate_unique_id()

    # Инициализация данных пользователя
    if user.id not in users_db:
        users_db[user.id] = {
            "cn_friends": [],
            "telegram_name": user.full_name,
            "telegram_id": user.id,
        }

    users_db[user.id].update(
        {
            "login": login,
            "password": password,
            "personal_id": personal_id,
        }
    )

    await update.message.reply_text(
        f"✅ Профиль создан!\n"
        f"🔑 Логин: {login}\n"
        f"🆔 Ваш ID: {personal_id}\n\n"
        "Теперь вы можете пользоваться ботом!"
    )
    await start(update, context)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline-кнопки"""
    query = update.callback_query
    await query.answer()

    handlers = {
        "all_users": handle_all_users,
        "send_message": select_user_for_message,
        "manage_cn_friends": manage_cn_friends_menu,
        "manage_blacklist": manage_blacklist_menu,
        "assign_support": assign_support_menu,
        "send_to_all": prepare_message_for_all,
        "back_to_admin": admin_panel,
    }

    # Проверяем, есть ли обработчик для данного callback_data
    for prefix, handler in handlers.items():
        if query.data == prefix:
            await handler(update, context)
            return

    # Обработка callback_data с префиксами
    if query.data.startswith("send_to_user_"):
        await prepare_message_for_user(update, context)
    elif query.data.startswith("toggle_support_"):
        await toggle_support(update, context)
    elif query.data.startswith("blacklist_user_"):
        await toggle_blacklist_user(update, context)
    elif query.data.startswith("user_cn_friends_"):
        await show_user_cn_friends(update, context)
    elif query.data.startswith("add_cn_friend_"):
        await add_cn_friend_menu(update, context)
    elif query.data.startswith("edit_cn_friends_"):
        await edit_cn_friends_menu(update, context)
    elif query.data.startswith("edit_cn_friend_"):
        await edit_cn_friend(update, context)
    elif query.data.startswith("change_"):
        await change_cn_friend_param(update, context)
    elif query.data.startswith("delete_cn_friend_"):
        await delete_cn_friend(update, context)


async def handle_all_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает список всех пользователей"""
    query = update.callback_query
    await query.answer()

    if not users_db:
        await query.edit_message_text("📭 Нет зарегистрированных пользователей")
        return

    users_list = "\n\n".join(
        f"👤 {data['telegram_name']}\n"
        f"🔑 Логин: {data.get('login', 'не установлен')}\n"
        f"🆔 ID: {data.get('personal_id', 'не установлен')}\n"
        f"📊 Cn Friends: {len(data.get('cn_friends', []))}\n"
        f"📝 TG ID: {user_id}\n"
        f"👑 {'Admin' if is_admin(user_id) else 'Support' if is_support(user_id) else 'User'}"
        for user_id, data in users_db.items()
        if "personal_id" in data
    )
    await query.edit_message_text(
        f"👥 Все пользователи ({len([u for u in users_db.values() if 'personal_id' in u])}):\n\n{users_list}"
    )


async def manage_blacklist_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Меню управления черным списком"""
    query = update.callback_query
    await query.answer()

    if not users_db:
        await query.edit_message_text("📭 Нет зарегистрированных пользователей")
        return

    keyboard = []
    for user_id, data in users_db.items():
        if "personal_id" in data:
            status = "🔴 Заблокирован" if user_id in blacklist else "🟢 Активен"
            btn_text = f"{data['telegram_name']} (ID: {data['personal_id']}) - {status}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"blacklist_user_{user_id}")])

    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_to_admin")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "👥 Черный список. Выберите пользователя:",
        reply_markup=reply_markup,
    )


async def toggle_blacklist_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавление/удаление пользователя из черного списка"""
    query = update.callback_query
    await query.answer()

    user_id = int(query.data.split("_")[-1])
    user_data = users_db[user_id]

    if user_id in blacklist:
        blacklist.remove(user_id)
        action = "разблокирован"
    else:
        blacklist.add(user_id)
        action = "заблокирован"

    keyboard = [
        [InlineKeyboardButton("Назад к списку", callback_data="manage_blacklist")],
        [InlineKeyboardButton("В админ-панель", callback_data="back_to_admin")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✅ Пользователь {user_data['telegram_name']} {action}!",
        reply_markup=reply_markup,
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений"""
    if not await check_profile(update, context):
        return

    text = update.message.text

    handlers = {
        "👤 Профиль": show_profile,
        "👑 Админ-панель": admin_panel,
        "📊 Cn Friends": show_cn_friends,
        "📚 Instructions": show_instructions,
    }

    # Проверяем стандартные команды
    if text in handlers:
        await handlers[text](update, context)
        return

    # Обработка состояний
    if "cn_friend_stage" in context.user_data:
        stages = {
            "login": process_cn_friend_login,
            "status": process_cn_friend_status,
            "taken_by": process_cn_friend_taken_by,
        }
        stage_handler = stages.get(context.user_data["cn_friend_stage"])
        if stage_handler:
            await stage_handler(update, context)
            return

    if "editing_cn_param" in context.user_data:
        await save_cn_friend_param(update, context)
        return

    if "message_target" in context.user_data:
        if context.user_data["message_target"] == "all":
            await send_broadcast_message(update, context)
        else:
            await send_individual_message(update, context)
        return


def setup_handlers(application: Application) -> None:
    """Настройка обработчиков команд и сообщений"""
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("profile", show_profile))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("send_message", handle_message))
    application.add_handler(CommandHandler("instructions", show_instructions))

    # Обработчики кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)  # ← Вот эта строка задаёт порт
