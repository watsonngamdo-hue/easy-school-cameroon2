from django.test import TestCase
from authapp.models import UserRegistration
from allauth.account.models import EmailAddress
from allauth.account.signals import email_confirmed
from django.test.client import RequestFactory

class OnboardingTest(TestCase):
    def test_onboarding_bonus(self):
        # Create a user
        user = UserRegistration.objects.create_user(
            email="test@example.com",
            password="testpassword123",
            first_name="Test",
            last_name="User"
        )
        
        # Verify initial balance
        self.assertEqual(user.somme, 0)
        self.assertEqual(user.wallet_credits, 0)
        self.assertTrue(user.is_first_login)
        
        # Mock email confirmation signal
        email_address = EmailAddress.objects.create(user=user, email=user.email, verified=False)
        request = RequestFactory().get('/')
        
        # Fire signal
        email_confirmed.send(sender=None, request=request, email_address=email_address)
        
        # Reload user
        user.refresh_from_db()
        
        # Verify bonus
        self.assertEqual(user.somme, 1000)
        self.assertEqual(user.wallet_credits, 500)


    def test_bonus_une_seule_fois(self):
        user = UserRegistration.objects.create_user(email="b@example.com", password="testpassword123")
        request = RequestFactory().get('/')
        for i in range(3):
            addr = EmailAddress.objects.create(user=user, email=f"b{i}@example.com", verified=False)
            email_confirmed.send(sender=None, request=request, email_address=addr)
        user.refresh_from_db()
        self.assertEqual(user.somme, 1000)
        self.assertEqual(user.wallet_credits, 500)
