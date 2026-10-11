from django.core.management.base import BaseCommand, CommandError
from authapp.models import UserRegistration
from django.db import transaction

class Command(BaseCommand):
    help = 'Credits a user\'s wallet with a specific amount'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='Email of the user to credit (or "all" for all users)')
        parser.add_argument('amount', type=int, help='Amount to credit in FCFA')

    def handle(self, *args, **options):
        email = options['email']
        amount = options['amount']

        if email.lower() == 'all':
            with transaction.atomic():
                users = UserRegistration.objects.all()
                count = users.count()
                for user in users:
                    user.somme += amount
                    user.save()
                self.stdout.write(self.style.SUCCESS(f'Successfully credited {amount} FCFA to all {count} users.'))
            return

        try:
            with transaction.atomic():
                user = UserRegistration.objects.get(email=email)
                user.somme += amount
                user.save()
                self.stdout.write(self.style.SUCCESS(f'Successfully credited {amount} FCFA to {email}. New balance: {user.somme} FCFA'))
        except UserRegistration.DoesNotExist:
            raise CommandError(f'User with email "{email}" does not exist')
        except Exception as e:
            raise CommandError(f'An error occurred: {str(e)}')
