from datetime import datetime
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from peewee import fn, JOIN

from admin import send_task
from models import (
    Review, ReviewRequest, Role, Task, User, UserRole, Video,
    get_videos_by_request_review, update_bloger_score_and_rating, update_reviewer_score, 
)
from common import get_due_date, get_user

router = Router()


async def get_reviewer_user_role(bot: Bot, user: User):
    """Проверяем наличие привилегии блогера"""
    
    # Наличие роли
    role = Role.get_or_none(name='Проверяющий')
    if role is None:
        await bot.send_message(
            chat_id=user.tg_id,
            text=(
                "Роль проверяющего не найдена! "
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
    if user_role is None:
        await bot.send_message(
            chat_id=user.tg_id,
            text='Вы не являетесь проверяющим!'
        )
        return None

    return user_role


@router.message(Command('check'))
async def check(message: Message):
    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    
    user_role = await get_reviewer_user_role(message.bot, user)
    if not user_role:
        return

    request = ReviewRequest.get_or_none(
        status=0, # на проверке
        reviewer=user,
    )
    if request:
        await message.answer(
            text='У вас уже выдано видео на проверку, проверьте сначала его'
        )
        try:
            await message.answer_video(
                video=request.video.file_id,
                caption=(
                    f'Курс: {request.video.task.theme.course.title}\n'
                    f'Тема: {request.video.task.theme.title}\n'
                    f'url: {request.video.task.theme.url}\n'
                ),
                # reply_markup=Rel
            )
        except TelegramBadRequest:
            print('TelegramBadRequest', 
                f'Курс: {request.video.task.theme.course.title}',
                f'Тема: {request.video.task.theme.title}',
                f'url: {request.video.task.theme.url}',
                sep='\n')
        return


    videos = get_videos_by_request_review(user)    

    if videos.count() == 0:
        await message.answer(
            text='Проверять нечего, можете отдохнуть'
        )
        return
    
    video: Video = videos.first()
    
    due_date = get_due_date(hours=25)
    request = ReviewRequest.create(
        reviewer=user,
        video=video,
        due_date=due_date
    )
    try:
        await message.bot.send_message(
            chat_id=video.task.implementer.tg_id,
            text="Ваше видео выдано на проверку",
        )
    except TelegramBadRequest as ex:
        print('TelegramBadRequest', 'Ваше видео выдано на проверку')

    try:
        caption = (
            f'Это видео нужно проверить до {due_date}.\n'
            f'Курс: "{video.task.theme.course.title}"\n'
            f'Тема: "{video.task.theme.title}"\n'
            f'url: "{video.task.theme.url}"\n'
            'Для оценки видео напишите одно сообщение '
            'в начале которого будет оценка в интервале [0.0; 5.0], '
            'а через пробел отзыв о видео'
        )
        await message.answer_video(
            video=video.file_id,
            caption=caption
        )
    except TelegramBadRequest:
        print(
            'TelegramBadRequest',
            caption,
            sep='\n'
        )

@router.message(F.text)
async def get_score_by_review(message:Message):
    
    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    
    user_role = await get_reviewer_user_role(message.bot, user)
    if not user_role:
        return
    
    """Поиск запроса на проверку"""
    review_request = ReviewRequest.get_or_none(
        reviewer=user,
        status=0 # На проверке
    )
    if review_request is None:
        await message.answer(
            text='Запрос на проверку не найден, используйте команду /check'
        )
        return


    """Валидация оценки"""
    text = message.text.strip()
    digit = text.find(' ')
    digit = text[:digit] if digit >= 0 else text
    digit = digit.replace(',', '.')
    
    try:
        digit = float(digit)
    except ValueError:
        await message.answer(
            text=f'Не удалось преобразовать {digit} в число'
        )
        return
    
    if digit < 0 or digit > 5:
        await message.answer(
            text=f'{digit} должно быть в пределах [0.0; 5.0]'
        )
        return
    
    """Фиксация отзыва"""
    Review.create(
        review_request=review_request,
        score=digit,
        comment=text,
    )
    review_request.status = 1 # Проверено
    review_request.save()
    
    new_score = update_reviewer_score(user)
    await message.answer("Спасибо, ответ записан. "
        f"Всего заработано баллов {new_score}. "
        "Для проверки нового видео, отправьте команду /check")
    
    await message.bot.send_message(
        chat_id=review_request.video.task.implementer.tg_id,
        text=f'Ваше видео оценили\n\n{text}',
    )

    """Выставление итоговой оценки"""    
    reviews = (
        Review
        .select(Review)
        .join(ReviewRequest)
        .where(
            (ReviewRequest.video==review_request.video) &
            (ReviewRequest.status==1)))
    
    if reviews.count() < 5:
        return

    task_score = sum([review.score for review in reviews]) / 25

    task = review_request.video.task
    task.score = task_score
    task.status = 2 if task_score >= 0.8 else -2
    task.save()
    report = update_bloger_score_and_rating(task.implementer)
    
    await message.bot.send_message(
        chat_id=task.implementer.tg_id,
        text=f'Закончена проверка вашего видео.\n\n{report}',
    )

    await send_task(message.bot)

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
            text=f'Видео пользователя @{user.username} на тему {task.theme.title} проверено.'
        )   


async def notify_reviewers(bot: Bot):

    # получить список проверяющих
    
    # для получившего списка задач посчитать количество проверяющих

    reviewers = (User
        .select(User)
        .join(UserRole, on=(UserRole.user_id == User.id))
        .join(Role, on=(UserRole.role_id == Role.id))
        .where(Role.name == 'Проверяющий'))

    # для каждого проверяющего сапоставить задачи которые он еще не проверял
    for reviewer in reviewers:
        # Получить список видео которые нуждаются в проверке и уже проверены текущим проверяющим
        videos = (Video
            .select(Video.id)
            .join(Task, on=(Task.id==Video.task_id))
            .join(ReviewRequest, on=(ReviewRequest.video_id == Video.id))
            .where(
                (Task.status==1) &
                (ReviewRequest.reviewer_id==reviewer.id)
            )
        )

        # получить список видео которые требуется проверить проверяющему
        # и проверяющих на одно видео  меньше 5
        videos = (
            Video
            .select(Video.id)
            .join(ReviewRequest, on=(ReviewRequest.video_id==Video.id))
            .where(
                (~Video.id << videos)
            )
            .group_by(Video.id)
            .having(fn.COUNT(Video.id) < 5)
        )

        try:
            await bot.send_message(
                chat_id=reviewer.tg_id,
                text=f'Доброе утро, {reviewer.comment}. '
                f'Сегодня Вам нужно проверить {len(videos)} видео.',
            )
        except TelegramBadRequest as ex:
            print('Отправка утреннего оповещения', ex)


async def loop(bot: Bot):
    now = datetime.now()
    if now.hour == 13:
        await notify_reviewers(bot)