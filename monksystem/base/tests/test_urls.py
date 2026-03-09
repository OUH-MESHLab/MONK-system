from django.test import SimpleTestCase
from django.urls import reverse, resolve
from base.views import *

class TestUrls(SimpleTestCase):
    
    def test_home_url_resolves(self):
        url = reverse('home')
        self.assertEqual(resolve(url).func, home_page)

    def test_login_url_resolves(self):
        url = reverse('login')
        self.assertEqual(resolve(url).func, login_page)

    def test_logout_url_resolves(self):
        url = reverse('logout')
        self.assertEqual(resolve(url).func, logout_user)

    def test_register_url_resolves(self):
        url = reverse('register')
        self.assertEqual(resolve(url).func, register_page)

    def test_file_detail_url_resolves(self):
        url = reverse('file', kwargs={'file_id': 1})
        self.assertEqual(resolve(url).func, file)

    def test_view_files_url_resolves(self):
        url = reverse('view_files')
        self.assertEqual(resolve(url).func, view_files)

    def test_import_file_url_resolves(self):
        url = reverse('import_file')
        self.assertEqual(resolve(url).func, import_file)

    def test_import_multiple_files_url_resolves(self):
        url = reverse('import_multiple_files')
        self.assertEqual(resolve(url).func, import_multiple_files)

    def test_user_detail_url_resolves(self):
        url = reverse('user', kwargs={'pk': '1'})
        self.assertEqual(resolve(url).func, user)

    def test_subject_detail_url_resolves(self):
        url = reverse('subject', kwargs={'pk': 'S001'})
        self.assertEqual(resolve(url).func, subject)

    def test_view_subjects_url_resolves(self):
        url = reverse('view_subjects')
        self.assertEqual(resolve(url).func, view_subjects)

    def test_project_detail_url_resolves(self):
        url = reverse('project', kwargs={'pk': 'P001'})
        self.assertEqual(resolve(url).func, project)

    def test_view_projects_url_resolves(self):
        url = reverse('view_projects')
        self.assertEqual(resolve(url).func, view_projects)

    def test_add_project_url_resolves(self):
        url = reverse('add_project')
        self.assertEqual(resolve(url).func, add_project)

    def test_leave_project_url_resolves(self):
        url = reverse('leave_project', kwargs={'project_id': 1})
        self.assertEqual(resolve(url).func, leave_project)

    def test_edit_project_url_resolves(self):
        url = reverse('edit_project', kwargs={'project_id': 1})
        self.assertEqual(resolve(url).func, edit_project)

    def test_download_mfer_header_url_resolves(self):
        url = reverse('download_mfer_header', kwargs={'file_id': 1})
        self.assertEqual(resolve(url).func, download_mfer_header)

    def test_download_mwf_url_resolves(self):
        url = reverse('download_mwf', kwargs={'file_id': 1})
        self.assertEqual(resolve(url).func, download_mwf)

    def test_plot_graph_url_resolves(self):
        url = reverse('plot_graph', kwargs={'file_id': 1})
        self.assertEqual(resolve(url).func, plot_graph)

    def test_download_csv_format_url_resolves(self):
        url = reverse('download_format_csv', kwargs={'file_id': 1})
        self.assertEqual(resolve(url).func, download_format_csv)
