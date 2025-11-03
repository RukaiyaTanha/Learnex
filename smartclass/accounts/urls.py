from django.urls import path
from . import views

urlpatterns = [
    
     # APIs
    path("register/", views.register, name="register_api"),
    path("login/", views.login_api, name="login_api"),
    path("logout/", views.logout_api, name="logout_api"),  
    path("forgot-password-api/", views.forgot_password_api, name="forgot_password_api"),
    path("save-courses/", views.save_courses_api, name="save_courses_api"),
    path("profile/update/", views.update_profile_api, name="update_profile_api"),
    path("upload-marks-api/", views.upload_marks_api, name="upload_marks_api"),
    path('get-marks/<int:course_id>/', views.get_marks_api, name='get_marks_api'),
    path('edit-marks-api/', views.edit_marks_api, name='edit_marks_api'),
   
    # HTML pages
    path("register-page/", views.registration_page, name="registration_page"),
    path("login-page/", views.login_page, name="login_page"),
    path("dashboard/", views.student_dashboard, name="student_dashboard"),  
    path("forgot-password-page/", views.forgot_password_page, name="forgot_password_page"), 
    path("course-selection/", views.course_selection_page, name="course_selection_page"),
    path("quiz-selection/", views.quiz_selection_page, name="quiz_selection_page"),
    path('quiz/start/<int:course_id>/<int:topic_id>/<str:type>/', views.quiz_page, name='quiz_page'),
    path("quiz/submit/", views.submit_quiz, name="submit_quiz"),
    path('profile/', views.profile_page, name='profile_page'),
    path("profile/edit/", views.profile_edit, name="profile_edit"),
    path('selected-courses/', views.selected_courses_page, name='selected_courses_page'),
    path('upload-marks/', views.upload_marks_page, name='upload_marks_page'),
    path('edit-marks/', views.edit_marks_page, name='edit_marks_page'),
    path('upload-syllabus/', views.upload_syllabus, name='upload_syllabus_page'),
    path('selected-syllabus/', views.selected_syllabus, name='selected_syllabus_page'),
    path('syllabus/delete/<int:pk>/', views.delete_syllabus, name='delete_syllabus'),
    path('syllabus/view/<int:pk>/', views.view_syllabus, name='view_syllabus'),
    path('calculate-cgpa/', views.calculate_cgpa_page, name='calculate_cgpa_page'),
    path("current-semester-cg/", views.current_semester_cg, name="current_semester_cg"),
    path('overall-performance/', views.overall_performance, name='overall_performance'),
    path("ai-assistant/", views.ai_assistant, name="ai_assistant"),
    #password reset
    path('reset-password/<uidb64>/<token>/', views.reset_password_page, name='reset_password_page'),
    path('reset-password-api/', views.reset_password_api, name='reset_password_api'),

    #Teacher
    path("teacher-dashboard/", views.teacher_dashboard, name="teacher_dashboard"),
    path('teacher/course-selection/', views.teacher_course_selection_page, name='teacher_course_selection_page'),
    path('teacher/save-courses/', views.save_teacher_courses_api, name='save_teacher_courses_api'),
    path('teacher/selected-courses/', views.teacher_selected_courses_page, name='teacher_selected_courses_page'),
    path('teacher/upload-students/', views.upload_student_info_page, name='upload_student_info_page'),
    path('teacher/uploaded-students/', views.uploaded_students_page, name='uploaded_students_page'),
]
