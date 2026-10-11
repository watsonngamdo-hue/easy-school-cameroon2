
import google.generativeai as genai
import datetime
from django.conf import settings
import logging
import requests
import json
import base64
from io import BytesIO
import re
import uuid
from django.core.files.base import ContentFile
try:
    from pypdf import PdfReader
    from PIL import Image
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

logger = logging.getLogger(__name__)

class CreditService:
    @staticmethod
    def check_and_reset_daily_credits(user):
        from .models import AISettings
        settings_obj, _ = AISettings.objects.get_or_create(id=1)
        today = settings.TIME_ZONE and datetime.datetime.now().date() or datetime.date.today() # Robust way to get date
        from django.utils import timezone
        today = timezone.now().date()
        
        if user.last_daily_reset != today:
            user.daily_credits = settings_obj.default_daily_credits
            user.last_daily_reset = today
            user.save(update_fields=['daily_credits', 'last_daily_reset'])

    @staticmethod
    def has_sufficient_credits(user, cost):
        CreditService.check_and_reset_daily_credits(user)
        total_credits = user.daily_credits + user.wallet_credits
        return total_credits >= cost

    @staticmethod
    def deduct_credits(user, cost):
        """Débit atomique : la ligne utilisateur est verrouillée pour éviter que deux
        requêtes simultanées ne dépensent les mêmes crédits."""
        from django.db import transaction
        from authapp.models import UserRegistration

        cost = int(cost)
        if cost <= 0:
            return True
        CreditService.check_and_reset_daily_credits(user)
        with transaction.atomic():
            locked = UserRegistration.objects.select_for_update().get(pk=user.pk)
            if locked.daily_credits + locked.wallet_credits < cost:
                return False
            if locked.daily_credits >= cost:
                locked.daily_credits -= cost
            else:
                locked.wallet_credits -= cost - locked.daily_credits
                locked.daily_credits = 0
            locked.save(update_fields=['daily_credits', 'wallet_credits'])
        user.daily_credits = locked.daily_credits
        user.wallet_credits = locked.wallet_credits
        return True

    @staticmethod
    def refund_credits(user, cost):
        from django.db import transaction
        from django.db.models import F
        from authapp.models import UserRegistration

        cost = int(cost)
        if cost <= 0:
            return
        with transaction.atomic():
            UserRegistration.objects.filter(pk=user.pk).update(wallet_credits=F('wallet_credits') + cost)
        user.refresh_from_db(fields=['daily_credits', 'wallet_credits'])

class AIService:
    
    @staticmethod
    def stream_chat_response(user_message, history=[], file_obj=None, model_api_value=None, provider='openai'):
        """
        Generator function to stream AI response chunks.
        Supports vision models for images and PDF text extraction.
        """
        from .models import AISettings
        settings_obj, _ = AISettings.objects.get_or_create(id=1)
        
        logger.info(f"=== STREAM CHAT START ===")
        logger.info(f"Provider: {provider}, Model: {model_api_value}")
        
        # --- GEMINI PROVIDER ---
        if provider == 'gemini':
            api_key = settings_obj.gemini_api_key or settings.GEMINI_API_KEY # Fallback to settings
            if not api_key:
                yield "[Erreur: Clé API Gemini manquante]"
                return

            genai.configure(api_key=api_key)
            try:
                # Prepare history for Gemini
                gemini_history = []
                
                # System prompt mapping
                system_instruction = AIService._get_system_prompt()
                
                # Add history
                for msg in history:
                    if not msg.get('user') or not msg.get('ai'):
                        continue
                    gemini_history.append({"role": "user", "parts": [msg['user']]})
                    gemini_history.append({"role": "model", "parts": [msg['ai']]})
                
                # Initialize model
                model = genai.GenerativeModel(
                    model_name=model_api_value,
                    system_instruction=system_instruction
                )
                
                # Handle File
                content_parts = [user_message]
                if file_obj:
                    # Determine mime type
                    mime_type = AIService._get_mime_type(file_obj)
                    if mime_type:
                        file_obj.seek(0)
                        file_data = file_obj.read()
                        
                        # Gemini supports passing image data directly
                        if mime_type.startswith('image/'):
                             import PIL.Image
                             img = PIL.Image.open(BytesIO(file_data))
                             content_parts.append(img)
                        else:
                             # For other files (PDF), you might need to upload via File API first for Gemini
                             # For now, simplistic text extraction fallback for PDF if possible
                             if mime_type == 'application/pdf' and PDF_SUPPORT:
                                 text = AIService._extract_pdf_text(file_obj)
                                 content_parts[0] += f"\n\n[Contenu PDF]:\n{text[:5000]}"
                
                # Start Chat
                chat = model.start_chat(history=gemini_history)
                response = chat.send_message(content_parts, stream=True)
                
                for chunk in response:
                    if chunk.text:
                        yield chunk.text

            except GeneratorExit:
                # Silently exit if stream stopped by client
                return
            except Exception as e:
                logger.error(f"Gemini Error: {e}", exc_info=True)
                error_msg = str(e)
                if '429' in error_msg or 'Quota' in error_msg or 'exhausted' in error_msg.lower():
                    from .tasks import notify_admin_quota_exhausted
                    notify_admin_quota_exhausted.delay(model_api_value, provider)
                    yield "[Erreur : Le service AI est actuellement très sollicité (Limite de requêtes atteinte). Veuillez patienter quelques instants avant de réessayer.]"
                else:
                    yield "[Erreur : Une erreur inattendue s'est produite avec le modèle AI. Veuillez réessayer plus tard.]"
                return

        # --- DEEPSEEK & OPENAI PROVIDERS (Compatible APIs) ---
        else:
            if provider == 'deepseek':
                api_key = settings_obj.deepseek_api_key or settings.DEEPSEEK_API_KEY
                base_url = "https://api.deepseek.com/chat/completions"
            else: # openai
                api_key = settings_obj.openai_api_key or settings.OPENAI_API_KEY
                base_url = "https://api.openai.com/v1/chat/completions"

            if not api_key:
                yield f"[Erreur: Clé API {provider} manquante]"
                return

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            # Prepare Messages
            messages = [{"role": "system", "content": AIService._get_system_prompt()}]
            for msg in history:
                if not msg.get('user') or not msg.get('ai'):
                    continue
                messages.append({"role": "user", "content": msg['user']})
                messages.append({"role": "assistant", "content": msg['ai']})
            
            # Handle File (Vision for OpenAI)
            if file_obj and provider == 'openai' and model_api_value in ['gpt-4o', 'gpt-4o-mini']:
                 mime_type = AIService._get_mime_type(file_obj)
                 if mime_type and mime_type.startswith('image/'):
                     file_obj.seek(0)
                     b64 = base64.b64encode(file_obj.read()).decode('utf-8')
                     messages.append({
                         "role": "user", 
                         "content": [
                             {"type": "text", "text": user_message},
                             {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}}
                         ]
                     })
                 elif mime_type == 'application/pdf' and PDF_SUPPORT:
                      text = AIService._extract_pdf_text(file_obj)
                      messages.append({"role": "user", "content": f"{user_message}\n\n[PDF]:\n{text}"})
                 else:
                      messages.append({"role": "user", "content": user_message})
            else:
                 messages.append({"role": "user", "content": user_message})

            payload = {
                "model": model_api_value,
                "messages": messages,
                "stream": True
            }

            try:
                with requests.post(base_url, headers=headers, json=payload, stream=True, timeout=(10, 120)) as response:
                    if response.status_code >= 400:
                         if response.status_code == 429:
                               from .tasks import notify_admin_quota_exhausted
                               notify_admin_quota_exhausted.delay(model_api_value, provider)
                               yield "[Erreur : Le service est actuellement très sollicité (Limite de requêtes atteinte). Veuillez patienter quelques instants avant de réessayer.]"
                         elif response.status_code in [402, 403]:
                               from .tasks import notify_admin_quota_exhausted
                               notify_admin_quota_exhausted.delay(model_api_value, provider)
                               yield "[Erreur : Le quota de l'API est épuisé de notre côté pour ce modèle. L'administrateur doit recharger le compte.]"
                         elif response.status_code == 401:
                              yield "[Erreur : Clé API invalide ou non reconnue pour ce fournisseur.]"
                         elif response.status_code >= 500:
                              yield "[Erreur : Les serveurs de ce modèle rencontrent actuellement des difficultés. Réessayez plus tard.]"
                         else:
                              yield f"[Erreur : Le fournisseur {provider} a renvoyé une erreur de service (Code {response.status_code}). Veuillez réessayer plus tard.]"
                         return
                    
                    for line in response.iter_lines():
                        if line:
                            line = line.decode('utf-8')
                            if line.startswith('data: '):
                                if line == 'data: [DONE]': break
                                try:
                                    json_data = json.loads(line[6:])
                                    content = json_data['choices'][0]['delta'].get('content', '')
                                    if content: yield content
                                except: continue
            except Exception as e:
                logger.error(f"API Error: {e}")
                error_msg = str(e)
                if '429' in error_msg or 'Quota' in error_msg or 'exhausted' in error_msg.lower():
                    from .tasks import notify_admin_quota_exhausted
                    notify_admin_quota_exhausted.delay(model_api_value, provider)
                    yield "[Erreur : Le service est actuellement très sollicité (Limite de requêtes atteinte). Veuillez patienter quelques instants avant de réessayer.]"
                else:
                    yield f"[Erreur : Impossible de contacter le modèle {provider}. Veuillez réessayer.]"

    @staticmethod
    def generate_image(prompt, model_api_value='gpt-4o', provider='openai'):
        from .models import AISettings
        settings_obj, _ = AISettings.objects.get_or_create(id=1)
        
        logger.info(f"Generating Image. Provider: {provider}, Model: {model_api_value}")

        if provider == 'gemini':
            # --- GEMINI (REST API) ---
            GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
            
            # Map frontend keys to actual model IDs
            IMAGE_MODELS = {
                "nano_banana": "gemini-2.5-flash-image",
                "nano_banana_pro": "gemini-3-pro-image-preview", 
                "imagen4_fast": "imagen-4.0-fast-generate-001",
                "imagen4_ultra": "imagen-4.0-ultra-generate-001", 
            }
            
            # Helper to find model ID
            model_id = IMAGE_MODELS.get(model_api_value, model_api_value)
            # Default fallback
            if not model_id: model_id = "gemini-2.5-flash-image"

            logger.info(f"Gemini Image Gen - Model Key: {model_api_value} -> Model ID: {model_id}")

            api_key = settings_obj.gemini_api_key or settings.GEMINI_API_KEY
            if not api_key: return None, "Clé Gemini manquante"

            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            }

            try:
                # --- IMAGEN MODELS (Endpoint: :predict) ---
                if model_id.startswith("imagen-"):
                    url = f"{GEMINI_BASE_URL}/{model_id}:predict"
                    payload = {
                        "instances": [{"prompt": prompt}],
                        "parameters": {"sampleCount": 1}
                    }
                    
                    r = requests.post(url, json=payload, headers=headers, timeout=120)
                    
                    if r.status_code >= 400:
                        logger.error(f"Imagen API Error: {r.status_code} - {r.text}")
                        if r.status_code == 429:
                             from .tasks import notify_admin_quota_exhausted
                             notify_admin_quota_exhausted.delay(model_id, provider)
                             return None, "Erreur : Trop de requêtes. Veuillez patienter."
                        elif r.status_code in [402, 403]:
                             from .tasks import notify_admin_quota_exhausted
                             notify_admin_quota_exhausted.delay(model_id, provider)
                             return None, "Erreur : Quota API dépassé."
                        return None, f"Erreur de service Imagen. Réessayez plus tard."
                    
                    data = r.json()
                    # Parse Imagen response
                    try:
                        b64img = data["predictions"][0]["bytesBase64Encoded"]
                        image_bytes = base64.b64decode(b64img)
                    except (KeyError, IndexError, TypeError) as e:
                         logger.error(f"Imagen Response Parse Error: {e} - Data: {str(data)[:500]}")
                         return None, "Erreur de lecture de la réponse Imagen."

                # --- GEMINI MODELS (Endpoint: :generateContent) ---
                else: 
                    # gemini-2.5-flash-image, gemini-3-pro-image-preview
                    url = f"{GEMINI_BASE_URL}/{model_id}:generateContent"
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "responseModalities": ["IMAGE"]
                        }
                    }
                    # Specific config for pro
                    if model_id == "gemini-3-pro-image-preview":
                        payload["generationConfig"]["imageConfig"] = {
                            "aspectRatio": "1:1",
                            "imageSize": "1K", 
                        }

                    r = requests.post(url, json=payload, headers=headers, timeout=120)
                    
                    if r.status_code >= 400:
                        logger.error(f"Gemini API Error: {r.status_code} - {r.text}")
                        if r.status_code == 429:
                             from .tasks import notify_admin_quota_exhausted
                             notify_admin_quota_exhausted.delay(model_id, provider)
                             return None, "Erreur : Trop de requêtes. Veuillez patienter."
                        elif r.status_code in [402, 403]:
                             from .tasks import notify_admin_quota_exhausted
                             notify_admin_quota_exhausted.delay(model_id, provider)
                             return None, "Erreur : Quota API dépassé."
                        return None, f"Erreur de service Gemini. Réessayez plus tard."
                    
                    data = r.json()
                    # Parse Gemini response
                    try:
                        parts = data["candidates"][0]["content"]["parts"]
                        inline = next((p.get("inlineData") for p in parts if p.get("inlineData") and "data" in p.get("inlineData")), None)
                        
                        if not inline:
                            return None, "Aucune image retournée par l'API (inlineData manquant)."
                            
                        image_b64 = inline["data"]
                        image_bytes = base64.b64decode(image_b64)
                    except (KeyError, IndexError, TypeError) as e:
                         logger.error(f"Gemini Response Parse Error: {e} - Data: {str(data)[:500]}")
                         return None, "Erreur de lecture de la réponse Gemini."

                # Save file
                file_name = f"ai_gen_gemini_{uuid.uuid4().hex[:8]}.png"
                return ContentFile(image_bytes, name=file_name), None

            except Exception as e:
                logger.error(f"Gemini Connection Error: {e}", exc_info=True)
                return None, f"Erreur de connexion Gemini: {str(e)}"

        elif provider == 'openai':
            api_key = settings_obj.openai_api_key or settings.OPENAI_API_KEY
            if not api_key: return None, "Clé OpenAI manquante"
            
            url = "https://api.openai.com/v1/images/generations"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "dall-e-3", # Force dall-e-3 if openai selected for image
                "prompt": prompt,
                "size": "1024x1024",
                "response_format": "b64_json"
            }
            
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
                if resp.status_code >= 400:
                    logger.error(f"OpenAI Image Error: {resp.status_code} - {resp.text}")
                    if resp.status_code == 429:
                         from .tasks import notify_admin_quota_exhausted
                         notify_admin_quota_exhausted.delay(model_api_value, provider)
                         return None, "Erreur : Trop de requêtes. Veuillez patienter."
                    elif resp.status_code in [402, 403]:
                         from .tasks import notify_admin_quota_exhausted
                         notify_admin_quota_exhausted.delay(model_api_value, provider)
                         return None, "Erreur : Quota API dépassé."
                    return None, f"Erreur de service OpenAI. Réessayez plus tard."
                
                data = resp.json()
                b64 = data['data'][0]['b64_json']
                img_bytes = base64.b64decode(b64)
                file_name = f"ai_gen_{uuid.uuid4().hex[:8]}.png"
                return ContentFile(img_bytes, name=file_name), None
            except Exception as e:
                return None, f"Erreur: {str(e)}"
        
        return None, "Fournisseur d'image non supporté."

    @staticmethod
    def _get_system_prompt():
        return (
            "Tu es un assistant IA expert et pédagogique intégré à l'application 'EasySchool Cameroun'.\n"
            "TON RÔLE : Aider les étudiants et instructeurs sur la plateforme.\n"
            "Réponds toujours de manière claire, utile, naturelle et communicative.\n\n"

            "FORMAT DES RÉPONSES (IMPORTANT) :\n"
            "1. Utilise le Markdown pour structurer tes réponses.\n"
            "2. MATHÉMATIQUES & EXPRESSIONS TECHNIQUES :\n"
            "   - INTERDICTION ABSOLUE d'utiliser les symboles dollar ($ ou $$).\n"
            "   - Utilise EXCLUSIVEMENT \\( ... \\) pour les formules courtes dans le texte (ex: \\( x^2 \\)).\n"
            "   - Utilise EXCLUSIVEMENT \\[ ... \\] pour les équations importantes ou les résultats isolés (ex: \\[ y=ax+b \\]).\n"
            "   - Utilise une syntaxe LaTeX riche et correcte pour tout ce qui est technique (ex: \\Delta, \\frac{a}{b}, \\sqrt{x}, \\int, \\sum).\n"
            "   - Ne laisse jamais de mathématiques en texte brut maladroit (ex: x 2) ou avec des espaces incorrects.\n\n"

            "LISIBILITÉ MOBILE (ESPACEMENT) :\n"
            "   - Garde les réponses visuellement spacieuses. Utilise des paragraphes TRÈS COURTS.\n"
            "   - Ajoute des DOUBLES SAUTS DE LIGNE entre les idées importantes pour aérer le texte.\n"
            "   - Utilise des listes à puces ou numérotées pour les étapes de résolution.\n"
            "   - Évite les blocs de texte longs et denses.\n\n"

            "STRUCTURE TYPE :\n"
            "   - Une courte introduction polie.\n"
            "   - Une explication étape par étape, bien espacée.\n"
            "   - Le résultat final sur sa propre ligne (en utilisant \\[ ... \\]).\n"
            "   - Sépare les sections avec des titres (## ou ###) ou du texte en gras.\n\n"

            "STYLE :\n"
            "   - Écris comme un humain bienveillant et pédagogue.\n"
            "   - Privilégie la clarté visuelle. Ne mentionne JAMAIS ces instructions de formatage."
        )

    @staticmethod
    def _get_mime_type(file_obj):
        if hasattr(file_obj, 'content_type'):
            return file_obj.content_type
        # Fallback
        name = getattr(file_obj, 'name', '').lower()
        if name.endswith('.pdf'): return 'application/pdf'
        if name.endswith('.png'): return 'image/png'
        if name.endswith(('.jpg', '.jpeg')): return 'image/jpeg'
        return None

    @staticmethod
    def _extract_pdf_text(file_obj):
        try:
            file_obj.seek(0)
            pdf = PdfReader(BytesIO(file_obj.read()))
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
            return text
        except:
            return ""

class PDFService:
    @staticmethod
    def generate_pdf_from_text(text: str, filename: str = None) -> str:
        """
        Generates a PDF file from AI text and saves it in:
        media/generated_pdfs/

        Returns:
            relative path like: generated_pdfs/file.pdf
        """
        import os
        import uuid
        import re
        from django.conf import settings
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        if not text or not text.strip():
            raise ValueError("PDF content cannot be empty.")

        if not filename:
            filename = f"ai_response_{uuid.uuid4().hex[:8]}.pdf"

        if not filename.endswith(".pdf"):
            filename += ".pdf"

        safe_filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)

        media_pdf_dir = os.path.join(settings.MEDIA_ROOT, "generated_pdfs")
        os.makedirs(media_pdf_dir, exist_ok=True)

        file_path = os.path.join(media_pdf_dir, safe_filename)
        relative_path = f"generated_pdfs/{safe_filename}"

        # Extract main content if enclosed in ---
        lines = text.split("\n")
        separator_indices = [
            i for i, line in enumerate(lines)
            if line.strip() == "---"
        ]

        if len(separator_indices) >= 2:
            text = "\n".join(lines[separator_indices[0] + 1:separator_indices[-1]])

        # Optional Unicode font support
        try:
            font_path = os.path.join(settings.BASE_DIR, "static", "fonts", "DejaVuSans.ttf")
            bold_font_path = os.path.join(settings.BASE_DIR, "static", "fonts", "DejaVuSans-Bold.ttf")

            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))

            if os.path.exists(bold_font_path):
                pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", bold_font_path))

            default_font = "DejaVuSans" if os.path.exists(font_path) else "Helvetica"
        except Exception:
            default_font = "Helvetica"

        doc = SimpleDocTemplate(
            file_path,
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40,
        )

        styles = getSampleStyleSheet()

        normal_style = styles["Normal"]
        normal_style.fontName = default_font
        normal_style.fontSize = 11
        normal_style.leading = 15

        h1_style = styles["Heading1"]
        h1_style.fontName = default_font
        h1_style.fontSize = 18
        h1_style.leading = 22

        h2_style = styles["Heading2"]
        h2_style.fontName = default_font
        h2_style.fontSize = 15
        h2_style.leading = 19

        h3_style = styles["Heading3"]
        h3_style.fontName = default_font
        h3_style.fontSize = 13
        h3_style.leading = 17

        def clean_math_symbols(value: str) -> str:
            """Convert common LaTeX/math symbols into readable Unicode text."""

            # Fractions
            value = re.sub(
                r"\\frac\{([^{}]+)\}\{([^{}]+)\}",
                r"(\1) / (\2)",
                value
            )

            # Square root and nth root
            value = re.sub(r"\\sqrt\{([^{}]+)\}", r"√(\1)", value)
            value = re.sub(r"\\sqrt\[([^]]+)\]\{([^{}]+)\}", r"\1√(\2)", value)

            # Subscripts and powers
            superscripts = {
                "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
                "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
                "+": "⁺", "-": "⁻", "=": "⁼", "n": "ⁿ", "i": "ⁱ",
            }

            subscripts = {
                "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
                "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
                "+": "₊", "-": "₋", "=": "₌", "a": "ₐ", "e": "ₑ",
                "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ",
                "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ",
                "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
            }

            def convert_sup(match):
                raw = match.group(1)
                return "".join(superscripts.get(ch, f"^{ch}") for ch in raw)

            def convert_sub(match):
                raw = match.group(1)
                return "".join(subscripts.get(ch, f"_{ch}") for ch in raw)

            value = re.sub(r"\^\{([^{}]+)\}", convert_sup, value)
            value = re.sub(r"_\{([^{}]+)\}", convert_sub, value)
            value = re.sub(r"\^([0-9+\-=ni])", lambda m: superscripts.get(m.group(1), m.group(0)), value)
            value = re.sub(r"_([0-9aehijklmnoprstuvx+\-=])", lambda m: subscripts.get(m.group(1), m.group(0)), value)

            latex_symbols = {
                # Greek lowercase
                r"\alpha": "α",
                r"\beta": "β",
                r"\gamma": "γ",
                r"\delta": "δ",
                r"\epsilon": "ε",
                r"\varepsilon": "ε",
                r"\zeta": "ζ",
                r"\eta": "η",
                r"\theta": "θ",
                r"\vartheta": "ϑ",
                r"\iota": "ι",
                r"\kappa": "κ",
                r"\lambda": "λ",
                r"\mu": "μ",
                r"\nu": "ν",
                r"\xi": "ξ",
                r"\omicron": "ο",
                r"\pi": "π",
                r"\rho": "ρ",
                r"\sigma": "σ",
                r"\tau": "τ",
                r"\upsilon": "υ",
                r"\phi": "φ",
                r"\varphi": "φ",
                r"\chi": "χ",
                r"\psi": "ψ",
                r"\omega": "ω",

                # Greek uppercase
                r"\Gamma": "Γ",
                r"\Delta": "Δ",
                r"\Theta": "Θ",
                r"\Lambda": "Λ",
                r"\Xi": "Ξ",
                r"\Pi": "Π",
                r"\Sigma": "Σ",
                r"\Upsilon": "Υ",
                r"\Phi": "Φ",
                r"\Psi": "Ψ",
                r"\Omega": "Ω",

                # Operators
                r"\times": "×",
                r"\cdot": "·",
                r"\div": "÷",
                r"\pm": "±",
                r"\mp": "∓",
                r"\ast": "∗",
                r"\star": "⋆",
                r"\circ": "∘",
                r"\bullet": "•",

                # Comparisons
                r"\leq": "≤",
                r"\le": "≤",
                r"\geq": "≥",
                r"\ge": "≥",
                r"\neq": "≠",
                r"\ne": "≠",
                r"\approx": "≈",
                r"\simeq": "≃",
                r"\sim": "∼",
                r"\equiv": "≡",
                r"\propto": "∝",

                # Logic / sets
                r"\in": "∈",
                r"\notin": "∉",
                r"\subset": "⊂",
                r"\subseteq": "⊆",
                r"\supset": "⊃",
                r"\supseteq": "⊇",
                r"\cup": "∪",
                r"\cap": "∩",
                r"\emptyset": "∅",
                r"\varnothing": "∅",
                r"\forall": "∀",
                r"\exists": "∃",
                r"\nexists": "∄",
                r"\land": "∧",
                r"\lor": "∨",
                r"\neg": "¬",
                r"\implies": "⇒",
                r"\Rightarrow": "⇒",
                r"\leftarrow": "←",
                r"\rightarrow": "→",
                r"\leftrightarrow": "↔",

                # Calculus / algebra
                r"\infty": "∞",
                r"\partial": "∂",
                r"\nabla": "∇",
                r"\sum": "∑",
                r"\prod": "∏",
                r"\int": "∫",
                r"\iint": "∬",
                r"\iiint": "∭",
                r"\oint": "∮",
                r"\lim": "lim",
                r"\log": "log",
                r"\ln": "ln",
                r"\sin": "sin",
                r"\cos": "cos",
                r"\tan": "tan",

                # Geometry
                r"\angle": "∠",
                r"\triangle": "△",
                r"\parallel": "∥",
                r"\perp": "⊥",
                r"\degree": "°",
                r"^\circ": "°",

                # Spacing / formatting
                r"\left": "",
                r"\right": "",
                r"\quad": " ",
                r"\qquad": "  ",
                r"\,": " ",
                r"\;": " ",
                r"\:": " ",
            }

            for latex, symbol in latex_symbols.items():
                value = value.replace(latex, symbol)

            # Text blocks
            value = re.sub(r"\\text\{([^{}]+)\}", r"\1", value)
            value = re.sub(r"\\mathrm\{([^{}]+)\}", r"\1", value)
            value = re.sub(r"\\mathbf\{([^{}]+)\}", r"\1", value)

            # Remove math delimiters
            value = value.replace("\\(", "").replace("\\)", "")
            value = value.replace("\\[", "").replace("\\]", "")
            value = value.replace("$", "")

            # Remove leftover braces
            value = value.replace("{", "").replace("}", "")

            return value

        story = []

        for paragraph in text.split("\n"):
            paragraph = paragraph.strip()

            if not paragraph:
                story.append(Spacer(1, 6))
                continue

            # Escape XML-sensitive characters before ReportLab Paragraph parsing
            paragraph = (
                paragraph
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )

            # Markdown bold and italic
            paragraph = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", paragraph)
            paragraph = re.sub(r"__(.*?)__", r"<b>\1</b>", paragraph)
            paragraph = re.sub(r"(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)", r"<i>\1</i>", paragraph)

            # Convert math/LaTeX symbols
            paragraph = clean_math_symbols(paragraph)

            # Headers
            if paragraph.startswith("### "):
                story.append(Paragraph(paragraph[4:], h3_style))

            elif paragraph.startswith("## "):
                story.append(Paragraph(paragraph[3:], h2_style))

            elif paragraph.startswith("# "):
                story.append(Paragraph(paragraph[2:], h1_style))

            # Numbered lists
            elif re.match(r"^\d+\.\s+", paragraph):
                story.append(Paragraph(paragraph, normal_style))

            # Bullet lists
            elif paragraph.startswith("- ") or paragraph.startswith("* "):
                story.append(Paragraph("• " + paragraph[2:], normal_style))

            else:
                story.append(Paragraph(paragraph, normal_style))

            story.append(Spacer(1, 6))

        doc.build(story)

        return relative_path
