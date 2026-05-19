from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from datetime import datetime

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
    published = models.BooleanField(default=False)   # NEW
    semester = models.CharField(max_length=50, null=True, blank=True)
    section = models.CharField(max_length=5, null=True, blank=True)

    def __str__(self):
        return f"{self.student.username} - {self.course.name} - {self.semester} - {self.section}"
    
# ---------------------- Syllabus ----------------------
class Syllabus(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    topic_name = models.CharField(max_length=200)
    lecture_slide = models.FileField(upload_to='syllabus/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.course.name} - {self.topic_name}"
    
# ---------------------- Quiz Attendence ----------------------
class QuizAttendance(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    week = models.PositiveIntegerField()
    attended = models.BooleanField(default=True)
    date = models.DateTimeField(auto_now_add=True)
    month = models.PositiveIntegerField(default=datetime.now().month)  
    score = models.FloatField(default=0)

    class Meta:
        unique_together = ('student', 'course', 'week', 'month')

    def __str__(self):
        return f"{self.student.username} - {self.course.name} (Week {self.week}, Month {self.month})"


class AIQuizAttempt(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey('Course', on_delete=models.CASCADE)
    topic_name = models.CharField(max_length=200, blank=True, null=True)
    score = models.FloatField(default=0)
    max_score = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']  

    def __str__(self):
        return f"{self.student.username} | {self.course.name} | {self.score}/{self.max_score}"

    def percentage(self):
        if self.max_score > 0:
            return round((self.score / self.max_score) * 100, 2)
        return 0

# ---------------------- Teacher ----------------------
# ---------------------- Teacher Course selection ----------------------
class TeacherCourseSelection(models.Model):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    semester = models.CharField(max_length=20, choices=[
        ("Spring24-25", "Spring 24-25"),
        ("Summer24-25", "Summer 24-25"),
        ("Fall24-25", "Fall 24-25"),
        ("Spring25-26", "Spring 25-26"),
        ("Summer25-26", "Summer 25-26"),
        ("Fall25-26", "Fall 25-26"),
    ])
    courses = models.ManyToManyField('Course', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.teacher.username} - {self.semester}"
    
# ---------------------- Section ----------------------
class Section(models.Model):
    SECTION_CHOICES = [
        ("A", "A"), ("B", "B"), ("C", "C"),
        ("D", "D"), ("E", "E"), ("F", "F"),
    ]

    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    semester = models.CharField(max_length=20)
    course = models.ForeignKey('Course', on_delete=models.CASCADE)
    section_name = models.CharField(max_length=2, choices=SECTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("teacher", "semester", "course", "section_name")

    def __str__(self):
        return f"{self.course.code} - {self.section_name} ({self.semester})"


# ---------------------- Student Info ----------------------
class StudentInfo(models.Model):
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='students')
    student_name = models.CharField(max_length=100)
    student_id = models.CharField(max_length=50)
    email = models.EmailField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student_name} ({self.student_id}) - {self.section}"
    

class TeacherSyllabusUpload(models.Model):
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    semester = models.CharField(max_length=100)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    section = models.CharField(max_length=10)

    syllabus_file = models.FileField(upload_to='syllabus_files/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.course.name} - {self.semester} - {self.section}"