from datetime import datetime
from peewee import ForeignKeyField, DateTimeField, IntegerField, FloatField
from models.base import Table, CASCADE
from models.user import User
from models.theme import Theme


class Task(Table):
    """Тема выданная для записи видео"""
    implementer: User = ForeignKeyField(User, **CASCADE)
    theme: Theme = ForeignKeyField(Theme, **CASCADE)
    at_created = DateTimeField(default=datetime.now)
    due_date = DateTimeField()
    status = IntegerField(default=0)
    score = FloatField(default=0.0)
    # 0 - кнопка с продлением не отправлялась или ей воспользовались
    # 1 - кнопка о продлении отправлена
    extension = IntegerField(default=0)
