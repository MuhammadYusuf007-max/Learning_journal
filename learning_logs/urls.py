"""Define URL patterns for learning_logs."""

from django.urls import path
from . import views

app_name = 'learning_logs'

urlpatterns = [
    # Home page
    path('', views.index, name='index'),
        
    # Page that shows all topics
    path('topics/', views.topics, name='topics'),
    
    # Detail page for a single topic
    path('topics/<int:topic_id>/', views.topic, name='topic'),
    
    # Page for adding a new topic
    path('new_topic/', views.new_topic, name='new_topic'),
    
    # Page for adding a new entry
    path('new_entry/<int:topic_id>/', views.new_entry, name='new_entry'),
    
    # Page for editing an entry
    path('edit_entry/<int:entry_id>/', views.edit_entry, name='edit_entry'),
    
    # Page for editing a topic
    path('edit_topic/<int:topic_id>/', views.edit_topic, name='edit_topic'),
    
    # Page for deleting a topic
    path('delete_topic/<int:topic_id>/', views.delete_topic, name='delete_topic'),

    # --- NEW: AI Topic Summary & Export ---
    # This path handles the web view AND the PDF/DOCX downloads via query parameters
    path('summary/<int:topic_id>/', views.topic_summary, name='topic_summary'),

    # Start a new quiz attempt for a topic (creates a QuizAttempt and redirects).
    path('quiz/<int:topic_id>/', views.topic_quiz, name='topic_quiz'),
    # Take an in-progress quiz attempt (GET shows form, POST grades it).
    path('quiz/attempt/<int:attempt_id>/', views.take_quiz, name='take_quiz'),
    # See graded results for a completed attempt.
    path('quiz/result/<int:attempt_id>/', views.quiz_result, name='quiz_result'),
    # See past attempts on a topic.
    path('quiz/history/<int:topic_id>/', views.quiz_history, name='quiz_history'),

    # AI Q&A chat for a topic (basic RAG over user's own notes)
    path('qa/<int:topic_id>/', views.topic_qa, name='topic_qa'),

    # Search across the user's topics and entries
    path('search/', views.search, name='search'),
]