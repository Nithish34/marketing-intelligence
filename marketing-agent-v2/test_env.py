from app.config import settings

print("KEY EXISTS:",
      bool(settings.GEMINI_API_KEY))

print("MODEL:",
      settings.GEMINI_MODEL)