from django.contrib import admin

from .models import Topic, Entry, QuizAttempt, Flashcard, Tag, AIUsage

admin.site.register(Topic)
admin.site.register(Entry)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'date_added')
    list_filter = ('owner',)
    search_fields = ('name',)


@admin.register(AIUsage)
class AIUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'feature', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'created_at')
    list_filter = ('feature', 'user')
    date_hierarchy = 'created_at'
    readonly_fields = ('user', 'feature', 'prompt_tokens', 'completion_tokens', 'total_tokens', 'created_at')


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'topic', 'score', 'total', 'percentage', 'completed', 'started_at')
    list_filter = ('completed', 'topic')
    search_fields = ('user__username', 'topic__text')
    readonly_fields = ('questions_data', 'answers_data', 'started_at', 'completed_at')


@admin.register(Flashcard)
class FlashcardAdmin(admin.ModelAdmin):
    list_display = ('front', 'topic', 'times_seen', 'times_correct', 'accuracy', 'date_added')
    list_filter = ('topic',)
    search_fields = ('front', 'back', 'topic__text')
