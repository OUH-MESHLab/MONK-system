import os
import tempfile
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from base.models import UserProfile, File, Subject, Project, FileImport
from django.http import HttpResponseForbidden, HttpResponse

class TestViews(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password123')
        self.user_profile, _ = UserProfile.objects.update_or_create(
            user=self.user, defaults={"name": "Test User", "mobile": "123456789"}
        )
        
        # Create a temporary file that simulates a .mwf file
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".mwf", delete=False)
        self.temp_file.write(b'Test content')
        self.temp_file.seek(0)
        
        self.file = File.objects.create(
            title='Test File',
            file=SimpleUploadedFile(
                name='test.mwf',
                content=self.temp_file.read(),
                content_type='application/octet-stream'
            )
        )
        self.subject = Subject.objects.create(subject_id='S001', name='Test Subject', gender='Male', file=self.file)
        self.project = Project.objects.create(rekNummer='R001', description='Test Project')
        self.project.users.add(self.user_profile)
        self.file_import = FileImport.objects.create(user=self.user_profile, file=self.file)

    def tearDown(self):
        self.temp_file.close()  # Clean up
        os.unlink(self.temp_file.name)  # Ensure temporary file is deleted

    def test_home_page_logged_in(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'base/home.html')

    def test_user_login_page(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'base/login_register.html')

    def test_user_login_post(self):
        response = self.client.post(reverse('login'), {'username': 'testuser', 'password': 'password123'})
        self.assertEqual(response.status_code, 302)  # Redirects after login

    def test_logout(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 302)  # Redirects after logout

    def test_register_page(self):
        response = self.client.get(reverse('register'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'base/login_register.html')

    def test_register_post(self):
        post_data = {
            'username': 'newuser',
            'name': 'New User',
            'mobile': 1234567890,
            'password1': 'testpassword123',
            'password2': 'testpassword123'
        }
        response = self.client.post(reverse('register'), post_data)
        self.assertEqual(response.status_code, 302)  # Check for redirect after successful registration
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_view_subjects_auth(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('view_subjects'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'base/view_subjects.html')

    def test_import_file_post(self):
        self.client.login(username='testuser', password='password123')
        with tempfile.NamedTemporaryFile(suffix=".mwf", delete=False) as tmp_file:
            tmp_file.write(b'This is a test MWF content')
            tmp_file.seek(0)
            post_data = {
                'file': SimpleUploadedFile(name='test.MWF', content=tmp_file.read(), content_type='application/octet-stream'),
                'title': 'Uploaded Test File',
                'submitted': 'true'
            }
            response = self.client.post(reverse('import_file'), data=post_data)
            self.assertEqual(response.status_code, 302)  

    def test_view_projects_auth(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('view_projects'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'base/view_projects.html')

    def test_file_access_permission(self):
        self.client.login(username='testuser', password='password123')
        # Creating a file object explicitly for this test to ensure isolated testing
        private_file = File.objects.create(
            title="Private File",
            file=self.file.file
        )
        response = self.client.get(reverse('file', args=[private_file.id]))
        self.assertIsInstance(response, HttpResponseForbidden)

    def test_download_mwf(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('download_mwf', args=[self.file.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'], 'application/octet-stream')
        self.assertIn('attachment; filename="', response['Content-Disposition'])

    def test_import_multiple_files(self):
        self.client.login(username='testuser', password='password123')
        with tempfile.NamedTemporaryFile(suffix=".mwf", delete=False) as tmp1, \
             tempfile.NamedTemporaryFile(suffix=".mwf", delete=False) as tmp2:
            tmp1.write(b'Test content for file 1')
            tmp2.write(b'Test content for file 2')
            tmp1.seek(0)
            tmp2.seek(0)
            files = {
                'file_field': [
                    SimpleUploadedFile(name='test1.mwf', content=tmp1.read(), content_type='application/octet-stream'),
                    SimpleUploadedFile(name='test2.mwf', content=tmp2.read(), content_type='application/octet-stream')
                ]
            }
            response = self.client.post(reverse('import_multiple_files'), {'file_field': files}, follow=True)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(File.objects.filter(title__contains='test').count(), 2)
