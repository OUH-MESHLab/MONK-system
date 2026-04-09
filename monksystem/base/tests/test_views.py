import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
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
        # New users start inactive and are redirected to login for approval
        new_user = User.objects.get(username='newuser')
        self.assertFalse(new_user.is_active)
        self.assertRedirects(response, reverse('login'))

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


class TestImportFromDirectory(TestCase):
    """Tests for the server-side directory import view, including recursive (CNS) subdirectory layout."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='diruser', password='pass1234')
        UserProfile.objects.update_or_create(
            user=self.user, defaults={"name": "Dir User", "mobile": "000"}
        )
        self.client.login(username='diruser', password='pass1234')

    # ------------------------------------------------------------------
    # GET – listing
    # ------------------------------------------------------------------

    def test_get_lists_flat_mwf_files(self):
        """Files directly in FILE_IMPORT_BASE_DIR are listed."""
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'flat.mwf').write_bytes(b'x')
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                response = self.client.get(reverse('import_from_directory'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'flat.mwf')

    def test_get_lists_mwf_files_in_subdirectories(self):
        """CNS layout: .mwf files nested inside device/timestamp subdirs are found recursively."""
        with tempfile.TemporaryDirectory() as d:
            subdir = Path(d, '172016007006_20260316154702969')
            subdir.mkdir()
            (subdir / 'CnsMferOutput_013469DE.mwf').write_bytes(b'x')
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                response = self.client.get(reverse('import_from_directory'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CnsMferOutput_013469DE.mwf')

    def test_get_relative_path_includes_subdirectory(self):
        """The checkbox value submitted by the form must contain the subdirectory component."""
        with tempfile.TemporaryDirectory() as d:
            subdir = Path(d, '172016007006_20260316154702969')
            subdir.mkdir()
            (subdir / 'CnsMferOutput_013469DE.mwf').write_bytes(b'x')
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                response = self.client.get(reverse('import_from_directory'))
        expected = '172016007006_20260316154702969/CnsMferOutput_013469DE.mwf'
        self.assertContains(response, expected)

    def test_get_both_flat_and_nested_files_listed(self):
        """Flat and nested .mwf files both appear in the same listing."""
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'flat.mwf').write_bytes(b'x')
            subdir = Path(d, '172016007006_20260316182241688')
            subdir.mkdir()
            (subdir / 'CnsMferOutput_01355D77.mwf').write_bytes(b'x')
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                response = self.client.get(reverse('import_from_directory'))
        self.assertContains(response, 'flat.mwf')
        self.assertContains(response, 'CnsMferOutput_01355D77.mwf')

    def test_get_empty_directory_shows_no_files_message(self):
        with tempfile.TemporaryDirectory() as d:
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                response = self.client.get(reverse('import_from_directory'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No .mwf files found')

    def test_get_lists_uppercase_mwf_extension(self):
        """Files with .MWF (uppercase) extension are found — CNS devices may use uppercase."""
        with tempfile.TemporaryDirectory() as d:
            subdir = Path(d, '172016007006_20260316154702969')
            subdir.mkdir()
            (subdir / 'CnsMferOutput_013469DE.MWF').write_bytes(b'x')
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                response = self.client.get(reverse('import_from_directory'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'CnsMferOutput_013469DE.MWF')

    def test_get_non_mwf_files_not_listed(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'notes.txt').write_bytes(b'x')
            Path(d, 'data.csv').write_bytes(b'x')
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                response = self.client.get(reverse('import_from_directory'))
        self.assertNotContains(response, 'notes.txt')
        self.assertNotContains(response, 'data.csv')

    def test_get_requires_login(self):
        self.client.logout()
        with tempfile.TemporaryDirectory() as d:
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                response = self.client.get(reverse('import_from_directory'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])

    def test_get_unconfigured_redirects(self):
        """If FILE_IMPORT_BASE_DIR is empty the view redirects with an error."""
        with override_settings(FILE_IMPORT_BASE_DIR=''):
            response = self.client.get(reverse('import_from_directory'))
        self.assertEqual(response.status_code, 302)

    # ------------------------------------------------------------------
    # POST – import
    # ------------------------------------------------------------------

    def test_post_imports_flat_file(self):
        """A flat .mwf file (no subdir) can be imported via POST."""
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'flat.mwf').write_bytes(b'mwf-bytes')
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                with patch('base.views.process_and_create_subject'):
                    response = self.client.post(
                        reverse('import_from_directory'),
                        {'filenames': ['flat.mwf']},
                    )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(File.objects.filter(title='flat').exists())

    def test_post_imports_file_from_subdirectory(self):
        """A .mwf file nested in a CNS subdirectory is imported correctly."""
        with tempfile.TemporaryDirectory() as d:
            subdir = Path(d, '172016007006_20260316154702969')
            subdir.mkdir()
            (subdir / 'CnsMferOutput_013469DE.mwf').write_bytes(b'mwf-bytes')
            rel = '172016007006_20260316154702969/CnsMferOutput_013469DE.mwf'
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                with patch('base.views.process_and_create_subject'):
                    response = self.client.post(
                        reverse('import_from_directory'),
                        {'filenames': [rel]},
                    )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(File.objects.filter(title='CnsMferOutput_013469DE').exists())

    def test_post_rejects_path_traversal(self):
        """A filename containing ../ path traversal is rejected without importing."""
        with tempfile.TemporaryDirectory() as d:
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                response = self.client.post(
                    reverse('import_from_directory'),
                    {'filenames': ['../../etc/passwd']},
                    follow=True,
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(File.objects.count(), 0)

    def test_post_no_files_selected_shows_error(self):
        with tempfile.TemporaryDirectory() as d:
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                response = self.client.post(
                    reverse('import_from_directory'),
                    {'filenames': []},
                    follow=True,
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(File.objects.count(), 0)

    def test_post_removes_empty_subdirectory_after_import(self):
        """After importing the only file in a CNS subdirectory, the now-empty subdir is deleted."""
        with tempfile.TemporaryDirectory() as d:
            subdir = Path(d, '172016007006_20260316154702969')
            subdir.mkdir()
            mwf = subdir / 'CnsMferOutput_013469DE.mwf'
            mwf.write_bytes(b'mwf-bytes')
            rel = '172016007006_20260316154702969/CnsMferOutput_013469DE.mwf'
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                with patch('base.views.process_and_create_subject'):
                    self.client.post(
                        reverse('import_from_directory'),
                        {'filenames': [rel]},
                    )
            self.assertFalse(subdir.exists(), "empty subdirectory should have been removed")

    def test_post_keeps_subdirectory_when_other_files_remain(self):
        """A subdirectory that still contains other files after import is NOT removed."""
        with tempfile.TemporaryDirectory() as d:
            subdir = Path(d, '172016007006_20260316154702969')
            subdir.mkdir()
            (subdir / 'CnsMferOutput_013469DE.mwf').write_bytes(b'mwf-bytes')
            (subdir / 'CnsMferOutput_ANOTHER.mwf').write_bytes(b'mwf-bytes')
            rel = '172016007006_20260316154702969/CnsMferOutput_013469DE.mwf'
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                with patch('base.views.process_and_create_subject'):
                    self.client.post(
                        reverse('import_from_directory'),
                        {'filenames': [rel]},
                    )
            self.assertTrue(subdir.exists(), "subdirectory with remaining files must not be removed")

    def test_post_directory_cleanup_does_not_delete_files(self):
        """The cleanup walk only removes directories, never files."""
        with tempfile.TemporaryDirectory() as d:
            subdir = Path(d, 'sub')
            subdir.mkdir()
            mwf = subdir / 'test.mwf'
            mwf.write_bytes(b'mwf-bytes')
            sibling_file = Path(d, 'sibling.txt')
            sibling_file.write_bytes(b'keep me')
            rel = 'sub/test.mwf'
            with override_settings(FILE_IMPORT_BASE_DIR=d):
                with patch('base.views.process_and_create_subject'):
                    self.client.post(
                        reverse('import_from_directory'),
                        {'filenames': [rel]},
                    )
            self.assertTrue(sibling_file.exists(), "files in base_dir must never be deleted by cleanup")


class TestUserManagement(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            username='admin', password='adminpass', is_staff=True, is_active=True
        )
        self.regular = User.objects.create_user(
            username='regular', password='regularpass', is_active=True
        )
        UserProfile.objects.update_or_create(
            user=self.regular, defaults={"name": "Regular User", "mobile": "0"}
        )

    def _register(self, username='newuser'):
        return self.client.post(reverse('register'), {
            'username': username,
            'name': 'New User',
            'mobile': '1234567890',
            'password1': 'testpassword123',
            'password2': 'testpassword123',
        })

    # Registration behaviour

    def test_register_sets_inactive(self):
        self._register('newuser')
        user = User.objects.get(username='newuser')
        self.assertFalse(user.is_active)

    def test_register_no_autologin(self):
        response = self._register('newuser2')
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_register_redirects_to_login(self):
        response = self._register('newuser3')
        self.assertRedirects(response, reverse('login'))

    # Login behaviour for pending account

    def test_login_pending_shows_warning(self):
        self._register('pending')
        response = self.client.post(reverse('login'), {
            'username': 'pending', 'password': 'testpassword123'
        })
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        messages_list = list(response.context['messages'])
        texts = [str(m) for m in messages_list]
        self.assertTrue(any('pending' in t.lower() for t in texts))

    # manage_users access control

    def test_manage_users_requires_login(self):
        response = self.client.get(reverse('manage_users'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response['Location'])

    def test_manage_users_non_staff_redirected(self):
        self.client.login(username='regular', password='regularpass')
        response = self.client.get(reverse('manage_users'), follow=True)
        self.assertRedirects(response, reverse('home'))

    def test_manage_users_staff_ok(self):
        self.client.login(username='admin', password='adminpass')
        response = self.client.get(reverse('manage_users'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'base/manage_users.html')

    def test_manage_users_shows_pending(self):
        self._register('pending2')
        self.client.login(username='admin', password='adminpass')
        response = self.client.get(reverse('manage_users'))
        self.assertContains(response, 'pending2')

    # Actions

    def test_approve_action(self):
        self._register('tobeapproved')
        target = User.objects.get(username='tobeapproved')
        self.client.login(username='admin', password='adminpass')
        self.client.post(
            reverse('manage_user_action', args=[target.id]),
            {'action': 'approve'}
        )
        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_deactivate_action(self):
        self.client.login(username='admin', password='adminpass')
        self.client.post(
            reverse('manage_user_action', args=[self.regular.id]),
            {'action': 'deactivate'}
        )
        self.regular.refresh_from_db()
        self.assertFalse(self.regular.is_active)

    def test_delete_action(self):
        victim = User.objects.create_user(username='victim', password='pass', is_active=True)
        self.client.login(username='admin', password='adminpass')
        self.client.post(
            reverse('manage_user_action', args=[victim.id]),
            {'action': 'delete'}
        )
        self.assertFalse(User.objects.filter(username='victim').exists())

    def test_cannot_self_deactivate(self):
        self.client.login(username='admin', password='adminpass')
        response = self.client.post(
            reverse('manage_user_action', args=[self.staff.id]),
            {'action': 'deactivate'},
            follow=True,
        )
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)
        messages_list = list(response.context['messages'])
        self.assertTrue(any('cannot' in str(m).lower() for m in messages_list))

    def test_cannot_self_delete(self):
        self.client.login(username='admin', password='adminpass')
        response = self.client.post(
            reverse('manage_user_action', args=[self.staff.id]),
            {'action': 'delete'},
            follow=True,
        )
        self.assertTrue(User.objects.filter(username='admin').exists())
        messages_list = list(response.context['messages'])
        self.assertTrue(any('cannot' in str(m).lower() for m in messages_list))

    def test_non_staff_cannot_post_action(self):
        self.client.login(username='regular', password='regularpass')
        response = self.client.post(
            reverse('manage_user_action', args=[self.regular.id]),
            {'action': 'delete'},
            follow=True,
        )
        self.assertRedirects(response, reverse('home'))
        self.assertTrue(User.objects.filter(username='regular').exists())
