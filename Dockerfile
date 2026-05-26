# 1. Official Python slim image
FROM python:3.10-slim

# 2. Chrome और जरूरी dependencies इंस्टॉल करना
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libnss3 \
    libx11-6 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxi6 \
    libxtst6 \
    libcups2 \
    libxss1 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# 3. Environment Variables
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# 4. Working Directory
WORKDIR /app

# 5. Requirements कॉपी और इंस्टॉल करें
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. पूरी एप्लीकेशन कॉपी करें
COPY . .

# 7. Render के लिए पोर्ट एक्सपोजर
EXPOSE 8501

# 8. Command
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
