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
        text = (
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


def get_data_by_courses(user: User):
    themes_done = (
        Theme
        .select(Theme.id)
        .join(Task)
        .where(Task.status >= 2)
    )
    
    themes: List[Theme] = (Theme
        .select(Theme)
        .join(Course, on=(Course.id==Theme.course))
        .join(Task, JOIN.LEFT_OUTER, on=(Task.theme==Theme.id))
        .where(
            (~Theme.id << themes_done)
        )
        .group_by(
            Theme.course,
            Theme.id
        )
        .order_by(
            fn.LENGTH(Course.title),
            Theme.id,
        )
    )
    
    data = {}
    text = '<b>Список курсов</b>\n\n'
    inline_keyboard=[]

    for theme in themes:
        course = theme.course
        
        if course.id not in data:
            data[course.id] = []
        
        if len(data[course.id]) >= 3:
            continue
        
        data[course.id].append(theme)

        user_course = UserCourse.get_or_none(
            user=user,
            course=course,
        )

        if len(data[course.id]) == 3:

            bloger_count = (
                UserCourse
                .select(fn.COUNT(UserCourse.id))
                .join(UserRole, on=(UserRole.user == UserCourse.user))
                .where(
                    (UserCourse.course_id == course.id) &
                    (UserRole.role_id == IsBloger.role.id)
                )
                .scalar()
            )
            themes_str = '\n'.join([ f'<a href="{t.url}">{t.title}</a>|{t.complexity}' for t in data[course.id][:3]])
            text+=f'<b>{course.title}</b>|{bloger_count}\n{themes_str}\n\n'
            row = None

            if len(inline_keyboard) == 0:
                row = []
            elif sum([len(i.text) for i in inline_keyboard[-1]]) + len(course.title) + 1 < 25:
                row = inline_keyboard.pop()
            else:
                row = []
            row.append(
                InlineKeyboardButton(
                    text=f'{"✅" if user_course else "❌"}{course.title}',
                    callback_data=f'del_user_course_{course.id}' if user_course else f'add_user_course_{course.id}'
                )
            )
            inline_keyboard.append(row)
    return {
        'text': text,
        'reply_markup': InlineKeyboardMarkup(
            inline_keyboard=inline_keyboard
        ),
        'parse_mode': "HTML",
        'disable_web_page_preview': True,
    }



@router.message(Command('courses'), IsUser())
@error_handler()
async def show_courses(message: Message):
    await message.answer(
        **get_data_by_courses(
            User.get(tg_id=message.from_user.id)
        )
    )



@router.callback_query(F.data.startswith('add_user_course_'), IsUser())
@error_handler()
async def add_user_course(callback: CallbackQuery):
    user = User.get(tg_id=callback.from_user.id)
    course = Course.get_by_id(int(callback.data[(callback.data.rfind('_')+1):]))
    UserCourse.get_or_create(
        user=user,
        course=course,
    )
    await callback.message.edit_text(
        **get_data_by_courses(user)
    )
    await send_message_admins(
        bot=callback.bot,
        text=f'Пользователь {user.comment} подписался на курс {course.title}'
    )
    await send_task(callback.bot)


@router.callback_query(F.data.startswith('del_user_course_'), IsUser())
@error_handler()
async def del_user_course(callback: CallbackQuery):

    user = User.get(tg_id=callback.from_user.id)
    course=Course.get_by_id(int(callback.data[(callback.data.rfind('_')+1):]))

    user_course = UserCourse.get_or_none(
        user=user,
        course=course,
    )

    if user_course:
        user_course.delete_instance()

    await callback.message.edit_text(
        **get_data_by_courses(user)
    )

    await send_message_admins(
        bot=callback.bot,
        text=f'Пользователь {user.comment} отписался от курса {course.title}'
    )
