# Use an official Python runtime as a parent image
FROM python:3.14-slim

# Set the working directory in the container to /app
WORKDIR /app

# Copy dependency files and install with uv
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

# Copy the current directory contents into the container at /app
COPY . /app

# Run Python via uv to use the virtual environment
CMD ["uv", "run", "python"]
