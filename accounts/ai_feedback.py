import google.generativeai as genai
import markdown2
from django.conf import settings

genai.configure(api_key="YOUR_API_KEY")
def generate_ai_feedback(performance_rate, results, topic_name):
    try:
        structured_data = []
        for r in results:
            structured_data.append({
                "question": r["question"],
                "selected": r["selected"],
                "correct": r["correct"],
                "is_correct": r["is_correct"],
            })

        prompt = f"""
You are an AI academic evaluator.
Topic: {topic_name}
Analyze the student's quiz performance based on the following JSON-like structure:
{structured_data}

Performance Rate: {performance_rate}%

Your task:
1. **Weak Areas**
2. **Improvement Suggestions**
3. **Performance Prediction**
4. **Learning Resources**

Return the answer in this format:

Weak Areas:
- ...

Improvement Suggestions:
- ...

Performance Prediction:
- Short-term: ...
- Long-term: ...

Learning Resources:
Provide four clear bullet points under the fixed categories below.
Write in simple, student-friendly language. Use short explanations.
Each category must include a direct, full URL.

Categories:
• YouTube - Give a short description of what the student will learn and provide a direct YouTube search link.
• W3Schools/MDN - Provide a simple, beginner-friendly explanation and a direct W3Schools or MDN URL.
• GeeksforGeeks - Provide a one-sentence explanation and a direct GFG URL.
• Extra Resource - Provide an additional useful link (RealPython, Programiz, etc.) with a short description.

Rules:
- No paragraphs. Only bullets.
- Start each bullet with the category name.
- Always include a direct link.
- Write only one sentence per category before the link.

"""

        model = genai.GenerativeModel("gemini-2.5-flash-lite-preview-09-2025")
        response = model.generate_content(prompt)
        ai_text = response.text
        feedback = {
            "weak_areas": "",
            "improvement": "",
            "prediction": "",
            "resources": "",
        }

        text = ai_text

        # Weak Areas
        if "Weak Areas:" in text:
            feedback["weak_areas"] = (
                text.split("Weak Areas:")[1]
                .split("Improvement Suggestions:")[0]
                .strip()
            )

        # Improvement Suggestions
        if "Improvement Suggestions:" in text:
            feedback["improvement"] = (
                text.split("Improvement Suggestions:")[1]
                .split("Performance Prediction:")[0]
                .strip()
            )

        # Performance Prediction
        if "Performance Prediction:" in text:
            feedback["prediction"] = (
                text.split("Performance Prediction:")[1]
                .split("Learning Resources:")[0]
                .strip()
            )
        # Learnign Resource    
        if "Learning Resources:" in text:
            section = text.split("Learning Resources:")[1]
                
            stop_words = [
                "Performance Prediction:",
                "Improvement Suggestions:",
                "Weak Areas:",
                 ]
                
            for w in stop_words:
                if w in section:
                    section = section.split(w)[0]
                        
            section = section.strip()
                        
            lines = []
            for line in section.split("\n"):
                clean = line.strip()
                if clean:
                    if clean.startswith("- ") or clean.startswith("* "):
                        clean = "• " + clean[2:]
                    elif clean.startswith("-") or clean.startswith("*"):
                        clean = "• " + clean[1:].strip()
                    lines.append(clean)
            feedback["resources"] = "\n".join(lines)

        if not any(feedback.values()):
            feedback["weak_areas"] = ai_text

        return feedback

    except Exception as e:
        return {
            "weak_areas": "⚠️ AI feedback unavailable.",
            "improvement": f"Error: {str(e)}",
            "prediction": "",
            "resources": "",
        }
