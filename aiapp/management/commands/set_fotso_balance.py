from django.core.management.base import BaseCommand
from authapp.models import UserRegistration

class Command(BaseCommand):
    help = 'Sets the balance (somme) of users with "fotso" in their email to 10000'

    def handle(self, *args, **options):
        keyword = 'fotso'
        target_balance = 10000
        
        users = UserRegistration.objects.filter(email__icontains=keyword)
        count = users.count()
        
        if count == 0:
            self.stdout.write(self.style.WARNING(f'No users found with "{keyword}" in their email.'))
            return

        updated_count = users.update(somme=target_balance)
        
        self.stdout.write(self.style.SUCCESS(f'Successfully updated {updated_count} user(s). Their balance (somme) is now set to {target_balance}.'))
