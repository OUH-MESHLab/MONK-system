from django.urls import path
from . import views 



urlpatterns = [
    path('', views.home_page, name="home"),
    
    path('accounts/login/', views.login_page, name='login'),
    path('login/', views.login_page, name = "login"),
    path('logout/', views.logout_user, name = "logout"),
    path('register/', views.register_page, name = "register"),
    
    path('file/<int:file_id>/', views.file, name='file'),    
    path('view_files/', views.view_files, name='view_files'),    
    path('import_file/', views.import_file, name='import_file'),
    path('import_multiple_files/', views.import_multiple_files, name='import_multiple_files'),
    path('import_from_directory/', views.import_from_directory, name='import_from_directory'),

    path('user/<str:pk>', views.user, name="user"),

    path('subject/<str:pk>', views.subject, name="subject"),
    path('view_subjects/', views.view_subjects, name = "view_subjects"),
    #path('addSubject/', views.addSubject, name = "addSubject"),

    path('project/<str:pk>', views.project, name="project"),
    path('view_projects/', views.view_projects, name = "view_projects"),
    path('add_project/', views.add_project, name = "add_project"),
    path('leave_project/<int:project_id>/', views.leave_project, name='leave_project'),
    path('edit_project/<int:project_id>/', views.edit_project, name='edit_project'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    
    path('download-MFER-Header/<int:file_id>/', views.download_mfer_header, name='download_mfer_header'),
    path('download-MWF/<int:file_id>/', views.download_mwf, name='download_mwf'),
    path('plot_graph/<int:file_id>/', views.plot_graph, name='plot_graph'),
    path('download-CSV-Format/<int:file_id>/', views.download_format_csv, name='download_format_csv'),
    path('list-export-dirs/', views.list_export_dirs_view, name='list_export_dirs'),
    path('browse-usb/', views.browse_usb_view, name='browse_usb'),
    path('scan-usb-mwf/', views.scan_usb_mwf_view, name='scan_usb_mwf'),
    path('import-from-usb/', views.import_from_usb, name='import_from_usb'),

    path('manage/users/', views.manage_users, name='manage_users'),
    path('manage/users/<int:user_id>/action/', views.manage_user_action, name='manage_user_action'),
]