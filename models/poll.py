from datetime import datetime
from peewee import IntegerField, CharField,BooleanField,DateTimeField
from models.base import Table

class Poll(Table):
    message_id = IntegerField()
    poll_id = CharField()
    result = CharField()
    stop = BooleanField(default=False)
    at_created = DateTimeField(default=datetime.now)