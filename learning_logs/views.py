import os
import io
import json
import re
from dotenv import load_dotenv
from openai import OpenAI

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, FileResponse, HttpResponse
from django.template.defaultfilters import striptags
from django.utils import timezone

from .models import Topic, Entry, QuizAttempt, Flashcard
from .forms import TopicForm, EntryForm, FlashcardForm

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


def _call_ai(system_msg, user_msg):
    """Low-level helper that makes one chat completion call."""
    client = _get_ai_client()
    if client is None:
        return "AI features disabled: GROQ_API_KEY is not set."
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI Error: {e}")
        return "Content unavailable at this time."


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

    return _call_ai(system_msg, user_msg)


def generate_ai_quiz_json(notes_text, num_questions=5):
    """
    Ask the AI for a structured multiple-choice quiz in JSON form.
    Returns a list of question dicts, or an empty list on failure.
    """
    MAX_NOTES_CHARS = 12000
    if len(notes_text) > MAX_NOTES_CHARS:
        notes_text = notes_text[:MAX_NOTES_CHARS]

    system_msg = (
        "You are a strict but fair tutor that creates multiple-choice quizzes. "
        "You MUST respond with ONLY a valid JSON array, no prose, no markdown fences. "
        "Each item must have exactly these keys: question (string), options (array of "
        "exactly 4 strings), correct_index (integer 0-3), explanation (short string)."
    )
    user_msg = (
        f"Create exactly {num_questions} multiple-choice questions based ONLY on the "
        f"notes below. Each question must have 4 options. Indicate the correct answer "
        f"by its index (0-3). Add a one-sentence explanation.\n\n"
        f"NOTES:\n{notes_text}\n\n"
        f"Return JSON only."
    )

    raw = _call_ai(system_msg, user_msg)
    if not raw or raw.startswith("AI features disabled"):
        return []

    # Strip optional ```json fences the model may add despite instructions.
    cleaned = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # If the model added prose before/after, try to extract the first JSON array.
    if not cleaned.startswith('['):
        bracket_match = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
        if bracket_match:
            cleaned = bracket_match.group(0)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"Quiz JSON parse error: {e}\nRaw: {raw[:500]}")
        return []

    # Validate shape and keep only well-formed items.
    valid = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        q = item.get('question')
        opts = item.get('options')
        ci = item.get('correct_index')
        expl = item.get('explanation', '')
        if (
            isinstance(q, str) and q.strip()
            and isinstance(opts, list) and len(opts) == 4
            and all(isinstance(o, str) for o in opts)
            and isinstance(ci, int) and 0 <= ci <= 3
        ):
            valid.append({
                'question': q.strip(),
                'options': [o.strip() for o in opts],
                'correct_index': ci,
                'explanation': str(expl).strip(),
            })
    return valid


def generate_ai_flashcards_json(notes_text, num_cards=8):
    """
    Ask the AI for flashcards in JSON form.
    Returns a list of {"front": str, "back": str} dicts, or [] on failure.
    """
    MAX_NOTES_CHARS = 12000
    if len(notes_text) > MAX_NOTES_CHARS:
        notes_text = notes_text[:MAX_NOTES_CHARS]

    system_msg = (
        "You are a study coach that creates concise flashcards. "
        "Respond with ONLY a valid JSON array, no prose, no markdown fences. "
        "Each item must have exactly: front (a short question or prompt, max 200 "
        "chars) and back (a clear answer, max 500 chars)."
    )
    user_msg = (
        f"Create exactly {num_cards} flashcards based ONLY on the notes below. "
        f"Cover the most important concepts. Make 'front' a question or term, "
        f"and 'back' the answer or definition.\n\n"
        f"NOTES:\n{notes_text}\n\n"
        f"Return JSON only."
    )

    raw = _call_ai(system_msg, user_msg)
    if not raw or raw.startswith("AI features disabled"):
        return []

    cleaned = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    if not cleaned.startswith('['):
        bracket_match = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
        if bracket_match:
            cleaned = bracket_match.group(0)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"Flashcard JSON parse error: {e}\nRaw: {raw[:500]}")
        return []

    valid = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        front = item.get('front')
        back = item.get('back')
        if isinstance(front, str) and front.strip() and isinstance(back, str) and back.strip():
            valid.append({
                'front': front.strip()[:300],
                'back': back.strip()[:2000],
            })
    return valid


def generate_ai_qa(context_text, question):
    """
    Answer a user's question using the topic's notes as context (basic RAG).

    For very large topics, the context could exceed the model's context window.
    A future improvement would be to embed entries and retrieve only the most
    relevant ones via cosine similarity (true RAG). For now we stuff all entries.
    """
    # Truncate context to keep us safely under the model's context window.
    MAX_CONTEXT_CHARS = 12000
    if len(context_text) > MAX_CONTEXT_CHARS:
        context_text = context_text[:MAX_CONTEXT_CHARS] + "\n[...notes truncated...]"

    system_msg = (
        "You are a helpful tutor that answers questions strictly using the "
        "student's own notes provided below. If the answer cannot be found in "
        "the notes, say so honestly and briefly suggest what they could study "
        "next. Be concise, accurate, and use bullet points when useful."
    )
    user_msg = (
        f"NOTES:\n{context_text}\n\n"
        f"QUESTION:\n{question}\n\n"
        "Answer using only the notes above."
    )

    return _call_ai(system_msg, user_msg)

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
    """Show a single topic and a paginated list of its entries."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    all_entries = topic.entry_set.order_by('-date_added')

    paginator = Paginator(all_entries, 10)  # 10 entries per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'topic': topic,
        'entries': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
    }
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
            messages.success(request, f'Topic "{new_topic.text}" created.')
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
            clean_text = striptags(new_entry.text)
            new_entry.ai_summary = generate_ai_content(clean_text, mode="summary")
            new_entry.save()
            messages.success(request, 'Entry added.')
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
            messages.success(request, 'Entry updated.')
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
            messages.success(request, 'Topic updated.')
            return redirect('learning_logs:topic', topic_id=topic.id)
    context = {'topic': topic, 'form': form}
    return render(request, 'learning_logs/edit_topic.html', context)

@login_required
def delete_topic(request, topic_id):
    """Delete an existing topic."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    if request.method == 'POST':
        topic_name = topic.text
        topic.delete()
        messages.success(request, f'Topic "{topic_name}" deleted.')
        return redirect('learning_logs:topics')
    return render(request, 'learning_logs/delete_topic.html', {'topic': topic})

@login_required
def topic_flashcards(request, topic_id):
    """List a topic's flashcards with management actions."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    cards = topic.flashcards.all()
    return render(request, 'learning_logs/flashcards_list.html', {
        'topic': topic,
        'cards': cards,
    })


@login_required
def generate_flashcards(request, topic_id):
    """POST endpoint that uses the AI to generate flashcards for the topic."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)

    if request.method != 'POST':
        return redirect('learning_logs:topic_flashcards', topic_id=topic.id)

    entries = topic.entry_set.all()
    if not entries.exists():
        messages.warning(request, 'Add at least one entry before generating flashcards.')
        return redirect('learning_logs:topic_flashcards', topic_id=topic.id)

    raw_text = " ".join(striptags(e.text) for e in entries)
    cards_data = generate_ai_flashcards_json(raw_text, num_cards=8)

    if not cards_data:
        messages.error(request, "Couldn't generate flashcards right now. Please try again in a moment.")
        return redirect('learning_logs:topic_flashcards', topic_id=topic.id)

    Flashcard.objects.bulk_create([
        Flashcard(topic=topic, front=c['front'], back=c['back'])
        for c in cards_data
    ])
    messages.success(request, f'Generated {len(cards_data)} flashcards.')
    return redirect('learning_logs:topic_flashcards', topic_id=topic.id)


@login_required
def new_flashcard(request, topic_id):
    """Manually add a single flashcard."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)

    if request.method != 'POST':
        form = FlashcardForm()
    else:
        form = FlashcardForm(data=request.POST)
        if form.is_valid():
            card = form.save(commit=False)
            card.topic = topic
            card.save()
            messages.success(request, 'Flashcard added.')
            return redirect('learning_logs:topic_flashcards', topic_id=topic.id)

    return render(request, 'learning_logs/new_flashcard.html', {
        'topic': topic,
        'form': form,
    })


@login_required
def delete_flashcard(request, card_id):
    """Delete a single flashcard (must be owned by current user)."""
    card = get_object_or_404(Flashcard, id=card_id, topic__owner=request.user)
    topic_id = card.topic.id
    if request.method == 'POST':
        card.delete()
        messages.success(request, 'Flashcard deleted.')
    return redirect('learning_logs:topic_flashcards', topic_id=topic_id)


@login_required
def review_flashcards(request, topic_id):
    """One-card-at-a-time review session. Tracks 'got it' / 'study again'."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    cards = list(topic.flashcards.all())

    if not cards:
        messages.warning(request, 'Add or generate some flashcards first.')
        return redirect('learning_logs:topic_flashcards', topic_id=topic.id)

    session_key = f'flashcard_session_{topic_id}'

    if request.method == 'POST':
        action = request.POST.get('action')
        card_id = request.POST.get('card_id')
        if card_id and action in ('correct', 'incorrect'):
            try:
                card = Flashcard.objects.get(id=int(card_id), topic=topic)
                card.times_seen += 1
                if action == 'correct':
                    card.times_correct += 1
                card.save()
            except (Flashcard.DoesNotExist, ValueError):
                pass

        # Advance the index in the session.
        idx = request.session.get(session_key, 0) + 1
        request.session[session_key] = idx

        if idx >= len(cards):
            request.session[session_key] = 0
            return redirect('learning_logs:topic_flashcards', topic_id=topic.id)
        return redirect('learning_logs:review_flashcards', topic_id=topic.id)

    idx = request.session.get(session_key, 0)
    if idx >= len(cards):
        idx = 0
        request.session[session_key] = 0

    return render(request, 'learning_logs/review_flashcards.html', {
        'topic': topic,
        'card': cards[idx],
        'index': idx + 1,
        'total': len(cards),
    })


@login_required
def topic_qa(request, topic_id):
    """Chat-style Q&A: ask a question, AI answers using only the topic's notes."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    entries = topic.entry_set.all().order_by('date_added')

    session_key = f'topic_qa_history_{topic_id}'
    history = request.session.get(session_key, [])

    if request.method == 'POST':
        action = request.POST.get('action', 'ask')

        if action == 'clear':
            request.session[session_key] = []
            messages.success(request, 'Conversation cleared.')
            return redirect('learning_logs:topic_qa', topic_id=topic.id)

        question = request.POST.get('question', '').strip()
        if not question:
            messages.warning(request, 'Please enter a question.')
            return redirect('learning_logs:topic_qa', topic_id=topic.id)

        if not entries.exists():
            messages.warning(
                request,
                'This topic has no entries yet. Add some notes before asking questions.',
            )
            return redirect('learning_logs:topic', topic_id=topic.id)

        context_text = "\n\n".join(
            f"[Entry {i+1}, {e.date_added:%Y-%m-%d}]\n{striptags(e.text)}"
            for i, e in enumerate(entries)
        )
        answer = generate_ai_qa(context_text, question)

        history.append({'q': question, 'a': answer})
        # Keep only the last 20 exchanges to bound session size.
        request.session[session_key] = history[-20:]
        return redirect('learning_logs:topic_qa', topic_id=topic.id)

    return render(request, 'learning_logs/topic_qa.html', {
        'topic': topic,
        'history': history,
        'has_entries': entries.exists(),
        'entry_count': entries.count(),
    })


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
    """Start a new quiz attempt: generate questions, save, then redirect to take it."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    entries = topic.entry_set.all()

    if not entries.exists():
        messages.warning(request, 'Add at least one entry before taking a quiz.')
        return redirect('learning_logs:topic', topic_id=topic.id)

    raw_text = " ".join(striptags(e.text) for e in entries)
    questions = generate_ai_quiz_json(raw_text, num_questions=5)

    if not questions:
        messages.error(request, "Couldn't generate a quiz right now. Please try again in a moment.")
        return redirect('learning_logs:topic', topic_id=topic.id)

    attempt = QuizAttempt.objects.create(
        user=request.user,
        topic=topic,
        questions_data=questions,
        total=len(questions),
    )
    return redirect('learning_logs:take_quiz', attempt_id=attempt.id)


@login_required
def take_quiz(request, attempt_id):
    """Display the quiz form and grade it on submit."""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)

    if attempt.completed:
        return redirect('learning_logs:quiz_result', attempt_id=attempt.id)

    if request.method == 'POST':
        answers = []
        score = 0
        for i, q in enumerate(attempt.questions_data):
            raw = request.POST.get(f'q_{i}')
            try:
                picked = int(raw) if raw is not None else None
            except (TypeError, ValueError):
                picked = None
            answers.append(picked)
            if picked == q.get('correct_index'):
                score += 1

        attempt.answers_data = answers
        attempt.score = score
        attempt.completed = True
        attempt.completed_at = timezone.now()
        attempt.save()
        messages.success(request, f'You scored {score} / {attempt.total} ({attempt.percentage}%).')
        return redirect('learning_logs:quiz_result', attempt_id=attempt.id)

    return render(request, 'learning_logs/take_quiz.html', {
        'attempt': attempt,
        'topic': attempt.topic,
    })


@login_required
def quiz_result(request, attempt_id):
    """Show the graded results for a completed quiz attempt."""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)

    if not attempt.completed:
        return redirect('learning_logs:take_quiz', attempt_id=attempt.id)

    # Build a list of {question, options, correct_index, picked, explanation, is_correct}
    review = []
    for i, q in enumerate(attempt.questions_data):
        picked = attempt.answers_data[i] if i < len(attempt.answers_data) else None
        review.append({
            'index': i,
            'question': q.get('question', ''),
            'options': q.get('options', []),
            'correct_index': q.get('correct_index'),
            'picked': picked,
            'explanation': q.get('explanation', ''),
            'is_correct': picked == q.get('correct_index'),
        })

    return render(request, 'learning_logs/quiz_result.html', {
        'attempt': attempt,
        'topic': attempt.topic,
        'review': review,
    })


@login_required
def quiz_history(request, topic_id):
    """List the user's past quiz attempts on a topic."""
    topic = get_object_or_404(Topic, id=topic_id, owner=request.user)
    attempts = QuizAttempt.objects.filter(user=request.user, topic=topic, completed=True)

    best = max((a.percentage for a in attempts), default=0)
    avg = round(sum(a.percentage for a in attempts) / len(attempts), 1) if attempts else 0

    return render(request, 'learning_logs/quiz_history.html', {
        'topic': topic,
        'attempts': attempts,
        'best': best,
        'avg': avg,
    })