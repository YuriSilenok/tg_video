from datetime import datetime

from peewee import JOIN, fn, Case

from models.base import Table
from models.task import Task
from models.theme import Theme
from models.video import Video

TASK_STATUS = {
    -2: "Без публикации",
    -1: "Брошена",
    0: "Выдана",
    1: "На проверке",
    2: "Ожидает публикации",
    3: "Опубликована",
}


def get_count_overs():
    """Получить количество просрочек для блогеров"""

    sql_query = """
    select t1.implementer_id, count(t2.implementer_id) as 'count'
    from (
        select t.implementer_id
        from task as t
        group by t.implementer_id
    ) as t1
    left join task as t2 on t2.implementer_id = t1.implementer_id and t2.status = -1
    group by t1.implementer_id
    """

    return {i['implementer_id']: i['count'] for i in
            Table.raw(sql_query).dicts()
            }


def get_minmax_over():
    """Получить минимакс для количества просрочек"""

    return Table.get_minmax(
        Task.get_count_overs()
    )


def get_avg_duration():
    """Получить среднюю относительную (сложности темы) продолжительность выполнения задачи для каждого блогера"""
    return {
        row['bloger']: (row['avg_hours'] if row['avg_hours'] else 0) for row in
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
            Task.implementer.alias('bloger')
        )
        .join(Theme)
        .join(Video, JOIN.LEFT_OUTER, on=(Video.task == Task.id))
        .where(
            (Task.status != -1)
        )
        .group_by(
            Task.implementer
        )
        .dicts()
    }


def get_minmax_duration():
    """Получить минимакс для продожительности выполнения задач"""

    return Table.get_minmax(
        data=Task.get_avg_duration()
    )


def get_avg_scores():
    """Получить средние оценки по задачам для каждого блогера"""

    return {
        row['bloger']: row['score'] for row in
        Task.select(
            fn.AVG(Task.score).alias('score'),
            Task.implementer.alias('bloger')
        ).where(
            (Task.status.not_in([0, 1]))
        ).group_by(
            (Task.implementer)
        ).dicts()
    }


def get_minmax_score():
    """Получить мин и макс средние оценки по задачам"""

    return Table.get_minmax(
        data=Task.get_avg_scores()
    )
