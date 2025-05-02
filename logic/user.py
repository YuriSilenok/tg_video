"""Логика при использовании модели User"""

from datetime import datetime
from typing import List
from peewee import fn, Case, JOIN
from models import User, ReviewRequest, Video, Task, Review, Theme


def get_sum_video_duration(user: User):
    """Получить сумму продолжительности всех проверенных видео в секундах"""
    return (
        ReviewRequest
        .select(fn.SUM(Video.duration))
        .join(Video)
        .where(
            (ReviewRequest.reviewer == user.id) &
            (ReviewRequest.status == 1)
        )
        .scalar()
    ) or 0


def update_reviewer_score(user: User):
    """Пересчитать баллы проверяющего"""

    user.reviewer_score = user.get_sum_video_duration() / 1200
    user.save()


def update_bloger_score(user: User):
    """Обновление количеста баллов (очков)"""

    tasks: List[Task] = (
        Task
        .select(Task)
        .where(
            (Task.implementer == user.id)
        )
        .execute()
    )

    bloger_score = 0
    i = 0
    for task in tasks:
        k = 1.05**i
        complexity = task.theme.complexity
        score = task.score * k * complexity
        bloger_score += score
        i += 1
    user.bloger_score = bloger_score
    user.save()


def get_reviewer_rating_from_score(user: User):
    '''Получить процент объективности оценок'''

    min_score, max_score = Review.get_minmax_score()
    delta = max_score - min_score
    video_avg_scores = Review.get_avg_scoress()

    data = [
        # проценты отклонений оценок. Чем меньше отклонение, тем рейтинг выше
        (max_score - abs(video_avg_scores[row['video']] - row['score']))
        / delta for row in
        Review  # Запрос на получение оценок текущего пользователя
        .select(
            ReviewRequest.video,
            Review.score,
        )
        .join(ReviewRequest)
        .where(ReviewRequest.reviewer == user.id)
        .dicts()
    ]

    return 1 if len(data) == 0 else (sum(data) / len(data))


def get_reviewer_rating_from_over(user: User):
    """Получить процент просрочек"""

    min_over, max_over = ReviewRequest.get_minmax_over()
    delta = max_over - min_over
    over_count = (
        ReviewRequest
        .select(fn.COUNT(ReviewRequest.id))
        .where(
            (ReviewRequest.status == -1) &
            (ReviewRequest.reviewer == user.id)
        )
        .scalar()
    )
    # Чем меньше просрочек, тем выше рейтинг
    return (
        1 if over_count is None or delta == 0
        else (max_over - over_count) / delta
    )


def get_reviewer_rating_from_duration(user: User):
    """Получить рейтинг блогера по продолжительности проверки видео"""

    min_dur, max_dur = ReviewRequest.get_minmax_review_duration()
    delta = max_dur - min_dur
    dur = (
        ReviewRequest
        .select(
            fn.AVG(
                (fn.julianday(Review.at_created) -
                    fn.julianday(ReviewRequest.at_created)) * 24,
            ).alias('avg_hours'),
        )
        .join(Review)
        .where(
            (ReviewRequest.status == 1) &
            (ReviewRequest.reviewer == user.id)
        )
        .scalar()
    )
    return 1 if dur is None or delta == 0 else (max_dur - dur) / delta


def update_reviewer_rating(user: User):
    '''Обновление рейтинга проверяющего'''

    ratings = (
        user.get_reviewer_rating_from_score(),
        user.get_reviewer_rating_from_over(),
        user.get_reviewer_rating_from_duration()
    )

    user.reviewer_rating = sum(ratings) / len(ratings)
    user.save()

    return user.reviewer_rating, *ratings


def get_bloger_rating_from_scores(user: User):
    """Получить рейтинг блогера, по средней оценке задач"""

    # Получить минмакс по средним оценкам блогеров
    min_score, max_score = Task.get_minmax_score()
    delta = max_score - min_score
    score = (Task
             .select(
                 fn.AVG(Task.score)
             )
             .where(
                 (Task.implementer == user.id) &
                 (Task.status.not_in([0, 1]))
             )
             .scalar()
             )
    return (
        0.7 if score is None or delta == 0
        else ((score - min_score) / delta)
    )


def get_bloger_rating_from_duration(user: User):
    '''Получить рейтинг блогера по продолжительности выполнения задачи'''

    min_duration, max_duration = Task.get_minmax_duration()
    delta = max_duration - min_duration
    duration = (
        Task
        .select(
            fn.AVG(
                Case(
                    None,
                    [(
                        Task.status == 0,
                        (fn.julianday(datetime.now()) -
                            fn.julianday(Task.at_created)) * 24
                    )],
                    (fn.julianday(Video.at_created) -
                        fn.julianday(Task.at_created)) * 24
                ) / Theme.complexity
            ).alias('avg_hours'),
        )
        .join(Theme)
        .join(
            Video,
            JOIN.LEFT_OUTER,
            on=Video.task == Task.id
        )
        .where(
            (Task.status != -1) &
            (Task.implementer == user.id)
        )
        .scalar()
    )

    return (
        0.7 if duration is None or delta == 0
        else ((max_duration - duration) / delta)
    )


def get_bloger_rating_from_over(user: User):
    """Рейтинг блогера по количеству просрочек"""

    min_over, max_over = Task.get_minmax_over()
    delta = max_over - min_over
    over = (
        Task
        .select(
            fn.COUNT(Task.id)
        )
        .where(
            (Task.status == -1) &
            (Task.implementer == user.id)
        )
        .scalar()
    )

    return 1 if over == 0 or delta == 0 else ((max_over - over) / delta)


def update_bloger_rating(user: User):
    '''Обновление рейтинга блогера'''

    ratings = (
        user.get_bloger_rating_from_scores(),
        user.get_bloger_rating_from_over(),
        user.get_bloger_rating_from_duration()
    )

    user.bloger_rating = sum(ratings) / len(ratings)
    user.save()

    return user.bloger_rating, *ratings


def get_bloger_report(user: User):
    """Получить отчет по блогеру"""

    tasks: List[Task] = (
        Task
        .select()
        .where(
            (Task.implementer == user.id) &
            (Task.status.not_in([0, 1]))
        )
        .order_by(Task.at_created)
    )

    report = 'Тема|Оценка|Cтаж|Объем|Итог\n'
    i = 0
    for task in tasks:
        k = 1.05**i
        complexity = task.theme.complexity
        score = task.score * k * complexity
        i += 1
        report += (
            f'<a href="{task.theme.url}">{i:05.0f}</a>'
            f'|{(task.score*100):05.2f}%|{k:05.2f}'
            f'|{complexity:06.3f}|{score:.2f}\n'
        )

    return (
        '<b>Рейтинг блогера</b>: '
        f'{(user.bloger_rating*100):.2f}%\n'
        '- скорость исполнения: '
        f'{(user.get_bloger_rating_from_duration()*100):.2f}%\n'
        '- соблюдение срока: '
        f'{(user.get_bloger_rating_from_over()*100):.2f}%\n'
        '- качество видео: '
        f'{(user.get_bloger_rating_from_scores()*100):.2f}%\n'
        '\n<b>Баллы блогера</b>: '
        f'{user.bloger_score:.2f}\n'
        f'{report}\n'
    )


def get_reviewer_report(user: User):
    '''Получить отчет проверяющего'''

    review_requests: List[ReviewRequest] = (
        ReviewRequest
        .select()
        .where(
            (ReviewRequest.reviewer == user.id) &
            (ReviewRequest.status == 1)
        )
        .execute()
    )

    report = 'Тема|Сек|Итог\n'
    i = 0
    for rr in review_requests:
        i += 1
        video: Video = rr.video
        score = video.duration / 1200
        report += (
            f'<a href="{video.task.theme.url}">{i:05.0f}</a>'
            f'|{video.duration:03.0f}|{score:.2f}\n'
        )

    return (
        '<b>Рейтинг проверяющего</b>: '
        f'{(user.reviewer_rating*100):5.2f}%\n'
        '- качество проверки: '
        f'{(user.get_reviewer_rating_from_score()*100):5.2f}%\n'
        '- скорость проверки: '
        f'{(user.get_reviewer_rating_from_duration()*100):5.2f}%\n'
        '- соблюдение срока: '
        f'{(user.get_reviewer_rating_from_over()*100):5.2f}%\n'
        '\n<b>Баллы проверяющего</b>: '
        f'{user.reviewer_score:.2f}\n'
        f'{report}\n'
    )


def get_report(user: User):
    '''Получить отчет по пользователю'''

    return f'{user.get_bloger_report()}\n{user.get_reviewer_report()}'
