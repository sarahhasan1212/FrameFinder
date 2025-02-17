# Use the official Python 3.12.6 image as the base image
FROM python:3.12.6

# Metadata for the image
LABEL authors="sara"

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# Set the working directory inside the container
WORKDIR /app

# Copy the current directory contents into the container
COPY . /app

# Copy only requirements.txt first to leverage Docker's caching
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy static and templates folders
COPY static /app/static
COPY templates /app/templates


# Expose the application port (FastAPI) and FiftyOne app port
#EXPOSE 5010 5151

# Command to run the application
#CMD ["uvicorn", "proj:app", "--port", "5010"]
