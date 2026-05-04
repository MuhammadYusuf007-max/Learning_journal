from django.db import models
from django.contrib.auth.models import User
from ckeditor.fields import RichTextField

class Topic(models.Model):
    """A topic the user is learning about."""
    text = models.CharField(max_length=200)
    date_added = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        """Return a string representation of the model."""
        return self.text

class Entry(models.Model):
    """Something the user learned about a topic."""
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
    text = RichTextField()  # Upgraded for CKEditor
    ai_summary = models.TextField(blank=True, null=True)  # New field to store the AI's summary
    date_added = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'entries'

    def __str__(self):
        """Return a string representation of the model."""
        # Strip HTML tags just for the string representation preview (optional but helpful)
        preview_text = self.text.replace('<p>', '').replace('</p>', '')
        if len(preview_text) > 50:
            return f"{preview_text[:50]}..."
        else:
            return preview_text