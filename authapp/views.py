from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import EditAccountForm


@login_required
@require_POST
def mark_onboarded(request):
    request.user.is_first_login = False
    request.user.save(update_fields=["is_first_login"])
    return JsonResponse({"status": "success"})


@login_required
@require_http_methods(["GET", "POST"])
def updateProfile(request):
    form = EditAccountForm(instance=request.user)
    if request.method == "POST":
        form = EditAccountForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil mis à jour !")
            return redirect("authapp:editprofile")
        messages.warning(request, "Le profil n'a pas été enregistré : vérifiez les champs signalés.")
    return render(request, "account/account-edit.html", {"form": form})
