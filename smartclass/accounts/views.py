from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from .models import Course, UserCourse,Topic
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.shortcuts import render, redirect 
from django.core.mail import EmailMultiAlternatives
from .models import CustomUser
from django.urls import reverse
import json

User = get_user_model()

# ---------- Registration API ----------
@csrf_exempt
def register(request):
    if request.method == "POST":
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')
        role = data.get('role')
        username = data.get('name')

        if not email or not password or not role or not username:
            return JsonResponse({"success": False, "message": "Missing fields"})

        if User.objects.filter(email=email).exists():
            return JsonResponse({"success": False, "message": "Email already registered"})

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role=role
        )
        return JsonResponse({"success": True, "message": "User registered successfully"})

    return JsonResponse({"success": False, "message": "Invalid request"})


# ---------- Registration HTML page ----------
def registration_page(request):
    return render(request, "accounts/registration.html")


# ---------- Login API ----------
@csrf_exempt
def login_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        email = data.get("email")
        password = data.get("password")
        role = data.get("role")  # <-- get role from request

        if not email or not password or not role:
            return JsonResponse({"success": False, "message": "Missing email, password, or role"})

        try:
            user = User.objects.get(email=email)

            # Check password
            if not user.check_password(password):
                return JsonResponse({"success": False, "message": "Invalid email or password"})

            # Check role
            if getattr(user, "role", "").lower() != role.lower():
                return JsonResponse({"success": False, "message": f"This account is not a {role}"})

            # Successful login
            login(request, user)  # start session
            return JsonResponse({
                "success": True,
                "message": "Login successful",
                "username": user.username,
                "role": getattr(user, "role", "N/A")
            })

        except User.DoesNotExist:
            return JsonResponse({"success": False, "message": "Invalid email or password"})

    return JsonResponse({"success": False, "message": "Invalid request"})

# ---------- Login HTML page ----------
def login_page(request):
    return render(request, "accounts/login.html")

# Dashboard page (protected)
# --------------------------
@login_required(login_url='/accounts/login-page/')
def student_dashboard(request):
    user = request.user
    context = {
        "username": user.username,
        "role": getattr(user, "role", "N/A"),
    }
    return render(request, "accounts/dashboard.html", context)

# Logout API
# --------------------------
@csrf_exempt
def logout_api(request):
    if request.method == "POST":
        logout(request)
        return JsonResponse({"success": True, "message": "Logged out"})
    return JsonResponse({"success": False, "message": "Invalid request"})

# forgot password

#save_courses_api
@csrf_exempt
@login_required(login_url='/accounts/login-page/')
def save_courses_api(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            selected_codes = data.get("courses", [])

            if not selected_codes:
                return JsonResponse({"success": False, "message": "No courses selected"})

            user = request.user

            # Only add courses that the user hasn't already selected
            for code in selected_codes:
                try:
                    course = Course.objects.get(code=code)
                    # get_or_create ensures no duplicates
                    UserCourse.objects.get_or_create(user=user, course=course)
                except Course.DoesNotExist:
                    return JsonResponse({"success": False, "message": f"Course '{code}' not found"})

            return JsonResponse({"success": True, "message": "Courses saved successfully"})

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)})

    return JsonResponse({"success": False, "message": "Invalid request"})

@login_required(login_url='/accounts/login-page/')
def course_selection_page(request):
    user = request.user
    courses = Course.objects.all()
    user_courses = UserCourse.objects.filter(user=user).values_list('course__code', flat=True)

    context = {
        "courses": courses,
        "user_courses": list(user_courses),
        "username": user.username,
    }
    return render(request, "accounts/course_selection.html", context)

@login_required(login_url='/accounts/login-page/')
def quiz_selection_page(request):
    courses = Course.objects.all()
    topics = Topic.objects.all()  # Or filter by selected course dynamically later
    context = {
        "courses": courses,
        "topics": topics,
    }
    return render(request, "accounts/quiz_selection.html", context)

# Forgot Password API
@csrf_exempt
def forgot_password_api(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        email = data.get('email')

        try:
            user = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'No account found with that email.'})

        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        reset_link = request.build_absolute_uri(
            reverse('reset_password_page', kwargs={'uidb64': uidb64, 'token': token})
        )

        html_content = render_to_string('accounts/reset_password_email.html', {
            'username': user.username,
            'reset_link': reset_link
        })
        text_content = f"Hi {user.username},\n\nPlease click the link to reset your password:\n{reset_link}"

        email_message = EmailMultiAlternatives(
            subject='Smart Class Password Reset',
            body=text_content,
            from_email='smartclass@example.com',
            to=[user.email],
        )
        email_message.attach_alternative(html_content, "text/html")
        email_message.send()

        return JsonResponse({'success': True, 'message': 'Password reset email sent!'})

# Forgot Password Page
def forgot_password_page(request):
    return render(request, 'accounts/forgot_password.html')

# Reset Password Page
def reset_password_page(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        return render(request, "accounts/reset_password.html", {"uidb64": uidb64, "token": token})
    else:
        return render(request, "accounts/reset_invalid.html")

# Reset Password API
@csrf_exempt
def reset_password_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        uidb64 = data.get("uidb64")
        token = data.get("token")
        new_password = data.get("password")

        try:
            uid = urlsafe_base64_decode(uidb64).decode()
            user = CustomUser.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
            return JsonResponse({"success": False, "message": "Invalid link"})

        if user and default_token_generator.check_token(user, token):
            user.set_password(new_password)
            user.save()
            return JsonResponse({"success": True, "message": "Password reset successful"})
        else:
            return JsonResponse({"success": False, "message": "Invalid or expired link"})

    return JsonResponse({"success": False, "message": "Invalid request"})

@login_required(login_url='/accounts/login-page/')
def profile_page(request):
    user = request.user
    context = {
        "username": user.username,
        "role": getattr(user, "role", "N/A"),
        "email": user.email,
        "date_joined": user.date_joined,
    }
    return render(request, "accounts/profile.html", context)


# ---------- Edit Profile Page ----------
@login_required(login_url='/accounts/login-page/')
def profile_edit(request):
    user = request.user
    context = {
        "username": user.username,
        "email": user.email,
        "role": getattr(user, "role", "N/A"),
    }
    return render(request, "accounts/profile_edit.html", context)


# ---------- Update Profile API ----------
@csrf_exempt
@login_required(login_url='/accounts/login-page/')
def update_profile_api(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user = request.user

            username = data.get("username", "").strip()
            email = data.get("email", "").strip()

            if not username or not email:
                return JsonResponse({"success": False, "message": "All fields are required."})

            # ✅ check for duplicate email (avoid overwriting another user)
            if User.objects.filter(email=email).exclude(id=user.id).exists():
                return JsonResponse({"success": False, "message": "This email is already in use."})

            user.username = username
            user.email = email
            user.save()

            return JsonResponse({"success": True, "message": "Profile updated successfully!"})
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)})

    return JsonResponse({"success": False, "message": "Invalid request"})