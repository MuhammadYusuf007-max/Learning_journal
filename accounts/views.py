from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum

from learning_logs.models import Topic, Entry, QuizAttempt

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

    # Quiz stats
    completed_attempts = QuizAttempt.objects.filter(user=user, completed=True)
    quiz_count = completed_attempts.count()

    # Compute percentages in Python because percentage isn't a DB column.
    if quiz_count:
        percentages = [a.percentage for a in completed_attempts]
        quiz_best = max(percentages)
        quiz_avg = round(sum(percentages) / quiz_count, 1)
        totals = completed_attempts.aggregate(points=Sum('score'), questions=Sum('total'))
        quiz_points = totals['points'] or 0
        quiz_total_questions = totals['questions'] or 0
    else:
        quiz_best = 0
        quiz_avg = 0
        quiz_points = 0
        quiz_total_questions = 0

    recent_attempts = completed_attempts.select_related('topic').order_by('-completed_at')[:5]

    context = {
        'topic_count': topic_count,
        'entry_count': entry_count,
        'top_topics': top_topics,
        'quiz_count': quiz_count,
        'quiz_best': quiz_best,
        'quiz_avg': quiz_avg,
        'quiz_points': quiz_points,
        'quiz_total_questions': quiz_total_questions,
        'recent_attempts': recent_attempts,
    }
    return render(request, 'registration/profile.html', context)
