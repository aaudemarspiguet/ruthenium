    #!/bin/sh
    # Build the Docker image
    docker build -t ruthenium-backend:latest .

    # Run the Docker container, mapping port 8080 and loading env vars from .env
    docker run --rm -it -p 8080:8080 --env-file .env ruthenium-backend:latest
