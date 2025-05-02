"""Обработка событий для администратора"""

import csv
from typing import List
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from peewee import JOIN, Case

from filters import IsAdmin
from common import (
    add_reviewer, get_date_time, error_handler, get_id, send_task
)
from models import (
    ReviewRequest, Review, Video, Task, User, Role, UserRole, Course, Theme
)


RR_STATUS = {
    -1: '❌',
    0: '⚡',
    1: '✅',
}


TASK_STATUS = {
    0: '📹',
    1: '👀',
    2: '⏱️'
}


router = Router()


class UploadVideo(StatesGroup):
    """Состояние для загрузки готовых видео при загрузке курса"""

    # Ожидает загрузки видео
    wait_upload = State()


@router.callback_query(F.data.startswith('del_rr_'))
@error_handler()
async def delete_review_request_handler(callback: CallbackQuery):
    """Удаление запроса на проверку и отчета о проверке"""

    review_request_id = get_id(callback.data)
    review_request: ReviewRequest = ReviewRequest.get_or_none(
        id=review_request_id
    )

    if not review_request:
        await callback.answer(
            text='Запрос на проверку не найден'
        )
        return

    review: Review = review_request.reviews.first()
    if not review:
        await callback.answer(
            text='Не найден отзыв'
        )
        return
    video: Video = review_request.video
    task: Task = video.task
    if task.status != 1:
        task.status = 1
        task.save()
        await callback.message.reply(
            text='Проверка по задаче возобновлена',
        )

    await callback.message.reply(
        text='Запрос на проверку и отзыв удалён'
    )

    await callback.bot.send_message(
        chat_id=review_request.reviewer.tg_id,
        text='Ваш отзыв и запрос на проверку видео удален. '
        'Ожидайте следующее видео на проверку. '
        'Возможно бот выдаст видео на проверку повторно.\n\n'
        f'{review.comment}'
    )

    await callback.bot.send_message(
        chat_id=task.implementer.tg_id,
        text=f'Отзыв по вашему видео удален.\n\n{review.comment}'
    )

    review_request.delete_instance(recursive=True)
    await add_reviewer(callback.bot, video.id)


@router.message(Command('send_task'), IsAdmin())
@error_handler()
async def send_task_handler(message: Message):
    """Отправить задачу блогеру"""
    await send_task(message.bot)


@router.message(Command('report_reviewers'), IsAdmin())
@error_handler()
async def report_reviewers_handler(message: Message):
    """Получить отчет по проверяющим"""
    old_date = get_date_time(hours=-24*14)
    reviewers: List[User] = (
        User
        .select(User)
        .where(
            (User.reviewer_score > 0) &
            (User.id << (
                ReviewRequest
                .select(ReviewRequest.reviewer)
                .join(Review)
                .where(Review.at_created >= old_date)
            ))
        )
        .group_by(User)
        .order_by(User.reviewer_rating.desc())
    )
    text = '👀📄<b>Отчет о проверяющих</b>\n'
    text += '\n'.join([
        f"{u.reviewer_score:05.2f}|{(u.reviewer_rating*100):05.2f}|{u.link}"
        for u in reviewers
    ])

    await message.answer(
        text=text,
        parse_mode='HTML',
        disable_web_page_preview=True,
    )


@router.message(Command('report_blogers'), IsAdmin())
@error_handler()
async def report_blogers_hadler(message: Message):
    """Отчет по блогерам"""
    points = ['📹📄<b>Отчет о блогерах</b>']
    old_date = get_date_time(hours=-24*14)
    blogers = (
        User
        .select(User)
        .where(
            (User.bloger_score > 0) &
            (User.id << (
                Task
                .select(Task.implementer)
                .join(Video)
                .where(Video.at_created >= old_date)
            ))
        )
        .order_by(User.bloger_rating.desc())
    )
    for bloger in blogers:
        points.append(
            f'{bloger.bloger_score:05.2f}'
            f'|{(bloger.bloger_rating*100):05.2f}'
            f'|{bloger.link}'
        )

    text = '\n'.join(points)
    await message.answer(
        text=text,
        parse_mode='HTML',
        disable_web_page_preview=True,
    )


@router.message(Command('add_role'), IsAdmin())
@error_handler()
async def add_role_handler(message: Message):
    """Добавление указанной роли указанному пользователю"""
    data = message.text.strip().replace('  ', '').split()
    if len(data) != 3:
        await message.answer(
            text=' ❌Неверное количество параметров. Команда, роль, юзернейм'
        )
        return
    role_name = data[2]
    role = Role.get_or_none(name=role_name)
    if role is None:
        await message.answer(
            text=f'📤🙅‍♂🔑Нет роли {role_name}'
        )
        return

    username = data[1].replace('@', '').strip()
    user = User.get_or_none(username=username)
    if user is None:
        await message.answer(
            text=f'📤🙅‍♂👩‍💻⏮🆔Нет пользователя с юзернейм {username}'
        )
        return
    UserRole.get_or_create(
        user=user,
        role=role
    )
    await message.answer(
        text='🔑🚮Роль добавлена'
    )


@router.message(Command('set_comment'), IsAdmin())
@error_handler()
async def set_comment_handler(message: Message):
    """Указать ФИО указанному пользователю"""
    data = message.text.strip().replace('  ', '').split(maxsplit=1)[1]
    data = data.split(maxsplit=1)
    username = data[0].replace('@', '').strip()
    user = User.get_or_none(username=username)
    if user is None:
        await message.answer(
            text='👩‍💻⏮👉🆔🚫🔎Пользователь с таким юзернейм не найден'
        )
        return

    user.comment = data[1]
    user.save()

    await message.answer(
        text='🏤⏺Комментарий записан'
    )


@router.message(Command('report_tasks'), IsAdmin())
@error_handler()
async def report_tasks_handler(message: Message):
    """Отчет по задачам"""
    tasks: List[Task] = (
        Task
        .select(Task)
        .where(Task.status.between(0, 2))
        .join(
            User,
            on=User.id == Task.implementer
        )
        .order_by(
            Task.status.desc(),
            User.bloger_rating.desc(),
        )
    )

    points = [[], [], []]

    for task in tasks:
        implementer: User = task.implementer
        point = ['|'.join([
            TASK_STATUS[task.status],
            f'{task.theme.complexity:5.3f}',
            task.theme.course.title,
            task.theme.title,
            (
                f'{task.due_date.strftime("%d %H:%M")}'
                if task.status == 0
                else '' if task.status == 1
                else f'{(task.score*100):05.2f}'
            ),
            implementer.link,
            f'{(implementer.bloger_rating*100):05.2f}'
        ])]
        if task.status > 0:
            rrs = (
                task
                .videos
                .first()
                .reviewrequests
                .join(Review, JOIN.LEFT_OUTER)
                .order_by(
                    ReviewRequest.status.desc(),
                    Case(
                        None,
                        [(ReviewRequest.status == 0, ReviewRequest.due_date)],
                        Review.at_created
                    )
                )
            )

            line = ''.join([
                (
                    (
                        f'<a href="https://t.me/{rr.reviewer.username}">'
                        f'{RR_STATUS[rr.status]}</a>'
                        f'{rr.reviews.first().score:3.1f}'
                    )
                    if rr.status == 1 else
                    (
                        f'<a href="https://t.me/{rr.reviewer.username}">'
                        f'{RR_STATUS[rr.status]}</a>'
                        f'{rr.due_date.strftime("%d %H:%M")}'
                    )
                    if rr.status == 0 else
                    (
                        f'<a href="https://t.me/{rr.reviewer.username}">'
                        f'{RR_STATUS[rr.status]}</a>'
                    )
                ) for rr in rrs
            ])
            if line:
                point.append(line)

        points[task.status].append(
            '\n'.join(point)
        )

    end_points = []
    char_count = 0
    for status in (1, 0, 2):
        for point in points[status]:
            if len(point) + char_count < 4096:
                end_points.append(point)
                char_count += len(point)

    await message.answer(
        text='\n\n'.join(end_points),
        parse_mode='HTML',
        disable_web_page_preview=True,
    )


@router.message(F.document.file_name.endswith(".csv"), IsAdmin())
@error_handler()
async def add_course_handler(message: Message, state: FSMContext):
    """Добавляет курсы из csv"""
    file = await message.bot.download(message.document.file_id)
    try:
        file.seek(0)  # Устанавливаем указатель в начало
        table = csv.reader(file.read().decode("utf-8").splitlines())

        load_videos = []
        for row in table:
            course_title = row[0]
            if not course_title:
                break

            course, _ = Course.get_or_create(
                title=course_title
            )
            theme_title = row[1]
            theme: Theme = Theme.get_or_none(
                course=course,
                title=theme_title,
            )

            theme_url = row[2]
            theme_complexity = float(row[3].replace(',', '.'))
            if not theme:
                theme = Theme.create(
                    course=course,
                    title=theme_title,
                    url=theme_url,
                    complexity=theme_complexity
                )
            else:
                is_save = False

                if theme.complexity != theme_complexity:
                    theme.complexity = theme_complexity
                    is_save = True

                if theme.url != theme_url:
                    theme.url = theme_url
                    is_save = True

                if is_save:
                    theme.save()

            if len(row) > 4 and row[4] != '':
                score = 0.0
                status = 1

                if len(row) > 5 and row[5] != '':
                    score = float(row[5].replace(',', '.'))
                    if score >= 0.8:
                        status = 2
                    else:
                        status = -2

                load_videos.append({
                    'theme': theme.id,
                    'title': theme.title,
                    'implementer': row[4].replace('@', ''),
                    'score': score,
                    'status': status,
                })

        if len(load_videos) == 0:
            await message.answer(
                text='↗️❔📐Темы курса загружены. Загрузка видео не требуется',
            )
            users: List[User] = User.select()
            for user in users:
                user.update_bloger_score()

        else:
            await state.set_data({
                'load_videos': load_videos
            })
            await state.set_state(UploadVideo.wait_upload)
            await message.answer(
                text=f'📨📹Отправьте видео на тему "{load_videos[0]["title"]}"'
            )
    except FileNotFoundError:
        await message.answer("Файл не найден. Проверьте путь.")
    except PermissionError:
        await message.answer("Нет прав для чтения файла.")
    except UnicodeDecodeError:
        await message.answer(
            "Ошибка кодировки файла. Проверьте кодировку (например, utf-8).")
    except csv.Error as e:
        await message.answer(f"Ошибка в формате CSV: {e}")
    except IsADirectoryError:
        await message.answer("Указан путь к папке, а не к файлу.")
    except OSError as e:
        await message.answer(f"Ошибка работы с файлом: {e}")
    except ValueError as e:
        await message.answer(f"Ошибка обработки данных в CSV: {e}")


@router.message(F.video, IsAdmin(), UploadVideo.wait_upload)
@error_handler()
async def upload_video_handler(message: Message, state: FSMContext):
    """Обработать загрузку видео к добавляемому курсу"""
    data = await state.get_data()
    load_videos = data['load_videos']
    if len(load_videos) == 0:
        await message.answer(
            text='🌐📹✔️📂Все видео загружены',
        )
        return

    load_video = load_videos.pop(0)
    implementer: User = User.get(username=load_video['implementer'])
    theme = Theme.get(id=load_video['theme'])
    status = load_video['status']
    score = load_video['score']
    task, _ = Task.get_or_create(
        implementer=implementer,
        theme=theme,
        status=status,
        score=score,
        due_date=get_date_time(0)
    )

    Video.get_or_create(
        task=task,
        file_id=message.video.file_id,
        duration=message.video.duration,
    )

    implementer.update_bloger_score()
    await message.bot.send_message(
        chat_id=implementer.tg_id,
        text=f'📹📂👨‍💼Видео на тему {theme.title} загружено администратором.'
        f'\n\n{implementer.get_bloger_report()}',
        parse_mode='HTML',
        disable_web_page_preview=True,
    )

    if len(load_videos) == 0:
        await state.clear()
        await message.answer(
            text='🌐📹✔️📂Все видео загружены'
        )
        return

    await state.set_data({
        'load_videos': load_videos
    })

    await message.answer(
        text=f'📨📹Отправьте видео на тему "{load_videos[0]["title"]}"'
    )
