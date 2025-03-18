"""Взаимодействие с блогером"""

from datetime import datetime, timedelta
from typing import List
from aiogram import Bot, Router, F
from aiogram.filters import Command, BaseFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from admin import error_handler, get_admins, send_message_admins
from models import (
    Course, Role, Task, Theme, UserCourse, UserRole, Video,
    User, TASK_STATUS, update_bloger_score_and_rating
)
from peewee import fn, JOIN
from common import IsUser, get_id, get_date_time

router = Router()


class IsBloger(IsUser):

    role = Role.get(name='Блогер')    

    async def __call__(self, message: Message) -> bool:
        is_user = await super().__call__(message)
        if not is_user:
            return False

        user_role = UserRole.get_or_none(
            user=User.get(tg_id=message.from_user.id),
            role=self.role
        )
        return user_role is not None


class WaitVideo(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        user = User.get(tg_id=message.from_user.id)
        task = Task.get(
            implementer=user,
            status=0
        )
        return task is not None


async def get_bloger_user_role(bot: Bot, user: User):
    """Проверяем наличие привилегии блогера"""
    
    # Наличие роли
    role = Role.get_or_none(name='Блогер')
    if role is None:
        await bot.send_message(
            chat_id=user.tg_id,
            text=(
                "Роль блогера не найдена! "
                "Это проблема администратора! "
                "Cообщите ему всё, что Вы о нем думаете. @YuriSilenok"
            )
        )
        return None
    
    # Наличие роли у пользователя
    user_role = UserRole.get_or_none(
        user=user,
        role=role,
    )

    return user_role


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


async def drop_bloger(bot:Bot, user: User):

    user_role = await get_bloger_user_role(bot, user)   
    if user_role is None:
        await bot.send_message(
            chat_id=user.tg_id,
            text='Вам не выдавалась роль блогера.'
        )
        return


    # Наличие выданной темы
    task = Task.get_or_none(
        implementer=user,
        status=0,
    )

    if task:
        await bot.send_message(
            chat_id=user.tg_id,
            text=f'У Вас выдана задача на тему "{task.theme.title}", '
            'Вы уверены что хотите отказаться?',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text='Да',
                    callback_data=f'del_task_yes_{task.id}',
                )
            ]])
        )
        return


    if user_role:
        user_role.delete_instance()

    await send_message_admins(
        bot=bot,
        text=f'''<b>Роль Блогер снята</b>
Пользователь: {user.comment}'''
    )

@router.message(Command('bloger_off'), IsBloger())
@error_handler()
async def bloger_off(message: Message):

    user = User.get(tg_id=message.from_user.id)
    await drop_bloger(message.bot, user)


@router.callback_query(F.data.startswith('del_task_yes_'), IsBloger())
@error_handler()
async def del_task_yes(query: CallbackQuery):
    """Подтверждение в отказе делать задачу"""

    await query.message.delete()

    task = Task.get_or_none(
        id=get_id(query.data)
    )

    if task is None:
        await query.message.answer(
            text='Задача не найдена'
        )
        return
    
    if task.status != 0:
        await query.message.answer(
            text='От задачи со статусом '
            f'"{TASK_STATUS[task.status]}" нельзя отказаться'
        )
        return

    task.status = -1
    task.save()

    user = User.get(tg_id=query.from_user.id)
    report = update_bloger_score_and_rating(user)

    await query.message.answer(
        text=f'Задача cнята\n\n{report}'
    )

    await drop_bloger(query.bot, user)


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
        themes_str = '\n'.join([ f'<a href="{t.url}">{t.title}</a>' for t in themes[:3]])
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


@router.callback_query(F.data.startswith('add_user_course_'), IsBloger())
@error_handler()
async def add_user_course(query: CallbackQuery):
    user = User.get(tg_id=query.from_user.id)
    course = Course.get_by_id(int(query.data[(query.data.rfind('_')+1):]))
    UserCourse.get_or_create(
        user=user,
        course=course,
    )
    await query.message.edit_reply_markup(
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


@router.callback_query(F.data.startswith('del_user_course_'), IsUser())
@error_handler()
async def del_user_course(query: CallbackQuery):
    user = User.get(tg_id=query.from_user.id)
    course=Course.get_by_id(int(query.data[(query.data.rfind('_')+1):]))
    user_course = UserCourse.get_or_none(
        user=user,
        course=course,
    )

    if not user_course:
        return

    await query.message.edit_reply_markup(
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


@router.message(F.video, IsBloger(), WaitVideo())
@error_handler()
async def upload_video(message: Message):
    user = User.get(tg_id=message.from_user.id)
    tasks = (Task
        .select()
        .where(
            (Task.status==0) &
            (Task.implementer==user)
        )
    )
    
    if tasks.count() == 0:
        await message.answer(
            text='У вас нет выданной темы, я не могу принять это видео'
        )
        return
    
    task = tasks.first()
    Video.create(
        task=task,
        file_id=message.video.file_id,
        duration=message.video.duration,
    )
    task.status = 1
    task.save()

    await message.answer(
        text=(
            'Видео принято на проверку, как только оно будет проверено, '
            'Вы получите новую тему, в этот период вы можете отказаться '
            'быть блогером без штрафов.'
        )
    )

    await send_message_admins(
        bot=message.bot,
        text=f'''<b>Блогер прислал видео</b>
Блогер: {user.comment}
Курс: {task.theme.course.title}
Тема: {task.theme.title}'''
    )


@router.callback_query(F.data.startswith('to_extend_'))
async def to_extend(callback_query: CallbackQuery):
    task_id = get_id(callback_query.data)
    task: Task = Task.get_by_id(task_id)
    task.due_date += timedelta(days=1)
    task.save()
    await callback_query.message.edit_text(
        text=f'Срок сдвинут до {task.due_date}',
        reply_markup=None,
    )

@error_handler()
async def check_old_task(bot:Bot):
    dd = get_date_time(24)
    old_tasks: List[Task] = (
        Task
        .select(Task)
        .where(
            (Task.status==0) &
            (Task.due_date == dd)
        )
    )
    for task in old_tasks:
        try:
            await bot.send_message(
                chat_id=task.implementer.tg_id,
                text='До окончания срока осталось 24 часа. Воспользуйтесь этой кнопкой, что бы продлить срок на сутки',
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text='Продлить',
                            callback_data=f'to_extend_{task.id}'
                        )
                    ]]
                )
            )
        except TelegramBadRequest as ex:
            print(ex, task.implementer.comment)

async def loop(bot: Bot):
    await check_old_task(bot)