from typing import List
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, BotCommand, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from admin import send_message_admins
from common import error_handler
from filters import IsUser
from models import Course, ReviewRequest, Role, Task, Theme, User, UserCourse, UserRole, Video, update_bloger_score_and_rating
from peewee import JOIN

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
        text='Спасибо! '
        'Для начала, Вам нужно ознакомится со списком курсов, при помощи команды /courses. '
        'В каждой курсе представлено несколько ссылок на ближайшие свободные темы. '
        'Вы можете ознакомится с материалом по ним, что бы понять сложность курса. '
        'Если курс Вам подходит, на него нужно подписаться, тогда бот бужет знать, '
        'что темы по этому курсу можно Вам выдавать. '
        'После того как Вы подпишетесь на все интересующие Вас курсы и будете готовы получить задачу, '
        'пошлике команду /bloger_on. Бот не выдаст тема для видео сразу, он поставит вас в очередь, '
        'и как только наступит ваша очередь, бод выдаст Вам тему. '
        'Если Вы больше не хотите получать темы, Вы можете воспользоваться командой /bloger_off. '
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

    
    commands = commands=[
        BotCommand(
            command='/courses',
            description='Выбрать курсы, по которым будут выдаваться темы'
        ),
        BotCommand(
            command='/bloger_on',
            description='Готов получить тему для видео'
        ),
        BotCommand(
            command='/bloger_off',
            description='Больше не выдавать мне темы для видео'
        ),
        BotCommand(
            command='/report',
            description='Получить отчет о заработанных баллах'
        ),
    ]
    await message.bot.set_my_commands(
        commands=commands   
    )

    await message.answer(
        text = (
            "Здравствуйте, Вы запустили бота который выдает темы для записи видео. "
            "Представьтесь, укажите свои ФИО отправив команду в следующем формате "
            "<b>/set_fio Иванов Иван Иванович</b>"
        ),
        parse_mode='HTML',
    )


@router.message(Command('report'), IsUser())
async def report(message: Message):
    user: User = User.get(tg_id=message.from_user.id)
    rev_bloger: List[ReviewRequest] = (
        ReviewRequest
        .select(ReviewRequest)
        .join(Video, on=(Video.id==ReviewRequest.video))
        .where(
            (ReviewRequest.status == 1) &
            (ReviewRequest.reviewer == user)
        )
    )
    if len(rev_bloger) > 0:
        text = ['<b>Отчёт проверяющего</b>']
        sum_score = 0
        for t in rev_bloger:
            score = t.video.duration / 1200
            text.append(
                f'{t.video.task.theme.title}:{t.video.duration}c.|{round(score, 2)} балла'
            )
            sum_score += score
        text.append(f'ИТОГ: {user.reviewer_score}')
        await message.answer(
            text='\n'.join(text),
            parse_mode='HTML',
        )

    if user.bloger_score > 0:
        await message.answer(
            text=update_bloger_score_and_rating(user)
        )



@router.message(Command('bloger_on'), IsUser())
@error_handler()
async def bloger_on(message: Message):
    """Пользователь подает заявку стать блогером"""

    user = User.get(tg_id=message.from_user.id)
    UserRole.create(
        user=user,
        role=Role.get(name='Блогер'),
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


@router.message(Command('courses'), IsUser())
@error_handler()
async def show_courses(message: Message):

    themes_done = (
        Theme
        .select(Theme.id)
        .join(Task)
        .where(Task.status >= 2)
    )
    
    themes: List[Theme] = (Theme
        .select(Theme)
        .join(Task, JOIN.LEFT_OUTER, on=(Task.theme==Theme.id))
        .where(
            (~Theme.id << themes_done)
        )
        .group_by(
            Theme.course,
            Theme.id
        )
        .order_by(
            Theme.course,
            Theme.id,
        )
    )
    
    data = {}

    for theme in themes:
        key = (theme.course.id, theme.course.title)
        if key not in data:
            data[(theme.course.id, theme.course.title)] = []
        data[key].append(theme)
        

    for (course_id, course_title), themes in data.items():

        if len(themes) == 0:
            continue

        user = User.get(tg_id=message.from_user.id)
        user_course = UserCourse.get_or_none(
            user=user,
            course=course_id,
        )
        themes_str = '\n'.join([ f'<a href="{t.url}">{t.title}</a>|{t.complexity}' for t in themes[:3]])
        await message.answer(
            text=f'<b>{course_title}</b>\n{themes_str}',
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text='Отписаться' if user_course else 'Подписаться',
                            callback_data=f'del_user_course_{course_id}' if user_course else f'add_user_course_{course_id}'
                        )
                    ]
                ]
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
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
    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Отписаться',
                        callback_data=f'del_user_course_{course.id}'
                    )
                ]
            ]
        )
    )
    await send_message_admins(
        bot=callback.bot,
        text=f'Пользователь {user.comment} подписался на курс {course.title}'
    )


@router.callback_query(F.data.startswith('del_user_course_'), IsUser())
@error_handler()
async def del_user_course(callback: CallbackQuery):
    user = User.get(tg_id=callback.from_user.id)
    course=Course.get_by_id(int(callback.data[(callback.data.rfind('_')+1):]))
    user_course = UserCourse.get_or_none(
        user=user,
        course=course,
    )

    if not user_course:
        return

    await callback.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text='Подписаться',
                        callback_data=f'add_user_course_{course.id}'
                    )
                ]
            ]
        )
    )
    user_course.delete_instance()
    await send_message_admins(
        bot=callback.bot,
        text=f'Пользователь {user.comment} отписался от курса {course.title}'
    )

