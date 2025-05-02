"""Взаимодействие с блогером"""

import traceback
from datetime import datetime, timedelta
from typing import List
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.exceptions import TelegramBadRequest
from peewee import JOIN


from filters import IsBloger, IsReviewer, WaitVideo
from models import Role, Table, Task, Theme, UserCourse, UserRole, Video, User, TASK_STATUS
from common import get_id, get_date_time, error_handler, send_message_admins, send_new_review_request, send_task

router = Router()


@router.message(F.document, IsBloger(), WaitVideo())
@error_handler()
async def upload_file(message: Message):
    """Обрабатывает"""
    await message.answer(
        text='Видео нужно отправить как видео, а не как файл'
    )


@router.message(F.video, IsBloger(), WaitVideo())
@error_handler()
async def upload_video(message: Message):
    user = User.get(tg_id=message.from_user.id)
    tasks = (Task
             .select()
             .where(
                 (Task.status == 0) &
                 (Task.implementer == user)
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


@router.callback_query(F.data.startswith('task_to_extend_'), IsBloger())
@error_handler()
async def to_extend(callback_query: CallbackQuery):
    task_id = get_id(callback_query.data)
    task: Task = Task.get_by_id(task_id)

    if task.status != 0:
        await callback_query.message.edit_text(
            text='Срок не может быть продлён. '
            f'Видео по теме {task.theme.link} уже получено.',
            parse_mode='HTML',
            reply_markup=None,
        )
        return
    theme: Theme = task.theme
    hours = int(theme.complexity * 72 / 2)
    if hours < 24:
        hours = 24

    task.due_date += timedelta(hours=hours)
    task.extension = 0
    task.save()

    await callback_query.message.edit_text(
        text=f'Срок Вашей задачи продлен до {task.due_date}',
        reply_markup=None,
    )

    await send_message_admins(
        bot=callback_query.bot,
        text=f'''<b>Блогер {task.implementer.link} продлил срок</b>
Тема: {task.theme.course.title}|{task.theme.link}
Срок: {task.due_date}'''
    )


@error_handler()
async def check_expired_task(bot: Bot):
    dd = get_date_time()
    old_tasks: List[Task] = (
        Task
        .select(Task)
        .where(
            (Task.status == 0) &
            (Task.due_date == dd)
        )
    )
    for task in old_tasks:
        try:
            task.status = -2
            task.save()

            user_role: UserRole = UserRole.get_or_none(
                user=task.implementer,
                role=IsBloger.role
            )
            if user_role:
                user_role.delete_instance(recursive=True)

            try:
                await bot.send_message(
                    chat_id=task.implementer.tg_id,
                    text='Вы просрочили срок записи видео. '
                    'Тема и Роль блогера с Вас снята. '
                    'Если Вы хотите снова получить темы для видео, '
                    'пошлите команду /bloger_on'
                )
            except TelegramBadRequest:
                await send_message_admins(
                    bot=bot,
                    text=traceback.format_exc()
                )

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
                        .where(UserCourse.course_id == task.theme.course_id)
                    )) &
                    (~UserRole.user_id << (
                        Task
                        .select(Task.implementer_id)
                        .where(
                            (Task.status.between(0, 1))
                        )
                    ))
                )
            )
            for user_role in query:
                try:
                    await bot.send_message(
                        chat_id=user_role.user.tg_id,
                        text=f'Для курса {task.theme.course.title} нет исполнителя'
                        ', подпишитесь на него и получите задачу на разработку видео'
                    )
                except TelegramBadRequest:
                    await send_message_admins(
                        bot=bot,
                        text=traceback.format_exc()
                    )

        except TelegramBadRequest as ex:
            print(ex, task.implementer.comment)


@error_handler()
async def check_old_task(bot: Bot):

    now = get_date_time()

    old_tasks: List[Task] = (
        Task
        .select(Task)
        .where(
            (Task.status == 0) &
            (Task.extension == 0)
        )
    )

    for task in old_tasks:

        theme: Theme = task.theme
        hours = int(theme.complexity * 72 / 2)
        if hours < 24:
            hours = 24
        reserve_time: timedelta = timedelta(hours=hours)
        left_time: datetime = task.due_date - now
        if left_time > reserve_time:
            continue

        try:
            sql_query = f'''
select u.user_id
from (
    select ur.user_id
    from userrole as ur
    inner join user_course as uc on ur.user_id=uc.user_id
    where uc.course_id = {task.theme.course_id} and ur.role_id={IsBloger.role.id}
) as u
left join task on task.implementer_id=u.user_id and task.status in (0, 1)
where task.id is NULL;
'''
            users: List[int] = [r['user_id']
                                for r in Table.raw(sql_query).dicts()]
            cont = False

            for user_id in users:
                u: User = User.get_by_id(user_id)
                if u.bloger_rating > task.implementer.bloger_rating:
                    cont = True
                    break

            if cont:
                continue

            await bot.send_message(
                chat_id=task.implementer.tg_id,
                text=f'Воспользуйтесь этой кнопкой, чтобы продлить срок Вашей задачи до {task.due_date + reserve_time} ',
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[
                        InlineKeyboardButton(
                            text=f'Продлить до {task.due_date + reserve_time}',
                            callback_data=f'task_to_extend_{task.id}'
                        )
                    ]]
                )
            )
            task.extension = 1
            task.save()
        except TelegramBadRequest as ex:
            print(ex, task.implementer.comment)


def update_rating_all_blogers():
    blogers: List[User] = (
        User
        .select(User)
        .join(Task)
        .where(
            (Task.status == 0)
        )
    )

    for bloger in blogers:
        bloger.update_bloger_rating()


@error_handler()
async def loop(bot: Bot):
    update_rating_all_blogers()
    await check_old_task(bot)
    await check_expired_task(bot)
