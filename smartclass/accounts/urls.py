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
    # HTML pages
    path("register-page/", views.registration_page, name="registration_page"),
    path("login-page/", views.login_page, name="login_page"),
    path("dashboard/", views.student_dashboard, name="student_dashboard"),  
    path("forgot-password-page/", views.forgot_password_page, name="forgot_password_page"), 
    path("course-selection/", views.course_selection_page, name="course_selection_page"),
    path("quiz-selection/", views.quiz_selection_page, name="quiz_selection_page"),
    path('profile/', views.profile_page, name='profile_page'),
    path("profile/edit/", views.profile_edit, name="profile_edit"),
 

    # ✅ password reset
    path('reset-password/<uidb64>/<token>/', views.reset_password_page, name='reset_password_page'),
    path('reset-password-api/', views.reset_password_api, name='reset_password_api'),
]
