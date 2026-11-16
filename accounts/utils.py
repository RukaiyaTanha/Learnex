from .models import (
    AIQuizAttempt,
    TeacherNotification,
    Section
)
def check_ai_quiz_decline(student, course):

    # Get latest 3 AI quizzes for this course
    attempts = AIQuizAttempt.objects.filter(
        student=student,
        course=course
    ).order_by('-created_at')[:3]
    # Need at least 3 quizzes
    if len(attempts) < 3:
        return
    scores = []
    for attempt in reversed(attempts):
        if attempt.max_score > 0:
            percentage = (
                attempt.score / attempt.max_score
            ) * 100
            scores.append(round(percentage,2))
    # Example:
    # [85,75,60]

    if len(scores) != 3:
        return
    first = scores[0]
    second = scores[1]
    third = scores[2]
    # Check continuous decrease

    if first > second > third:
        # Find student's section/course teacher

        section = Section.objects.filter(
            course=course
        ).first()

        if not section:
            return

        teacher = section.teacher
        message = f"""
        Recent AI quiz scores:
        {first}%
        {second}%
        {third}%
        
        The student's AI quiz performance is continuously decreasing.
        Please review the student's progress and provide guidance.
        """

    existing_alert = TeacherNotification.objects.filter(
    teacher=teacher,
    student=student,
    course=course,
    resolved=False
    ).exists()
    
    if not existing_alert:
        TeacherNotification.objects.create(
            teacher=teacher,
            student=student,
            course=course,
            semester=section.semester,
            section=section.section_name,
            title="Performance Alert",
            message=message
        )