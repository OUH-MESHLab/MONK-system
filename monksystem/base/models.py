from django.db import models
from django import forms
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
import uuid
import os
from django.utils.timezone import now


# Create your models here.

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null = True, related_name='userprofile')
    name = models.CharField(max_length=50)
    email = models.EmailField(blank=True)
    
    def __str__(self):
        return self.name


# Model for the files
class File(models.Model):
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='nihon_kohden_files/')
    anonymize = models.BooleanField(default=False)
    imported_at = models.DateTimeField(auto_now_add=True)

    
    def save(self, *args, **kwargs):
        if not self.title:
            # Automatically set the title to the file name without the extension
            base = os.path.basename(self.file.name)  # Extracts filename from the path
            self.title = os.path.splitext(base)[0]  # Removes the extension
        super(File, self).save(*args, **kwargs)
        
    def __str__(self):
        return self.title

class Subject(models.Model):
    subject_id = models.CharField(max_length=50, unique=True, null=True)
    unique_identifier = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=50)
    gender = models.CharField(max_length=10)
    birth_date = models.DateField(null=True, blank=True)
    file = models.ForeignKey(File, null=True, on_delete=models.CASCADE, related_name='subjects')

    def __str__(self):
        return f"{self.subject_id} - {self.name}"



class Project(models.Model):
    rekNummer = models.TextField(null = True, blank = True) 
    description = models.TextField(null = True, blank = True) # Description of project. Makes sure the values can be left blank. 
    
    users = models.ManyToManyField(UserProfile, related_name='projects')
    subjects = models.ManyToManyField(Subject, related_name='projects')
    
    updated = models.DateTimeField(auto_now = True) # Takes a snapshot of anytime the table (model instance) is updated. Takes a timestamp every time appointment is updated.
    created = models.DateTimeField(auto_now_add = True) # Takes a timestamp of when the instance was created.
    
    def __str__(self):
        return self.rekNummer or ""
    
# Model for file import
class FileImport(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    file = models.ForeignKey(File, on_delete=models.CASCADE)
    imported_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file.title} imported by {self.user.name}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Ensure every User always has a UserProfile, regardless of how it was created."""
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={"name": instance.username, "email": ""},
        )