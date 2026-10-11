
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from django.shortcuts import render
from .models import Quiz
from django.views.generic import ListView
from django.http import JsonResponse
from .models import Question, Answer
from .models import Result


@login_required
def list_view_quiz(request):
    object_list = Quiz.objects.filter(lesson_id=request.session.get('lesson'))
    lesson = object_list.first().lesson if object_list.exists() else None
    if lesson:
        from programme.models import Payment
        import datetime
        from django.contrib import messages
        from django.shortcuts import redirect
        date_exp = Payment.objects.filter(user=request.user, niveau=lesson.niveau).order_by('-date_pay')
        if not date_exp.exists() or datetime.date.today() > date_exp.first().date_expired:
            messages.error(request, "Accès refusé. Veuillez souscrire à ce niveau pour accéder aux quiz.")
            return redirect('programme:billing')
            
    return render(request, 'dash/main-quiz.html', {"object_list":object_list, 'lesson':lesson})

@login_required
def quiz_view(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk)
    lesson = quiz.lesson
    if lesson:
        from programme.models import Payment
        import datetime
        from django.contrib import messages
        from django.shortcuts import redirect
        date_exp = Payment.objects.filter(user=request.user, niveau=lesson.niveau).order_by('-date_pay')
        if not date_exp.exists() or datetime.date.today() > date_exp.first().date_expired:
            messages.error(request, "Accès refusé. Veuillez souscrire à ce niveau pour accéder aux quiz.")
            return redirect('programme:billing')

    quiz_num = Question.objects.filter(quiz=quiz).count()
    return render(request, 'dash/quiz.html', {'obj': quiz, 'num':quiz_num})

@login_required
def quiz_data_view(request, pk):
    quiz = get_object_or_404(Quiz, pk=pk)
    lesson = quiz.lesson
    if lesson:
        from programme.models import Payment
        import datetime
        date_exp = Payment.objects.filter(user=request.user, niveau=lesson.niveau).order_by('-date_pay')
        if not date_exp.exists() or datetime.date.today() > date_exp.first().date_expired:
            return JsonResponse({'error': 'Unauthorized'}, status=403)

    questions = []
    for q in quiz.get_questions():
        answers = []
        for a in q.get_answers():
            answers.append(a.text)
        questions.append({str(q): answers})
    return JsonResponse({
        'data': questions,
        'time': quiz.time,
    })

def is_ajax(request):
    return request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'

@login_required
@require_POST
def save_quiz_view(request, pk):
    if not is_ajax(request=request):
        return JsonResponse({'error': 'Requête invalide'}, status=400)
    if True:
        quiz = get_object_or_404(Quiz, pk=pk)
        lesson = quiz.lesson
        if lesson:
            from programme.models import Payment
            import datetime
            date_exp = Payment.objects.filter(user=request.user, niveau=lesson.niveau).order_by('-date_pay')
            if not date_exp.exists() or datetime.date.today() > date_exp.first().date_expired:
                return JsonResponse({'error': 'Unauthorized'}, status=403)

        questions = []
        data = request.POST
        data_ = dict(data.lists())

        data_.pop('csrfmiddlewaretoken', None)

        # Seules les questions appartenant à CE quiz sont prises en compte
        # (avant : on pouvait soumettre les questions d'autres quiz pour gonfler le score).
        questions = list(Question.objects.filter(quiz=quiz, text__in=list(data_.keys())))

        user = request.user

        score = 0
        multiplier = 100 / max(quiz.number_of_questions, 1)
        results = []
        correct_answer = None

        for q in questions:
            a_selected = request.POST.get(q.text)

            if a_selected != "":
                question_answers = Answer.objects.filter(question=q)
                for a in question_answers:
                    if a_selected == a.text:
                        if a.correct:
                            score += 1
                            correct_answer = a.text
                    else:
                        if a.correct:
                            correct_answer = a.text

                results.append({str(q): {'correct_answer': correct_answer, 'answered': a_selected}})
            else:
                results.append({str(q): 'not answered'})
            
        score_ = min(round(score * multiplier, 2), 100)
        esq = Result.objects.filter(quiz=quiz, user=user)
        if esq.exists():
            esq.delete()
        Result.objects.create(quiz=quiz, user=user, score=score_)

        if score_ >= quiz.required_score_to_pass:
            return JsonResponse({'passed': True, 'score': score_, 'results': results})
        else:
            return JsonResponse({'passed': False, 'score': score_, 'results': results})



@login_required
def result(request):
    from programme.models import Payment
    import datetime
    from django.contrib import messages
    from django.shortcuts import redirect
    
    date_exp = Payment.objects.filter(user=request.user).order_by('-date_pay')
    if not date_exp.exists() or datetime.date.today() > date_exp.first().date_expired:
        messages.error(request, "Accès refusé. Veuillez avoir un abonnement actif pour consulter vos résultats.")
        return redirect('programme:billing')

    my_result = Result.objects.filter(user=request.user)
    return render(request, 'dash/quiz-results.html', {'my_result': my_result})