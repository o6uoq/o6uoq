# Use an official Python runtime as a parent image
FROM python:3.13-slim

# Set the working directory in the container to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any required Python packages specified in requirements.txt
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Run Python when the container launches
CMD ["python"]