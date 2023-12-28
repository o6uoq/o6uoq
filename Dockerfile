# Use an official Python runtime as a parent image
FROM python:3.11.6-slim

# Set the working directory in the container to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any required Python packages specified in requirements.txt
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Run fitbit.py when the container launches
CMD ["python", "fitbit.py"]
