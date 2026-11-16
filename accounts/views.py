from django.shortcuts import render
from django.http import JsonResponse,FileResponse
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from .models import Course, MarksHistory, UserCourse,Topic, Question,Marks,Syllabus, QuizAttendance,TeacherCourseSelection,StudentInfo,Section, TeacherSyllabusUpload, AIQuizAttempt
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.shortcuts import render, redirect, get_object_or_404
from django.core.mail import EmailMultiAlternatives
from .models import CustomUser,TeacherNotification
from django.urls import reverse
import json as pyjson
from difflib import SequenceMatcher
from django.contrib import messages
from django.views.decorators.http import require_POST
import mimetypes
from django.db.models import F, Avg
from django.db import IntegrityError
from django.db.models.functions import Lower, Trim
import csv, io, json
import os
import pdfplumber
from PIL import Image
import pytesseract
import docx
from pptx import Presentation
import openpyxl
from io import BytesIO
from django.conf import settings
from django.contrib import messages
import markdown2
from .ai_feedback import generate_ai_feedback
from django.utils.safestring import mark_safe
from datetime import datetime
from django.db import transaction
from collections import defaultdict
from datetime import timedelta
from django.utils.timezone import now
import google.generativeai as genai
from google.genai import types
from .utils import check_ai_quiz_decline
from collections import defaultdict
from django.db.models import Avg
from .models import AIQuizAttempt


User = get_user_model()

# Starter AIUB course catalog used to backfill missing courses in the database.
AIUB_COURSE_CATALOG = [
    ("CSE101", "Introduction to Computer Systems", "Core introductory computing course."),
    ("CSE102", "Structured Programming", "Programming basics and problem solving."),
    ("CSE103", "Discrete Mathematics", "Logic, sets, relations, and proofs."),
    ("CSE104", "Object Oriented Programming", "Classes, objects, inheritance, and design."),
    ("CSE105", "Data Structures", "Arrays, stacks, queues, trees, and graphs."),
    ("CSE201", "Algorithms", "Algorithm design, complexity, and analysis."),
    ("CSE202", "Database Systems", "Relational databases and SQL."),
    ("CSE203", "Digital Logic Design", "Boolean logic, circuits, and combinational design."),
    ("CSE204", "Computer Organization", "Processor architecture and memory systems."),
    ("CSE205", "Operating Systems", "Processes, memory, and file systems."),
    ("CSE206", "Computer Networks", "Network models, protocols, and communication."),
    ("CSE207", "Software Engineering", "Requirements, design, testing, and maintenance."),
    ("CSE208", "Web Technologies", "Frontend and backend web application development."),
    ("CSE209", "Artificial Intelligence", "Search, reasoning, and intelligent systems."),
    ("CSE210", "Compiler Design", "Lexing, parsing, and code generation."),
    ("CSE211", "Microprocessors and Interfacing", "Embedded processor basics and interfacing."),
    ("CSE212", "Theory of Computation", "Automata, grammars, and computability."),
    ("CSE213", "Computer Graphics", "2D and 3D graphics fundamentals."),
    ("CSE214", "System Analysis and Design", "Modeling and designing information systems."),
    ("CSE215", "Mobile Application Development", "Building applications for mobile platforms."),
    ("CSE216", "Machine Learning", "Data-driven models and predictive methods."),
    ("CSE217", "Information Security", "Security principles, threats, and defense."),
    ("CSE218", "Distributed Systems", "Coordination and communication in distributed computing."),
    ("CSE219", "Parallel Computing", "Concurrent computation and performance scaling."),
    ("CSE220", "Human Computer Interaction", "User-centered design and usability."),
    ("CSE221", "Research Methodology", "Research design, writing, and evaluation."),
    ("CSE322", "Advanced Database Management", "Database tuning, optimization, and transactions."),
    ("CSE323", "Cloud Computing", "Virtualized infrastructure and cloud services."),
    ("CSE324", "Data Mining", "Discovering patterns from structured data."),
    ("MAT101", "Calculus and Analytical Geometry", "Differential and integral calculus."),
    ("MAT102", "Linear Algebra", "Vectors, matrices, and linear systems."),
    ("MAT103", "Differential Equations", "Ordinary differential equations and applications."),
    ("PHY101", "Physics", "Fundamental mechanics and modern physics."),
    ("ENG101", "English Language", "Academic writing and communication skills."),
]


def ensure_aiub_courses_exist():
    existing_codes = set(Course.objects.values_list("code", flat=True))
    missing_courses = [
        Course(code=code, name=name, description=description)
        for code, name, description in AIUB_COURSE_CATALOG
        if code not in existing_codes
    ]

    if missing_courses:
        Course.objects.bulk_create(missing_courses)


def get_student_assigned_sections(user):
    if not user.email:
        return Section.objects.none()

    email = user.email.strip().lower()
    return (
        Section.objects.annotate(student_email_clean=Lower(Trim("students__email")))
        .filter(student_email_clean=email)
        .select_related("course")
        .distinct()
        .order_by("semester", "course__name", "section_name")
    )


def sync_student_courses_from_teacher_uploads(user):
    assigned_sections = get_student_assigned_sections(user)
    assigned_courses = []
    seen_course_ids = set()

    for section in assigned_sections:
        if section.course_id in seen_course_ids:
            continue
        seen_course_ids.add(section.course_id)
        assigned_courses.append(section.course)

    for course in assigned_courses:
        UserCourse.objects.get_or_create(user=user, course=course)

    return assigned_sections


def is_teacher(user):
    return getattr(user, "role", "").lower() == "teacher"


def require_teacher_page(request):
    if is_teacher(request.user):
        return None

    messages.error(request, "Please log in with a Teacher account to use teacher pages.")
    return redirect("student_dashboard")


def parse_student_info_file(student_file):
    filename = student_file.name.lower()
    rows = []

    if filename.endswith(".xlsx"):
        workbook = openpyxl.load_workbook(BytesIO(student_file.read()), read_only=True, data_only=True)
        sheet = workbook.active
        sheet_rows = list(sheet.iter_rows(values_only=True))
        if not sheet_rows:
            return rows

        headers = [str(value or "").strip().lower() for value in sheet_rows[0]]
        for sheet_row in sheet_rows[1:]:
            row = {
                headers[index]: "" if value is None else str(value).strip()
                for index, value in enumerate(sheet_row)
                if index < len(headers)
            }
            rows.append(row)
        return rows

    decoded_file = student_file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded_file))
    for row in reader:
        rows.append({str(key or "").strip().lower(): str(value or "").strip() for key, value in row.items()})

    return rows

# ---------- Registration API ----------
@csrf_exempt
def register(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "message": "Invalid JSON payload"}, status=400)

        email = (data.get('email') or '').strip()
        password = data.get('password')
        role = (data.get('role') or '').strip().title()
        username = (data.get('name') or '').strip()
        first_name = (data.get('first_name') or '').strip()
        last_name = (data.get('last_name') or '').strip()

        if not email or not password or not role or not username:
            return JsonResponse({"success": False, "message": "Missing fields"}, status=400)

        if role not in dict(CustomUser.ROLE_CHOICES):
            return JsonResponse({"success": False, "message": "Invalid role selected"}, status=400)

        if User.objects.filter(email__iexact=email).exists():
            return JsonResponse({"success": False, "message": "Email already registered"}, status=400)

        if User.objects.filter(username__iexact=username).exists():
            return JsonResponse({"success": False, "message": "Username already taken"}, status=400)

        try:
            User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                email=email,
                password=password,
                role=role
            )
            return JsonResponse({"success": True, "message": "User registered successfully"})
        except IntegrityError:
            return JsonResponse({"success": False, "message": "Username or email already exists"}, status=400)
        except Exception as exc:
            return JsonResponse({"success": False, "message": f"Registration failed: {exc}"}, status=500)

    return JsonResponse({"success": False, "message": "Invalid request"})


# ---------- Registration HTML page ----------
def registration_page(request):
    return render(request, "accounts/registration.html")


# ---------- Login API ----------
@csrf_exempt
def login_api(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "message": "Invalid JSON payload"}, status=400)

        email = (data.get("email") or '').strip()
        password = data.get("password")
        role = (data.get("role") or '').strip().lower()

        if not email or not password or not role:
            return JsonResponse({"success": False, "message": "Missing email, password, or role"}, status=400)

        try:
            user = User.objects.filter(email__iexact=email).order_by("id").first()

            if not user:
                return JsonResponse({"success": False, "message": "Invalid email or password"}, status=401)

            if not user.check_password(password):
                return JsonResponse({"success": False, "message": "Invalid email or password"}, status=401)

            user_role = getattr(user, "role", "").strip().lower()
            if user_role != role:
                return JsonResponse({"success": False, "message": f"This account is not a {role}"}, status=403)

            login(request, user)

            if role == "student":
                redirect_url = reverse("student_dashboard")
            elif role == "teacher":
                redirect_url = reverse("teacher_dashboard")
            else:
                redirect_url = reverse("student_dashboard")

            return JsonResponse({
                "success": True,
                "message": "Login successful",
                "username": user.username,
                "role": getattr(user, "role", "N/A"),
                "redirect_url": redirect_url,
            })

        except Exception as exc:
            return JsonResponse({"success": False, "message": f"Login failed: {exc}"}, status=500)

    return JsonResponse({"success": False, "message": "Invalid request"})

# ---------- Login HTML page ----------
def login_page(request):
    return render(request, "accounts/login.html")

# Student Dashboard page (protected)
@login_required(login_url='/accounts/login-page/')
def student_dashboard(request):
    user = request.user
    sync_student_courses_from_teacher_uploads(user)
    context = {
        "username": user.username,
        "role": getattr(user, "role", "N/A"),
    }
    return render(request, "accounts/dashboard.html", context)

# Logout API
@csrf_exempt
def logout_api(request):
    if request.method == "POST":
        logout(request)
        return JsonResponse({"success": True, "message": "Logged out"})
    return JsonResponse({"success": False, "message": "Invalid request"})

#save_courses_api
@csrf_exempt
@login_required(login_url='/accounts/login-page/')
def save_courses_api(request):
    if request.method == "POST":
        try:
            ensure_aiub_courses_exist()
            data = json.loads(request.body)
            selected_codes = data.get("courses", [])
            if not isinstance(selected_codes, list):
                return JsonResponse({"success": False, "message": "Invalid courses data"})

            user = request.user

            all_courses = Course.objects.filter(code__in=selected_codes)

            added = []
            for course in all_courses:
                uc, created = UserCourse.objects.get_or_create(user=user, course=course)
                if created:
                    added.append(course.code)

            removed = []
            user_courses_qs = UserCourse.objects.filter(user=user)
            for uc in user_courses_qs:
                if uc.course.code not in selected_codes:
                    removed.append(uc.course.code)
                    uc.delete()

            current = list(UserCourse.objects.filter(user=user).values_list('course__code', flat=True))

            return JsonResponse({
                "success": True,
                "message": f"Added {len(added)} course(s), removed {len(removed)} course(s).",
                "courses": current
            })
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)})

    return JsonResponse({"success": False, "message": "Invalid request"})

@login_required(login_url='/accounts/login-page/')
def course_selection_page(request):
    user = request.user
    ensure_aiub_courses_exist()
    assigned_sections = sync_student_courses_from_teacher_uploads(user)
    assigned_courses = []
    for section in assigned_sections:
        assigned_courses.append({
            "course": section.course,
            "semester": section.semester,
            "section": section.section_name,
            "teacher": section.teacher,
        })

    context = {
        "username": user.username,
        "assigned_courses": assigned_courses,
    }
    return render(request, "accounts/course_selection.html", context)

@login_required(login_url='/accounts/login-page/')
def selected_courses_page(request):
    assigned_sections = sync_student_courses_from_teacher_uploads(request.user)
    return render(request, 'accounts/selected_courses.html', {
        'username': request.user.username,
        'assigned_sections': assigned_sections,
    })

# ---------- Quiz Selection ----------
@login_required(login_url='/accounts/login-page/')
def quiz_selection_page(request):
    user = request.user
    ensure_aiub_courses_exist()
    sync_student_courses_from_teacher_uploads(user)
    enrolled_courses = Course.objects.filter(usercourse__user=user)

    course_topics = {str(course.id): [{"id": t.id, "name": t.name} for t in course.topics.all()] for course in enrolled_courses}

    context = {
        "username": user.username,
        "courses": enrolled_courses,
        "course_topics": course_topics,
    }
    return render(request, "accounts/quiz_selection.html", context)

# ---------- Start Quiz ----------
@login_required(login_url='/accounts/login-page/')
def start_quiz(request, course_id, topic_id, quiz_type):
    try:
        course = Course.objects.get(id=course_id)
        topic = Topic.objects.get(id=topic_id, course=course)
    except (Course.DoesNotExist, Topic.DoesNotExist):
        return render(request, "accounts/quiz_invalid.html", {"message": "Invalid course or topic."})

    questions = Question.objects.filter(course=course, topic=topic, q_type=quiz_type)

    context = {
        "username": request.user.username,
        "course": course,
        "topic": topic,
        "type": quiz_type,
        "questions": questions,
    }
    return render(request, "accounts/quiz_page.html", context)

# ---------- Submit Quiz ----------
@login_required(login_url='/accounts/login-page/')
def submit_quiz(request):
    if request.method == "POST":
        score = 0
        total = 0
        for key, value in request.POST.items():
            if key.startswith("q_"):
                qid = int(key.split("_")[1])
                try:
                    question = Question.objects.get(id=qid)
                    total += 1
                    if question.answer == value:
                        score += 1
                except Question.DoesNotExist:
                    continue
        return render(request, "accounts/quiz_result.html", {"score": score, "total": total})

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
#profile page
@login_required(login_url='/accounts/login-page/')
def profile_page(request):
    user = request.user

    role = getattr(user, "role", "N/A")

    if role.lower() == "teacher":
        dashboard_url = "teacher_dashboard"
    else:
        dashboard_url = "student_dashboard"

    context = {
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": role,
        "email": user.email,
        "date_joined": user.date_joined,
        "dashboard_url": dashboard_url,
    }

    return render(request, "accounts/profile.html", context)

# ---------- Edit Profile Page ----------
@login_required(login_url='/accounts/login-page/')
def profile_edit(request):
    user = request.user

    role = getattr(user, "role", "N/A")

    if role.lower() == "teacher":
        dashboard_url = "teacher_dashboard"
    else:
        dashboard_url = "student_dashboard"

    context = {
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "role": role,
        "dashboard_url": dashboard_url,
    }

    return render(request, "accounts/profile_edit.html", context)

# ---------- Update Profile API ----------
@csrf_exempt
@login_required(login_url='/accounts/login-page/')
def update_profile_api(request):
    if request.method == "POST":
        try:
            data = request.POST
            user = request.user

            username = data.get("username", "").strip()
            first_name = data.get("first_name", "").strip()
            last_name = data.get("last_name", "").strip()
            email = data.get("email", "").strip()
            profile_picture = request.FILES.get("profile_picture")
            expects_json = (
                request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or "application/json" in request.headers.get("Accept", "")
            )

            if not username or not email or not first_name or not last_name:
                if expects_json:
                    return JsonResponse({"success": False, "message": "All fields are required."})
                messages.error(request, "All fields are required.")
                return redirect("profile_edit")

            if User.objects.filter(email=email).exclude(id=user.id).exists():
                if expects_json:
                    return JsonResponse({"success": False, "message": "This email is already in use."})
                messages.error(request, "This email is already in use.")
                return redirect("profile_edit")

            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            if profile_picture:
                user.profile_picture = profile_picture
            user.save()

            if expects_json:
                return JsonResponse({"success": True, "message": "Profile updated successfully!"})

            messages.success(request, "Profile updated successfully!")
            return redirect("profile_page")
        except Exception as e:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", ""):
                return JsonResponse({"success": False, "message": str(e)})
            messages.error(request, str(e))
            return redirect("profile_edit")

    return JsonResponse({"success": False, "message": "Invalid request"})

# ---------- Quiz page ----------
@login_required(login_url='/accounts/login-page/')
def quiz_page(request, course_id, topic_id, type):
    try:
        course = Course.objects.get(id=course_id)
        topic = Topic.objects.get(id=topic_id, course=course)
        topic_name = topic.name
    except (Course.DoesNotExist, Topic.DoesNotExist):
        return render(request, "accounts/quiz_invalid.html", {"message": "Invalid course or topic selected."})

    all_questions = {
    "6": {  # Course: Differential
        "94": {  # Topic: Limits
            "mcq": {
                "time_duration": "15 Minutes",
                "marks": 20,
                "questions": [
                    {"question": "lim x→2 (x^2 - 4)/(x - 2)", "options": ["2", "4", "6", "8"], "answer": "4"},
                    {"question": "lim x→0 sin(x)/x", "options": ["0", "1", "Infinity", "-Infinity"], "answer": "1"},
                    {"question": "lim x→1 (x^3 - 1)/(x - 1)", "options": ["1", "2", "3", "0"], "answer": "3"},
                    {"question": "lim x→0 |x|/x", "options": ["0", "1", "Does not exist", "-1"], "answer": "Does not exist"},
                    {"question": "If lim x→a f(x)=L, it may or may not equal f(a)", "options": ["True", "False"], "answer": "True"},
                    {"question": "lim x→∞ 1/x", "options": ["0", "1", "Infinity", "-Infinity"], "answer": "0"},
                    {"question": "lim x→0 (1+x)^(1/x)", "options": ["1", "e", "0", "Infinity"], "answer": "e"},
                    {"question": "Rule used to solve 0/0 form", "options": ["L’Hôpital’s Rule", "Chain Rule", "Product Rule", "Quotient Rule"], "answer": "L’Hôpital’s Rule"},
                    {"question": "lim x→0 (1-cos(x))/x^2", "options": ["0", "1/2", "1", "2"], "answer": "1/2"},
                    {"question": "lim x→0 tan(x)/x", "options": ["0", "1", "Infinity", "-Infinity"], "answer": "1"},
                    {"question": "lim x→3 (x^2+2x-9)/(x-3)", "options": ["6", "7", "8", "9"], "answer": "8"},
                    {"question": "lim x→0 (e^x - 1)/x", "options": ["0", "1", "e", "-1"], "answer": "1"},
                    {"question": "If left-hand ≠ right-hand limits, limit does not exist", "options": ["True", "False"], "answer": "True"},
                    {"question": "lim x→0 x*ln(x)", "options": ["0", "1", "-Infinity", "Does not exist"], "answer": "0"},
                    {"question": "lim x→∞ (1 + 2/x)^x", "options": ["2", "e", "e^2", "Infinity"], "answer": "e^2"},
                    {"question": "For f(x)=|x|, lim x→0^- f(x)", "options": ["0", "1", "-1", "Does not exist"], "answer": "0"},
                    {"question": "Removable discontinuity is called?", "options": ["Hole", "Jump", "Infinite", "Oscillation"], "answer": "Hole"},
                    {"question": "lim x→0 sin(3x)/x", "options": ["1", "3", "0", "Does not exist"], "answer": "3"},
                    {"question": "lim x→∞ (2x^2+5x)/(x^2+3x)", "options": ["1", "2", "3", "5"], "answer": "2"},
                    {"question": "Formal definition of limit involves |x-a|<δ ⇒ |f(x)-L|<ε", "options": ["True", "False"], "answer": "True"}
                ]
            },
            "scenario-mcq": {
                "time_duration": "20 Minutes",
                "marks": 20,
                "questions": [
                    {"question": "Function jumps from 2 to 5 at x=1", "options": ["Limit exists", "Limit does not exist"], "answer": "Limit does not exist"},
                    {"question": "LHL=RHL=2", "options": ["Limit exists", "Limit does not exist"], "answer": "Limit exists"},
                    {"question": "Graph has hole at (1,2)", "options": ["Limit = 0", "Limit = 2"], "answer": "Limit = 2"},
                    {"question": "lim Δt→0 Δs/Δt", "options": ["Displacement", "Velocity", "Acceleration", "Speed"], "answer": "Velocity"},
                    {"question": "P(t)=100t/(t+1), t→∞", "options": ["100", "0", "Infinity", "1"], "answer": "100"},
                    {"question": "E(x)=(x^2-4)/(x-2)", "options": ["Exact error", "Approximated error"], "answer": "Approximated error"},
                    {"question": "T(t)=5+2*sin(t), t→0", "options": ["5", "0", "2", "Infinity"], "answer": "5"},
                    {"question": "f(x)=1/x, x→0+", "options": ["0", "∞", "-∞", "Does not exist"], "answer": "∞"},
                    {"question": "sin(0.00001)/0.00001", "options": ["≈0", "≈1", "≈2", "Undefined"], "answer": "≈1"},
                    {"question": "Limit exists but f(a) undefined", "options": ["Function continuous", "Function discontinuous"], "answer": "Function discontinuous"},
                    {"question": "Infinite oscillation (sin(1/x))", "options": ["Limit exists", "Limit does not exist"], "answer": "Limit does not exist"},
                    {"question": "Growth rate→0", "options": ["Growth continues", "Growth stops"], "answer": "Growth stops"},
                    {"question": "Left and right limits differ", "options": ["Bilateral limit", "Jump discontinuity"], "answer": "Jump discontinuity"},
                    {"question": "Supply→∞, price→0", "options": ["Direct relation", "Inverse relation"], "answer": "Inverse relation"},
                    {"question": "f(x)=1/(x-2), x→2", "options": ["Limit exists", "Limit does not exist"], "answer": "Limit does not exist"},
                    {"question": "Same value both sides", "options": ["Bilateral limit", "Jump discontinuity"], "answer": "Bilateral limit"},
                    {"question": "T(x)=x^2, x→-3", "options": ["Limit = -9", "Limit = 9"], "answer": "Limit = 9"},
                    {"question": "f(x)=|x|/x, x=0", "options": ["Defined", "Undefined"], "answer": "Undefined"},
                    {"question": "(1+1/x)^x, x→∞", "options": ["1", "e"], "answer": "e"},
                    {"question": "Limit depends on path", "options": ["Path-dependent", "Path-independent"], "answer": "Path-dependent"}
                ]
            },
            "code": {
                "time_duration": "1 Hour",
                "marks": 35,
                "questions": [
                    {"question": "Python program to approximate limit of sin(x)/x as x→0",  "options": [],"answer": "import math\nx = 0.000001\nprint(math.sin(x)/x)"},
                    {"question": "Python program to calculate (1 + 1/x)^x as x→∞", "options": [], "answer": "x = 10000\nprint((1 + 1/x) ** x)"},
                    {"question": "Trace output:\nimport math\nx = 0.000001\nprint(math.sin(x)/x)",  "options": [], "answer": "0.9999999999998334"},
                    {"question": "Trace output:\nx = 10000\nprint((1 + 1/x)**x)", "options": [], "answer": "2.7181459"},
                    {"question": "Trace output:\ndef f(x):\n    return (x**2 - 4)/(x - 2)\nprint(f(2.0001))",  "options": [],"answer": "4.0001"}
                ]
            },
            "theory": {
                "time_duration": "45 Minutes",
                "marks": 30,
                "questions": [
                    {"question": "What is a limit?", "options": [], "answer": "The value a function approaches as the input approaches a specific point."},
                    {"question": "What are left-hand and right-hand limits?",  "options": [],"answer": "Left-hand (x→a⁻) approaches from left; Right-hand (x→a⁺) from right. Limit exists if both equal."},
                    {"question": "What is an indeterminate form?", "options": [], "answer": "A form like 0/0, ∞/∞, 0×∞, where direct substitution fails."},
                    {"question": "Explain continuity using limits.",  "options": [],"answer": "A function is continuous at x=a if lim x→a f(x) = f(a)."},
                    {"question": "What is the geometric meaning of a limit?", "options": [], "answer": "The point the function’s graph approaches as x gets closer to a value."},
                    {"question": "Discuss types of discontinuities with examples.",  "options": [],"answer": "Removable: Limit exists but function value missing or different. Jump: Left and right limits unequal. Infinite: Function tends to ∞ near a point."},
                    {"question": "Explain L’Hôpital’s Rule with examples.", "options": [], "answer": "If a limit gives 0/0 or ∞/∞, lim x→a f(x)/g(x) = lim x→a f'(x)/g'(x). Examples: lim x→0 sin(x)/x = 1; lim x→∞ ln(x)/x = 0."}
                ]
            }
        }
    },
    "1": {  # Course: Web Technology
       "84": {  # Topic: HTML Basics
            "mcq": {
            "time_duration": "15 Minutes",
            "marks": 20,
            "questions": [
                {"question": "Which tag is used for paragraph?", "options": ["<p>", "<div>", "<span>", "<h1>"], "answer": "<p>"},
                {"question": "Which tag is used for the largest heading?", "options": ["<h1>", "<h6>", "<head>", "<header>"], "answer": "<h1>"},
                {"question": "Which tag is used to create a hyperlink?", "options": ["<a>", "<link>", "<url>", "<button>"], "answer": "<a>"},
                {"question": "Which attribute specifies the link URL in <a>?", "options": ["href", "src", "link", "url"], "answer": "href"},
                {"question": "Which tag is used for unordered list?", "options": ["<ul>", "<ol>", "<li>", "<list>"], "answer": "<ul>"},
                {"question": "Which tag is used for ordered list?", "options": ["<ol>", "<ul>", "<li>", "<list>"], "answer": "<ol>"},
                {"question": "Which tag is used for table row?", "options": ["<tr>", "<td>", "<table>", "<th>"], "answer": "<tr>"},
                {"question": "Which tag is used for table header?", "options": ["<th>", "<td>", "<tr>", "<thead>"], "answer": "<th>"},
                {"question": "Which tag is used to embed image?", "options": ["<img>", "<picture>", "<image>", "<src>"], "answer": "<img>"},
                {"question": "Which attribute is used for alternative text for images?", "options": ["alt", "title", "src", "href"], "answer": "alt"},
                {"question": "Which tag is used for bold text?", "options": ["<b>", "<strong>", "<bold>", "<em>"], "answer": "<b>"},
                {"question": "Which tag is used for italic text?", "options": ["<i>", "<em>", "<italic>", "<it>"], "answer": "<i>"},
                {"question": "Which tag defines a division or section?", "options": ["<div>", "<span>", "<section>", "<article>"], "answer": "<div>"},
                {"question": "Which tag is inline element?", "options": ["<span>", "<div>", "<p>", "<header>"], "answer": "<span>"},
                {"question": "Which tag is block-level element?", "options": ["<div>", "<span>", "<a>", "<img>"], "answer": "<div>"},
                {"question": "Which tag is used for adding page title?", "options": ["<title>", "<head>", "<meta>", "<h1>"], "answer": "<title>"},
                {"question": "Which tag is used to add a comment?", "options": ["<!-- -->", "//", "#", "/* */"], "answer": "<!-- -->"},
                {"question": "Which tag is used for line break?", "options": ["<br>", "<hr>", "<lb>", "<break>"], "answer": "<br>"},
                {"question": "Which tag is used to define a list item?", "options": ["<li>", "<ul>", "<ol>", "<list>"], "answer": "<li>"},
                {"question": "Which tag is used for embedding video?", "options": ["<video>", "<media>", "<embed>", "<movie>"], "answer": "<video>"}
            ]
        },
        "scenario-mcq": {
            "time_duration": "20 Minutes",
            "marks": 20,
            "questions": [
                {"question": "You want a navigation menu with links to Home, About, Contact. Which tag should you use?", "options": ["<nav>", "<div>", "<ul>", "<header>"], "answer": "<nav>"},
                {"question": "You want a table with header and 3 rows of data. Which tags are necessary?", "options": ["<table>, <tr>, <th>, <td>", "<table>, <row>, <th>, <td>", "<table>, <tr>, <td>", "<table>, <tr>, <header>, <cell>"], "answer": "<table>, <tr>, <th>, <td>"},
                {"question": "You want to display an image logo.png with alt text. Which tag and attribute?", "options": ["<img src='logo.png' alt='Logo'>", "<image src='logo.png' alt='Logo'>", "<picture src='logo.png'>", "<div src='logo.png'>"], "answer": "<img src='logo.png' alt='Logo'>"},
                {"question": "You want text 'Important' to be emphasized. Which tag is correct?", "options": ["<strong>", "<b>", "<em>", "<i>"], "answer": "<strong>"},
                {"question": "You need a horizontal line to separate sections. Which tag?", "options": ["<hr>", "<br>", "<line>", "<divider>"], "answer": "<hr>"},
                {"question": "You want a form input for user email. Which tag?", "options": ["<input type='email'>", "<input type='text'>", "<form type='email'>", "<email>"], "answer": "<input type='email'>"},
                {"question": "You want to embed a YouTube video. Which tag?", "options": ["<iframe>", "<embed>", "<video>", "<object>"], "answer": "<iframe>"},
                {"question": "You want text aligned center. Which attribute/tag?", "options": ["<p style='text-align:center'>", "<center>", "<div align='center'>", "All of the above"], "answer": "All of the above"},
                {"question": "You want a dropdown selection in a form. Which tag?", "options": ["<select>", "<input>", "<option>", "<dropdown>"], "answer": "<select>"},
                {"question": "You want multiple checkboxes in a form. Which tag?", "options": ["<input type='checkbox'>", "<input type='radio'>", "<checkbox>", "<check>"], "answer": "<input type='checkbox'>"},
                {"question": "You want a numbered list. Which tag?", "options": ["<ol>", "<ul>", "<li>", "<list>"], "answer": "<ol>"},
                {"question": "You want a tooltip to appear on hover. Which attribute?", "options": ["title", "alt", "hover", "tooltip"], "answer": "title"},
                {"question": "You want a footer section with copyright info. Which tag?", "options": ["<footer>", "<bottom>", "<section>", "<div>"], "answer": "<footer>"},
                {"question": "You want a sidebar menu. Which semantic tag?", "options": ["<aside>", "<section>", "<nav>", "<div>"], "answer": "<aside>"},
                {"question": "You want to highlight text. Which tag?", "options": ["<mark>", "<highlight>", "<em>", "<strong>"], "answer": "<mark>"},
                {"question": "You want to group multiple form elements. Which tag?", "options": ["<fieldset>", "<form>", "<div>", "<section>"], "answer": "<fieldset>"},
                {"question": "You want to create a clickable image link. Which combination?", "options": ["<a><img></a>", "<img><a></img>", "<link><img></link>", "<div><img></div>"], "answer": "<a><img></a>"},
                {"question": "You want a semantic article block for blog content. Which tag?", "options": ["<article>", "<section>", "<div>", "<main>"], "answer": "<article>"},
                {"question": "You want to create a form with submit button. Which tag?", "options": ["<button>", "<input type='submit'>", "Both", "<form>"], "answer": "Both"},
                {"question": "You want to include external CSS file. Which tag?", "options": ["<link>", "<style>", "<css>", "<import>"], "answer": "<link>"}
            ]
        },
        "code": {
            "time_duration": "1 Hour",
            "marks": 35,
            "questions": [
                {"question": "Write HTML code to create a hyperlink to https://example.com with text 'Visit Example'", "options": [], "answer": "<a href='https://example.com'>Visit Example</a>"},
                {"question": "Write HTML code to create an ordered list with 3 items: Apple, Banana, Cherry", "options": [], "answer": "<ol><li>Apple</li><li>Banana</li><li>Cherry</li></ol>"},
                {"question": "Trace the output: <ul><li>One</li><li>Two</li></ul> (How many bullets will appear?)", "options": [], "answer": "2 bullets"},
                {"question": "Trace the output: <p style='text-align:center'>Hello</p>", "options": [], "answer": "Text 'Hello' centered"},
                {"question": "Trace the output: <img src='logo.png' alt='Logo'>", "options": [], "answer": "Displays image 'logo.png' with alt text 'Logo'"}
            ]
        },
        "theory": {
            "time_duration": "45 Minutes",
            "marks": 30,
            "questions": [
                {"question": "Define HTML and its purpose in web development.", "options": [], "answer": "HTML (HyperText Markup Language) is used to structure content on the web using elements and tags."},
                {"question": "Explain the difference between block-level and inline elements.", "options": [], "answer": "Block-level elements start on a new line and take full width (<div>, <p>), while inline elements do not start on a new line and take only needed width (<span>, <a>)."},
                {"question": "Describe the structure of an HTML document with its main sections.", "options": [], "answer": "An HTML document has <!DOCTYPE html>, <html>, <head> (meta info, title), <body> (visible content)."},
                {"question": "Explain semantic HTML and provide examples.", "options": [], "answer": "Semantic HTML elements describe meaning: <header>, <footer>, <article>, <section>."},
                {"question": "Explain the use of attributes in HTML tags with examples.", "options": [], "answer": "Attributes provide additional info about elements, e.g., <img src='logo.png' alt='Logo'> where src and alt are attributes."},
                {"question": "Discuss the difference between <div> and <section>.", "options": [], "answer": "<div> is generic container, <section> is semantic section of related content."},
                {"question": "Explain how HTML forms work and their main elements.", "options": [], "answer": "Forms collect user input. Main elements: <form>, <input>, <textarea>, <button>, <select>, <label>."}
            ]
        }
    }
}
}

    quiz_data = all_questions.get(str(course_id), {}).get(str(topic_id), {}).get(type, {})
    questions = quiz_data.get("questions", [])
    time_duration = quiz_data.get("time_duration", "N/A")
    marks = quiz_data.get("marks", "N/A")

    if request.method == "POST":
        user_answers = {}
        correct_count = 0
        results = []

        for i, q in enumerate(questions, start=1):
            selected = request.POST.get(f'answer_{i}')
            correct = q["answer"]
            is_correct = (selected == correct)

            user_answers[i] = selected
            if is_correct:
                correct_count += 1

            results.append({
                "question": q["question"],
                "options": q.get("options", []),
                "selected": selected,
                "correct": correct,
                "is_correct": is_correct,
            })

        total_score = correct_count
        performance_rate = round((correct_count / len(questions)) * 100, 2) if questions else 0

        ai_feedback = ""
        if type in ["mcq","scenario-mcq","code", "theory"]:
            try:
                ai_feedback = generate_ai_feedback(performance_rate, results, topic.name)
            except Exception as e:
                ai_feedback = f"(Feedback unavailable — {str(e)})"

        week_number = datetime.now().isocalendar()[1] % 4  
        if week_number == 0:
            week_number = 4
            
        QuizAttendance.objects.update_or_create(
            student=request.user,
            course=course,
            week=week_number,
            month=datetime.now().month, 
            defaults={
                "attended": True,
                "date": datetime.now()
                }
        )    
        
        context = {
            "course": course,
            "topic": topic,
            "type": type,
            "total_score": total_score,
            "performance_rate": performance_rate,
            "results": results,
            "ai_feedback": ai_feedback,
        }

        return render(request, "accounts/quiz_result.html", context)

    context = {
        "username": request.user.username,
        "course": course,
        "topic": topic,
        "type": type,
        "questions": questions,
        "time_duration": time_duration,
        "marks": marks,
    }
    return render(request, "accounts/quiz_page.html", context)

@login_required(login_url='/accounts/login-page/')
def upload_marks_page(request):
    user = request.user
    courses = Course.objects.filter(usercourse__user=user)  
    return render(request, "accounts/upload_marks.html", {"username": user.username, "courses": courses})


@login_required(login_url='/accounts/login-page/')
@csrf_exempt
def upload_marks_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        student = request.user 
        course = Course.objects.get(id=data['course_id'])

        marks, created = Marks.objects.update_or_create(
            student=student,
            course=course,
            defaults={
                "quiz1": data.get("quiz1", 0),
                "quiz2": data.get("quiz2", 0),
                "quiz3": data.get("quiz3", 0),
                "attendance": data.get("attendance", 0),
                "assignment": data.get("assignment", 0),
                "presentation": data.get("presentation", 0),
                "termexam": data.get("termexam", 0),
            },
        )

        return JsonResponse({"success": True, "message": "Marks saved successfully!"})
    return JsonResponse({"error": "Invalid request"}, status=400)

@login_required(login_url='/accounts/login-page/')
def edit_marks_page(request):
    user = request.user
    courses = Course.objects.filter(usercourse__user=user)
    return render(request, "accounts/edit_marks.html", {"username": user.username, "courses": courses})

@login_required(login_url='/accounts/login-page/')
def get_marks_api(request, course_id):
    user = request.user
    try:
        course = Course.objects.get(id=course_id)
        marks = Marks.objects.filter(student=user, course=course).first()
        if marks:
            data = {
                "quiz1": marks.quiz1,
                "quiz2": marks.quiz2,
                "quiz3": marks.quiz3,
                "attendance": marks.attendance,
                "assignment": marks.assignment,
                "presentation": marks.presentation,
                "termexam": marks.termexam,
            }
        else:
            data = {
                "quiz1": 0, "quiz2":0, "quiz3":0,
                "attendance":0, "assignment":0,
                "presentation":0, "termexam":0
            }
        return JsonResponse({"success": True, "marks": data})
    except Course.DoesNotExist:
        return JsonResponse({"success": False, "message": "Course not found"})


@login_required(login_url='/accounts/login-page/')
@csrf_exempt
def edit_marks_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        student = request.user
        course = Course.objects.get(id=data['course_id'])

        marks, created = Marks.objects.update_or_create(
            student=student,
            course=course,
            defaults={
                "quiz1": data.get("quiz1", 0),
                "quiz2": data.get("quiz2", 0),
                "quiz3": data.get("quiz3", 0),
                "attendance": data.get("attendance", 0),
                "assignment": data.get("assignment", 0),
                "presentation": data.get("presentation", 0),
                "termexam": data.get("termexam", 0),
            },
        )
        return JsonResponse({"success": True, "message": "Marks updated successfully!"})
    return JsonResponse({"success": False, "message": "Invalid request"})

@login_required(login_url='/accounts/login-page/')
def upload_syllabus_page(request):
    user_courses = Course.objects.filter(usercourse__user=request.user)

    if request.method == "POST":
        course_id = request.POST.get("course")
        topic_name = request.POST.get("topic_name")
        lecture_slide = request.FILES.get("lecture_slide")

        if course_id and topic_name and lecture_slide:
            course = Course.objects.get(id=course_id)
            Syllabus.objects.create(
                user=request.user,
                course=course,
                topic_name=topic_name,
                lecture_slide=lecture_slide
            )
            return redirect('upload_syllabus_page')  

    return render(request, "accounts/upload_syllabus.html", {"courses": user_courses})

@login_required(login_url='/accounts/login-page/')
def upload_syllabus(request):
    user_courses = UserCourse.objects.filter(user=request.user).values_list('course', flat=True)
    courses = Course.objects.filter(id__in=user_courses)

    if request.method == 'POST':
        course_id = request.POST.get('course')
        topic_name = request.POST.get('topic_name')
        lecture_slide = request.FILES.get('lecture_slide')

        if not course_id or not topic_name or not lecture_slide:
            messages.error(request, "All fields are required!")
        else:
            course = Course.objects.get(id=course_id)
            Syllabus.objects.create(
                user=request.user,
                course=course,
                topic_name=topic_name,
                lecture_slide=lecture_slide
            )
            messages.success(request, "Syllabus uploaded successfully!")
            return redirect('upload_syllabus_page')

    return render(request, 'accounts/upload_syllabus.html', {'courses': courses})

@login_required(login_url='/accounts/login-page/')
def selected_syllabus(request):
    syllabi = Syllabus.objects.filter(user=request.user).order_by('-uploaded_at')

    for s in syllabi:
        if s.lecture_slide:
            full_name = s.lecture_slide.name         
            filename = full_name.split('/')[-1]   
            ext = filename.split('.')[-1].upper() 

            s.display_name = filename
            s.file_type = ext
        else:
            s.display_name = ""
            s.file_type = ""

    return render(request, 'accounts/selected_syllabus.html', {
        'syllabi': syllabi
    })

@login_required(login_url='/accounts/login-page/')
@require_POST
def delete_syllabus(request, pk):
    s = get_object_or_404(Syllabus, pk=pk, user=request.user)

    if s.lecture_slide:
        s.lecture_slide.delete(save=False)
    s.delete()
    messages.success(request, "Syllabus deleted.")
    return redirect('selected_syllabus_page')

@login_required(login_url='/accounts/login-page/')
def view_syllabus(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk, user=request.user)
    file_path = syllabus.lecture_slide.path
    file_mime, _ = mimetypes.guess_type(file_path)
    response = FileResponse(open(file_path, 'rb'), content_type=file_mime)
    response['Content-Disposition'] = f'inline; filename="{syllabus.lecture_slide.name.split("/")[-1]}"'
    return response

@login_required(login_url='/accounts/login-page/')
def calculate_cgpa_page(request):
    return render(request, 'accounts/calculate_cgpa.html')

#------------ai overall feedback + performance-----------
def generate_overall_ai_feedback(courses, performance_rate, weak_topics=None, average_ai_score=None):
    try:
        course_lines = "\n".join([f"{c['name']}: {c['performance']}%" for c in courses])

        weak_topics = weak_topics or []
        weak_topics_lines = "\n".join(
        [f"{w['topic']}: {w['average']}%" for w in weak_topics]
    ) or "None"

        prompt = f"""
You are an academic performance advisor.

Student overall offline performance: {performance_rate}%
Student AI quiz average: {average_ai_score}%

Course-wise offline performance:
{course_lines}

Weak topics detected from AI quizzes (below 50%):
{weak_topics_lines}

Tasks:
1. Identify courses that need attention (offline performance below 60%) AND any topics listed under "Weak topics detected from AI quizzes" below 50%.
2. Give short, practical improvement advice based on both offline performance and weak AI quiz topics.
3. Predict achievable performance percentage if the student improves steadily.
4. End with a short motivational line.

Rules:
- Keep it concise.
- No paragraphs.
- Use short bullet points.
- Friendly student tone.
- Do not mention AI.
Format exactly like this:

Focus Areas:
- ...

Improvement Advice:
- ...

Prediction:
- ...

Motivation:
- ...
"""

        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)

        try:
            return response.text.strip()
        except AttributeError:
            return str(response).strip()

    except Exception:
        return (
            "Focus Areas:\n"
            "- Overall data insufficient.\n\n"
            "Improvement Advice:\n"
            "- Keep practicing consistently.\n\n"
            "Prediction:\n"
            "- Gradual improvement expected.\n\n"
            "Motivation:\n"
            "- Keep going strong."
        )
#-------------------
from datetime import timedelta
from django.utils.timezone import now
from django.db.models import Avg, F
from django.contrib.auth.decorators import login_required
import json

@login_required(login_url='/accounts/login-page/')
def overall_performance(request):
    user = request.user

    # ==============================
    # Teacher Marks Data
    # ==============================

    student_marks = Marks.objects.filter(student=user)

    marks_data = []
    courses = []

    total_course_scores = []

    for mark in student_marks:

        course_total = (
            mark.quiz1 +
            mark.quiz2 +
            mark.quiz3 +
            mark.attendance +
            mark.assignment +
            mark.presentation +
            mark.termexam
        )

        course_total = round(course_total, 2)

        total_course_scores.append(course_total)

        quiz_average = ((mark.quiz1 + mark.quiz2 + mark.quiz3) / 30) * 100


        marks_data.append({
            "course": mark.course,
            "quiz_average": round(quiz_average, 2),
            "assignment": round((mark.assignment / 10) * 100, 2),
            "presentation": round((mark.presentation / 10) * 100, 2),
            "termexam": round((mark.termexam / 40) * 100, 2),
            "total": course_total,
        })


        courses.append({
            "name": mark.course.name,
            "performance": course_total
        })


    # Overall academic score
    if total_course_scores:
        performance_rate = round(
            sum(total_course_scores) / len(total_course_scores),
            2
        )
    else:
        performance_rate = 0
    # ==============================
    # AI Quiz Data
    # ==============================

    ai_attempts = AIQuizAttempt.objects.filter(
        student=user
    ).order_by("created_at")

    ai_quiz_attempts = ai_attempts.count()

    ai_scores = []

    for quiz in ai_attempts:

        if quiz.max_score > 0:

            percentage = (
                quiz.score /
                quiz.max_score
            ) * 100

            ai_scores.append(round(percentage, 2))

    if ai_scores:

        average_ai_score = round(
            sum(ai_scores) / len(ai_scores),
            2
        )

    else:
        average_ai_score = 0

    # ==============================
    # Offline Improvement
    # ==============================
    offline_improvement = 0

    if student_marks.count() >= 2:

        first = student_marks.order_by(
            "uploaded_at"
        ).first()

        last = student_marks.order_by(
            "uploaded_at"
        ).last()

        first_quiz = (
            first.quiz1 +
            first.quiz2 +
            first.quiz3
        ) / 3

        last_quiz = (
            last.quiz1 +
            last.quiz2 +
            last.quiz3
        ) / 3

        offline_improvement = round(
            last_quiz - first_quiz,
            2
        )
    # ==============================
    # AI Quiz Improvement
    # ==============================
    ai_improvement = 0

    if len(ai_scores) >= 6:

        first_average = sum(
            ai_scores[:3]
        ) / 3

        latest_average = sum(
            ai_scores[-3:]
        ) / 3

        ai_improvement = round(
            latest_average - first_average,
            2
        )

    # ==============================
    # Weak Topic Detection
    # ==============================

    topic_scores = defaultdict(list)
    student_ai_attempts = AIQuizAttempt.objects.filter(
    student=user
    )
    
    for attempt in student_ai_attempts:
        topic = attempt.topic_name if attempt.topic_name else "General"
        topic_scores[topic].append(
            attempt.percentage()
            )
        
        weak_topics = []
        
    for topic, scores in topic_scores.items():
        average = round(
            sum(scores) / len(scores),
            2
        )
            
        if average < 50:
            weak_topics.append({
                "topic": topic,
                "average": average
            })
    # ==============================
    # AI Feedback
    # ==============================

    try:

        ai_overall_feedback = generate_overall_ai_feedback(
            courses,
            performance_rate,
            weak_topics=weak_topics,
            average_ai_score=average_ai_score
        )

    except Exception:

        ai_overall_feedback = (
            "Focus Areas:\n"
            "- Continue practicing regularly.\n\n"
            "Improvement Advice:\n"
            "- Review weak topics.\n\n"
            "Prediction:\n"
            "- Keep improving steadily.\n\n"
            "Motivation:\n"
            "- Good effort, keep going."
        )
    # ==============================
    # Recent AI Quiz History
    # ==============================

    recent_quizzes = AIQuizAttempt.objects.filter(
        student=user
    ).order_by(
        "-created_at"
    )[:10]

    # ==============================
    # Chart Data
    # ==============================
    courses_json = json.dumps(courses)

    context = {
        "student": user,
        # Cards
        "performance_rate": performance_rate,
        "ai_quiz_attempts": ai_quiz_attempts,
        "average_ai_score": average_ai_score,
        "offline_improvement": offline_improvement,
        "ai_improvement": ai_improvement,
        "weak_topics": weak_topics,
        # Tables
        "marks_data": marks_data,
        "recent_quizzes": recent_quizzes,
        # Chart
        "courses": courses,
        "courses_json": courses_json,
        # AI
        "ai_overall_feedback": ai_overall_feedback,
    }


    return render(
        request,
        "accounts/overall_performance.html",
        context
    )
# AIUB grade points mapping
GRADE_POINTS = {
    "A+": 4.00,
    "A": 3.75,
    "B+": 3.50,
    "B": 3.25,
    "C+": 3.00,
    "C": 2.75,
    "D+": 2.50,
    "D": 2.25,
    "F": 0.00
}

@login_required(login_url='/accounts/login-page/')
def current_semester_cg(request):
    courses = []
    cg = None
    total_credits = None

    if request.method == "POST":
        num_courses = int(request.POST.get("num_courses", 0))
        total_points = 0
        total_credits = 0

        for i in range(1, num_courses + 1):
            grade = request.POST.get(f"grade_{i}")
            credits = float(request.POST.get(f"credits_{i}", 0))
            if grade in GRADE_POINTS and credits > 0:
                total_points += GRADE_POINTS[grade] * credits
                total_credits += credits

        if total_credits > 0:
            cg = round(total_points / total_credits, 2)

    return render(request, "accounts/current_semester_cg.html", {
        "courses": courses,
        "cg": cg,
        "total_credits": total_credits,
        "grades": list(GRADE_POINTS.keys())
    })

# -------------- File extraction functions --------------------
def extract_text_from_pdf(file_path):
    """
    Extract text from a PDF file.
    Handles both plain text PDFs and scanned image PDFs using OCR.
    """
    text = ""

    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                else:
                    pil_image = page.to_image(resolution=300).original
                    ocr_text = pytesseract.image_to_string(pil_image)
                    text += ocr_text + "\n"
    except Exception as e:
        text += f"\n[Error reading PDF {os.path.basename(file_path)}: {str(e)}]\n"

    return text

def extract_text_from_docx(file_path):
    text = ""
    try:
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            if para.text.strip():
                text += para.text + "\n"
    except Exception as e:
        text += f"\n[Error reading DOCX {os.path.basename(file_path)}: {str(e)}]\n"
    return text

def extract_text_from_pptx(file_path):
    text = ""
    try:
        prs = Presentation(file_path)
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    text += shape.text + "\n"
                if shape.has_table:
                    for row in shape.table.rows:
                        for cell in row.cells:
                            if cell.text.strip():
                                text += cell.text + "\n"
    except Exception as e:
        text += f"\n[Error reading PPTX {os.path.basename(file_path)}: {str(e)}]\n"
    return text

def extract_text_from_excel(file_path):
    text = ""
    wb = openpyxl.load_workbook(file_path)
    
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            row_text = [str(cell) for cell in row if cell is not None]
            if row_text:
                text += "\t".join(row_text) + "\n"
 
        for image in sheet._images:
            img_bytes = image._data() 
            pil_image = Image.open(BytesIO(img_bytes))
            ocr_text = pytesseract.image_to_string(pil_image)
            if ocr_text.strip():
                text += "\n[Image Text]: " + ocr_text + "\n"

    return text

def extract_text_from_image(file_path):
    """
    Extract text from an image or screenshot using OCR.
    Supports PNG, JPG, JPEG, BMP, etc.
    """
    text = ""
    try:
        img = Image.open(file_path)
        ocr_text = pytesseract.image_to_string(img)
        if ocr_text.strip():
            text += ocr_text
        else:
            text += "[No text detected in image]"
    except Exception as e:
        text += f"\n[Error reading image {os.path.basename(file_path)}: {str(e)}]\n"
    return text
# -------------------- Aggregate all syllabus content --------------------
def get_syllabus_text(user):
    """Return all text from all syllabus files for this user."""
    syllabi = Syllabus.objects.filter(user=user)
    full_text = ""
    for s in syllabi:
        path = s.lecture_slide.path
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            full_text += extract_text_from_pdf(path) + "\n"
        elif ext == ".docx":
            full_text += extract_text_from_docx(path) + "\n"
        elif ext == ".pptx":
            full_text += extract_text_from_pptx(path) + "\n"
        elif ext == ".xlsx": 
            full_text += extract_text_from_excel(path) + "\n"
        elif ext in [".png", ".jpg", ".jpeg", ".bmp"]:
            full_text += extract_text_from_image(path) + "\n"
        else:
            full_text += f"\n[Unsupported file type {s.lecture_slide.name} skipped]\n"
    return full_text

# -------------------- AI Assistant view --------------------
@login_required(login_url='/accounts/login-page/')
def ai_assistant(request):
    user_prompt = ""

    if 'conversation' not in request.session:
        request.session['conversation'] = []

    if request.method == "POST":
        user_prompt = request.POST.get("prompt", "").strip()
        if user_prompt:
            conversation_history = request.session.get('conversation', [])

            syllabus_text = get_syllabus_text(request.user)
            full_prompt = f"""You are an AI tutor with full general knowledge and syllabus awareness.  
Use the syllabus text below when the user's question is related to the course.  
If the question is NOT related to the syllabus, answer normally using your full capabilities.
Syllabus content:
{syllabus_text}
Conversation so far:
"""
            for msg in conversation_history:
                full_prompt += f"{msg['role']}: {msg['content']}\n"
            full_prompt += f"user: {user_prompt}"

            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                result = model.generate_content(full_prompt)
                ai_raw_response = result.text
                ai_response = markdown2.markdown(
                    ai_raw_response,
                    extras=["fenced-code-blocks", "break-on-newline"]
                )

            except Exception as e:
                ai_response = f"⚠️ Error generating AI response: {str(e)}"

            conversation_history.append({'role': 'user', 'content': user_prompt})
            conversation_history.append({'role': 'ai', 'content': ai_response})
            request.session['conversation'] = conversation_history

    return render(request, "accounts/ai_assistant.html", {
        "conversation": request.session.get('conversation', []),
        "prompt": user_prompt
    })

#-------------------
def tools_page(request):
    user = request.user
    return render(request, "accounts/tools_page.html",{
        "username": user.username
    })
#-------------------------------
def get_course_syllabus_text(course, user, filename=None):
    syllabi = Syllabus.objects.filter(course=course, user=user)
    if filename:
        syllabi = syllabi.filter(lecture_slide__icontains=filename)

    text = ""
    for s in syllabi:
        if not s.lecture_slide:
            continue
        path = s.lecture_slide.path
        if not os.path.exists(path):
            continue
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            text += extract_text_from_pdf(path)
        elif ext == ".docx":
            text += extract_text_from_docx(path)
        elif ext == ".pptx":
            text += extract_text_from_pptx(path)
        elif ext in [".png", ".jpg", ".jpeg"]:
            text += extract_text_from_image(path)
        text += "\n"

    return text[:12000]

# AI Quiz Page
@login_required(login_url='/accounts/login-page/')
def ai_quiz_page(request):
    sync_student_courses_from_teacher_uploads(request.user)
    courses = Course.objects.filter(usercourse__user=request.user)
    topics = Syllabus.objects.filter(user=request.user).values_list("lecture_slide", flat=True).distinct()
    topics = [os.path.basename(t) for t in topics if t]

    return render(request, "accounts/ai_quiz.html", {
        "courses": courses,
        "topics": topics
    })

# Generate AI Quiz
@login_required(login_url='/accounts/login-page/')
def generate_ai_quiz(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Invalid request method"})

    data = json.loads(request.body)
    course_id = data.get("course_id")
    filename = data.get("topic_name")
    instruction = data.get("instruction", "").strip()

    if not course_id:
        return JsonResponse({"status": "error", "message": "Course not selected"})

    try:
        course = Course.objects.get(
            id=int(course_id),
            usercourse__user=request.user
        )
    except Course.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Course not found"})

    syllabus_text = get_course_syllabus_text(course, request.user, filename)

    if not syllabus_text.strip():
        return JsonResponse({"status": "error", "message": "No syllabus content found for this topic"})

    # instruction is REQUIRED for controlling output
    if not instruction:
        return JsonResponse({
            "status": "error",
            "message": "Please specify what you want the AI to generate"
        })

    prompt = f"""
Follow the user's instruction EXACTLY.
Especially the number of questions requested.

Each MCQ must include:
- question_text
- options a, b, c, d
- correct_answer (a/b/c/d)
- marks = 1

Return ONLY a valid JSON array.
No markdown. No explanation.

USER INSTRUCTION:
{instruction}

SYLLABUS CONTENT:
{syllabus_text}
"""

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)

        raw = response.text.strip()
        raw = raw.replace("```json", "").replace("```", "")
        questions = json.loads(raw)

        return JsonResponse({
            "status": "success",
            "questions": questions
        })

    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        })
    
#------------------------------     
from .models import (
    AIQuizAttempt,
    TeacherNotification,
    Section
)

def check_ai_quiz_decline(student, course):

    # ==========================
    # Last 3 AI Quiz Attempts
    # ==========================

    attempts = AIQuizAttempt.objects.filter(
        student=student,
        course=course
    ).order_by('-created_at')[:3]


    if attempts.count() < 3:
        return


    scores = [
        attempt.percentage()
        for attempt in reversed(attempts)
    ]


    print("LAST 3 SCORES:", scores)


    # ==========================
    # Rule 1: Continuous Decline
    # Example: 100, 80, 60
    # ==========================

    continuous_decline = (
        scores[0] > scores[1] > scores[2]
    )


    # ==========================
    # Rule 2: Critical Failure
    # Example: 60, 0, 0
    # ==========================

    critical_failure = (
        scores[1] == 0 and
        scores[2] == 0
    )


    # ==========================
    # Rule 3: Last 5 Quiz Average
    # ==========================

    last_five_attempts = AIQuizAttempt.objects.filter(
        student=student,
        course=course
    ).order_by('-created_at')[:5]


    last_five_scores = [
        attempt.percentage()
        for attempt in reversed(last_five_attempts)
    ]


    low_average = False
    average = 0


    if len(last_five_scores) == 5:

        average = round(
            sum(last_five_scores) / 5,
            2
        )

        if average < 40:
            low_average = True

    # ==========================
    # Rule 4: Sudden Performance Drop
    # ==========================

    sudden_drop = False
    previous_average = 0
    current_score = scores[-1]

    all_attempts = AIQuizAttempt.objects.filter(
        student=student,
        course=course
        ).order_by(
            'created_at'
        )


    if all_attempts.count() >= 4:
        all_attempts = list(all_attempts)
        previous_scores = [
            attempt.percentage()
            for attempt in all_attempts[:-1]
        ]

        previous_average = round(
            sum(previous_scores) /
            len(previous_scores),
            2
        )

        drop_difference = (previous_average - current_score)
        
        if drop_difference > 30:
            sudden_drop = True

    # ==========================
    # If no risk detected
    # ==========================

    if not (
        continuous_decline
        or critical_failure
        or low_average
        or sudden_drop
    ):
        return

    # ==========================
    # Find Teacher
    # ==========================

    section = Section.objects.filter(
        course=course,
        section_name="A"
    ).first()

    if not section:

        print("No section found")
        return

    teacher = section.teacher

    # ==========================
    # Alert Reason
    # ==========================

    reason = ""

    if continuous_decline:

        reason += (
            "Continuous score decline detected.\n"
        )

    if critical_failure:

        reason += (
            "Two consecutive zero-score attempts detected.\n"
        )

    if low_average:

        reason += (
            f"Average of last five quizzes is {average}% "
            "which is below 40%.\n"
        )

    if sudden_drop:

        reason += (
            f"Sudden performance drop detected. "
            f"Previous average: {previous_average}%, "
            f"Current score: {current_score}%.\n"
        )
    # ==========================
    # Prevent Duplicate Alert
    # ==========================

    existing_alert = TeacherNotification.objects.filter(
        teacher=teacher,
        student=student,
        course=course,
        resolved=False
    ).exists()

    if existing_alert:

        print("Alert already exists")
        return
    # ==========================
    # Risk Classification
    # ==========================

    risk_level = "Low Risk"
    
    if (
        critical_failure
        or low_average
    ):
        risk_level = "High Risk"
        
    elif (
        continuous_decline
        or sudden_drop
    ):
        risk_level = "Medium Risk"
        
    # ==========================
    # Create Notification
    # ==========================

    TeacherNotification.objects.create(
        teacher=teacher,
        student=student,
        course=course,
        semester=section.semester,
        section=section.section_name,
        title="Performance Alert",
        message=(
            f"Recent AI quiz scores:\n"
            f"{scores[0]}%, {scores[1]}%, {scores[2]}%\n\n"
            f"Alert Reason:\n"
            f"{reason}\n"
            "Please review the student's progress "
            "and provide guidance."
        )
    )

    print("Teacher notification created")
#------------------------------
@login_required(login_url='/accounts/login-page/')
def submit_ai_quiz(request):
    data = json.loads(request.body)
    total = 0
    max_total = 0
    detailed_feedback = []
    evaluation_data = []
    syllabus_cache = {} 

    for q in data.get("questions", []):
        marks = q.get("marks", 1)
        max_total += marks
        student_answer = q.get("student_answer")
        correct_answer = q.get("correct_answer")
        filename = data.get("topic_name")

        is_correct = student_answer == correct_answer
        if is_correct:
            total += marks

        if filename not in syllabus_cache:
            syllabus_cache[filename] = get_course_syllabus_text(
                Course.objects.get(id=data.get("course_id")),
                user=request.user,
                filename=filename
            )
        syllabus_text = syllabus_cache[filename]

        if not is_correct and student_answer:
            #explanation = f"Review the following key points from the syllabus:\n{syllabus_text[:1000]}."
            explanation = f"You wronged question."
        elif is_correct:
            explanation = f"Answered correctly."
        else:
            explanation = f"You did not answer this question."

        detailed_feedback.append({
            "question_text": q.get("question_text"),
            "student_answer": student_answer,
            "correct_answer": correct_answer,
            "is_correct": is_correct,
            "explanation": explanation
        })
        evaluation_data.append({
            "topic": filename,
            "question": q.get("question_text"),
            "student_answer": student_answer,
            "correct_answer": correct_answer,
            "status": "Correct" if is_correct else "Wrong"
            })     
        
    attempt = AIQuizAttempt.objects.create(
        student=request.user,
        course_id=data.get("course_id"),
        topic_name=data.get("topic_name"),
        score=total,
        max_score=max_total
        )
# Check performance decline
    check_ai_quiz_decline(
        request.user,
        attempt.course
    )

    from .ai_feedback import generate_performance_feedback
    
    ai_feedback = generate_performance_feedback(
        evaluation_data
        )

    return JsonResponse({
         "status":"success",
         "total_marks":total,
         "max_marks":max_total,
         "detailed_feedback":detailed_feedback,
         "ai_feedback":ai_feedback
})

#progress
@login_required(login_url='/accounts/login-page/')
def student_progress(request):
    student = request.user

    attempts = AIQuizAttempt.objects.filter(
        student=student
    ).order_by('created_at')

    progress_data = defaultdict(lambda: defaultdict(list))

    weak_topics = []
    
    for course in Course.objects.filter(
        aiquizattempt__student=student
        ).distinct():
        
        result = detect_weak_topics(
            student,
            course
        )
        
        for item in result:
            weak_topics.append({
                "course": course.name,
                "topic": item["topic"],
                "average": item["average"]
            })

    for attempt in attempts:
        course = attempt.course.name
        topic = attempt.topic_name if attempt.topic_name else "General"

        progress_data[course][topic].append({
            "score": attempt.percentage(),
            "date": attempt.created_at.strftime("%Y-%m-%d")
        })

    context = {
        "username": student.username,
        "progress_json": json.dumps(progress_data),
        "weak_topics": weak_topics
    }

    return render(request, "accounts/student_progress.html", context)

# teacher Dashboard page (protected)
@login_required(login_url='/accounts/login-page/')
def teacher_dashboard(request):
    teacher_redirect = require_teacher_page(request)
    if teacher_redirect:
        return teacher_redirect

    user = request.user
    unread_alerts_count = TeacherNotification.objects.filter(
        teacher=user, is_read=False
    ).count()

    context = {
        "username": user.username,
        "role": getattr(user, "role", "N/A"),
        "unread_alerts_count": unread_alerts_count,
    }
    return render(request, "accounts/teacher_dashboard.html", context)

# ---------- Teacher Course Selection Page ----------
@login_required(login_url='/accounts/login-page/')
def teacher_course_selection_page(request):
    teacher_redirect = require_teacher_page(request)
    if teacher_redirect:
        return teacher_redirect

    user = request.user
    ensure_aiub_courses_exist()
    courses = Course.objects.order_by("name")

    selections = TeacherCourseSelection.objects.filter(teacher=user)
    # Dict: { "Spring": ["CSE101", "CSE102"], "Fall": ["CSE201"] }
    semester_courses = {
        sel.semester: list(sel.courses.values_list('code', flat=True))
        for sel in selections
    }
    context = {
        "courses": courses,
        "semester_courses_json": json.dumps(semester_courses),  # for JS
        "username": user.username,
    }
    return render(request, "accounts/teacher_course_selection.html", context)


def _ensure_course_catalog_loaded():
    """Populate the course table on demand if a deployed DB starts empty."""
    if Course.objects.exists():
        return

    # Only do this when the catalog table is genuinely empty.
    try:
        from django.core.management import call_command
        call_command("import_course_catalog")
    except Exception:
        # Fall back to the empty page; the next request will try again.
        pass

@csrf_exempt
@login_required(login_url='/accounts/login-page/')
def save_teacher_courses_api(request):
    if not is_teacher(request.user):
        return JsonResponse({"success": False, "message": "Please log in with a Teacher account."}, status=403)

    if request.method == "POST":
        try:
            ensure_aiub_courses_exist()
            data = json.loads(request.body)
            semester = data.get("semester")
            selected_codes = data.get("courses", [])

            if not semester or not isinstance(selected_codes, list):
                return JsonResponse({"success": False, "message": "Invalid data"})

            user = request.user
            selection, _ = TeacherCourseSelection.objects.get_or_create(
                teacher=user, semester=semester
            )
            courses = Course.objects.filter(code__in=selected_codes)
            selection.courses.set(courses)
            selection.save()

            return JsonResponse({
                "success": True,
                "message": f"Saved {len(selected_codes)} course(s) for {semester}.",
                "semester": semester,
                "courses": selected_codes
            })

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)})

    return JsonResponse({"success": False, "message": "Invalid request"})

@login_required(login_url='/accounts/login-page/')
def teacher_selected_courses_page(request):
    teacher_redirect = require_teacher_page(request)
    if teacher_redirect:
        return teacher_redirect

    user = request.user
    selections = TeacherCourseSelection.objects.filter(teacher=user)
    return render(request, "accounts/teacher_selected_courses.html", {
        "username": user.username,
        "selections": selections
    })
#----------------------
@login_required(login_url='/accounts/login-page/')
def upload_student_info_page(request):
    teacher_redirect = require_teacher_page(request)
    if teacher_redirect:
        return teacher_redirect

    user = request.user
    selections = TeacherCourseSelection.objects.filter(teacher=user)

    semester_courses_dict = {}
    for sel in selections:
        course_list = list(sel.courses.values_list('name', flat=True))
        semester_courses_dict[sel.semester] = course_list

    if request.method == "POST":
        semester = request.POST.get('semester')
        course_name = request.POST.get('course')
        section_name = request.POST.get('section')
        student_file = request.FILES.get('studentFile')

        if not (semester and course_name and section_name and student_file):
            messages.error(request, "All fields are required!")
            return redirect('upload_student_info_page')

        try:
            course_obj = Course.objects.get(name=course_name)
        except Course.DoesNotExist:
            messages.error(request, f"Course '{course_name}' not found!")
            return redirect('upload_student_info_page')

        try:
            parsed_rows = parse_student_info_file(student_file)
            student_rows = []
            skipped = 0

            for row in parsed_rows:
                student_name = (row.get('student_name') or row.get('name') or "").strip()
                student_id = (row.get('student_id') or row.get('id') or "").strip()
                email = (row.get('email') or row.get('student_email') or "").strip().lower()
                if not student_name or not student_id or not email:
                    skipped += 1
                    continue  

                student_rows.append({
                    "student_name": student_name,
                    "student_id": student_id,
                    "email": email,
                })

            if not student_rows:
                messages.error(
                    request,
                    "No valid students found. Use columns: student_name, student_id, email."
                )
                return redirect('upload_student_info_page')

            with transaction.atomic():
                section_obj, _ = Section.objects.get_or_create(
                    teacher=user,
                    semester=semester,
                    course=course_obj,
                    section_name=section_name
                )
                section_obj.students.all().delete()
                StudentInfo.objects.bulk_create([
                    StudentInfo(section=section_obj, **student_row)
                    for student_row in student_rows
                ])

            messages.success(
                request,
                f"Successfully replaced and uploaded {len(student_rows)} students for {course_name} ({section_name}) - {semester}. Skipped {skipped} invalid row(s)."
            )
            return redirect('upload_student_info_page')

        except Exception as e:
            messages.error(request, f"Error processing CSV file: {str(e)}")
            return redirect('upload_student_info_page')

    from collections import defaultdict
    
    semester_course_sections = defaultdict(dict)
    sections = Section.objects.filter(
        teacher=user
        ).select_related("course")
    
    for section in sections:
        semester = section.semester
        course = section.course.name
        semester_course_sections.setdefault(semester, {})
        semester_course_sections[semester].setdefault(course, [])
        semester_course_sections[semester][course].append(section.section_name)

    context = {
        "username": user.username,
        "semester_courses_dict": semester_courses_dict,
        "semester_courses_json": json.dumps(semester_courses_dict),  
        "semester_course_sections_json": json.dumps(semester_course_sections),
    }
    return render(request, "accounts/upload_student_info.html", context)

@login_required(login_url='/accounts/login-page/')
def uploaded_students_page(request):
    teacher_redirect = require_teacher_page(request)
    if teacher_redirect:
        return teacher_redirect

    user = request.user

    sections = (
        Section.objects.filter(teacher=user)
        .select_related('course')
        .prefetch_related('students')
        .order_by('semester', 'course__name', 'section_name')
    )

    data = {}
    for section in sections:
        sem = section.semester
        course = section.course.name
        sec_name = section.section_name
        students = section.students.all()

        if sem not in data:
            data[sem] = {}
        if course not in data[sem]:
            data[sem][course] = {}
        data[sem][course][sec_name] = students

    context = {
        "username": user.username,
        "uploaded_data": data
    }

    return render(request, "accounts/uploaded_students.html", context)

@login_required(login_url='/accounts/login-page/')
def delete_section(request):
    teacher_redirect = require_teacher_page(request)
    if teacher_redirect:
        return teacher_redirect

    if request.method == "POST":
        user = request.user
        semester = request.POST.get('semester')
        course_name = request.POST.get('course')
        section_name = request.POST.get('section')

        try:
            course_obj = Course.objects.get(name=course_name)
            section = Section.objects.get(
                teacher=user,
                semester=semester,
                course=course_obj,
                section_name=section_name
            )
            section.delete()  
            messages.success(request, f"Deleted section {section_name} ({course_name}) successfully!")
        except Section.DoesNotExist:
            messages.error(request, "Section not found or you don't have permission!")

    return redirect('uploaded_students_page')

def get_teacher_semester_courses(user):
    selections = TeacherCourseSelection.objects.filter(teacher=user)
    semester_courses = {}
    for sel in selections:
        course_list = list(sel.courses.values_list('name', flat=True))
        semester_courses[sel.semester] = course_list
    return semester_courses

@login_required(login_url='/accounts/login-page/')
def teacher_post_marks_page(request):
    """
    Teacher page to upload marks via CSV for a selected semester/course/section.
    Automatically replaces old marks for same semester/course/section uploaded by same teacher.
    CSV expected columns:
      student_email or student_name, quiz1, quiz2, quiz3, attendance, assignment, presentation, termexam
    Missing numeric fields default to 0.
    """
    user = request.user
    semester_courses_dict = get_teacher_semester_courses(user)
    section_choices = ["A", "B", "C", "D", "E", "F"]

    if request.method == "POST":
        semester = request.POST.get('semester')
        course_name = request.POST.get('course')
        section_name = request.POST.get('section')
        csv_file = request.FILES.get('marksFile')

        if not (semester and course_name and section_name and csv_file):
            messages.error(request, "All fields are required (semester, course, section, and CSV file).")
            return redirect('teacher_post_marks_page')
        try:
            course_obj = Course.objects.get(name=course_name)
        except Course.DoesNotExist:
            messages.error(request, f"Course '{course_name}' not found.")
            return redirect('teacher_post_marks_page')

        section_obj, _ = Section.objects.get_or_create(
            teacher=user,
            semester=semester,
            course=course_obj,
            section_name=section_name
        )

        try:
            decoded = csv_file.read().decode('utf-8')
            io_string = io.StringIO(decoded)
            reader = csv.DictReader(io_string)

            inserted = 0
            updated = 0
            from django.contrib.auth import get_user_model
            User = get_user_model()
            old_marks = Marks.objects.filter(
                course=course_obj,
                semester=semester,
                section=section_name
                )
            
            # Save old marks into history before deleting
            for old_mark in old_marks:
                MarksHistory.objects.create(
                    student=old_mark.student,
                    course=old_mark.course,
                    quiz1=old_mark.quiz1,
                    quiz2=old_mark.quiz2,
                    quiz3=old_mark.quiz3,

                    attendance=old_mark.attendance,
                    assignment=old_mark.assignment,
                    presentation=old_mark.presentation,
                    termexam=old_mark.termexam,

                    semester=old_mark.semester,
                    section=old_mark.section
                )

            # Now remove old marks
            old_marks.delete()

            with transaction.atomic():
                for row in reader:
                    email = (row.get('student_email') or row.get('email') or "").strip().lower()
                    student_name = (row.get('student_name') or row.get('name') or "").strip()

                    student_user = None
                    student_info = None

                    if email:
                        try:
                            student_user = User.objects.get(email=email)
                            student_info = StudentInfo.objects.filter(email=email, section=section_obj).first()
                        except User.DoesNotExist:
                            student_user = None

                    if not student_user and student_name:
                        student_info = StudentInfo.objects.filter(
                            student_name__iexact=student_name,
                            section=section_obj
                        ).first()
                        if student_info and student_info.email:
                            student_user = User.objects.filter(email=student_info.email).first()

                    if not student_user:
                        continue 
                    def to_float(v):
                        try:
                            return float(v)
                        except Exception:
                            return 0.0

                    quiz1 = to_float(row.get('quiz1') or row.get('quiz_1') or row.get('q1'))
                    quiz2 = to_float(row.get('quiz2') or row.get('quiz_2') or row.get('q2'))
                    quiz3 = to_float(row.get('quiz3') or row.get('quiz_3') or row.get('q3'))
                    attendance = to_float(row.get('attendance') or row.get('att'))
                    assignment = to_float(row.get('assignment') or row.get('assign'))
                    presentation = to_float(row.get('presentation') or row.get('presentation_score') or row.get('present'))
                    termexam = to_float(row.get('termexam') or row.get('term_exam') or row.get('final'))

                    Marks.objects.create(
                        student=student_user,
                        course=course_obj,
                        semester=semester,
                        section=section_name,
                        quiz1=quiz1,
                        quiz2=quiz2,
                        quiz3=quiz3,
                        attendance=attendance,
                        assignment=assignment,
                        presentation=presentation,
                        termexam=termexam,
                        published=False
                    )
                    inserted += 1

            messages.success(
                request,
                f"Marks uploaded successfully for {course_name} (Sem {semester}, Sec {section_name}). "
                f"Old marks replaced with {inserted} new entries."
            )
            return redirect('teacher_post_marks_page')

        except Exception as e:
            messages.error(request, f"Error processing CSV: {str(e)}")
            return redirect('teacher_post_marks_page')
        
    from collections import defaultdict
    
    semester_course_sections = defaultdict(dict)
    sections = Section.objects.filter(
        teacher=user
        ).select_related("course")
    
    for section in sections:
        semester = section.semester
        course = section.course.name
        semester_course_sections.setdefault(semester, {})
        semester_course_sections[semester].setdefault(course, [])
        semester_course_sections[semester][course].append(section.section_name)

    context = {
        "username": user.username,
        "semester_courses_dict": semester_courses_dict,
        "semester_courses_json": json.dumps(semester_courses_dict),
        "semester_course_sections_json": json.dumps(semester_course_sections),
    }
    return render(request, 'accounts/teacher_post_marks.html', context)

@login_required(login_url='/accounts/login-page/')
def publish_marks(request):
    """
    Publish marks for a given semester/course/section (POST).
    This will set published=True for all Marks objects for that course and for students in that section.
    """
    if request.method != "POST":
        return redirect('teacher_post_marks_page')

    user = request.user
    semester = request.POST.get('semester')
    course_name = request.POST.get('course')
    section_name = request.POST.get('section')

    if not (semester and course_name and section_name):
        messages.error(request, "Semester, course and section required to publish marks.")
        return redirect('teacher_post_marks_page')

    try:
        course_obj = Course.objects.get(name=course_name)
    except Course.DoesNotExist:
        messages.error(request, "Course not found.")
        return redirect('teacher_post_marks_page')

    try:
        section_obj = Section.objects.get(teacher=user, semester=semester, course=course_obj, section_name=section_name)
    except Section.DoesNotExist:
        messages.error(request, "Section not found.")
        return redirect('teacher_post_marks_page')

    student_infos = StudentInfo.objects.filter(section=section_obj)
    user_emails = [s.email for s in student_infos if s.email]

    from django.contrib.auth import get_user_model
    User = get_user_model()
    students_qs = User.objects.filter(email__in=user_emails)
    marks_qs = Marks.objects.filter(course=course_obj, student__in=students_qs)
    updated = marks_qs.update(published=True)

    messages.success(request, f"Published marks for {section_name} ({course_name}) — {updated} mark rows published.")
    return redirect('teacher_post_marks_page')

@login_required(login_url='/accounts/login-page/')
def student_my_marks_page(request):
    """
    Student view: show only published Marks for the logged-in student.
    """
    user = request.user
    if hasattr(user, 'role') and user.role != 'Student':
        pass

    marks = Marks.objects.filter(student=user, published=True).select_related('course').order_by('course__name')

    return render(request, 'accounts/student_my_marks.html', {
        'username': user.username,
        'marks': marks
    })

@login_required(login_url='/accounts/login-page/')
def teacher_uploaded_marks_page(request):
    """
    Show marks uploaded/published by the teacher, filtered by semester, course, and section.
    Uses semester and section stored in Marks model itself.
    """
    user = request.user
    teacher_marks = Marks.objects.filter(course__section__teacher=user)

    semesters = teacher_marks.values_list('semester', flat=True).distinct()
    courses = Course.objects.filter(id__in=teacher_marks.values_list('course', flat=True).distinct())
    sections = teacher_marks.values_list('section', flat=True).distinct()

    selected_sem = request.GET.get('semester')
    selected_course_id = request.GET.get('course')
    selected_section = request.GET.get('section')

    marks = Marks.objects.none()  
    selected_course_name = None

    if selected_course_id:
        try:
            course_obj = Course.objects.get(id=selected_course_id)
            selected_course_name = course_obj.name

            if selected_sem and selected_section:
                marks = teacher_marks.filter(
                    course=course_obj,
                    semester=selected_sem,
                    section=selected_section
                ).select_related('student', 'course')

        except Course.DoesNotExist:
            selected_course_name = None
            marks = Marks.objects.none()

    context = {
        'username': user.username,
        'semesters': semesters,
        'courses': courses,
        'sections': sections,
        'marks': marks,
        'selected_sem': selected_sem,
        'selected_course_id': int(selected_course_id) if selected_course_id else None,
        'selected_section': selected_section,
        'selected_course_name': selected_course_name,
    }

    return render(request, 'accounts/teacher_published_marks.html', context)
#----------------------
@login_required(login_url='/accounts/login-page/')
def teacher_view_performance(request):

    sections = Section.objects.filter(
        teacher=request.user
    ).order_by(
        'semester',
        'course__name',
        'section_name'
    )

    context = {
        "username": request.user.username,
        "sections": sections
    }

    return render(
        request,
        "accounts/teacher_view_performance.html",
        context
    )

@login_required(login_url='/accounts/login-page/')
def teacher_student_list(request, section_id):

    section = Section.objects.get(
        id=section_id,
        teacher=request.user
    )

    students = section.students.all()

    return render(
        request,
        "accounts/student_list_modal.html",
        {
            "section": section,
            "students": students
        }
    )

import json

@login_required(login_url='/accounts/login-page/')
def student_performance_detail(request, email, course_id):

    student = User.objects.get(
        email=email
    )

    course = Course.objects.get(
        id=course_id
    )
    # ==========================
    # Offline Performance
    # ==========================

    marks = Marks.objects.filter(
        student=student,
        course=course
    ).select_related(
        "course"
    )
    # ==========================
    # Online AI Performance
    # (ONLY THIS COURSE)
    # ==========================

    ai_attempts_queryset = AIQuizAttempt.objects.filter(
        student=student,
        course=course
    ).order_by(
        #"topic_name",
        "created_at"
    )

    total_ai_attempts = ai_attempts_queryset.count()

    if total_ai_attempts > 0:

        avg_ai_score = round(
            sum(
                attempt.percentage()
                for attempt in ai_attempts_queryset
            )
            /
            total_ai_attempts,
            2
        )
        latest_ai = ai_attempts_queryset.last()

    else:

        avg_ai_score = 0
        latest_ai = None

    # AI Learning Trend (Grouped by Topic)
    # ==========================

    from collections import defaultdict
    learning_trend = defaultdict(list)
    
    for attempt in ai_attempts_queryset:
        learning_trend[
            attempt.topic_name or "General"
            ].append({
                 "score": attempt.percentage(),
                 "date": attempt.created_at.strftime("%Y-%m-%d %H:%M:%S")
                })    

    print("======== LEARNING TREND ========")
    print(dict(learning_trend))
    print("================================")
    # ==========================
    # Course Wise Combined Result
    # Offline + AI
    # ==========================

    course_scores = []

    # Offline score

    for mark in marks:

        offline_average = (

            mark.quiz1 +
            mark.quiz2 +
            mark.quiz3 +
            mark.assignment +
            mark.presentation +
            mark.termexam

        ) / 6
        course_scores.append(
            offline_average
        )
    # AI score

    for attempt in ai_attempts_queryset:

        course_scores.append(
            attempt.percentage()
        )
    if course_scores:

        combined_average = round(
            sum(course_scores) /
            len(course_scores),
            2
        )

    else:

        combined_average = 0

    course_wise_result = [

        {
            "course": course.name,
            "average": combined_average
        }

    ]

    context = {

        "student": student,
        # Offline
        "marks": marks,
        # AI Online
        "ai_attempts": total_ai_attempts,
        "avg_ai_score": avg_ai_score,
        "latest_ai": latest_ai,
        # Chart data
        "learning_trend": json.dumps(dict(learning_trend)),
        # Combined
        "course_wise_result": course_wise_result,
    }
    return render(
        request,
        "accounts/student_performance_modal.html",
        context
    )
#----------------------
@login_required(login_url='/accounts/login-page/')
def teacher_upload_syllabus(request):
    teacher = request.user

    semester_courses_qs = TeacherCourseSelection.objects.filter(teacher=teacher).prefetch_related('courses')
    semesters = semester_courses_qs.values_list('semester', flat=True).distinct()

    courses = set()
    for sc in semester_courses_qs:
        for c in sc.courses.all():
            courses.add((c.id, c.name))  
    courses = list(courses)

    sections = Section.objects.filter(teacher=teacher).values_list('section_name', flat=True).distinct()

    if request.method == "POST":
        semester = request.POST.get("semester")
        course_id = request.POST.get("course")
        section = request.POST.get("section")
        syllabus_file = request.FILES.get("syllabus_file")

        if not (semester and course_id and section and syllabus_file):
            messages.error(request, "All fields are required!")
            return redirect("teacher_upload_syllabus")

        existing = TeacherSyllabusUpload.objects.filter(
            teacher=teacher,
            semester=semester,
            course_id=course_id,
            section=section
        ).first()

        if existing:
            existing.syllabus_file.delete()
            existing.delete()

        TeacherSyllabusUpload.objects.create(
            teacher=teacher,
            semester=semester,
            course_id=course_id,
            section=section,
            syllabus_file=syllabus_file
        )

        messages.success(request, "Syllabus uploaded successfully!")
        return redirect("teacher_upload_syllabus")

    context = {
        "username": teacher.username,
        "semesters": semesters,
        "courses": courses,
        "sections": sections,
    }
    return render(request, "accounts/teacher_upload_syllabus.html", context)

#
@login_required(login_url='/accounts/login-page/')
def student_view_syllabus(request):
    user = request.user
    assigned_sections = sync_student_courses_from_teacher_uploads(user)

    syllabus_uploads = TeacherSyllabusUpload.objects.none()
    for section in assigned_sections:
        section_uploads = TeacherSyllabusUpload.objects.filter(
            teacher=section.teacher,
            semester=section.semester,
            course=section.course,
            section=section.section_name,
        )
        syllabus_uploads = syllabus_uploads | section_uploads

    syllabus_uploads = syllabus_uploads.select_related("teacher", "course").order_by(
        "-uploaded_at"
    )

    return render(request, "accounts/student_view_syllabus.html", {
        "syllabus": syllabus_uploads,
        "username": user.username
    })

@login_required(login_url='/accounts/login-page/')
def teacher_my_syllabus(request):

    syllabi = TeacherSyllabusUpload.objects.filter(
        teacher=request.user
    ).select_related(
        "course"
    ).order_by("-uploaded_at")

    return render(
        request,
        "accounts/teacher_my_syllabus.html",
        {
            "username": request.user.username,
            "syllabi": syllabi,
        },
    )

#---teacher notifications---
@login_required(login_url='/accounts/login-page/')
def teacher_notifications(request):

    notifications = TeacherNotification.objects.filter(
        teacher=request.user
    ).order_by('-created_at')

    unread_notifications = notifications.filter(is_read=False)
    unread_notifications.update(is_read=True)

    context = {
        "notifications": notifications
    }
    return render(
        request,
        "accounts/teacher_notifications.html",
        context
    )

#----------------------
def detect_weak_topics(student, course):

    attempts = AIQuizAttempt.objects.filter(
        student=student,
        course=course
    )


    topic_scores = {}


    for attempt in attempts:

        topic = attempt.topic_name or "General"

        percentage = attempt.percentage()


        if topic not in topic_scores:
            topic_scores[topic] = []


        topic_scores[topic].append(
            percentage
        )


    weak_topics = []


    for topic, scores in topic_scores.items():

        average = round(
            sum(scores) / len(scores),
            2
        )


        if average < 50:

            weak_topics.append({
                "topic": topic,
                "average": average
            })


    return weak_topics