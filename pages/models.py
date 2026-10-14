from django.db import models


class ContactMessage(models.Model):
    """A message sent from the Contact page. Also emailed to the team."""
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    location = models.ForeignKey('fleet.Location', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='contact_messages', verbose_name='City')
    message = models.TextField(max_length=3000)
    handled = models.BooleanField(default=False, help_text='Tick once someone has replied')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name}: {self.message[:40]}'
