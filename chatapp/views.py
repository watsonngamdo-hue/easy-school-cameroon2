from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin

from chatapp.forms import ForumForm, ForumFormPrivate
from chatapp.models import Forum, ForumPrivate
from programme.models import Matiere, Niveaux, Payment
from django.contrib import messages
import datetime


class ForumView(LoginRequiredMixin, View):
    template_name = 'dash/forum-thread.html'
    def get(self, request, niveau_slug, matiere_slug , *arg, **kwargs):
        niveau = get_object_or_404(Niveaux, slug=niveau_slug)
        matiere = get_object_or_404(Matiere, slug=matiere_slug, niveau=niveau)
        
        # Check if user has a valid payment for this level
        date_exp = Payment.objects.filter(user=request.user, niveau=niveau).order_by('-date_pay')
        if not date_exp.exists():
            messages.error(request, "Accès refusé. Veuillez souscrire à ce niveau pour accéder au forum.")
            return redirect('programme:billing')
            
        exp = date_exp.first().date_expired
        if datetime.date.today() > exp:
            messages.error(request, "Votre abonnement pour ce niveau a expiré. Veuillez renouveler votre souscription.")
            return redirect('programme:billing')

        form = ForumForm(niveau=niveau, matiere=matiere)
        forum_msg = Forum.objects.select_related('niveau', 'user', 'matiere').filter(niveau=niveau, matiere=matiere, deleted=False).order_by('created_at')
        context = {'messages':forum_msg, 'form':form, 'niveau_slug':niveau.libelle, 'matiere_slug':matiere.nom, 'slug':niveau.slug}
        return render(request, self.template_name, context)

    def post(self, request, niveau_slug, matiere_slug , *arg, **kwargs):
        niveau = get_object_or_404(Niveaux, slug=niveau_slug)
        matiere = get_object_or_404(Matiere, slug=matiere_slug, niveau=niveau)
        
        # Check if user has a valid payment for this level
        date_exp = Payment.objects.filter(user=request.user, niveau=niveau).order_by('-date_pay')
        if not date_exp.exists():
            messages.error(request, "Accès refusé. Veuillez souscrire à ce niveau pour poster dans le forum.")
            return redirect('programme:billing')
            
        exp = date_exp.first().date_expired
        if datetime.date.today() > exp:
            messages.error(request, "Votre abonnement pour ce niveau a expiré. Veuillez renouveler votre souscription.")
            return redirect('programme:billing')

        form = ForumForm(request.POST, request.FILES, niveau=niveau, matiere=matiere)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.user = request.user
            msg.niveau = niveau
            msg.matiere = matiere
            msg.save()
            return redirect('chatapp:forum', niveau_slug=niveau_slug, matiere_slug=matiere_slug)
        
        forum_msg = Forum.objects.select_related('niveau', 'user', 'matiere').filter(niveau=niveau, matiere=matiere, deleted=False).order_by('created_at')
        messages.error(request, "Message non envoyé : " + " ".join(e for errs in form.errors.values() for e in errs))
        context = {'messages':forum_msg, 'form':form, 'niveau_slug':niveau.libelle, 'matiere_slug':matiere.nom, 'slug':niveau.slug}
        return render(request, self.template_name, context)       

        
class ForumViewPrivate(LoginRequiredMixin, View):
    template_name = 'dash/forum-private.html'

    def get(self, request, *arg, **kwargs):
        form = ForumFormPrivate(user=request.user)
        # Combined query ensuring distinct messages where user is either sender OR recipient
        all_messages = ForumPrivate.objects.filter(
            Q(from_message=request.user) | Q(to_message=request.user),
            deleted=False
        ).distinct().order_by('created_at')
        
        # Mark as read
        unread_ids = list(ForumPrivate.objects.filter(to_message=request.user, deleted=False).exclude(read_by=request.user).values_list('pk', flat=True))
        if unread_ids:
            ForumPrivate.read_by.through.objects.bulk_create(
                [ForumPrivate.read_by.through(forumprivate_id=pk, userregistration_id=request.user.pk) for pk in unread_ids],
                ignore_conflicts=True,
            )
        
        context = {'all_messages': all_messages, 'form': form}
        return render(request, self.template_name, context)

    def post(self, request, *arg, **kwargs):
        form = ForumFormPrivate(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.save()
            # The sender is the current user
            msg.from_message.add(request.user)
            form.save_m2m() # Ensure to_message and any others are saved
            # Redirect to GET to prevent double POST on refresh
            return redirect('chatapp:forum-private')
            
        all_messages = ForumPrivate.objects.filter(
            Q(from_message=request.user) | Q(to_message=request.user),
            deleted=False
        ).distinct().order_by('created_at')
        
        messages.error(request, "Message non envoyé : " + " ".join(e for errs in form.errors.values() for e in errs))
        context = {'all_messages': all_messages, 'form': form}   
        return render(request, self.template_name, context)      