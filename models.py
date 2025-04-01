from datetime import datetime
import math
from typing import Dict, List, Tuple
from peewee import Model, SqliteDatabase, JOIN, fn, Case, BooleanField, FloatField, CharField, IntegerField, ForeignKeyField, DateTimeField, Value


db = SqliteDatabase('sqlite.db')


CASCADE = {
    'on_delete': 'CASCADE',
    'on_update': 'CASCADE',
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
    class Meta:
        database = db


class User(Table):
    tg_id = IntegerField()
    username = CharField(null=True)
    # рейтинг блогера/проверющего
    bloger_rating = FloatField(default=0.8)
    bloger_score = FloatField(default=0)
    reviewer_rating = FloatField(default=0)
    reviewer_score = FloatField(default=0)
    comment = CharField(null=True)


    @property
    def link(self):
        surname = self.comment.split(maxsplit=1)[0] if self.comment else 'Аноним'
        return f'<a href="https://t.me/{self.username}">{surname}</a>'


    def get_avg_duration(self):
        """Получить общую продолжительность всех проверенных видео в секундах"""
        return (
            ReviewRequest
            .select(fn.SUM(Video.duration))
            .join(Video)
            .where(
                (ReviewRequest.reviewer_id == self.id) &
                (ReviewRequest.status == 1)
            )
            .scalar()
        )


    def update_reviewer_score(self):
        """Пересчитать баллы проверяющего"""

        self.reviewer_score = self.get_avg_duration() / 1200
        self.save()


    def get_reviewer_rating_from_score(self):
        '''Получить рейтинг проверяющего по оценками'''
        
        min_score, max_score = Review.get_minmax_score()
        delta = max_score - min_score
        video_avg_scores = Review.get_avg_scores()
        
        data = [
            abs(video_avg_scores[row['video']] - row['score']) / delta for row in
            Review
            .select(
                ReviewRequest.video,
                Review.score,
            )
            .join(ReviewRequest)
            .where(ReviewRequest.reviewer == self.id)
            .dicts()
        ]

        return sum(data) / len(data)


    def get_reviewer_rating_from_over(self):
        """Получить рейтинг проверяющего по просрочкам"""


    def update_reviewers_rating(self):
        '''Обновление рейтинга проверяющего'''
    
        rating_from_score = self.get_reviewer_rating_from_score()


        """Расчет пропусков проверок"""

        if len(reviewer_overs) == 0:
            return None
        max_reviewer = max(reviewer_overs, key=reviewer_overs.get)
        max_reviewer_over = reviewer_overs[max_reviewer]

        rating = {}
        for reviewer in list(set(score_over.keys()) | set(reviewer_overs.keys())):
            rating[reviewer] = (
                score_over.get(reviewer, 0) + 
                (reviewer_overs.get(reviewer, 0)/max_reviewer_over) ** 2
            )

        max_hours = max([row['hours'] for row in 
            ReviewRequest
            .select(
                fn.AVG(
                    fn.ROUND(
                        (fn.julianday(Review.at_created) - fn.julianday(ReviewRequest.at_created)) * 24,
                        2
                    )
                ).alias('hours')
            )
            .join(Review)
            .group_by(
                ReviewRequest.reviewer
            ).dicts()
        ])

        query: List[Review] = (
            Review
            .select(
                    ReviewRequest.reviewer.alias('reviewer'),
                    fn.AVG(
                        fn.ROUND(
                            (fn.julianday(Review.at_created) - fn.julianday(ReviewRequest.at_created)) * 24,
                            2
                        )
                    ).alias('hours')
            )
            .join(ReviewRequest)
            .group_by(ReviewRequest.reviewer)
        )
        for row in query.dicts():
            rating[row['reviewer']] = (
                rating.get(row['reviewer'], 0) + 
                (row['hours']/max_hours) ** 2
            )


        for reviewer in rating:
            user: User = User.get_by_id(reviewer)
            user.reviewer_rating = math.sqrt(rating[reviewer])
            user.save()


    def update_bloger_score(self):

        self.bloger_rating = bloger_avg_tsk_score
        result = f'Ваш рейтинг: {bloger_avg_tsk_score}\n'
        
        bloger_score = 0
        tasks = (Task
            .select()
            .where(
                (Task.implementer == bloger) &
                (Task.status.not_in([0,1]))
            )
        )
        result += f'Видео которые Вы записали были оценены:\n\n'
        i = 0
        for task in tasks:
            k = 1.05**i
            complexity = task.theme.complexity
            score = task.score * k * complexity
            bloger_score += score
            i+=1
            result +=  f'{task.theme.title}\ns*k*c={round(task.score, 4)}*{round(k, 4)}*{complexity}={score}\n\n'
        result += f's = Оценка за видео, k=за стаж, с=за объем материала\n'
        bloger.bloger_score = round(bloger_score, 2)
        bloger.save()
        result += f'ИТОГО БАЛЛОВ: {bloger.bloger_score}'
        return result


class Role(Table):
    # Блогер, Проверяющий
    name = CharField()


class UserRole(Table):
    user = ForeignKeyField(User, **CASCADE)
    role = ForeignKeyField(Role, **CASCADE)


class Course(Table):
    title = CharField()


class UserCourse(Table):
    """Желание пользователя записывать видео по этому курсу"""
    user = ForeignKeyField(User, **CASCADE)
    course = ForeignKeyField(Course, backref='usercourse', **CASCADE)


class Theme(Table):
    course = ForeignKeyField(Course, backref='themes', **CASCADE)
    title = CharField()
    url = CharField()
    complexity = FloatField(default=1.0)

    
    @property
    def link(self):
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
    def get_avg_duration():
        """Получить среднюю продолжительность выполнения задачи для каждого блогера"""
        return {row['bloger']: (row['avg_hours'] if row['avg_hours'] else 0) for row in
            Task
            .select(
                fn.AVG(
                        Case(
                            None,
                            [(
                                Task.status==0, 
                                (fn.julianday(datetime.now()) - fn.julianday(Task.at_created)) * 24
                            )],
                            (fn.julianday(Video.at_created) - fn.julianday(Task.at_created)) * 24
                        ) / Theme.complexity
                ).alias('avg_hours'),
                Task.implementer.alias('bloger')
            )
            .join(Theme)
            .join(Video, JOIN.LEFT_OUTER, on=(Video.task==Task.id))
            .where(
                (Task.status != -1)
            )
            .group_by(
                Task.implementer
            )
            .dicts()
        }


    @staticmethod
    def get_avg_score():
        """Получить средние оценки по задачам для каждого блогера"""
        return {row['bloger']: row['score'] for row in
            Task 
            .select(
                fn.AVG(Task.score).alias('score'),
                Task.implementer.alias('bloger')
            )
            .where(
                (Task.status.not_in([0,1]))
            )
            .group_by(
                (Task.implementer)
            )
            .dicts()
        }


class Video(Table):
    """Видео которое было прислано на оценку по задаче"""
    task = ForeignKeyField(Task, backref='videos', **CASCADE)
    file_id = IntegerField()
    at_created = DateTimeField(default=datetime.now)
    duration = IntegerField(default=0)


class ReviewRequest(Table):
    """Видео выданное на проверку проверяющему"""
    reviewer = ForeignKeyField(User, **CASCADE)
    video = ForeignKeyField(Video, backref='reviewrequests', **CASCADE)
    status = IntegerField(default=0)
    at_created = DateTimeField(default=datetime.now)
    due_date = DateTimeField()


    @staticmethod
    def get_overs():
        """Получить список просрочек каждого проверяющего"""

        sql_query = """
        select rr1.reviewer_id, count(rr2.video_id)
        from (
            select rr.reviewer_id
            from reviewrequest as rr
            group by rr.reviewer_id
        ) as rr1
        left join reviewrequest as rr2 on rr2.reviewer_id = rr1.reviewer_id and rr2.status = -1
        group by rr1.reviewer_id
        """

        return {i['reviewer_id']: i['video_id'] for i in
            Table.raw(sql_query).dicts()
        }

class Review(Table):
    """Результат проверки видео"""
    review_request = ForeignKeyField(ReviewRequest, backref='reviews', **CASCADE)
    score = FloatField()
    comment = CharField()
    at_created = DateTimeField(default=datetime.now)


    @staticmethod
    def get_avg_scores() -> Dict[int, int]:
        '''Плучить среднюю оценку для каждого видео'''

        return { row['video']: row['avg'] for row in
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
        """Получить минимальное и максимальное отклонения оценки от средней оценки"""

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
            min(data, key=lambda i: i[0])[0],
            max(data, key=lambda i: i[1])[1]
        )


class Poll(Table):
    message_id = IntegerField()
    poll_id = CharField()
    result = CharField()
    stop = BooleanField(default=False)
    at_created = DateTimeField(default=datetime.now)

class Var(Table):
    name = CharField()
    value = CharField(null=True)


if __name__ == '__main__':
    db.create_tables([
        User, Role, UserRole,
        Course, Theme, Task, 
        Video, ReviewRequest, Review,
        UserCourse, Poll, Var
    ])        

    for row in ReviewRequest.get_overs().items():
        print(*row)
