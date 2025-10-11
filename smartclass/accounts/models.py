from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('Student', 'Student'),
        ('Teacher', 'Teacher'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)

# Courses
# ----------------------
class Course(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField()

    def __str__(self):
        return self.name

# ----------------------
# UserCourse mapping
# ----------------------
class UserCourse(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "course")

    def __str__(self):
        return f"{self.user.username} - {self.course.name}"

# Topic model
# ----------------------
class Topic(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='topics')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.course.name} - {self.name}"
    
    # ---------- Question ----------
class Question(models.Model):
    TYPE_CHOICES = [
        ('mcq', 'MCQ'),
        ('scenario-mcq', 'Scenario MCQ'),
        ('code', 'Code'),
        ('theory', 'Theory'),
    ]
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
    q_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    question_text = models.TextField()
    options = models.JSONField(blank=True, null=True)  # {"a":"Option 1","b":"Option 2"...}
    answer = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.course.name} - {self.topic.name} - {self.q_type}"
    
     # ---------- Marks ----------
class Marks(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey('Course', on_delete=models.CASCADE)
    quiz1 = models.FloatField(default=0)
    quiz2 = models.FloatField(default=0)
    quiz3 = models.FloatField(default=0)
    attendance = models.FloatField(default=0)
    assignment = models.FloatField(default=0)
    presentation = models.FloatField(default=0)
    termexam = models.FloatField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.username} - {self.course.name}" 
    
# ---------------------- Syllabus ----------------------
class Syllabus(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    topic_name = models.CharField(max_length=200)
    lecture_slide = models.FileField(upload_to='syllabus/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.course.name} - {self.topic_name}"