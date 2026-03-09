from django import forms
from django.core.exceptions import ValidationError
from .models import File
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class FileForm(forms.ModelForm):
    class Meta:
        model = File
        fields = ('title', 'file',)

    def clean_file(self):
        file = self.cleaned_data['file']
        # Validate file extension in a case-insensitive way
        if not file.name.lower().endswith('.mwf'):
            raise ValidationError("Only '.mwf' files are accepted.")
        return file

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        # Support handling multiple files
        files = [super(MultipleFileField, self).clean(d, initial) for d in data] if isinstance(data, list) else [super(MultipleFileField, self).clean(data, initial)]
        for file in files:
            if not file.name.lower().endswith('.mwf'):
                raise ValidationError("Only '.mwf' files are accepted.")
        return files

class FileFieldForm(forms.Form):
    file_field = MultipleFileField(help_text="Upload one or more '.mwf' files.")

class UserRegistrationForm(UserCreationForm):
    name = forms.CharField(max_length=50, help_text='Required. Add your full name.')
    mobile = forms.CharField(max_length=20, help_text='Required. Add a contact number.')
    
    class Meta:
        model = User
        fields = ['username', 'name', 'mobile', 'password1', 'password2']
