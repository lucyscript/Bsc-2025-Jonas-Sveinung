# How to run dockerfile

# Build the Docker image

docker build -t whatsapp-bot .

# Run the container with a persistent volume for the database

docker run -v feedback_data:/app/data -p 8085:8085 whatsapp-bot

# Note: The -v flag creates/uses a named volume 'feedback_data' that persists the database

# even when the container is stopped or removed
