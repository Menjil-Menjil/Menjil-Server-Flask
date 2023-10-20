### Flask
FROM python:3.10-slim

WORKDIR /app

COPY . /app
COPY requirements.txt requirements.txt

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_ENV=production

# Install any needed packages specified in requirements.txt
# use --verbose to get more detailed logs
RUN pip install --verbose --no-cache-dir -r requirements.txt

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run Flask app when the container launches
CMD ["python3", "-m", "flask", "run"]
