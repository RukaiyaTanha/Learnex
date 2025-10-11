from django.shortcuts import render
from django.http import JsonResponse,FileResponse
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from .models import Course, UserCourse,Topic, Question,Marks,Syllabus
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.shortcuts import render, redirect, get_object_or_404
from django.core.mail import EmailMultiAlternatives
from .models import CustomUser
from django.urls import reverse
import json as pyjson
from difflib import SequenceMatcher
from django.contrib import messages
from django.views.decorators.http import require_POST
import mimetypes
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
        first_name = data.get('first_name')
        last_name = data.get('last_name')

        if not email or not password or not role or not username:
            return JsonResponse({"success": False, "message": "Missing fields"})

        if User.objects.filter(email=email).exists():
            return JsonResponse({"success": False, "message": "Email already registered"})

        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
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
            if not isinstance(selected_codes, list):
                return JsonResponse({"success": False, "message": "Invalid courses data"})

            user = request.user

            # Get all courses in DB for these codes
            all_courses = Course.objects.filter(code__in=selected_codes)

            # --- Add new courses ---
            added = []
            for course in all_courses:
                uc, created = UserCourse.objects.get_or_create(user=user, course=course)
                if created:
                    added.append(course.code)

            # --- Remove courses that are not selected ---
            removed = []
            user_courses_qs = UserCourse.objects.filter(user=user)
            for uc in user_courses_qs:
                if uc.course.code not in selected_codes:
                    removed.append(uc.course.code)
                    uc.delete()

            # Return the authoritative current list from DB
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
    courses = Course.objects.all()
    # list of codes currently saved for this user
    user_courses_qs = UserCourse.objects.filter(user=user).values_list('course__code', flat=True)
    user_courses = list(user_courses_qs)

    context = {
        "courses": courses,
        "user_courses": user_courses,                     # Python list for template use if needed
        "user_courses_json": pyjson.dumps(user_courses),  # JSON string safe for embedding
        "username": user.username,
    }
    return render(request, "accounts/course_selection.html", context)

@login_required(login_url='/accounts/login-page/')
def selected_courses_page(request):
    user_courses = UserCourse.objects.filter(user=request.user).select_related('course')
    return render(request, 'accounts/selected_courses.html', {
        'username': request.user.username,
        'user_courses': user_courses,
    })

# ---------- Quiz Selection ----------
@login_required(login_url='/accounts/login-page/')
def quiz_selection_page(request):
    user = request.user
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

@login_required(login_url='/accounts/login-page/')
def profile_page(request):
    user = request.user
    context = {
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
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
        "first_name": user.first_name,
        "last_name": user.last_name,
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
            data = request.POST
            profile_picture = request.FILES.get('profile_picture')
            user = request.user

            username = data.get("username", "").strip()
            first_name = data.get("first_name", "").strip()
            last_name = data.get("last_name", "").strip()
            email = data.get("email", "").strip()
            profile_picture = request.FILES.get("profile_picture")

            if not username or not email or not first_name or not last_name:
                return JsonResponse({"success": False, "message": "All fields are required."})

            # ✅ check for duplicate email (avoid overwriting another user)
            if User.objects.filter(email=email).exclude(id=user.id).exists():
                return JsonResponse({"success": False, "message": "This email is already in use."})

            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            if profile_picture:
                user.profile_picture = profile_picture
            user.save()

            return JsonResponse({"success": True, "message": "Profile updated successfully!"})
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)})

    return JsonResponse({"success": False, "message": "Invalid request"})

# ---------- Quiz page ----------

@login_required(login_url='/accounts/login-page/')
def quiz_page(request, course_id, topic_id, type):
    try:
        course = Course.objects.get(id=course_id)
        topic = Topic.objects.get(id=topic_id, course=course)
    except (Course.DoesNotExist, Topic.DoesNotExist):
        return render(request, "accounts/quiz_invalid.html", {"message": "Invalid course or topic selected."})

    # Hardcoded questions with time_duration and marks per quiz type
    all_questions = {
        "6": {  # Course: Differential
            "94": {  # Topic: Limits
                "mcq": {
                    "time_duration": "15 Minutes",
                    "marks": 20,
                    "questions": [
                        {"question": f"What is the limit of x approaching {i+1} for f(x)?",
                         "options": [str(j) for j in range(i, i+4)], "answer": str(i+2)}
                        for i in range(20)
                    ]
                },
                "scenario-mcq": {
                    "time_duration": "20 Minutes",
                    "marks": 20,
                    "questions": [
                        {"question": f"Function behavior analysis. What is the correct limit?",
                         "options": ["0", "1", "Infinity", "-Infinity"], "answer": "1"}
                        for i in range(20)
                    ]
                },
                "code": {
                    "time_duration": "1 Hour",
                    "marks": 35,
                    "questions": [
                        {"question": "Write Python function to compute limit of f(x) = x^2 - 1 as x -> 1.", "options": [], "answer": ""},
                        {"question": "Write Python code to find the limit of sin(x)/x as x -> 0.", "options": [], "answer": ""},
                        {"question": "Trace the output:\nfor i in range(3):\n    print(i**2)", "options": [], "answer": "0 1 4"},
                        {"question": "Trace the output:\na = [1,2,3]\nprint(a[-1])", "options": [], "answer": "3"},
                        {"question": "Trace the output:\nprint(len('limit'))", "options": [], "answer": "5"},
                    ]
                },
                "theory": {
                    "time_duration": "45 Minutes",
                    "marks": 30,
                    "questions": [
                        {"question": "Short Question 1: Define the concept of limit in calculus.", "options": [], "answer": ""},
                        {"question": "Short Question 2: What is a left-hand limit?", "options": [], "answer": ""},
                        {"question": "Short Question 3: What is a right-hand limit?", "options": [], "answer": ""},
                        {"question": "Short Question 4: State limit laws.", "options": [], "answer": ""},
                        {"question": "Short Question 5: Explain continuity at a point.", "options": [], "answer": ""},
                        {"question": "Broad Question 1: Discuss how limits are used to find derivatives.", "options": [], "answer": ""},
                        {"question": "Broad Question 2: Solve a real-world problem using limits.", "options": [], "answer": ""},
                    ]
                },
            }
        },
        "1": {  # Course: Web Technology
            "84": {  # Topic: HTML Basics
                "mcq": {
                    "time_duration": "15 Minutes",
                    "marks": 15,
                    "questions": [
                        {"question": f"Which HTML tag is used for {['paragraph', 'heading', 'link', 'image'][i%4]}?",
                         "options": ["<p>", "<h1>", "<a>", "<img>"], "answer": ["<p>", "<h1>", "<a>", "<img>"][i%4]}
                        for i in range(10)
                    ]
                },
                "scenario-mcq": {
                    "time_duration": "20 Minutes",
                    "marks": 20,
                    "questions": [
                        {"question": f"You want to display an image on a webpage. Which tag should you use?",
                         "options": ["<p>", "<img>", "<div>", "<span>"], "answer": "<img>"}
                        for i in range(5)
                    ]
                },
                "code": {
                    "time_duration": "1 Hour",
                    "marks": 35,
                    "questions": [
                        {"question": "Write the HTML code to create a hyperlink to https://example.com", "options": [], "answer": "<a href='https://example.com'>Link</a>"},
                        {"question": "Write the HTML code to create an ordered list with 3 items", "options": [], "answer": "<ol><li>Item1</li><li>Item2</li><li>Item3</li></ol>"},
                    ]
                },
                "theory": {
                    "time_duration": "45 Minutes",
                    "marks": 30,
                    "questions": [
                        {"question": "Define what HTML is.", "options": [], "answer": ""},
                        {"question": "Explain the difference between <div> and <span>.", "options": [], "answer": ""},
                        {"question": "List some commonly used HTML tags.", "options": [], "answer": ""},
                    ]
                },
            }
        }
    }

    quiz_data = all_questions.get(str(course_id), {}).get(str(topic_id), {}).get(type, {})
    questions = quiz_data.get("questions", [])
    time_duration = quiz_data.get("time_duration", "N/A")
    marks = quiz_data.get("marks", "N/A")

     # ----------- ✅ When user submits the quiz -----------
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
                "options": q["options"],
                "selected": selected,
                "correct": correct,
                "is_correct": is_correct,
            })

        total_score = correct_count
        performance_rate = round((correct_count / len(questions)) * 100, 2)

        # 🧠 Simple AI-like analysis
        weak_areas = "Conceptual misunderstanding" if performance_rate < 70 else "Minor errors"
        improvement = (
            "Review weak topics and practice more timed quizzes."
            if performance_rate < 80 else
            "Excellent work! Keep your consistency."
        )
        prediction = (
            "Performance expected to improve with continued study."
            if performance_rate < 75 else
            "Strong performance trend likely to continue."
        )

        context = {
            "course": course,
            "topic": topic,
            "type": type,
            "total_score": total_score,
            "performance_rate": performance_rate,
            "weak_areas": weak_areas,
            "improvement": improvement,
            "prediction": prediction,
            "results": results,
        }
        return render(request, "accounts/quiz_result.html", context)

    # ----------- When quiz page is first loaded -----------
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
#
def evaluate_answer(user_answer, correct_answer, keywords=[]):
    """
    Evaluate theory/code answers using similarity and keyword match.
    Returns (is_correct: bool, feedback: str)
    """
    if not user_answer:
        return False, "Not answered"

    user_answer = user_answer.strip().lower()
    correct_answer = correct_answer.strip().lower()

    # Similarity check
    similarity = SequenceMatcher(None, user_answer, correct_answer).ratio()

    # Keyword check
    keyword_hits = sum(1 for k in keywords if k.lower() in user_answer)
    keyword_score = keyword_hits / len(keywords) if keywords else 0

    # Use whichever is higher
    score = max(similarity, keyword_score)

    if score > 0.7:
        return True, "Mostly correct"
    elif score > 0.4:
        return False, "Partially correct"
    else:
        return False, "Incorrect"
#
def ai_quiz_analysis(results):
    total = len(results)
    correct_count = sum(1 for r in results if r["is_correct"])
    performance_rate = round((correct_count / total) * 100, 2)

    theory_incorrect = [r for r in results if r["question_type"] in ["theory", "code"] and not r["is_correct"]]
    mcq_incorrect = [r for r in results if r["question_type"] == "mcq" and not r["is_correct"]]

    weak_areas_list = []
    if theory_incorrect:
        weak_areas_list.append("Conceptual understanding in theory/code questions")
    if mcq_incorrect:
        weak_areas_list.append("Multiple-choice knowledge gaps")
    if not weak_areas_list:
        weak_areas_list.append("Minor mistakes")

    weak_areas = ", ".join(weak_areas_list)

    if performance_rate < 50:
        improvement = "Focus on revising fundamental concepts and practice more questions."
    elif performance_rate < 80:
        improvement = "Review weak topics and take targeted practice quizzes."
    else:
        improvement = "Excellent work! Keep practicing to maintain consistency."

    if performance_rate < 60:
        prediction = "Performance may improve significantly with focused study."
    elif performance_rate < 85:
        prediction = "Steady improvement expected with continued practice."
    else:
        prediction = "Strong performance trend likely to continue."

    return weak_areas, improvement, prediction, performance_rate

#Upload marks
@login_required(login_url='/accounts/login-page/')
def upload_marks_page(request):
    user = request.user
    courses = Course.objects.filter(usercourse__user=user)  # only enrolled courses
    return render(request, "accounts/upload_marks.html", {"username": user.username, "courses": courses})


@login_required(login_url='/accounts/login-page/')
@csrf_exempt
def upload_marks_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        student = request.user  # assuming logged in
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
    # Get courses this user selected
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
            return redirect('upload_syllabus_page')  # Redirect to clear form

    return render(request, "accounts/upload_syllabus.html", {"courses": user_courses})



@login_required(login_url='/accounts/login-page/')
def upload_syllabus(request):
    # Only courses the user has selected
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
    syllabi = Syllabus.objects.filter(user=request.user).order_by('uploaded_at')

    # Add absolute URLs for Google Docs viewer
    for s in syllabi:
        if s.lecture_slide:
            s.absolute_url = request.build_absolute_uri(s.lecture_slide.url)
        else:
            s.absolute_url = ""

    return render(request, 'accounts/selected_syllabus.html', {'syllabi': syllabi})

@login_required(login_url='/accounts/login-page/')
@require_POST
def delete_syllabus(request, pk):
    # allow user to delete their own upload
    s = get_object_or_404(Syllabus, pk=pk, user=request.user)
    # remove file from disk (optional)
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