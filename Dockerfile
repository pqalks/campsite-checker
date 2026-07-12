# Playwright's official image includes Chromium + all system dependencies
# No manual apt-get installs needed
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt --break-system-packages

COPY campsite_checker.py .

CMD ["python", "campsite_checker.py"]
