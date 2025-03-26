from datetime import datetime
import math
from typing import List, Tuple
from peewee import Model, SqliteDatabase, JOIN, fn, Cast, BooleanField, FloatField, CharField, IntegerField, ForeignKeyField, DateTimeField, Value


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



    @classmethod
    def link_alias(cls):
        # Извлекаем первое слово из comment или используем "Аноним", если comment пустой
        surname = fn.COALESCE(
            fn.SUBSTR(
                cls.comment,
                1,
                fn.INSTR(cls.comment, ' ') - 1  # Находим позицию первого пробела
            ),
            Value("Аноним")
        )
        # Формируем строку с использованием fn.printf
        result = fn.printf(
            Value('<a href="https://t.me/%s">%s</a>'), cls.username, surname
        )
        return result.alias('link')



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


class Review(Table):
    """Результат проверки видео"""
    review_request = ForeignKeyField(ReviewRequest, backref='reviews', **CASCADE)
    score = FloatField()
    comment = CharField()
    at_created = DateTimeField(default=datetime.now)


class Poll(Table):
    message_id = IntegerField()
    poll_id = CharField()
    result = CharField()
    stop = BooleanField(default=False)
    at_created = DateTimeField(default=datetime.now)

class Var(Table):
    name = CharField()
    value = CharField(null=True)


def get_videos_by_request_review(user: User) -> List[User]:
    """Получить все видео, требующие этого проверяющего"""

    query = (
        Video
        .select(Video)
        .join(Task, on=(Video.task == Task.id))
        .join(ReviewRequest, JOIN.LEFT_OUTER, on=(ReviewRequest.video == Video.id))
        .where(
            (Task.status == 1) &  # Задача в статусе 1
            (Video.id.not_in(
                Video
                .select(Video.id)
                .join(ReviewRequest)
                .where(ReviewRequest.reviewer_id == user.id)  # Исключаем видео, которые я проверял
            ))
        )
        .group_by(Video.id)
        .having(fn.COUNT(ReviewRequest.id) < 5)  # У видео должно быть < 5 запросов на проверку
    )

    return list(query.execute())


def update_bloger_score_and_rating(bloger: User):

    bloger_rating = (Task
        .select(fn.AVG(Task.score))
        .where(
            (Task.implementer == bloger) &
            (Task.status.not_in([0,1]))
        )
        .scalar()
    )

    bloger.bloger_rating = bloger_rating if bloger_rating else 0.8
    result = f'Ваш рейтинг: {bloger_rating}\n'
    
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


def get_max_score_over():
    max_score_over = (
        Review
        .select(
            (fn.MAX(Review.score)-fn.MIN(Review.score)).alias('score'),
        )
        .join(ReviewRequest)
        .group_by(ReviewRequest.video)
    )
    return max(max_score_over, key=lambda i: i.score).score


def update_reviewers_rating():
    '''Обновление рейтинга проверяющего'''
  
    """Расчет завышения оценки"""
    video_avg_scores = {i['video']:i['score'] for i in
        Review
        .select(
            (fn.AVG(Review.score)).alias('score'),
            ReviewRequest.video,
        )
        .join(ReviewRequest)
        .where(ReviewRequest.status==1)
        .group_by(ReviewRequest.video)
        .dicts()
    }

    reviewer_scores = (
        ReviewRequest
        .select(
            ReviewRequest.video,
            ReviewRequest.reviewer,
            Review.score,
        )
        .join(Review)
    )

    score_over = {}

    for row in reviewer_scores.dicts():
        score_over[row['reviewer']] = (
            score_over.get(row['reviewer'], []) 
            + [abs(row['score'] - video_avg_scores[row['video']])]
        )

    for reviewer in score_over:
        scores = score_over[reviewer]
        avg_score = (sum(scores) / len(scores)) ** 2
        score_over[reviewer] = avg_score


    """Расчет пропусков проверок"""
    reviewer_overs = {i['reviewer']: i['over'] for i in
        ReviewRequest
        .select(
            ReviewRequest.reviewer,
            fn.COUNT(ReviewRequest.reviewer).alias('over')
        )
        .where(
            (ReviewRequest.status==-1)
        )
        .group_by(ReviewRequest.reviewer)
        .dicts()
    }
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


def update_reviewer_score(reviewer: User):

    review_requests = (
        ReviewRequest
        .select()
        .join(Video)
        .where(
            (ReviewRequest.reviewer_id == reviewer.id) &
            (ReviewRequest.status == 1)
        )
    )
    
    reviewer_score = 0
    for review_request in review_requests:
        reviewer_score += review_request.video.duration / 1200
    
    reviewer.reviewer_score = round(reviewer_score, 2)
    reviewer.save()
    return reviewer.reviewer_score


if __name__ == '__main__':
    db.create_tables([
        User, Role, UserRole,
        Course, Theme, Task, 
        Video, ReviewRequest, Review,
        UserCourse, Poll, Var
    ])        

    for user in User.select():
        update_reviewer_score(user)
        update_bloger_score_and_rating(user)
    update_reviewers_rating()

    for theme in Theme.select():
        title = theme.course.title

        if theme.title.startswith(title):
            if theme.title.startswith(f'{title} - '):
                title = f'{title} - '
            theme.title = theme.title.replace(title, '').strip()
            theme.save()