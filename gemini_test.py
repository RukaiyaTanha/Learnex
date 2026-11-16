import os
from google import genai

# --- Step 1: Initialize client ---
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# --- Step 2: Choose model ---
model = "models/gemini-2.5-flash"   # or "gemini-1.5-pro-latest"

# --- Step 3: Generate content ---
response = client.models.generate_content(
    model=model,
    contents="write newton 3rd law"
)

# --- Step 4: Print result ---
print(response.text)
