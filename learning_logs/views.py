import os
import io
from dotenv import load_dotenv
from openai import OpenAI

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404, FileResponse, HttpResponse
from django.template.defaultfilters import striptags

from .models import Topic, Entry
from .forms import TopicForm, EntryForm

# Libraries for file export
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from docx import Document

# --- AI SETUP ---
load_dotenv()

_ai_client = None


def _get_ai_client():
    """Lazily build the AI client so the app can boot without an API key."""
    global _ai_client
    if _ai_client is not None:
        return _ai_client

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None

    _ai_client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )
    return _ai_client


def generate_ai_content(text, mode="summary"):
    """
    Refined AI helper to handle different tasks.
    Modes: 'summary', 'master', 'quiz'
    """
    if mode == "quiz":
        system_msg = "You are a demanding university professor."
        user_msg = f"Based on the following notes, generate 5 challenging multiple-choice or open-ended study questions. Do not provide answers, just the questions. Notes: {text}"
    elif mode == "master":
        system_msg = "You are a helpful academic assistant."
        user_msg = f"Provide a cohesive 3-paragraph summary of this learning progress: {text}"
    else:
        system_msg = "You are a helpful assistant."
        user_msg = f"Summarize this in one short sentence: {text}"

    client = _get_ai_client()
    if client is None:
        return "AI features disabled: GROQ_API_KEY is not set."

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI Error: {e}")
        return "Content unavailable at this time."

# --- VIEWS ---

def index(request):
    """The home page for Learning Log"""
    return render(request, 'learning_logs/index.html')

@login_required
def topics(request):
    """Show all topics"""
    topics = Topic.objects.filter(owner=request.user).order_by('date_added')
    context = {'topics': topics}
    return render(request, 'learning_logs/topics.html', context)

@login_required
def topic(request, topic_id):
    """Show a single topic and all its entries."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    entries = topic.entry_set.order_by('-date_added')
    context = {'topic': topic, 'entries': entries}
    return render(request, 'learning_logs/topic.html', context)

@login_required
def topic_summary(request, topic_id):
    """Generates a master summary and handles PDF/Docx exports."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    entries = topic.entry_set.all().order_by('date_added')
    
    # Combine entries for the AI
    raw_text = " ".join([striptags(e.text) for e in entries])
    summary_text = generate_ai_content(raw_text, mode="master")

    export_format = request.GET.get('export')

    # Handle Word Export
    if export_format == 'docx':
        doc = Document()
        doc.add_heading(f'Learning Summary: {topic.text}', 0)
        doc.add_paragraph(summary_text)
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename=f'{topic.text}_summary.docx')

    # Handle PDF Export
    elif export_format == 'pdf':
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        p.setFont("Helvetica-Bold", 16)
        p.drawString(72, height - 72, f"Learning Summary: {topic.text}")
        
        p.setFont("Helvetica", 12)
        text_object = p.beginText(72, height - 100)
        
        # Wrapping text so it doesn't go off the page
        lines = simpleSplit(summary_text, "Helvetica", 12, width - 144)
        for line in lines:
            if text_object.getY() < 72: # Create new page if full
                p.drawText(text_object)
                p.showPage()
                p.setFont("Helvetica", 12)
                text_object = p.beginText(72, height - 72)
            text_object.textLine(line)
            
        p.drawText(text_object)
        p.showPage()
        p.save()
        buffer.seek(0)
        return FileResponse(buffer, as_attachment=True, filename=f'{topic.text}_summary.pdf')

    return render(request, 'learning_logs/topic_summary.html', {
        'topic': topic,
        'summary': summary_text
    })

@login_required
def new_topic(request):
    """Add a new topic."""
    if request.method != 'POST':
        form = TopicForm()
    else:
        form = TopicForm(data=request.POST)
        if form.is_valid():
            new_topic = form.save(commit=False)
            new_topic.owner = request.user
            new_topic.save()
            return redirect('learning_logs:topics')
    context = {'form': form}
    return render(request, 'learning_logs/new_topic.html', context)

@login_required
def new_entry(request, topic_id):
    """Add a new entry for a topic."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    if request.method != 'POST':
        form = EntryForm()
    else:
        form = EntryForm(data=request.POST)
        if form.is_valid():
            new_entry = form.save(commit=False)
            new_entry.topic = topic
            # Clean text and summarize
            clean_text = striptags(new_entry.text)
            new_entry.ai_summary = generate_ai_content(clean_text, mode="summary")
            new_entry.save()
            return redirect('learning_logs:topic', topic_id=topic_id)
    context = {'topic': topic, 'form': form}
    return render(request, 'learning_logs/new_entry.html', context)

@login_required
def edit_entry(request, entry_id):
    """Edit an existing entry."""
    entry = get_object_or_404(Entry, id=entry_id)
    topic = entry.topic
    if topic.owner != request.user:
        raise Http404

    if request.method != 'POST':
        form = EntryForm(instance=entry)
    else:
        form = EntryForm(instance=entry, data=request.POST)
        if form.is_valid():
            edited_entry = form.save(commit=False)
            clean_text = striptags(edited_entry.text)
            edited_entry.ai_summary = generate_ai_content(clean_text, mode="summary")
            edited_entry.save()
            return redirect('learning_logs:topic', topic_id=topic.id)
    context = {'entry': entry, 'topic': topic, 'form': form}
    return render(request, 'learning_logs/edit_entry.html', context)

@login_required
def edit_topic(request, topic_id):
    """Edit an existing topic."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    if request.method != 'POST':
        form = TopicForm(instance=topic)
    else:
        form = TopicForm(instance=topic, data=request.POST)
        if form.is_valid():
            form.save()
            return redirect('learning_logs:topic', topic_id=topic.id)
    context = {'topic': topic, 'form': form}
    return render(request, 'learning_logs/edit_topic.html', context)

@login_required
def delete_topic(request, topic_id):
    """Delete an existing topic."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    if request.method == 'POST':
        topic.delete()
        return redirect('learning_logs:topics')
    return render(request, 'learning_logs/delete_topic.html', {'topic': topic})

@login_required
def search(request):
    """Search the current user's topics and entries."""
    query = request.GET.get('q', '').strip()

    topic_results = []
    entry_results = []

    if query:
        topic_results = (
            Topic.objects
            .filter(owner=request.user, text__icontains=query)
            .order_by('-date_added')
        )
        entry_results = (
            Entry.objects
            .filter(topic__owner=request.user, text__icontains=query)
            .select_related('topic')
            .order_by('-date_added')
        )

    context = {
        'query': query,
        'topic_results': topic_results,
        'entry_results': entry_results,
        'total': len(topic_results) + len(entry_results),
    }
    return render(request, 'learning_logs/search_results.html', context)


@login_required
def topic_quiz(request, topic_id):
    """Generates ONLY a quiz based on the topic entries."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    entries = topic.entry_set.all()
    
    # Combine entries and strip HTML
    raw_text = " ".join([striptags(e.text) for e in entries])
    
    # Call the AI specifically for a Quiz
    quiz_questions = generate_ai_content(raw_text, mode="quiz")

    return render(request, 'learning_logs/topic_quiz.html', {
        'topic': topic,
        'quiz': quiz_questions
    })