"""Объекты затрагивающие все модели"""
from typing import Dict
from peewee import Model, SqliteDatabase

db = SqliteDatabase('sqlite.db')


CASCADE = {
    'on_delete': 'CASCADE', 
    'on_update': 'CASCADE',
}


class Table(Model):
    class Meta:
        database = db

    @staticmethod
    def get_minmax(data: Dict[int, int]):
        return (
            data.get(-1 if len(data) == 0 else min(data, key=data.get), 0),
            data.get(-1 if len(data) == 0 else max(data, key=data.get), 0),
        )


if __name__ == '__main__':

    from models import *
    db.create_tables([
        User, Role, UserRole,
        Course, Theme, Task,
        Video, ReviewRequest, Review,
        UserCourse, Poll
    ])
