import os
from django.core.management.base import BaseCommand
from quizapp.models import Quiz, Question, Answer
from programme.models import Lesson

class Command(BaseCommand):
    help = 'Create a quiz for a lesson'

    def add_arguments(self, parser):
        parser.add_argument('--lesson_id', type=int, help='ID of the lesson')
        parser.add_argument('--name', type=str, default='Default Quiz')
        parser.add_argument('--topic', type=str, default='General')
        parser.add_argument('--questions', type=int, default=5)

    def handle(self, *args, **options):
        lesson_id = options.get('lesson_id')
        if not lesson_id:
            lesson = Lesson.objects.first()
        else:
            lesson = Lesson.objects.filter(id=lesson_id).first()

        if not lesson:
            self.stdout.write(self.style.ERROR('No lesson found. Please create a lesson first.'))
            return

        quiz = Quiz.objects.create(
            lesson=lesson,
            name=options['name'],
            topic=options['topic'],
            number_of_questions=options['questions'],
            time=15,
            required_score_to_pass=50,
            difficluty='easy'
        )
        for i in range(options['questions']):
            q = Question.objects.create(text=f'Question {i+1} for {quiz.name}', quiz=quiz)
            Answer.objects.create(text=f'Answer 1 for Q{i+1}', correct=True, question=q)
            Answer.objects.create(text=f'Answer 2 for Q{i+1}', correct=False, question=q)
            Answer.objects.create(text=f'Answer 3 for Q{i+1}', correct=False, question=q)

        self.stdout.write(self.style.SUCCESS(f'Successfully created quiz ID {quiz.id} for lesson ID {lesson.id}.'))
