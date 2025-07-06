"""Модуль обработки пользовательских команд"""

from ast import Dict
from typing import List

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from peewee import fn

from common import error_handler, send_message_admins, send_task
from filters import IsAdmin, IsBloger, IsUser
from models import Course, Task, Theme, User, UserCourse, UserRole

# pylint: disable=no-member

router = Router()


@router.message(Command("set_fio"))
async def set_fio(message: Message):
    """Обрабатывает команду /set_fio для установки ФИО пользователя"""
    data = message.text.replace("  ", " ").split(maxsplit=1)
    if len(data) < 2:
        await message.answer(text="После команды ожидается ФИО")
        return
    fio = data[1]
    if len(fio.split()) != 3:
        await message.answer(text="Ожидается 3 слова")
        return

    user = User.get(tg_id=message.from_user.id)
    user.comment = fio
    user.save()

    await message.answer(
        text=(
            "Спасибо!\n"
            "Для начала, Вам нужно ознакомиться со списком курсов, "
            "при помощи команды /courses.\n"
            "В каждом курсе представлено несколько ссылок на ближайшие "
            "свободные темы.\n"
            "Вы можете ознакомиться с материалами по ним, чтобы понять "
            "сложность курса.\n"
            "Если курс Вам подходит, на него нужно подписаться, "
            "тогда бот будет знать, что темы по этому курсу можно "
            "Вам выдавать.\n"
            "После того как Вы подпишетесь на все интересующие Вас курсы "
            "и будете готовы получить задачу, пошлите команду /bloger_on.\n"
            "Бот не выдаст тему для видео сразу, он поставит вас в очередь, "
            "и как только наступит ваша очередь, бот выдаст Вам тему.\n"
            "Если Вы больше не хотите получать темы, "
            "Вы можете воспользоваться командой /bloger_off."
        )
    )

    await send_message_admins(
        bot=message.bot,
        text=f"Пользователь @{user.username} указал свои ФИО {user.comment}",
    )


@router.message(Command("start"))
async def start(message: Message):
    """Обрабатывает команду /start для регистрации/приветствия пользователя"""
    user: User = User.get_or_none(tg_id=message.from_user.id)

    if user is None:

        user = User.create(
            tg_id=message.from_user.id,
            username=message.from_user.username,
        )

        await send_message_admins(
            bot=message.bot, text=f"Регистрация пользователя @{user.username}"
        )

    elif user.username != message.from_user.username:
        user.username = message.from_user.username
        user.save()

    commands = [
        BotCommand(command="/courses", description="Выбрать курсы"),
        BotCommand(command="/bloger_on", description="Выдавать темы"),
        BotCommand(command="/bloger_off", description="Не выдавать темы"),
        BotCommand(command="/report", description="Мои баллы"),
    ]

    await message.bot.set_my_commands(commands=commands)

    reply_markup = None

    if UserRole.get_or_none(user=user, role=IsAdmin.role):

        keyboard = [
            [
                KeyboardButton(text="/report_reviewers"),
                KeyboardButton(text="/report_blogers"),
            ],
            [
                KeyboardButton(text="/report_tasks"),
                KeyboardButton(text="/send_task"),
            ],
        ]

        reply_markup = ReplyKeyboardMarkup(
            keyboard=keyboard, resize_keyboard=True
        )

    text = (
        "Здравствуйте, Вы запустили бота который выдает темы "
        "для записи видео. "
    )

    if user.comment is None:
        text += (
            "Представьтесь, укажите свои ФИО отправив команду "
            "в следующем формате <b>/set_fio Иванов Иван Иванович</b>"
        )

    await message.answer(
        text=text, parse_mode="HTML", reply_markup=reply_markup
    )


@router.message(Command("report"), IsUser())
async def report(message: Message):
    """Обрабатывает команду /report для получения отчета пользователя"""
    user: User = User.get(tg_id=message.from_user.id)
    await message.answer(
        text=user.get_report(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(Command("bloger_on"), IsUser())
@error_handler()
async def bloger_on(message: Message):
    """Пользователь подает заявку стать блогером"""

    user = User.get(tg_id=message.from_user.id)
    UserRole.get_or_create(
        user=user,
        role=IsBloger.role,
    )

    await message.answer(
        text="Теперь вы Блогер.\n"
        "Ожидайте, как только наступит Ваша очередь, "
        "Вам будет выдана тема."
    )

    await send_message_admins(
        bot=message.bot,
        text=f"""<b>Роль Блогер выдана</b>
Пользователь: @{user.username}|{user.comment}""",
    )

    await send_task(message.bot)


def get_text_by_result(result):
    text = "<b>Список курсов</b>\n"

    for course_id in result:
        course: Dict[int, Dict] = result[course_id]
        course_text: str = (
            f"\n<b>{course['title']}</b>|{course['bloger_count']} желающих\n"
        )

        for theme_text in course["themes"]:
            course_text += theme_text

        text += course_text

    return text


def get_data_by_courses(user: User):
    """Получает данные о курсах для пользователя."""
    themes_done = Theme.select(Theme.id).join(Task).where(Task.status >= 2)

    courses = (
        Course.select(
            Course.id.alias("course_id"),
            Course.title.alias(alias="course_title"),
            Theme.id.alias("theme_id"),
            Theme.title.alias(alias="theme_title"),
            Theme.url.alias(alias="theme_url"),
            Theme.complexity.alias(alias="theme_complexity"),
        )
        .join(Theme, on=Theme.course == Course.id)
        .where((~Theme.id << themes_done))
        .group_by()
    )

    data: Dict[int, Dict] = {}

    for row in courses.dicts():
        if row["course_id"] not in data:

            bloger_count = (
                UserCourse.select(fn.COUNT(UserCourse.id))
                .join(UserRole, on=UserRole.user == UserCourse.user)
                .where(
                    (UserCourse.course_id == row["course_id"])
                    & (UserRole.role_id == IsBloger.role.id)
                )
                .scalar()
            )

            user_course: UserCourse = UserCourse.get_or_none(
                user=user,
                course=row["course_id"],
            )

            data[row["course_id"]] = {
                "title": row["course_title"],
                "themes": {},
                "bloger_count": bloger_count,
                "button_text": f'{"✅" if user_course else "❌"}{row["course_title"]}',
                "callback_data": (
                    f"del_user_course_{row['course_id']}"
                    if user_course
                    else f"add_user_course_{row['course_id']}"
                ),
            }

        course = data[row["course_id"]]
        # if len(course['themes']) < 3:
        course["themes"][row["theme_id"]] = {
            "title": row["theme_title"],
            "url": row["theme_url"],
            "complexity": row["theme_complexity"],
        }

    course_ids: List[int] = sorted(
        data,
        key=lambda k: -data[k]["bloger_count"] * 10 + len(data[k]["themes"]),
    )

    inline_keyboard = []

    result = {}

    theme_ind = -1
    run = True
    while run:
        run = False
        theme_ind += 1

        for course_id in course_ids:

            course = data[course_id]

            if course_id not in result:

                result[course_id] = {
                    "title": course["title"],
                    "themes": [],
                    "bloger_count": course["bloger_count"],
                    "button_text": course["button_text"],
                    "callback_data": course["callback_data"],
                }

            themes = list(course["themes"].values())

            if theme_ind < len(themes):
                theme: Dict[int, str] = themes[theme_ind]
                theme_text = f'<a href="{theme["url"]}">{theme["title"]}</a>|{theme["complexity"]}\n'
                if len(get_text_by_result(result) + theme_text) >= 4096:
                    continue
                run = True
                result[course_id]["themes"].append(theme_text)

            if len(get_text_by_result(result)) >= 4096:
                continue

            inline_keyboard.append(
                [
                    InlineKeyboardButton(
                        text=course["button_text"],
                        callback_data=course["callback_data"],
                    )
                ]
            )

    return {
        "text": get_text_by_result(result),
        "reply_markup": InlineKeyboardMarkup(inline_keyboard=inline_keyboard),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }


@router.message(Command("courses"), IsUser())
@error_handler()
async def show_courses(message: Message):
    """Обработчик команды /courses."""
    await message.answer(
        **get_data_by_courses(User.get(tg_id=message.from_user.id))
    )


@router.callback_query(F.data.startswith("add_user_course_"), IsUser())
@error_handler()
async def add_user_course(callback: CallbackQuery):
    """Обработчик добавления курса пользователю."""
    user = User.get(tg_id=callback.from_user.id)
    course = Course.get_by_id(
        int(callback.data[(callback.data.rfind("_") + 1) :])
    )
    UserCourse.get_or_create(
        user=user,
        course=course,
    )
    await callback.message.edit_text(**get_data_by_courses(user=user))
    await send_message_admins(
        bot=callback.bot,
        text=f"Пользователь {user.comment} подписался на курс {course.title}",
    )
    await send_task(callback.bot)


@router.callback_query(F.data.startswith("del_user_course_"), IsUser())
@error_handler()
async def del_user_course(callback: CallbackQuery):
    """Обработчик удаления курса у пользователя."""
    user = User.get(tg_id=callback.from_user.id)
    course = Course.get_by_id(
        int(callback.data[(callback.data.rfind("_") + 1) :])
    )

    user_course = UserCourse.get_or_none(
        user=user,
        course=course,
    )

    if user_course:
        user_course.delete_instance(recursive=True)

    await callback.message.edit_text(**get_data_by_courses(user))

    await send_message_admins(
        bot=callback.bot,
        text=f"Пользователь {user.comment} отписался от курса {course.title}",
    )
