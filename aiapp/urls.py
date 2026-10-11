from django.urls import path
from .views import AIAssistantView, BuyCreditsView, CreatePDFView

app_name = 'aiapp'

urlpatterns = [
    path('', AIAssistantView.as_view(), name='index'),
    path('buy/', BuyCreditsView.as_view(), name='buy_credits'),
    path('create-pdf/', CreatePDFView.as_view(), name='create_pdf'),
]
