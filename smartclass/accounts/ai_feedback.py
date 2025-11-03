import google.generativeai as genai
import markdown2
from django.conf import settings

genai.configure(api_key="AIzaSyCPopZHtLDeaMwiyB5rYpDZb6F4V9LS6OM")

def generate_ai_feedback(performance_rate, results):
    """
    Uses Gemini to analyze quiz performance and generate personalized feedback.
    """
    try:
        # Build structured summary for the model
        summary = "Here are the quiz results:\n"
        for r in results:
            summary += f"- Q: {r['question']}\n Your Answer: {r['selected']}\n Correct: {r['correct']}\n"

        prompt = f"""
        You are an AI tutor. Analyze the student's quiz performance.
        Performance Rate: {performance_rate}%
        Based on the following quiz results, identify:
        Weak areas (concepts or patterns they struggle with)
        Improvement suggestions
        Future performance prediction
        Be concise and encouraging.
        {summary}
        """

        # Generate response from Gemini
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)

        # Convert markdown → HTML for rendering
        html_response = markdown2.markdown(
            response.text,
            extras=["fenced-code-blocks", "break-on-newline"]
        )

        # Split AI response into sections (if possible)
        text = response.text.lower()
        feedback = {
            "weak_areas": "",
            "improvement": "",
            "prediction": "",
        }

        if "weak" in text:
            feedback["weak_areas"] = response.text.split("Improvement")[0].strip()
        if "improvement" in text:
            feedback["improvement"] = response.text.split("Improvement")[1].split("Prediction")[0].strip()
        if "prediction" in text:
            feedback["prediction"] = response.text.split("Prediction")[-1].strip()

        # Fallback: if parsing fails, return full text
        if not any(feedback.values()):
            feedback["weak_areas"] = response.text

        return feedback

    except Exception as e:
        return {
            "weak_areas": "⚠️ AI feedback unavailable.",
            "improvement": str(e),
            "prediction": "",
        }
