"""Взаимодействие с блогером"""

from datetime import datetime, timedelta
from typing import List
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest


from filters import IsBloger, WaitVideo
from models import Course, Role, Task, UserCourse, UserRole, Video, User, TASK_STATUS, update_bloger_score_and_rating
from common import get_id, get_date_time, error_handler, send_message_admins, send_new_review_request, send_task

router = Router()


@error_handler()
@router.message(F.document, IsBloger(), WaitVideo())
async def upload_file(message: Message):
    await message.answer(
        text='📹🔜📨📹🚫📁.Видео нужно отправить как видео, а не как файл'
    )


@error_handler()
async def get_bloger_user_role(bot: Bot, user: User):
    """Проверяем наличие привилегии блогера"""
    
    # Наличие роли
    role = Role.get_or_none(name='Блогер')
    if role is None:
        await bot.send_message(
            chat_id=user.tg_id,
            text=(
                "🕴🔑🚫🔎Роль блогера не найдена! "
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


@error_handler()
async def drop_bloger(bot:Bot, user: User):

    user_role = await get_bloger_user_role(bot, user)   
    if user_role is None:
        await bot.send_message(
            chat_id=user.tg_id,
            text='✔️👆🛠🔑🕴Вам не выдавалась роль блогера.'
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
            text=f'👆💭👆💚☑👅❓У Вас выдана задача на тему "{task.theme.title}", '
            'Вы уверены что хотите отказаться?',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text='👌Да',
                    callback_data=f'del_task_yes_{task.id}',
                )
            ]])
        )
        return


    if user_role:
        user_role.delete_instance()

    await bot.send_message(
        chat_id=user.tg_id,
        text='Роль блогера с Вас снята'
    )

    await send_message_admins(
        bot=bot,
        text=f'''<b>Роль Блогер снята</b>
Пользователь: {user.comment}'''
    )

    await send_task(bot)


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
            'Видео принято на проверку. '
            'Пока новая тема не выдана, '
            'Вы можете отказаться быть блогером без снижения рейтинга.'
        )
    )

    await send_message_admins(
        bot=message.bot,
        text=f'''🕴📨📹<b>Блогер {user.link} прислал видео</b>
Тема: {task.theme.course.title}|{task.theme.link}'''
    )

    await send_new_review_request(message.bot)


@router.callback_query(F.data.startswith('to_extend_') | F.data.startswith('task_to_extend_'), IsBloger())
@error_handler()
async def to_extend(callback_query: CallbackQuery):
    task_id = get_id(callback_query.data)
    task: Task = Task.get_by_id(task_id)

    if task.status != 0:
        await callback_query.message.edit_text(
            text='Срок не может быть продлен. '
            f'Видео по теме <b>{task.theme.title}</b> уже получено.',
            parse_mode='HTML',
            reply_markup=None,
        )
        return
    
    task.due_date += timedelta(days=1)
    task.save()

    await callback_query.message.edit_text(
        text=f'Срок сдвинут до {task.due_date}',
        reply_markup=None,
    )

    await send_message_admins(
        bot=callback_query.bot,
        text=f'''<b>Блогер {task.implementer.link} продлил срок</b>
Тема: {task.theme.course.title}|{task.theme.link}
Срок: {task.due_date}'''
    )


@error_handler()
async def check_expired_task(bot:Bot):
    dd = get_date_time()
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
                text='Вы просрочили срок записи видео. '
                'Тема и Роль блогера с Вас снята',
            )
            task.status = -2
            task.save()
            
            user_role: UserRole = UserRole.get_or_none(
                user=task.implementer,
                role=IsBloger.role
            )
            if user_role:
                user_role.delete_instance()        
            
            await send_message_admins(
                bot=bot,
                text=f'Тему {task.theme.link} просрочил {task.implementer.link}'
            )
            await send_task(bot)

            new_task = Task.get_or_none(
                theme=task.theme,
                status=0,
            )
            if new_task:
                continue

            query: List[UserRole] = (
                UserRole
                .select()
                .where(
                    (UserRole.role_id == IsBloger.role.id) &
                    (~UserRole.user_id << (
                        User
                        .select(User.id)
                        .join(UserCourse)
                        .where(UserCourse.course_id==task.theme.course_id)
                    )) &
                    (~UserRole.user_id<<(
                        Task
                        .select(Task.implementer_id)
                        .where(
                            (Task.status.between(0, 1))
                        )
                    ))
                )
            )
            for user_role in query:
                await bot.send_message(
                    chat_id=user_role.user.tg_id,
                    text=f'Для курса {task.theme.course.title} нет исполнителя'
                    ', подпишитесь на него и получите задачу на разработку видео'
                )
 
        except TelegramBadRequest as ex:
            print(ex, task.implementer.comment)



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
                            callback_data=f'task_to_extend_{task.id}'
                        )
                    ]]
                )
            )
        except TelegramBadRequest as ex:
            print(ex, task.implementer.comment)
    


@error_handler()
async def loop(bot: Bot):
    await check_old_task(bot)
    await check_expired_task(bot)