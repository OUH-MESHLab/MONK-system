from django import forms
from django.core.exceptions import ValidationError
from .models import File, UserProfile
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
    name = forms.CharField(
        max_length=50,
        help_text='Required. Add your full name.',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full name'}),
    )
    email = forms.EmailField(
        required=False,
        help_text='Optional. Add a contact email.',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
    )

    class Meta:
        model = User
        fields = ['username', 'name', 'email', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Choose a username'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Enter password'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Confirm password'})


class EditProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['name', 'email']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
        }
