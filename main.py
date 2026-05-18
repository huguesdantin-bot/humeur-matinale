import os
import feedparser
import requests
import json
import re
import io
import time
from datetime import datetime
from google import genai
from google.genai import types

# =============================================================
# CONFIGURATION — variables d'environnement (GitHub Secrets)
# =============================================================

GEMINI_API_KEY     = os.environ["GEMINI_API_KEY"]
RESEND_API_KEY     = os.environ["RESEND_API_KEY"]
EMAIL_DESTINATAIRE = os.environ["EMAIL_DESTINATAIRE"]

client = genai.Client(api_key=GEMINI_API_KEY)

# =============================================================
# SOURCES
# =============================================================

SOURCES = [
    {
        "media": "France Inter",
        "emission": "L'invité de 8h20 — Le grand entretien",
        "journaliste": "Nicolas Demorand et Benjamin Duhamel",
        "heure": "8h20",
        "type": "rss",
        "rss": "https://radiofrance-podcast.net/podcast09/rss_10239.xml"
    },
    {
        "media": "France Info",
        "emission": "8h30 franceinfo",
        "journaliste": "Agathe Lambret et Paul
