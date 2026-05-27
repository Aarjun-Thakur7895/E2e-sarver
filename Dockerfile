# 1. Official Python slim image
FROM python:3.10-slim

# 2. Chrome और जरूरी dependencies इंस्टॉल करना (xvfb भी जोड़ा गया है)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    xvfb \
    libnss3 \
    libxss1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# 3. Environment Variables
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV DISPLAY=:99

# 4. Working Directory
WORKDIR /app

# 5. Requirements कॉपी और इंस्टॉल करें
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. पूरी एप्लीकेशन कॉपी करें
COPY . .

# 7. Port
EXPOSE 8501

# 8. Command - (Xvfb को सही तरीके से शुरू करना)
CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 & streamlit run app.py --server.port=8501 --server.address=0.0.0.0"]
