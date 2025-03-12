"""Взаимодействие с блогером"""

from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from models import (
    Course, Role, Task, Theme, UserCourse, UserRole, Video,
    User, TASK_STATUS, update_bloger_score_and_rating
)
from peewee import fn, JOIN
from common import get_id, get_user

router = Router()


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



@router.message(Command('bloger_on'))
async def bloger_on(message: Message):
    """Пользователь подает заявку стать блогером"""

    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    
    user_role = await get_bloger_user_role(message.bot, user)
    if user_role:
        await message.answer(
            text='У вас уже есть роль блогера, ожидайте полчения темы.'
        )
        return

    UserRole.create(
        user=user,
        role=Role.get(name='Блогер'),
    )

    await message.answer(
        text='Теперь вы Блогер.\n'
        'Ожидайте, как только наступит Ваша очередь, '
        'Вам будет выдана тема.'
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

    await bot.send_message(
        chat_id=user.tg_id,
        text='Роль блогера снята'
    )


@router.message(Command('bloger_off'))
async def bloger_off(message: Message):

    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    
    await drop_bloger(message.bot, user)


@router.callback_query(F.data.startswith('del_task_yes_'))
async def del_task_yes(query: CallbackQuery):
    """Подтверждение в отказе делать задачу"""

    await query.message.delete()

    user = await get_user(query.bot, query.from_user.id)
    if user is None:
        return

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

    report = update_bloger_score_and_rating(user)

    await query.message.answer(
        text=f'Задача cнята\n\n{report}'
    )

    await drop_bloger(query.bot, user)



@router.message(Command('courses'))
async def show_courses(message: Message):
    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    

    query = (Course
        .select(Course)
        .join(Theme)
        .join(Task, JOIN.LEFT_OUTER)
        .where((Task.status < 0) | (Task.status.is_null()))
        .group_by(Course)
        .having(fn.COUNT(Theme) > 0))
    
    for course in query:
        
        user_course = UserCourse.get_or_none(
            user=user,
            course=course,
        )
        
        await message.answer(
            text=course.title,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text='Отписаться' if user_course else 'Подписаться',
                            callback_data=f'del_user_course_{course.id}' if user_course else f'add_user_course_{course.id}'
                        )
                    ]
                ]
            )
        )


@router.callback_query(F.data.startswith('add_user_course_'))
async def add_user_course(query: CallbackQuery):
    user = await get_user(query.bot, query.from_user.id)
    if user is None:
        return

    course=Course.get_by_id(int(query.data[(query.data.rfind('_')+1):]))
    user_course, _ = UserCourse.get_or_create(
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


@router.callback_query(F.data.startswith('del_user_course_'))
async def del_user_course(query: CallbackQuery):
    user = await get_user(query.bot, query.from_user.id)
    if user is None:
        return

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

@router.message(F.video)
async def upload_video(message: Message):
    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    
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

    admins = (
        User
        .select(User)
        .join(UserRole)
        .join(Role)
        .where(Role.name=='Админ')
    )

    for admin in admins:
        await message.bot.send_message(
            chat_id=admin.tg_id,
            text=f'Пользователь @{user.username} прислал видео по теме {task.theme.title}'
        )   
