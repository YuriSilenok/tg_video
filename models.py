"""Модуль модели БД"""

from datetime import datetime
from typing import List, Dict, Tuple

from peewee import (
    JOIN,
    BooleanField,
    Case,
    CharField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    fn,
)

# pylint: disable=no-member
# pylint: disable=too-few-public-methods

db = SqliteDatabase("sqlite.db")


CASCADE = {
    "on_delete": "CASCADE",
    "on_update": "CASCADE",
}


TASK_STATUS = {
    -2: "Без публикации",
    -1: "Брошена",
    0: "Выдана",
    1: "На проверке",
    2: "Ожидает публикации",
    3: "Опубликована",
}


REVIEW_REQUEST_STATUS = {
    0: "На проверке",
    1: "Проверено",
    2: "Не проверено",
}


class Table(Model):
    """Базовый класс моделей с подключением к БД"""

    class Meta:
        """Позволяет работать с БД"""

        database = db

    @staticmethod
    def get_minmax(data: Dict[int, int]):
        """Поиска минимального/максимального значений в словаре."""
        return (
            data.get(-1 if len(data) == 0 else min(data, key=data.get), 0),
            data.get(-1 if len(data) == 0 else max(data, key=data.get), 0),
        )


class User(Table):
    """Модель пользователя с данными Telegram"""

    tg_id = IntegerField()
    username = CharField(null=True)
    # рейтинг блогера/проверющего
    bloger_rating = FloatField(default=0.8)
    bloger_score = FloatField(default=0)
    reviewer_rating = FloatField(default=0)
    reviewer_score = FloatField(default=0)
    comment = CharField(null=True)
    is_banned = BooleanField(default=False)

    @property
    def link(self):
        """Формирует HTML-ссылку на пользователя"""
        surname = (
            self.comment.split(maxsplit=1)[0] if self.comment else "Аноним"
        )
        return f'<a href="https://t.me/{self.username}">{surname}</a>'

    def get_sum_video_duration(self):
        """Получить сумму продолжительности всех проверенных
        видео в секундах"""
        return (
            ReviewRequest.select(fn.SUM(Video.duration))
            .join(Video)
            .where(
                (ReviewRequest.reviewer_id == self.id)
                & (ReviewRequest.status == 1)
            )
            .scalar()
        ) or 0

    def update_reviewer_score(self):
        """Пересчитать баллы проверяющего"""

        self.reviewer_score = self.get_sum_video_duration() / 1200
        self.save()

    def update_bloger_score(self):
        """Обновление количеста баллов (очков)"""

        tasks: List[Task] = list(
            Task.select(Task).where(
                (Task.implementer == self.id) & (Task.status.in_([2, 3]))
            )
        )

        bloger_score = 0
        i = 0
        for task in tasks:
            k = 1.05**i
            complexity = task.theme.complexity
            score = task.score * k * complexity
            bloger_score += score
            i += 1
        if self.bloger_score < bloger_score:
            self.bloger_score = bloger_score
            self.save()

    def get_reviewer_rating_from_score(self):
        """Получить процент объективности оценок"""

        min_score, max_score = Review.get_minmax_score()
        delta = max_score - min_score
        video_avg_scores = Review.get_best_scores()

        data = [  # проценты отклонений оценок. Чем меньше отклонение,
            # тем рейтинг выше
            (max_score - abs(video_avg_scores[row["video"]] - row["score"]))
            / delta
            for row in Review.select(  # Запрос на получение оценок
                # текущего пользователя
                ReviewRequest.video,
                Review.score,
            )
            .join(ReviewRequest)
            .where(ReviewRequest.reviewer == self.id)
            .dicts()
        ]

        return 1 if len(data) == 0 else (sum(data) / len(data))

    def get_reviewer_rating_from_over(self):
        """Получить процент просрочек"""

        min_over, max_over = ReviewRequest.get_minmax_over()
        delta = max_over - min_over
        over_count = (
            ReviewRequest.select(fn.COUNT(ReviewRequest.id))
            .where(
                (ReviewRequest.status == -1)
                & (ReviewRequest.reviewer == self.id)
            )
            .scalar()
        )
        # Чем меньше просрочек, тем выше рейтинг
        return (
            1
            if over_count is None or delta == 0
            else (max_over - over_count) / delta
        )

    def get_reviewer_rating_from_duration(self):
        """Получить рейтинг проверяющего по продолжительности проверки видео"""

        min_dur, max_dur = ReviewRequest.get_minmax_review_duration()
        delta = max_dur - min_dur
        dur = (
            ReviewRequest.select(
                fn.AVG(
                    (
                        fn.julianday(Review.at_created)
                        - fn.julianday(ReviewRequest.at_created)
                    )
                    * 24,
                ).alias("avg_hours"),
            )
            .join(Review)
            .where(
                (ReviewRequest.status == 1)
                & (ReviewRequest.reviewer == self.id)
            )
            .scalar()
        )
        return 1 if dur is None or delta == 0 else (max_dur - dur) / delta

    def update_reviewer_rating(self):
        """Обновление рейтинга проверяющего"""

        ratings = (
            self.get_reviewer_rating_from_score(),
            self.get_reviewer_rating_from_over(),
            self.get_reviewer_rating_from_duration(),
        )

        self.reviewer_rating = sum(ratings) / len(ratings)
        self.save()

        return self.reviewer_rating, *ratings

    def get_bloger_rating_from_scores(self):
        """Получить рейтинг блогера, по средней оценке задач"""

        # Получить минмакс по средним оценкам блогеров
        min_score, max_score = Task.get_minmax_score()
        delta = max_score - min_score
        score = (
            Task.select(fn.AVG(Task.score))
            .where(
                (Task.implementer == self.id) & (Task.status.not_in([0, 1]))
            )
            .scalar()
        )
        return (
            0.7
            if score is None or delta == 0
            else ((score - min_score) / delta)
        )

    def get_bloger_rating_from_duration(self):
        """Получить рейтинг блогера по продолжительности выполнения задачи"""

        min_duration, max_duration = Task.get_minmax_duration()
        delta = max_duration - min_duration
        duration = (
            Task.select(
                fn.AVG(
                    Case(
                        None,
                        [
                            (
                                Task.status == 0,
                                (
                                    fn.julianday(datetime.now())
                                    - fn.julianday(Task.at_created)
                                )
                                * 24,
                            )
                        ],
                        (
                            fn.julianday(Video.at_created)
                            - fn.julianday(Task.at_created)
                        )
                        * 24,
                    )
                    / Theme.complexity
                ).alias("avg_hours"),
            )
            .join(Theme)
            .join(Video, JOIN.LEFT_OUTER, on=Video.task == Task.id)
            .where((Task.status != -1) & (Task.implementer == self.id))
            .scalar()
        )

        return (
            0.7
            if duration is None or delta == 0
            else ((max_duration - duration) / delta)
        )

    def get_bloger_rating_from_over(self):
        """Рейтинг блогера по количеству просрочек"""

        min_over, max_over = Task.get_minmax_over()
        delta = max_over - min_over
        over = (
            Task.select(fn.COUNT(Task.id))
            .where((Task.status == -1) & (Task.implementer == self.id))
            .scalar()
        )

        return 1 if over == 0 or delta == 0 else ((max_over - over) / delta)

    def update_bloger_rating(self):
        """Обновление рейтинга блогера"""

        ratings = (
            self.get_bloger_rating_from_scores(),
            self.get_bloger_rating_from_over(),
            self.get_bloger_rating_from_duration(),
        )

        self.bloger_rating = sum(ratings) / len(ratings)
        self.save()

        return self.bloger_rating, *ratings

    def get_bloger_report(self):
        """Получить отчет по блогеру"""

        tasks: List[Task] = (
            Task.select()
            .where((Task.implementer == self.id) & (Task.status.in_([2, 3])))
            .order_by(Task.at_created)
        )

        report = "Тема|Оценка|Cтаж|Объем|Итог\n"
        i = 0
        for task in tasks:
            k = 1.05**i
            complexity = task.theme.complexity
            score = task.score * k * complexity
            i += 1
            report += (
                f'<a href="{task.theme.url}">{i:05.0f}</a>|'
                f"{(task.score * 100):05.2f}%|{k:05.2f}|"
                f"{complexity:06.3f}|{score:.2f}\n"
            )
        return (
            f"<b>Рейтинг блогера</b>: {(self.bloger_rating * 100):.2f}%\n"
            f"- скорость исполнения: "
            f"{(self.get_bloger_rating_from_duration() * 100):.2f}%\n"
            f"- соблюдение срока: "
            f"{(self.get_bloger_rating_from_over() * 100):.2f}%\n"
            f"- качество видео: "
            f"{(self.get_bloger_rating_from_scores() * 100):.2f}%\n"
            f"\n<b>Баллы блогера</b>: {self.bloger_score:.2f}\n"
            f"{report}\n"
        )

    def get_reviewer_report(self):
        """Получить отчет проверяющего"""

        rrs: List[ReviewRequest] = list(
            ReviewRequest.select().where(
                (ReviewRequest.reviewer == self.id)
                & (ReviewRequest.status == 1)
            )
        )

        report = "Тема|Сек|Итог\n"
        i = 0
        for rr in rrs:
            i += 1
            video: Video = rr.video
            score = video.duration / 1200
            report += (
                f'<a href="{video.task.theme.url}">{i:05.0f}</a>|'
                f"{video.duration:03.0f}|{score:.2f}\n"
            )

        return (
            f"<b>Рейтинг проверяющего</b>: "
            f"{(self.reviewer_rating * 100):5.2f}%\n"
            f"- качество проверки: "
            f"{(self.get_reviewer_rating_from_score() * 100):5.2f}%\n"
            f"- скорость проверки: "
            f"{(self.get_reviewer_rating_from_duration() * 100):5.2f}%\n"
            f"- соблюдение срока: "
            f"{(self.get_reviewer_rating_from_over() * 100):5.2f}%\n"
            f"\n<b>Баллы проверяющего</b>: {self.reviewer_score:.2f}\n"
            f"{report}\n"
        )

    def get_report(self):
        """Получить отчет по пользователю"""

        return f"{self.get_bloger_report()}\n{self.get_reviewer_report()}"


class Role(Table):
    """Содержит названия ролей пользователей"""

    name = CharField()


class UserRole(Table):
    """Связывает пользователей с их ролями"""

    user = ForeignKeyField(User, backref="user_roles", **CASCADE)
    role = ForeignKeyField(Role, **CASCADE)


class Tag(Table):
    """Теги"""

    title = CharField()


class Course(Table):
    """Описывает учебные курсы"""

    title = CharField()


class CourseTag(Table):
    """Теги для курса"""

    tag = ForeignKeyField(Tag, **CASCADE)
    course = ForeignKeyField(Course, backref="coursetag", **CASCADE)


class UserCourse(Table):
    """Желание пользователя записывать видео по этому курсу"""

    user = ForeignKeyField(User, **CASCADE)
    course = ForeignKeyField(Course, backref="usercourse", **CASCADE)


class Theme(Table):
    """Описывает темы внутри курсов"""

    course = ForeignKeyField(Course, backref="themes", **CASCADE)
    title = CharField()
    url = CharField()
    complexity = FloatField(default=1.0)

    @property
    def link(self):
        """Возвращает ссылку"""
        return f'<a href="{self.url}">{self.title}</a>'


class Task(Table):
    """Тема выданная для записи видео"""

    implementer = ForeignKeyField(User, **CASCADE)
    theme = ForeignKeyField(Theme, **CASCADE)
    at_created = DateTimeField(default=datetime.now)
    due_date = DateTimeField()
    status = IntegerField(default=0)
    score = FloatField(default=0.0)
    # 0 - кнопка с продлением не отправлялась или ей воспользовались
    # 1 - кнопка о продлении отправлена
    extension = IntegerField(default=0)

    @staticmethod
    def get_count_overs():
        """Получить количество просрочек для блогеров"""

        sql_query = """
        select t1.implementer_id, count(t2.implementer_id) as 'count'
        from (
            select t.implementer_id
            from task as t
            group by t.implementer_id
        ) as t1
        left join task as t2
        on t2.implementer_id = t1.implementer_id
        and t2.status = -1
        group by t1.implementer_id
        """

        return {
            i["implementer_id"]: i["count"]
            for i in Table.raw(sql_query).dicts()
        }

    @staticmethod
    def get_minmax_over():
        """Получить минимакс для количества просрочек"""

        return Table.get_minmax(Task.get_count_overs())

    @staticmethod
    def get_avg_duration():
        """Получить среднюю относительную (сложности темы) продолжительность
        выполнения задачи для каждого блогера"""
        return {
            row["bloger"]: (row["avg_hours"] if row["avg_hours"] else 0)
            for row in Task.select(
                fn.AVG(
                    Case(
                        None,
                        [
                            (
                                Task.status == 0,
                                (
                                    fn.julianday(datetime.now())
                                    - fn.julianday(Task.at_created)
                                )
                                * 24,
                            )
                        ],
                        (
                            fn.julianday(Video.at_created)
                            - fn.julianday(Task.at_created)
                        )
                        * 24,
                    )
                    / Theme.complexity
                ).alias("avg_hours"),
                Task.implementer.alias("bloger"),
            )
            .join(Theme)
            .join(Video, JOIN.LEFT_OUTER, on=Video.task == Task.id)
            .where(Task.status != -1)
            .group_by(Task.implementer)
            .dicts()
        }

    @staticmethod
    def get_minmax_duration():
        """Получить минимакс для продожительности выполнения задач"""

        return Table.get_minmax(data=Task.get_avg_duration())

    @staticmethod
    def get_avg_scores():
        """Получить средние оценки по задачам для каждого блогера"""

        return {
            row["bloger"]: row["score"]
            for row in Task.select(
                fn.AVG(Task.score).alias("score"),
                Task.implementer.alias("bloger"),
            )
            .where(Task.status.not_in([0, 1]))
            .group_by(Task.implementer)
            .dicts()
        }

    @staticmethod
    def get_minmax_score():
        """Получить мин и макс средние оценки по задачам"""

        return Table.get_minmax(data=Task.get_avg_scores())


class Video(Table):
    """Видео которое было прислано на оценку по задаче"""

    task = ForeignKeyField(Task, backref="videos", **CASCADE)
    file_id = IntegerField()
    at_created = DateTimeField(default=datetime.now)
    duration = IntegerField(default=0)


class ReviewRequest(Table):
    """Видео выданное на проверку проверяющему"""

    reviewer = ForeignKeyField(User, **CASCADE)
    video = ForeignKeyField(Video, backref="reviewrequests", **CASCADE)
    status = IntegerField(default=0)
    at_created = DateTimeField(default=datetime.now)
    due_date = DateTimeField()

    @staticmethod
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
        on rr2.reviewer_id = rr1.reviewer_id
        and rr2.status = -1
        group by rr1.reviewer_id
        """

        return {
            i["reviewer_id"]: i["video_id"]
            for i in Table.raw(sql_query).dicts()
        }

    @staticmethod
    def get_minmax_over():
        """Возвращает минимальное и максимальное количество
        просроченных запросов"""
        return Table.get_minmax(data=ReviewRequest.get_count_overs())

    @staticmethod
    def get_minmax_review_duration():
        """Получить минимальное и максимальное время проверки видео в часах"""
        query = (
            ReviewRequest.select(
                fn.MIN(
                    (
                        fn.julianday(Review.at_created)
                        - fn.julianday(ReviewRequest.at_created)
                    )
                    * 24,
                ).alias("min_hours"),
                fn.MAX(
                    (
                        fn.julianday(Review.at_created)
                        - fn.julianday(ReviewRequest.at_created)
                    )
                    * 24,
                ).alias("max_hours"),
            )
            .join(Review)
            .where(ReviewRequest.status == 1)
            .first()
        )
        return (
            0 if query.min_hours is None else int(query.min_hours),
            0 if query.max_hours is None else int(query.max_hours),
        )


class Review(Table):
    """Результат проверки видео"""

    review_request = ForeignKeyField(
        ReviewRequest, backref="reviews", **CASCADE
    )
    score = FloatField()
    comment = CharField()
    at_created = DateTimeField(default=datetime.now)

    @staticmethod
    def get_best_scores() -> Dict[int, int]:
        """Плучить лучшие оценки для каждого видео"""

        return {
            row["video"]: row["avg"]
            for row in Review.select(
                fn.MIN(Review.score).alias("avg"),
                ReviewRequest.video.alias("video"),
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
                min(
                    abs(row["avg"] - row["min"]), abs(row["avg"] - row["max"])
                ),
                max(
                    abs(row["avg"] - row["min"]), abs(row["avg"] - row["max"])
                ),
            )
            for row in Review.select(
                fn.MIN(Review.score).alias("min"),
                fn.MAX(Review.score).alias("max"),
                fn.AVG(Review.score).alias("avg"),
            )
            .join(ReviewRequest)
            .group_by(ReviewRequest.video)
            .dicts()
        ]
        return (
            0 if len(data) == 0 else min(data, key=lambda i: i[0])[0],
            0 if len(data) == 0 else max(data, key=lambda i: i[1])[1],
        )


class Poll(Table):
    """Хранит данные опроса"""

    message_id = IntegerField()
    poll_id = CharField()
    result = CharField()
    is_stop = BooleanField(default=False)
    at_created = DateTimeField(default=datetime.now)
    is_delete = BooleanField(default=False)


class Var(Table):
    """Содержит пары ключ-значение"""

    name = CharField()
    value = CharField(null=True)


if __name__ == "__main__":
    db.create_tables(
        [
            User,
            Role,
            UserRole,
            Course,
            Theme,
            Task,
            Video,
            ReviewRequest,
            Review,
            UserCourse,
            Poll,
            Var,
            Tag,
            CourseTag,
        ]
    )

    users: List[User] = list(User.select())
    for user in users:
        user.update_bloger_score()
        user.update_bloger_rating()
        user.update_reviewer_score()
        user.update_reviewer_rating()
