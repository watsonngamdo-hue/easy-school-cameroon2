from django.core.management.base import BaseCommand
from aiapp.models import AIModel

class Command(BaseCommand):
    help = 'Populates initial AI models'

    def handle(self, *args, **kwargs):
        models_data = [
            # Image Models
            {
                'name': 'Nano Banana (Gemini 2.5 Flash)',
                'api_value': 'nano_banana',
                'model_type': 'image',
                'provider': 'gemini',
                'cost': 25,
                'is_active': True
            },
            {
                'name': 'Nano Banana Pro (Gemini 3 Pro)',
                'api_value': 'nano_banana_pro',
                'model_type': 'image',
                'provider': 'gemini',
                'cost': 40,
                'is_active': True
            },
            {
                'name': 'Imagen 4 Fast',
                'api_value': 'imagen4_fast',
                'model_type': 'image',
                'provider': 'gemini', 
                'cost': 40,
                'is_active': True
            },
            {
                'name': 'Imagen 4 Ultra',
                'api_value': 'imagen4_ultra',
                'model_type': 'image',
                'provider': 'gemini',
                'cost': 80,
                'is_active': True
            },
             {
                'name': 'DALL-E 3',
                'api_value': 'dall-e-3',
                'model_type': 'image',
                'provider': 'openai',
                'cost': 100,
                'is_active': True
            },
            # Chat Models
            {
                'name': 'DeepSeek V3',
                'api_value': 'deepseek-chat',
                'model_type': 'chat',
                'provider': 'deepseek',
                'cost': 5,
                'is_active': True
            },
            {
                'name': 'GPT-4o',
                'api_value': 'gpt-4o',
                'model_type': 'chat',
                'provider': 'openai',
                'cost': 15,
                'is_active': True
            },
            {
                'name': 'GPT-4o Mini',
                'api_value': 'gpt-4o-mini',
                'model_type': 'chat',
                'provider': 'openai',
                'cost': 5,
                'is_active': True
            },
             {
                'name': 'Gemini 1.5 Flash',
                'api_value': 'gemini-flash-latest',
                'model_type': 'chat',
                'provider': 'gemini',
                'cost': 5,
                'is_active': True
            },
            {
                'name': 'Gemini 1.5 Pro',
                'api_value': 'gemini-pro-latest',
                'model_type': 'chat',
                'provider': 'gemini',
                'cost': 15,
                'is_active': True
            },
        ]

        for data in models_data:
            model, created = AIModel.objects.update_or_create(
                api_value=data['api_value'],
                defaults=data
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created model: {model.name}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Updated model: {model.name}'))
