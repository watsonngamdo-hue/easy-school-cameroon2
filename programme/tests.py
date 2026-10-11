from django.test import TestCase
from django.urls import reverse
from authapp.models import UserRegistration
from .models import PaymentIssue
from .tasks import send_admin_deposit_email
from unittest.mock import patch

class DepositEmailTest(TestCase):
    def setUp(self):
        self.admin = UserRegistration.objects.create_superuser(
            email='admin@example.com',
            password='password123'
        )
        self.user = UserRegistration.objects.create_user(
            email='user@example.com',
            password='password123',
            first_name='John',
            last_name='Doe'
        )
        self.client.login(email='user@example.com', password='password123')

    @patch('programme.tasks.send_admin_deposit_email.delay')
    def test_pay_view_triggers_email(self, mock_send_email):
        url = reverse('programme:pay')
        data = {
            'numero': '123456789',
            'description': 'Test Deposit',
            'reference': 'REF123',
            'date': '2026-03-21'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PaymentIssue.objects.filter(reference='REF123').exists())
        mock_send_email.assert_called_once()

    def test_send_admin_deposit_email_task(self):
        issue = PaymentIssue.objects.create(
            numero='123456789',
            description='Test Deposit',
            reference='REF123',
            user=self.user,
            date='2026-03-21'
        )
        with patch('django.core.mail.EmailMultiAlternatives.send') as mock_send:
            result = send_admin_deposit_email(issue.id)
            self.assertIn("Email sent to 1 admins", result)
            mock_send.assert_called_once()
