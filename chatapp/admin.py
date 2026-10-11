from django.contrib import admin

# Register your models here.
from .models import Forum, ForumPrivate

class AdminForum(admin.ModelAdmin):
    list_display = ('user', 'matiere', 'niveau', 'created_at', 'deleted')
    search_fields = ('matiere',) 


class AdminForumPrivate(admin.ModelAdmin):
    list_display = ('created_at', 'deleted')
    search_fields = ('from_message',) 


admin.site.register(Forum, AdminForum)
admin.site.register(ForumPrivate, AdminForumPrivate)