from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import JsonResponse, StreamingHttpResponse
from .services import CreditService, AIService
from . import cache as cache_ia
from .models import AIMessage, Conversation, Pack, AIModel, AISettings
from django.utils.decorators import method_decorator
from django.db import transaction
from django.core.exceptions import ValidationError
from authapp.models import UserRegistration
import os
import uuid
import json
import logging

logger = logging.getLogger(__name__)

AI_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
AI_UPLOAD_ALLOWED = {
    '.pdf': {'application/pdf'},
    '.png': {'image/png'},
    '.jpg': {'image/jpeg'},
    '.jpeg': {'image/jpeg'},
    '.webp': {'image/webp'},
    '.txt': {'text/plain'},
}


def validate_ai_upload(f):
    """Refuse les fichiers trop gros ou d'un type non autorisé (HTML, SVG, exécutables…)."""
    ext = os.path.splitext(f.name or '')[1].lower()
    if ext not in AI_UPLOAD_ALLOWED:
        raise ValidationError("Type de fichier non autorisé (PDF, image ou texte uniquement).")
    if f.size > AI_UPLOAD_MAX_BYTES:
        raise ValidationError("Fichier trop volumineux (10 Mo maximum).")
    head = f.read(8)
    f.seek(0)
    signatures = {
        '.pdf': [b'%PDF'],
        '.png': [b'\x89PNG'],
        '.jpg': [b'\xff\xd8\xff'],
        '.jpeg': [b'\xff\xd8\xff'],
        '.webp': [b'RIFF'],
    }
    if ext in signatures and not any(head.startswith(sig) for sig in signatures[ext]):
        raise ValidationError("Le contenu du fichier ne correspond pas à son extension.")


class AIAssistantView(LoginRequiredMixin, TemplateView):
    template_name = 'aiapp/ai_assistant.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Reset credits if needed
        CreditService.check_and_reset_daily_credits(self.request.user)
        context['daily_credits'] = self.request.user.daily_credits
        context['wallet_credits'] = self.request.user.wallet_credits
        context['conversations'] = Conversation.objects.filter(user=self.request.user)
        
        # Load AI Models for frontend
        from .models import AIModel, AISettings
        allowed_models = ['gpt-4o', 'gpt-4o-mini', 'gemini-3-flash-preview', 'gemini-3.1-pro-preview']
        context['all_models'] = AIModel.objects.filter(
            is_active=True, 
            model_type='chat',
            api_value__in=allowed_models,
            cost__gt=0
        ).order_by('cost')
        
        # Fetch or create settings to pass file upload cost to default
        settings_obj, _ = AISettings.objects.get_or_create(id=1)
        context['file_upload_cost'] = settings_obj.file_upload_cost
        
        # Load specific conversation if ID is provided
        conversation_id = self.request.GET.get('c')
        if conversation_id:
            conversation = get_object_or_404(Conversation, id=conversation_id, user=self.request.user)
            context['active_conversation'] = conversation
            context['messages'] = conversation.messages.all()
        
        return context

    def post(self, request, *args, **kwargs):
        logger.info(f"POST request to AIAssistantView from user: {request.user}")
        
        # Handle both JSON (AJAX) and Multipart (File Uploads)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            try:
                if request.content_type.startswith('multipart/form-data'):
                    data = request.POST.dict()
                    files = request.FILES
                    action = data.get('action')
                else:
                    data = json.loads(request.body)
                    files = None
                    action = data.get('action')

                logger.info(f"Action: {action}, Files: {files.keys() if files else 'None'}")

                if action == 'chat':
                    return self.handle_chat(request, data, files)
                elif action == 'generate_image':
                    return self.handle_image(request, data)
                elif action == 'new_conversation':
                    return self.create_conversation(request)
                elif action == 'delete_conversation':
                    return self.delete_conversation(request, data)
                else:
                    return JsonResponse({'error': 'Invalid action'}, status=400)
            except ValidationError as e:
                return JsonResponse({'error': ' '.join(e.messages)}, status=400)
            except Exception:
                logger.exception("Erreur dans AIAssistantView.post")
                return JsonResponse({'error': "Une erreur interne est survenue. Veuillez réessayer."}, status=500)
        
        logger.warning(f"POST request not XMLHttpRequest or finished unexpectedly. Headers: {request.headers}")
        return self.get(request, *args, **kwargs)

    def create_conversation(self, request):
        conversation = Conversation.objects.create(user=request.user)
        return JsonResponse({'id': str(conversation.id), 'title': conversation.title})

    def delete_conversation(self, request, data):
        c_id = data.get('id')
        Conversation.objects.filter(id=c_id, user=request.user).delete()
        return JsonResponse({'status': 'deleted'})

    def handle_chat(self, request, data, files=None):
        user_message = data.get('message', '')
        conversation_id = data.get('conversation_id')
        
        if len(user_message) > 8000:
            return JsonResponse({'error': 'Message trop long (8000 caractères maximum).'}, status=400)

        # If file is present, title could be "File Upload"
        if not user_message and not files:
            return JsonResponse({'error': 'Message empty'}, status=400)

        # Retrieve or create conversation
        if conversation_id:
            conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
        else:
            title_text = user_message[:30] if user_message else "File Upload..."
            conversation = Conversation.objects.create(user=request.user, title=title_text + "...")
            conversation_id = str(conversation.id)

        # Update title if needed
        if conversation.messages.count() == 0 and user_message:
            conversation.title = user_message[:30] + "..."
            conversation.save()

        logger.info(f"Conversation ready: {conversation.id} - {conversation.title}")

        # Calculate Credits
        # Get Model Cost
        model_api_value = data.get('model')
        settings_obj, _ = AISettings.objects.get_or_create(id=1)
        
        # Seuls les modèles actifs configurés par l'administrateur sont acceptés
        # (avant : un modèle inconnu était facturé 10 crédits quel que soit son coût réel).
        if not model_api_value:
            model_api_value = 'gpt-4o-mini'
        ai_model = AIModel.objects.filter(api_value=model_api_value, model_type='chat', is_active=True).first()
        if ai_model is None:
            return JsonResponse({'error': "Modèle d'IA indisponible."}, status=400)
        cost = max(int(ai_model.cost), 1)
        provider = ai_model.provider

        uploaded_file = None
        if files:
            if len(files) > 1:
                return JsonResponse({'error': 'Un seul fichier par message.'}, status=400)
            uploaded_file = next(iter(files.values()))
            validate_ai_upload(uploaded_file)
            cost += settings_obj.file_upload_cost
        
        logger.info(f"Model: {model_api_value}, Provider: {provider}, Cost: {cost}")
        
        if not CreditService.deduct_credits(request.user, cost):
            logger.warning(f"Insufficient credits for user {request.user.id}")
            return JsonResponse({'error': f'Crédits insuffisants. Coût requis : {cost} crédits.'}, status=403)

        # Save User Message & Files immediately
        message_obj = AIMessage.objects.create(
            conversation=conversation,
            user=request.user,
            user_message=user_message,
            mode='chat',
            modele=model_api_value,
        )
        logger.info(f"AIMessage created: {message_obj.id}")
        
        if uploaded_file:
            first_file = uploaded_file
            ext = os.path.splitext(first_file.name)[1].lower()
            original_name = os.path.basename(first_file.name)[:100]
            first_file.name = f"{uuid.uuid4().hex}{ext}"
            message_obj.file = first_file
            message_obj.file_type = first_file.content_type  # Save content type
            message_obj.save()
            
            user_message += f"\n[Utilisateur a joint un fichier: {original_name}]"

        # Prepare History (exclude image generation or failed messages without text response)
        history = [
            {'user': m.user_message, 'ai': m.ai_response} 
            for m in conversation.messages.filter(ai_response__isnull=False).exclude(id=message_obj.id)
        ]

        # Question déjà posée ? On réutilise la réponse enregistrée : aucun appel
        # à l'API (donc aucun coût pour EasySchool), mais l'élève est débité normalement.
        question_initiale = data.get('message', '')
        cache_possible = cache_ia.peut_utiliser_cache(question_initiale, bool(uploaded_file), bool(history))
        reponse_cache = cache_ia.chercher(model_api_value, question_initiale) if cache_possible else None

        # Generator for Streaming
        def stream_response():
            # Send initial metadata header as a separate JSON line
            metadata = {
                'conversation_id': conversation_id,
                'title': conversation.title,
                'daily_credits': request.user.daily_credits,
                'wallet_credits': request.user.wallet_credits,
                'file_url': message_obj.file.url if message_obj.file else None
            }
            yield json.dumps(metadata) + "\n"
            
            full_ai_response = []

            if reponse_cache is not None:
                for i in range(0, len(reponse_cache), 200):
                    yield reponse_cache[i:i + 200]
                message_obj.ai_response = reponse_cache
                message_obj.depuis_cache = True
                message_obj.save(update_fields=['ai_response', 'depuis_cache'])
                return

            try:
                # Stream the AI response, passing file if present
                file_to_pass = message_obj.file if message_obj.file else None
                for chunk in AIService.stream_chat_response(
                    user_message, 
                    history, 
                    file_obj=file_to_pass,
                    model_api_value=model_api_value,
                    provider=provider
                ):
                    full_ai_response.append(chunk)
                    yield chunk
                
                # Check for PDF action
                final_text = "".join(full_ai_response)
                
                if "ACTION:GENERATE_PDF" in final_text:
                    from .services import PDFService
                    import uuid
                    import posixpath
                    from django.conf import settings
                    
                    # Hide the tag if it's visible or replace it
                    final_text = final_text.replace("<!-- ACTION:GENERATE_PDF -->", "").replace("[ACTION:GENERATE_PDF]", "").strip()
                    
                    filename = f"reponse_ai_{uuid.uuid4().hex[:8]}.pdf"
                    relative_path = PDFService.generate_pdf_from_text(final_text, filename)
                    
                    media_path = posixpath.join(settings.MEDIA_URL, relative_path.lstrip('/'))
                    pdf_url = request.build_absolute_uri(media_path)
                    
                    # Yield the download link markdown chunk to the user
                    download_link = f"\n\n[📄 Cliquez ici pour télécharger le PDF]({pdf_url})"
                    yield download_link
                    
                    final_text += download_link
                
                # Update the message object with full response
                message_obj.ai_response = final_text
                message_obj.save()

                if "[Erreur" in final_text:
                    # L'IA n'a pas répondu : l'élève est remboursé.
                    CreditService.refund_credits(request.user, cost)
                elif cache_possible:
                    cache_ia.enregistrer(model_api_value, question_initiale, final_text)
                
            except GeneratorExit:
                # Client disconnected prematurely
                return
            except Exception as e:
                logger.error(f"Streaming Error: {e}")
                error_msg = str(e)
                if '429' in error_msg or 'Quota' in error_msg or 'exhausted' in error_msg.lower():
                    yield "\n[Erreur : Le service est actuellement très sollicité (Limite de requêtes atteinte). Veuillez patienter quelques instants avant de réessayer.]"
                else:
                    yield "\n[Erreur : Un problème inattendu est survenu lors de la génération. Veuillez réessayer.]"

        return StreamingHttpResponse(stream_response(), content_type='text/plain')

    def handle_image(self, request, data):
        prompt = data.get('prompt')
        conversation_id = data.get('conversation_id')
        
        if not prompt:
            return JsonResponse({'error': 'Prompt empty'}, status=400)

        # Retrieve or create conversation
        if conversation_id:
            conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
        else:
            conversation = Conversation.objects.create(user=request.user, title=prompt[:30] + "...")
            conversation_id = str(conversation.id)

        if len(prompt) > 2000:
            return JsonResponse({'error': 'Description trop longue.'}, status=400)

        model_api_value = data.get('model')
        ai_model = AIModel.objects.filter(api_value=model_api_value, model_type='image', is_active=True).first()
        if ai_model is None:
            return JsonResponse({'error': "Modèle d'image indisponible."}, status=400)
        cost = max(int(ai_model.cost), 1)
        provider = ai_model.provider

        logger.info(f"Image Gen - Model: {model_api_value}, Provider: {provider}, Cost: {cost}")
        
        if not CreditService.deduct_credits(request.user, cost):
            return JsonResponse({'error': f'Crédits insuffisants pour générer une image (Coût: {cost} crédits).'}, status=403)

        # Generate Image
        image_content, error = AIService.generate_image(prompt, model_api_value=model_api_value, provider=provider)
        
        if error:
            # Remboursement des crédits si la génération a échoué.
            CreditService.refund_credits(request.user, cost)
            logger.warning("Échec génération d'image : %s", error)
            return JsonResponse({'error': "La génération de l'image a échoué. Vos crédits ont été remboursés."}, status=502)

        # Save Message
        message = AIMessage.objects.create(
            conversation=conversation,
            user=request.user,
            user_message=prompt,
            mode='image'
        )
        message.image.save(image_content.name, image_content)
        message.save()

        return JsonResponse({
            'image_url': message.image.url,
            'daily_credits': request.user.daily_credits,
            'wallet_credits': request.user.wallet_credits,
            'conversation_id': conversation_id,
            'conversation_title': conversation.title
        })

class BuyCreditsView(LoginRequiredMixin, View):
    template_name = 'aiapp/buy_credits.html'

    def get(self, request):
        # Ensure daily credits are up to date
        CreditService.check_and_reset_daily_credits(self.request.user)
        packs = Pack.objects.all().order_by('price')
        return render(request, self.template_name, {'somme': request.user.somme, 'packs': packs})

    def post(self, request):
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        try:
            amount = int(request.POST.get('amount', 0))
        except (TypeError, ValueError):
            amount = 0

        # Seuls les packs définis par l'administrateur peuvent être achetés.
        # (Avant : un montant négatif permettait de se créditer de l'argent.)
        pack = Pack.objects.filter(credit=amount).order_by('price').first() if amount > 0 else None
        if pack is None or pack.price <= 0:
            message = "Pack de crédits invalide."
            if is_ajax:
                return JsonResponse({'success': False, 'message': message}, status=400)
            messages.error(request, message)
            return redirect('aiapp:buy_credits')

        with transaction.atomic():
            user = UserRegistration.objects.select_for_update().get(pk=request.user.pk)
            if user.somme >= pack.price:
                user.somme -= pack.price
                user.wallet_credits += pack.credit
                user.save(update_fields=['somme', 'wallet_credits'])
                success = True
                message = f"Achat réussi ! Vous avez reçu {pack.credit} crédits."
            else:
                success = False
                message = "Solde insuffisant dans le portefeuille."

        (messages.success if success else messages.error)(request, message)
        if is_ajax:
            return JsonResponse({
                'success': success,
                'message': message,
                'somme': user.somme,
                'wallet_credits': user.wallet_credits,
            })
        return redirect('aiapp:buy_credits')

class CreatePDFView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            content = str(data.get("content", "")).strip()
            if len(content) > 50000:
                return JsonResponse({"error": "Contenu trop long."}, status=400)
            
            if not content:
                logger.warning("PDF creation failed: Content empty")
                return JsonResponse({"error": "Le contenu ne peut pas être vide."}, status=400)
                
            from .services import PDFService
            import uuid
            
            filename = f"reponse_ai_{uuid.uuid4().hex[:8]}.pdf"
            relative_path = PDFService.generate_pdf_from_text(content, filename)
            
            from django.conf import settings
            import posixpath
            
            media_path = posixpath.join(settings.MEDIA_URL, relative_path.lstrip('/'))
            pdf_url = request.build_absolute_uri(media_path)
            
            return JsonResponse({
                "message": "PDF created successfully",
                "pdf_url": pdf_url
            })
            
        except Exception as e:
            logger.error(f"Error creating PDF: {str(e)}", exc_info=True)
            return JsonResponse({"error": "Erreur lors de la création du PDF."}, status=500)
