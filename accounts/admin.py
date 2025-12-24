from django.contrib import admin

# Register your models here.
from .models import CustomUser, Course, UserCourse, Topic, Question

admin.site.register(CustomUser)
admin.site.register(Course)
admin.site.register(Topic)
admin.site.register(UserCourse)
admin.site.register(Question)