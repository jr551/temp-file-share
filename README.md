# Temporary File Share Service

A simple file sharing service where uploaded files are automatically deleted after 60 minutes.

## Features

- Upload files via a simple HTTP POST request
- Get a unique download link for each file
- Files are automatically deleted after 60 minutes
- Simple REST API interface
- Containerized with Docker for easy deployment

## Getting Started

### Prerequisites

- Docker and Docker Compose

### Running with Docker

1. Build and start the service:
   ```bash
   docker-compose up --build
   ```

2. The service will be available at `http://localhost:8000`

## API Endpoints

- `POST /upload` - Upload a file
  - Content-Type: multipart/form-data
  - Returns: JSON with file ID and download URL

- `GET /download/{file_id}` - Download a file
  - Returns: The requested file

- `GET /` - Service information
  - Returns: Basic service information

## Example Usage

### Upload a file

```bash
curl -X POST -F "file=@/path/to/your/file.txt" http://localhost:8000/upload
```

Example response:
```json
{
  "file_id": "550e8400-e29b-41d4-a716-446655440000",
  "download_url": "/download/550e8400-e29b-41d4-a716-446655440000",
  "expires_at": "2025-10-12T21:30:00.000000",
  "original_filename": "file.txt"
}
```

### Download a file

```bash
curl -OJ http://localhost:8000/download/550e8400-e29b-41d4-a716-446655440000
```

## Notes

- Files are stored in the `uploads` directory inside the container
- The service automatically cleans up expired files every minute
- There is no authentication - anyone with the download link can access the file
- The service is not intended for production use without additional security measures
