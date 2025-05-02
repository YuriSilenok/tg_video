from datetime import datetime
from peewee import ForeignKeyField, IntegerField, DateTimeField
from models.base import Table, CASCADE
from models.task import Task


class Video(Table):
    """Видео которое было прислано на оценку по задаче"""
    task = ForeignKeyField(Task, backref='videos', **CASCADE)
    file_id = IntegerField()
    at_created = DateTimeField(default=datetime.now)
    duration = IntegerField(default=0)
