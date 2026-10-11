import uuid
import os
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.core.files import File
from authapp.models import UserRegistration
from programme.models import Niveaux, Matiere, Lesson
from quizapp.models import Quiz, Question, Answer
import random

class Command(BaseCommand):
    help = 'Populate all classes (Niveaux) with multiple diverse subjects, lessons, and quizzes'

    def handle(self, *args, **options):
        # 1. Get or create a superuser for content creation
        admin_user = UserRegistration.objects.filter(is_superuser=True).first()
        if not admin_user:
            self.stdout.write(self.style.ERROR('No superuser found. Please create one first.'))
            return

        # Path to images
        image_dir = 'media/matieres/'
        available_images = []
        if os.path.exists(image_dir):
            available_images = [f for f in os.listdir(image_dir) if f.endswith(('.png', '.jpg', '.jpeg'))]

        niveaux = Niveaux.objects.all()
        if not niveaux.exists():
            self.stdout.write(self.style.WARNING('No Niveaux found. Creating default levels.'))
            for n in ["TROISIEME", "SECONDE", "PREMIERE", "TERMINALE"]:
                Niveaux.objects.create(niveau=n)
            niveaux = Niveaux.objects.all()
        
        self.stdout.write(self.style.SUCCESS(f'Found {niveaux.count()} levels.'))

        subjects_pool = [
            "Mathématiques", "Physique-Chimie", "Sciences de la Vie et de la Terre", 
            "Français", "Anglais", "Histoire-Géographie", "Philosophie", 
            "Informatique", "Allemand", "Espagnol"
        ]

        for niveau in niveaux:
            self.stdout.write(self.style.NOTICE(f'\nLevel: {niveau.niveau}'))
            
            # Select 5 subjects for this level
            random.shuffle(subjects_pool)
            selected_subjects = subjects_pool[:5]

            for subj_name in selected_subjects:
                matiere_id = f"{subj_name.upper()[:4]}_{niveau.niveau[:3]}_{str(uuid.uuid4())[:4]}"
                
                # Check for existing matiere for this level to avoid exact duplicates
                matiere, created = Matiere.objects.get_or_create(
                    nom=f"{subj_name} ({niveau.niveau})",
                    niveau=niveau,
                    defaults={
                        'matiere_id': matiere_id,
                        'description': f'<p>Cours complet de {subj_name} pour la classe de {niveau.niveau}.</p>'
                    }
                )

                if created:
                    # Assign a random image if available
                    if available_images:
                        img_name = random.choice(available_images)
                        matiere.image = f'matieres/{img_name}'
                        matiere.save()
                    self.stdout.write(self.style.SUCCESS(f'  - Created subject: {matiere.nom}'))
                else:
                    self.stdout.write(self.style.NOTICE(f'  - Subject already exists: {matiere.nom}'))
                
                # Create 3 sample lessons per subject
                for i in range(1, 4):
                    lesson_name = f'Chapitre {i}: Maîtriser {subj_name}'
                    
                    lesson, l_created = Lesson.objects.get_or_create(
                        nom=f"{lesson_name} ({niveau.niveau})",
                        niveau=niveau,
                        matiere=matiere,
                        defaults={
                            'lesson_id': str(uuid.uuid4())[:15],
                            'creer_par': admin_user,
                            'description': f'<p>Contenu pédagogique pour le chapitre {i} de {subj_name}.</p>',
                            'position': i,
                            'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
                        }
                    )

                    if l_created:
                        # Create a Quiz
                        quiz = Quiz.objects.create(
                            lesson=lesson,
                            name=f'Évaluation: {lesson.nom}',
                            topic=subj_name,
                            number_of_questions=3,
                            time=15,
                            required_score_to_pass=75,
                            difficluty='medium'
                        )

                        # Questions
                        for q_idx in range(1, 4):
                            question = Question.objects.create(
                                text=f'Question {q_idx} sur le chapitre {i} de {subj_name}?',
                                quiz=quiz
                            )
                            Answer.objects.create(text='Réponse Correcte', correct=True, question=question)
                            Answer.objects.create(text='Réponse B (Fausse)', correct=False, question=question)
                            Answer.objects.create(text='Réponse C (Fausse)', correct=False, question=question)

        self.stdout.write(self.style.SUCCESS('\nSuccessfully populated platform with courses!'))
