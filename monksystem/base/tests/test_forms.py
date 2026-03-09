from django.test import TestCase
from base.forms import FileForm, UserRegistrationForm, FileFieldForm
from django.core.files.uploadedfile import SimpleUploadedFile

class TestForms(TestCase):

    def test_file_form_valid_data(self):
        file = SimpleUploadedFile(name='test_file.mwf', content=b'Some file content', content_type='application/octet-stream')
        form = FileForm(data={'title': 'Test File'}, files={'file': file})
        self.assertTrue(form.is_valid())

    def test_file_form_no_data(self):
        form = FileForm(data={})
        self.assertFalse(form.is_valid())
        self.assertEqual(len(form.errors), 2)  # Expecting errors for 'title' and 'file'

    def test_user_registration_form_valid_data(self):
        form = UserRegistrationForm(data={
            'username': 'testuser',
            'name': 'Test User',
            'mobile': 1234567890,
            'password1': 'verysecurepassword123',
            'password2': 'verysecurepassword123'
        })
        self.assertTrue(form.is_valid())

    def test_user_registration_form_invalid_data(self):
        form = UserRegistrationForm(data={
            'username': 'testuser',
            'name': 'Test User',
            'mobile': '',  # Required field left empty
            'password1': 'verysecurepassword123',
            'password2': 'verysecurepassword123'
        })
        self.assertFalse(form.is_valid())
        self.assertIn('mobile', form.errors)

    def test_user_registration_form_no_data(self):
        form = UserRegistrationForm(data={})
        self.assertFalse(form.is_valid())
        self.assertEqual(len(form.errors), 5)  # Expecting errors for 'username', 'name', 'mobile', 'password1', 'password2'

    def test_multiple_file_input_multiple_files(self):
        file1 = SimpleUploadedFile(name='test1.mwf', content=b'Some MWF content', content_type='application/octet-stream')
        file2 = SimpleUploadedFile(name='test2.mwf', content=b'Another MWF content', content_type='application/octet-stream')
        form = FileFieldForm(data={}, files={'file_field': [file1, file2]})
        self.assertTrue(form.is_valid(), "Should be valid with multiple files")
        self.assertEqual(len(form.cleaned_data['file_field']), 2, "Should contain two files")

