from django import forms

from .models import Topic, Entry, Flashcard


class TopicForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = ['text']
        labels = {'text': ''}


class EntryForm(forms.ModelForm):
    class Meta:
        model = Entry
        fields = ['text']
        labels = {'text': ''}
        widgets = {'text': forms.Textarea(attrs={'cols': '80', 'rows': '4'})}


class FlashcardForm(forms.ModelForm):
    class Meta:
        model = Flashcard
        fields = ['front', 'back']
        labels = {
            'front': 'Question / prompt',
            'back': 'Answer / explanation',
        }
        widgets = {
            'back': forms.Textarea(attrs={'rows': 3}),
        }