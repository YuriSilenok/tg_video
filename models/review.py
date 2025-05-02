from datetime import datetime
from typing import Tuple, Dict
from peewee import fn, ForeignKeyField, CharField, FloatField, DateTimeField
from models.base import Table, CASCADE
from models.review_request import ReviewRequest

class Review(Table):
    """Результат проверки видео"""
    review_request = ForeignKeyField(
        ReviewRequest, backref='reviews', **CASCADE)
    score = FloatField()
    comment = CharField()
    at_created = DateTimeField(default=datetime.now)

    @staticmethod
    def get_avg_scoress() -> Dict[int, int]:
        '''Плучить среднюю оценку для каждого видео'''

        return {row['video']: row['avg'] for row in
                Review
                .select(
                fn.AVG(Review.score).alias('avg'),
                ReviewRequest.video.alias('video'),
                )
                .join(ReviewRequest)
                .group_by(ReviewRequest.video)
                .dicts()
                }

    @staticmethod
    def get_minmax_score() -> Tuple[int, int]:
        """Получить минимальное и максимальное отклонения оценки"""

        data = [
            (
                min(abs(row['avg']-row['min']), abs(row['avg']-row['max'])),
                max(abs(row['avg']-row['min']), abs(row['avg']-row['max']))
            ) for row in
            Review
            .select(
                fn.MIN(Review.score).alias('min'),
                fn.MAX(Review.score).alias('max'),
                fn.AVG(Review.score).alias('avg'),
            )
            .join(ReviewRequest)
            .group_by(ReviewRequest.video)
            .dicts()
        ]
        return (
            0 if len(data) == 0 else min(data, key=lambda i: i[0])[0],
            0 if len(data) == 0 else max(data, key=lambda i: i[1])[1],
        )
