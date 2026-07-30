from django import forms


class ChatMessageForm(forms.Form):
    message = forms.CharField(
        max_length=4000,
        strip=True,
        widget=forms.Textarea,
    )
    conversation_id = forms.IntegerField(required=False, min_value=1)
