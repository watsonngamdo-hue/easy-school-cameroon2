from django.urls import path

from .views import (
   list_view_quiz,
    quiz_view,
    quiz_data_view,
   result,
    save_quiz_view
)

app_name = 'quizapp'
urlpatterns = [
    path('quiz/', list_view_quiz, name='main-view'),
    path('quiz/<int:pk>/', quiz_view, name='quiz-view'),
    path('quiz/<int:pk>/save/', save_quiz_view, name='save-view'),
    path('quiz/<int:pk>/data/', quiz_data_view, name='quiz-data-view'),
    path('result/', result, name='result'),
    #path('lecon_quiz', lecon_quiz, name="lecon_quiz"),
#     path('quiz_result', quiz_result, name="quiz_result"),
#     path('ajax_get_quiz', ajax_get_quiz, name="ajax_get_quiz"),
]



