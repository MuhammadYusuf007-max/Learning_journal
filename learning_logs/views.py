import os
from dotenv import load_dotenv
from openai import OpenAI

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import Http404

from .models import Topic, Entry
from .forms import TopicForm, EntryForm

# --- AI SETUP START ---
# Load the secret keys from the .env file
load_dotenv()

# Set up the AI client to talk to Groq's free servers
client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

def generate_ai_summary(entry_text):
    """Sends the journal text to the AI and returns a 1-sentence summary."""
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant", # <-- THIS IS THE ONLY LINE WE CHANGED
            messages=[
                {
                    "role": "system", 
                    "content": "You are a helpful assistant. Summarize the following journal entry in exactly one short, concise sentence. Do not include any conversational filler."
                },
                {
                    "role": "user", 
                    "content": entry_text
                }
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI Error: {e}")
        return "AI Summary temporarily unavailable."

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
    topic = Topic.objects.get(id=topic_id)
    # Make sure the topic belongs to the current user.
    if topic.owner != request.user:
        raise Http404
    
    #Get all the entries related to this topic
    entries = topic.entry_set.order_by('-date_added')
    context = {'topic': topic, 'entries': entries}
    return render(request, 'learning_logs/topic.html', context)

@login_required
def new_topic(request):
    """Add a new topic."""
    if request.method != 'POST':
        # No data submitted; create a blank form.
        form = TopicForm()
    else:
        # POST data submitted; process the data.
        form = TopicForm(data=request.POST)
        if form.is_valid():
            new_topic = form.save(commit=False)
            new_topic.owner = request.user
            new_topic.save()
            return redirect('learning_logs:topics')
    
    # Display a blank or invalid form.
    context = {'form': form}
    return render(request, 'learning_logs/new_topic.html', context)

@login_required
def new_entry(request, topic_id):
    """Add a new entry for a particular topic."""
    topic = Topic.objects.get(id=topic_id)

    # Make sure the topic belongs to the current user.
    if topic.owner != request.user:
        raise Http404

    if request.method != 'POST':
        # No data submitted; create a blank form.
        form = EntryForm()
    else:
        # POST data submitted; process the data.
        form = EntryForm(data=request.POST)
        if form.is_valid():
            new_entry = form.save(commit=False)
            new_entry.topic = topic
            
            # --- ✨ AI INTEGRATION START ✨ ---
            # Clean up the CKEditor HTML tags so the AI doesn't get confused
            clean_text = new_entry.text.replace('<p>', '').replace('</p>', '')
            
            # Generate the summary and assign it to the new database field
            new_entry.ai_summary = generate_ai_summary(clean_text)
            # --- ✨ AI INTEGRATION END ✨ ---

            new_entry.save()
            return redirect('learning_logs:topic', topic_id=topic_id)
    
    # Display a blank or invalid form.
    context = {'topic': topic, 'form':form}
    return render(request, 'learning_logs/new_entry.html', context)

@login_required
def edit_entry(request, entry_id):
    """Edit an existing entry."""
    entry = Entry.objects.get(id=entry_id)
    topic = entry.topic
    
    #Make sure the topic belongs to the current user.
    if topic.owner != request.user:
        raise Http404

    if request.method != 'POST':
        # Initial request; pre-fill form with the current entry
        form = EntryForm(instance=entry)
    else:
        # POST data submitted; process data
        form = EntryForm(instance=entry, data=request.POST)
        if form.is_valid():
            edited_entry = form.save(commit=False)
            
            # --- ✨ AI INTEGRATION START ✨ ---
            # Clean up the CKEditor HTML tags
            clean_text = edited_entry.text.replace('<p>', '').replace('</p>', '')
            
            # Generate a new summary based on the edited text
            edited_entry.ai_summary = generate_ai_summary(clean_text)
            # --- ✨ AI INTEGRATION END ✨ ---
            
            edited_entry.save()
            return redirect('learning_logs:topic', topic_id=topic.id)

    context = {'entry':entry, 'topic':topic, 'form':form}
    return render(request, 'learning_logs/edit_entry.html', context)

@login_required
def edit_topic(request, topic_id):
    """Edit an existing topic."""
    topic = Topic.objects.get(id=topic_id)
    
    #Make sure the topic belongs to the current user.
    if topic.owner != request.user:
        raise Http404

    if request.method != 'POST':
        # Initial request; pre-fill form with the current topic
        form = TopicForm(instance=topic)
    else:
        # POST data submitted; process data
        form = TopicForm(instance=topic, data=request.POST)
        if form.is_valid():
            form.save()
            return redirect('learning_logs:topic', topic_id=topic.id)

    context = {'topic':topic, 'form':form}
    return render(request, 'learning_logs/edit_topic.html', context)

@login_required
def delete_topic(request, topic_id):
    """Delete an existing topic."""
    topic = Topic.objects.get(id=topic_id)
    
    #Make sure the topic belongs to the current user.
    if topic.owner != request.user:
        raise Http404

    if request.method == 'POST':
        # Delete the topic and redirect to topics page
        topic.delete()
        return redirect('learning_logs:topics')

    # If GET, show confirmation page
    context = {'topic':topic}
    return render(request, 'learning_logs/delete_topic.html', context)