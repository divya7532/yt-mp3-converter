# Use a lightweight Python version
FROM python:3.9-slim

# Install FFmpeg (The missing piece on Vercel)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Set up the app
WORKDIR /app
COPY . /app

# Install Python libraries
RUN pip install --no-cache-dir -r requirements.txt

# Run the application
# Note: We bind to 0.0.0.0 to make it accessible outside the container
CMD ["python", "app.py"]