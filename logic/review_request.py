"""Контроллер для запросов на проверку"""
from peewee import fn
from models.base import Table
from models import ReviewRequest, Review

REVIEW_REQUEST_STATUS = {
    0: "На проверке",
    1: "Проверено",
    2: "Не проверено",
}


def get_count_overs():
    """Получить список просрочек каждого проверяющего"""

    sql_query = """
    select rr1.reviewer_id, count(rr2.video_id)
    from (
        select rr.reviewer_id
        from reviewrequest as rr
        group by rr.reviewer_id
    ) as rr1
    left join reviewrequest as rr2
    on rr2.reviewer_id = rr1.reviewer_id and rr2.status = -1
    group by rr1.reviewer_id
    """

    return {i['reviewer_id']: i['video_id'] for i in
            Table.raw(sql_query).dicts()
            }


def get_minmax_over():
    """Получить минимальное и максимальное количество просрочек"""
    return Table.get_minmax(
        data=get_count_overs()
    )


def get_minmax_review_duration():
    """Получить минимальное и максимальное время проверки видео в часах"""
    query = (
        ReviewRequest
        .select(
            fn.MIN(
                (fn.julianday(Review.at_created) -
                    fn.julianday(ReviewRequest.at_created)) * 24,
            ).alias('min_hours'),
            fn.MAX(
                (fn.julianday(Review.at_created) -
                    fn.julianday(ReviewRequest.at_created)) * 24,
            ).alias('max_hours')
        )
        .join(Review)
        .where(
            (ReviewRequest.status == 1)
        )
        .first()
    )
    return (
        0 if query.min_hours is None else int(query.min_hours),
        0 if query.max_hours is None else int(query.max_hours),
    )
