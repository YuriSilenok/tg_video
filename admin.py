import csv
from typing import List
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from peewee import fn, JOIN, Case

from filters import IsAdmin
from common import get_date_time, error_handler, send_task
from models import *


router = Router()



class UploadVideo(StatesGroup):
    wait_upload = State()


@router.message(Command('send_task'), IsAdmin())
@error_handler()
async def st(message: Message):
    await send_task(message.bot)


@router.message(Command('report_reviewers'), IsAdmin())
@error_handler()
async def report_reviewers(message: Message):
    reviewers: List[User] = (
        User
        .select(User)
        .join(UserRole)
        .join(Role)
        .join(ReviewRequest, on=(ReviewRequest.reviewer_id==User.id))
        .where(
            (Role.name == 'Проверяющий') &
            (ReviewRequest.status == 1) # Видео проверено
        )
        .group_by(User)
        .order_by(User.reviewer_rating)
    )
    result = 'Отчет о проверяющих\n\n'
    result += '\n'.join([
        f"{u.reviewer_score:05.2f}|{u.reviewer_rating:05.3f}|{u.link}" for u in reviewers
    ])

    await message.answer(
        text=result,
        parse_mode='HTML',
        disable_web_page_preview=True,
    )


@router.message(Command('report_blogers'), IsAdmin())
@error_handler()
async def report_blogers(message: Message):
    points = []
    blogers = (
        User
        .select(User)
        .where(User.bloger_score > 0)
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
async def add_role(message: Message):
    
    data = message.text.strip().replace('  ', '').split()
    if len(data) != 3:
        await message.answer(
            text=' Не верное коичетво параметров. Команда, роль, юзернейм'
        )
        return
    role_name = data[2]
    role = Role.get_or_none(name=role_name)
    if role is None:
        await message.answer(
            text=f'Нет роли {role_name}'
        )
        return
    
    username = data[1].strip()
    user = User.get_or_none(username=username)
    if user is None:
        await message.answer(
            text=f'Нет пользователя с юзернейм {username}'
        )
        return
    UserRole.get_or_create(
        user=user,
        role=role
    )
    await message.answer(
        text='Роль добавлена'
    )


@router.message(Command('set_comment'), IsAdmin())
@error_handler()
async def set_comment(message: Message):
    
    data = message.text.strip().replace('  ', '').split(maxsplit=1)[1]
    data = data.split(maxsplit=1)
    username = data[0]
    user = User.get_or_none(username=username)
    if user is None:
        await message.answer(
            text='Пользователь с таким юзернейм не найден'
        )
        return

    user.comment = data[1]
    user.save()

    await message.answer(
        text='Комментарий записан'
    )


RR_STATUS = {
    -1: '❌',
    0: '⚡' ,
    1: '✅',
}

TASK_STATUS = {
    0: '📹',
    1: '👀',
    2: '⏱️'
}


@router.message(Command('report_themes'), IsAdmin())
@error_handler()
async def report_themes(message: Message):
    
    tasks: List[Task] = (
        Task
        .select(Task)
        .where(Task.status.between(0,2))
        .join(User, on=(User.id==Task.implementer))
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
            # (
            #     task.due_date if task.status == 0 
            #     else task.videos.first().at_created
            # ).strftime("%Y-%m-%d %H:%M"),
            (
                f'{task.due_date.strftime("%d %H:%M")}' if task.status == 0 else
                '' if task.status == 1 
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
                        [(ReviewRequest.status==0, ReviewRequest.due_date)],
                        Review.at_created
                    )
                )
            )

            line = ''.join([
                (
                    f'{rr.reviews.first().score:3.1f}<a href="https://t.me/{rr.reviewer.username}">{RR_STATUS[rr.status]}</a>'
                    if rr.status == 1 else
                    f'{rr.due_date.strftime("%d %H:%M")}<a href="https://t.me/{rr.reviewer.username}">{RR_STATUS[rr.status]}</a>'
                    if rr.status == 0 else
                    f'<a href="https://t.me/{rr.reviewer.username}">{RR_STATUS[rr.status]}</a>'
                ) for rr in rrs
            ])
    
            if line:
                point.append(line)
    
        points[task.status].append(
            '\n'.join(point)
        )


    end_points = []
    char_count = 0
    for status in (1,0,2):
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
async def add_course(message: Message, state: FSMContext):

    file = await message.bot.download(message.document.file_id)
    try:
        file.seek(0)  # Устанавливаем указатель в начало
        table = csv.reader(file.read().decode("utf-8").splitlines())  # Читаем строки
        
        load_videos = []
        for row in table:
            course_title = row[0]
            if not course_title:
                break

            course, _ = Course.get_or_create(
                title=course_title
            )
            theme_title = row[1]
            theme_url = row[2]
            theme, _ = Theme.get_or_create(
                course=course,
                title=theme_title,
                url=theme_url
            )

            theme_complexity = float(row[3].replace(',', '.'))
            if theme.complexity != theme_complexity:
                theme.complexity = theme_complexity
                theme.save()

            if len(row) > 4 and row[4] != '':
                score = 0.0
                status = 1

                if len(row) > 5 and row[5] != '':
                    score = float(row[5].replace(',', '.'))
                    if score  >= 0.8:
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
                text='Темы курса загружены. Загрузка видео не требуется',
            )
            for user in User.select():
                update_bloger_score_and_rating(user)

        else:            
            await state.set_data({
                'load_videos': load_videos
            })
            await state.set_state(UploadVideo.wait_upload)
            await message.answer(
                text=f'Отправьте видео на тему "{load_videos[0]["title"]}"'
            )
        
    except Exception as e:
        await message.answer(f"Ошибка при чтении CSV: {e}")


@router.message(F.video, IsAdmin(), UploadVideo.wait_upload)
@error_handler()
async def upload_video(message: Message, state: FSMContext):

    data = await state.get_data()
    load_videos = data['load_videos']
    if len(load_videos) == 0:
        await message.answer(
            text='Все видео загружены',
        )
        return
    
    load_video = load_videos.pop(0)
    implementer = User.get(username=load_video['implementer'])
    theme = Theme.get(id=load_video['theme'])
    status=load_video['status']
    score=load_video['score']
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

    text = update_bloger_score_and_rating(implementer)
    await message.bot.send_message(
        chat_id=implementer.tg_id,
        text=f'Видео на тему {theme.title} загружено администратором.\n\n{text}'
    )

    if len(load_videos) == 0:
        await state.clear()
        await message.answer(
            text='Все видео загружены'
        )
        return

    await state.set_data({
        'load_videos': load_videos
    })

    await message.answer(
        text=f'Отправьте видео на тему "{load_videos[0]["title"]}"'
    )
