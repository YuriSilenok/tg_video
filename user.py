from typing import List
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, BotCommand, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup


from common import error_handler, send_task, send_message_admins
from filters import IsBloger, IsReviewer, IsUser, IsAdmin
from models import Course, Role, Task, Theme, User, UserCourse, UserRole
from peewee import JOIN, fn

router = Router()


@router.message(Command('set_fio'))
async def set_fio(message: Message):
    data = message.text.replace('  ', ' ').split(maxsplit=1)
    if len(data) < 2:
        await message.answer(
            text='После команды ожидается ФИО'
        )
        return
    fio = data[1]
    if len(fio.split()) != 3:
        await message.answer(
            text='Ожидается 3 слова'
        )
        return

    user = User.get(tg_id=message.from_user.id)
    user.comment = fio
    user.save()

    await message.answer(
        text='''Спасибо! 
Для начала, Вам нужно ознакомиться со списком курсов, при помощи команды /courses.
В каждом курсе представлено несколько ссылок на ближайшие свободные темы.
Вы можете ознакомиться с материалами по ним, чтобы понять сложность курса.
Если курс Вам подходит, на него нужно подписаться, тогда бот будет знать, что темы по этому курсу можно Вам выдавать.
После того как Вы подпишетесь на все интересующие Вас курсы и будете готовы получить задачу,  пошлите команду /bloger_on.
Бот не выдаст тему для видео сразу, он поставит вас в очередь, и как только наступит ваша очередь, бот выдаст Вам тему.
Если Вы больше не хотите получать темы, Вы можете воспользоваться командой /bloger_off.'''
    )

    await send_message_admins(
        bot=message.bot,
        text=f'Пользователь @{user.username} указал свои ФИО {user.comment}'
    )


@router.message(Command('start'))
async def start(message: Message):

    user = User.get_or_none(
        tg_id=message.from_user.id
    )

    if user is None:

        user = User.create(
            tg_id=message.from_user.id,
            username=message.from_user.username,
        )

        await send_message_admins(
            bot=message.bot,
            text=f'Регистрация пользователя @{user.username}'
        )

    elif user.username != message.from_user.username:
        user.username = message.from_user.username
        user.save()

    commands = [
        BotCommand(
            command='/courses',
            description='Выбрать курсы'
        ),
        BotCommand(
            command='/bloger_on',
            description='Выдавать темы'
        ),
        BotCommand(
            command='/bloger_off',
            description='Не выдавать темы'
        ),
        BotCommand(
            command='/report',
            description='Мои баллы'
        ),
    ]

    await message.bot.set_my_commands(
        commands=commands
    )

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
            ]
        ]

        reply_markup = ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True
        )

    await message.answer(
        text=(
            "Здравствуйте, Вы запустили бота который выдает темы для записи видео. "
            "Представьтесь, укажите свои ФИО отправив команду в следующем формате "
            "<b>/set_fio Иванов Иван Иванович</b>"
        ),
        parse_mode='HTML',
        reply_markup=reply_markup
    )


@router.message(Command('report'), IsUser())
async def report(message: Message):
    user: User = User.get(tg_id=message.from_user.id)
    await message.answer(
        text=user.get_report(),
        parse_mode='HTML',
        disable_web_page_preview=True,
    )


@router.message(Command('bloger_on'), IsUser())
@error_handler()
async def bloger_on(message: Message):
    """Пользователь подает заявку стать блогером"""

    user = User.get(tg_id=message.from_user.id)
    UserRole.get_or_create(
        user=user,
        role=IsBloger.role,
    )

    await message.answer(
        text='Теперь вы Блогер.\n'
        'Ожидайте, как только наступит Ваша очередь, '
        'Вам будет выдана тема.'
    )

    await send_message_admins(
        bot=message.bot,
        text=f'''<b>Роль Блогер выдана</b>
Пользователь: @{user.username}|{user.comment}''',
    )

    await send_task(message.bot)


@router.message(Command('courses'), IsUser())
@error_handler()
async def show_courses(message: Message):
    await message.answer(
        **get_data_by_courses(
            User.get(tg_id=message.from_user.id)
        )
    )
