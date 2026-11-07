import os

# All of these are set as "Secrets" in the Hugging Face Space settings.
WA_TOKEN = os.getenv("WA_TOKEN", "")              # WhatsApp permanent access token
WA_PHONE_ID = os.getenv("WA_PHONE_ID", "")        # WhatsApp phone number ID
WA_VERIFY = os.getenv("WA_VERIFY", "myagent123")  # any word you choose, used once in Meta webhook setup
OWNER_NUMBER = os.getenv("OWNER_NUMBER", "")      # your WhatsApp number, e.g. 919876543210 (only you can control the bot)

GROQ_KEY = os.getenv("GROQ_KEY", "")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-large-v3")

YT_CLIENT_ID = os.getenv("YT_CLIENT_ID", "")
YT_CLIENT_SECRET = os.getenv("YT_CLIENT_SECRET", "")
YT_REFRESH_TOKEN = os.getenv("YT_REFRESH_TOKEN", "")

IG_USER_ID = os.getenv("IG_USER_ID", "")          # Instagram Business account ID
IG_TOKEN = os.getenv("IG_TOKEN", "")              # long-lived Instagram/Facebook token

PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")  # e.g. https://yourname-myagent.hf.space
DATA = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
os.makedirs(DATA, exist_ok=True)
