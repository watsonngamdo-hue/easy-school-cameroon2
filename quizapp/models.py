from datetime import datetime
from django.db import models

from django.db import models

from programme.models import Lesson
from ckeditor.fields import RichTextField, RichTextFormField

from django.conf import settings

UserRegistration = settings.AUTH_USER_MODEL


from django.db import models
import random

DIFF_CHOICES = (
    ('easy', 'FACO;E'),
    ('medium', 'MOYEN'),
    ('hard', 'DIFFICILE'),
)

class Quiz(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, null=True)
    name = models.CharField(max_length=120)
    topic = models.CharField(max_length=120)
    number_of_questions = models.IntegerField()
    time = models.IntegerField(help_text="duration of the quiz in minutes")
    required_score_to_pass = models.IntegerField(help_text="required score in %")
    difficluty = models.CharField(max_length=6, choices=DIFF_CHOICES)

    def __str__(self):
        return f"{self.name}-{self.topic}"

    def get_questions(self):
        questions = list(self.question_set.all())
        random.shuffle(questions)
        return questions[:self.number_of_questions]

    class Meta:
        verbose_name_plural = 'Quizes' 

class Question(models.Model):
    text = models.CharField(max_length=200)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.text)

    def get_answers(self):
        return self.answer_set.all()

class Answer(models.Model):
    text = models.CharField(max_length=200)
    correct = models.BooleanField(default=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"question: {self.question.text}, answer: {self.text}, correct: {self.correct}"

class Result(models.Model):
    user = models.ForeignKey(UserRegistration, on_delete=models.PROTECT)
    quiz = models.ForeignKey(Quiz, on_delete=models.PROTECT)
    score = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.pk}"        