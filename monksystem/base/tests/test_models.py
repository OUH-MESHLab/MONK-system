from django.test import TestCase
from django.contrib.auth.models import User
from base.models import UserProfile, File, Subject, Project, FileImport
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
import datetime

class TestModels(TestCase):

    def setUp(self):
        # User object
        self.user = User.objects.create_user(username='testuser', password='12345')

        # UserProfile object (signal may have already created it)
        self.user_profile, _ = UserProfile.objects.update_or_create(
            user=self.user,
            defaults={"name": "Test User", "mobile": "123456789"},
        )

        # File object with custom save method to set the title
        self.file = File.objects.create(
            file=SimpleUploadedFile(name='test_file.mwf', content=b'Some MWF content', content_type='application/octet-stream')
        )

        # Subject object
        self.subject = Subject.objects.create(
            subject_id='S001',
            name='Test Subject',
            gender='Male',
            birth_date=timezone.now().date() - datetime.timedelta(days=365*20),
            file=self.file
        )

        # Project object
        self.project = Project.objects.create(rekNummer='R001', description='Test Project Description')
        self.project.users.add(self.user_profile)
        self.project.subjects.add(self.subject)

        # FileImport object
        self.file_import = FileImport.objects.create(
            user=self.user_profile,
            file=self.file
        )
    
    def test_user_profile_creation_and_str(self):
        self.assertEqual(str(self.user_profile), 'Test User')

    def test_file_creation_and_str(self):
        # Verifies custom save method
        self.assertTrue(self.file.file.name.endswith('.mwf'))  
        self.assertEqual(self.file.title, 'test_file')  
        self.assertEqual(str(self.file), 'test_file')

    def test_subject_creation_and_str(self):
        self.assertEqual(str(self.subject), 'S001 - Test Subject')

    def test_project_creation_and_relationships(self):
        # Test string representation
        self.assertEqual(str(self.project), 'R001')
        # Test relationships
        self.assertIn(self.user_profile, self.project.users.all())
        self.assertIn(self.subject, self.project.subjects.all())

    def test_file_import_creation_and_str(self):
        expected_str = f"{self.file.title} imported by {self.user_profile.name}"
        self.assertEqual(str(self.file_import), expected_str)

    def test_auto_now_add_fields(self):
        # Verify that auto_now_add fields are set
        self.assertIsInstance(self.file_import.imported_at, datetime.datetime)
        self.assertIsInstance(self.file.imported_at, datetime.datetime)
        self.assertIsInstance(self.project.created, datetime.datetime)
        self.assertIsInstance(self.project.updated, datetime.datetime)

    def test_nullability_in_project(self):
        # Ensure that nulls are handled appropriately
        new_project = Project.objects.create(description='A new project with no rekNummer')
        self.assertIsNone(new_project.rekNummer)
        self.assertEqual(new_project.description, 'A new project with no rekNummer')
