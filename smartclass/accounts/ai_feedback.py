import google.generativeai as genai
import markdown2
from django.conf import settings

genai.configure(api_key="AIzaSyCPopZHtLDeaMwiyB5rYpDZb6F4V9LS6OM")

def generate_ai_feedback(performance_rate, results):
    """
    Uses Gemini to analyze quiz performance and generate clean HTML feedback.
    Converts bullets/markdown into numbered lists and proper sections.
    """
    try:
        # Build structured summary for the model
        summary = "Here are the quiz results:\n"
        for r in results:
            summary += f"- Q: {r['question']}\n  Your Answer: {r['selected']}\n  Correct: {r['correct']}\n"
        
        prompt = f"""
You are an AI tutor. Analyze the student's quiz performance.
Performance Rate: {performance_rate}%

Based on the following quiz results, identify:
1. Weak areas (concepts or patterns they struggle with)
2. Improvement suggestions
3. Future performance prediction

Be concise, encouraging, and return the results as markdown lists.

{summary}
"""

        # Generate response from Gemini
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        text = response.text

        # Helper to clean headings
        def clean_heading(text, heading):
            return text.replace(f"{heading}:", "").strip()

        # Split AI response into sections
        feedback = {"weak_areas": "", "improvement": "", "prediction": ""}

        # Try splitting by section names
        text_lower = text.lower()
        if "weak" in text_lower:
            feedback["weak_areas"] = clean_heading(text.split("Improvement")[0], "Weak areas")
        if "improvement" in text_lower:
            feedback["improvement"] = clean_heading(text.split("Improvement")[1].split("Prediction")[0], "Improvement suggestions")
        if "prediction" in text_lower:
            feedback["prediction"] = clean_heading(text.split("Prediction")[-1], "Performance prediction")

        # Convert markdown bullets to HTML numbered lists
        def markdown_to_html(md_text):
            if not md_text:
                return ""
            html = markdown2.markdown(md_text, extras=["fenced-code-blocks", "break-on-newline"])
            # Optional: replace <ul> with <ol> if you want numbered lists
            html = html.replace("<ul>", "<ol>").replace("</ul>", "</ol>")
            return html

        # Apply conversion
        feedback = {k: markdown_to_html(v) for k, v in feedback.items()}

        # Fallback: if parsing fails, return full text
        if not any(feedback.values()):
            feedback["weak_areas"] = markdown_to_html(text)

        return feedback

    except Exception as e:
        return {
            "weak_areas": "⚠️ AI feedback unavailable.",
            "improvement": str(e),
            "prediction": "",
        }