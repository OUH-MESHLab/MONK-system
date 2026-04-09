from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import UserProfile, Subject, Project, File, FileImport

admin.site.register(UserProfile)
admin.site.register(Subject)
admin.site.register(Project)
admin.site.register(File)
admin.site.register(FileImport)

admin.site.unregister(User)

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'is_active', 'is_staff', 'date_joined')
    list_filter = ('is_active', 'is_staff')
    ordering = ('date_joined',)


