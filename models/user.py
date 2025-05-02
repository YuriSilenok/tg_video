"""Модуль для хранения модели пользвателя"""
from peewee import IntegerField, CharField, FloatField
from models.base import Table


class User(Table):
    """Модель пользователь"""
    tg_id = IntegerField()
    username = CharField(null=True)
    bloger_rating = FloatField(default=0.8)
    bloger_score = FloatField(default=0)
    reviewer_rating = FloatField(default=0)
    reviewer_score = FloatField(default=0)
    comment = CharField(null=True)

    @property
    def link(self) -> str:
        """Получить ссылку на пользователя"""
        surname = (
            self.comment.split(maxsplit=1)[0]
            if self.comment
            else 'Аноним'
        )
        return f'<a href="https://t.me/{self.username}">{surname}</a>'
