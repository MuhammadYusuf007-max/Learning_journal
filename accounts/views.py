from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count

from learning_logs.models import Topic, Entry

from .forms import CustomUserCreationForm


def register(request):
    """Register a new user."""
    if request.method != 'POST':
        form = CustomUserCreationForm()
    else:
        form = CustomUserCreationForm(data=request.POST)

        if form.is_valid():
            new_user = form.save()
            login(request, new_user)
            return redirect('learning_logs:index')

    context = {'form': form}
    return render(request, 'registration/register.html', context)


@login_required
def profile(request):
    """Show the current user's profile page with usage stats."""
    user = request.user

    topic_count = Topic.objects.filter(owner=user).count()
    entry_count = Entry.objects.filter(topic__owner=user).count()

    top_topics = (
        Topic.objects
        .filter(owner=user)
        .annotate(num_entries=Count('entry'))
        .order_by('-num_entries', '-date_added')[:5]
    )

    context = {
        'topic_count': topic_count,
        'entry_count': entry_count,
        'top_topics': top_topics,
    }
    return render(request, 'registration/profile.html', context)
