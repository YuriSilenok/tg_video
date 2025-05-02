from datetime import datetime
from peewee import ForeignKeyField, IntegerField, DateTimeField
from models.base import Table, CASCADE
from models.user import User
from models.video import Video


class ReviewRequest(Table):
    """Видео выданное на проверку проверяющему"""
    reviewer: User = ForeignKeyField(User, **CASCADE)
    video: Video = ForeignKeyField(Video, backref='reviewrequests', **CASCADE)
    status = IntegerField(default=0)
    at_created = DateTimeField(default=datetime.now)
    due_date = DateTimeField()
