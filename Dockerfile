FROM python:3.10-slim

WORKDIR /app

COPY . /app
COPY requirements.txt requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run Flask app when the container launches
CMD ["python3", "-m", "flask", "run", "--host=0.0.0.0"]
