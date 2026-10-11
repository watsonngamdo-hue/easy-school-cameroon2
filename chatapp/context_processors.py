from chatapp.models import ForumPrivate

def unread_messages_count(request):
    if request.user.is_authenticated:
        # Count messages where the user is a recipient but hasn't read it yet
        count = ForumPrivate.objects.filter(
            to_message=request.user,
            deleted=False
        ).exclude(read_by=request.user).distinct().count()
        return {'unread_count': count}
    return {'unread_count': 0}
