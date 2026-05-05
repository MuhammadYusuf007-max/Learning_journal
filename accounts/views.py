import json
from datetime import timedelta

from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from learning_logs.models import Topic, Entry, QuizAttempt, AIUsage

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

    # AI usage stats
    user_usage = AIUsage.objects.filter(user=user)
    usage_totals = user_usage.aggregate(calls=Count('id'), tokens=Sum('total_tokens'))
    ai_calls = usage_totals['calls'] or 0
    ai_tokens = usage_totals['tokens'] or 0
    by_feature = list(
        user_usage.values('feature')
        .annotate(calls=Count('id'), tokens=Sum('total_tokens'))
        .order_by('-tokens')
    )

    # Daily series for the last 30 days for the chart.
    today = timezone.now().date()
    start = today - timedelta(days=29)
    daily_qs = (
        user_usage.filter(created_at__date__gte=start)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(calls=Count('id'))
        .order_by('day')
    )
    daily_lookup = {row['day']: row['calls'] for row in daily_qs}
    chart_labels = []
    chart_values = []
    for i in range(30):
        d = start + timedelta(days=i)
        chart_labels.append(d.strftime('%b %d'))
        chart_values.append(daily_lookup.get(d, 0))

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
        'ai_calls': ai_calls,
        'ai_tokens': ai_tokens,
        'ai_by_feature': by_feature,
        'ai_chart_labels': json.dumps(chart_labels),
        'ai_chart_values': json.dumps(chart_values),
    }
    return render(request, 'registration/profile.html', context)
