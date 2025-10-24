from google import genai

# --- Step 1: Initialize client ---
client = genai.Client(api_key="AIzaSyCPopZHtLDeaMwiyB5rYpDZb6F4V9LS6OM")

# --- Step 2: Choose model ---
model = "models/gemini-2.5-flash"   # or "gemini-1.5-pro-latest"

# --- Step 3: Generate content ---
response = client.models.generate_content(
    model=model,
    contents="write newton 3rd law"
)

# --- Step 4: Print result ---
print(response.text)
