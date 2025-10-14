import os
import uuid
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, UploadFile, HTTPException, Depends, status, Form
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer
import uvicorn
from typing import Optional
import threading
import time

app = FastAPI(title="Temporary File Share")

# Configuration
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)
FILE_LIFETIME = 3600  # 60 minutes in seconds
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB in bytes
HOST = "0.0.0.0"
PORT = 8000

# Extensive whitelist of safe file types (MIME types and extensions)
ALLOWED_MIME_TYPES = {
    # Documents
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
    "application/rtf",
    "text/plain",
    "text/csv",
    "text/markdown",
    "text/html",
    "text/css",
    
    # Images
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/bmp",
    "image/tiff",
    "image/x-icon",
    "image/heic",
    "image/heif",
    
    # Audio
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/ogg",
    "audio/aac",
    "audio/flac",
    "audio/m4a",
    "audio/webm",
    
    # Video
    "video/mp4",
    "video/mpeg",
    "video/quicktime",
    "video/x-msvideo",
    "video/webm",
    "video/ogg",
    "video/x-matroska",
    
    # Archives
    "application/zip",
    "application/x-zip-compressed",
    "application/x-rar-compressed",
    "application/x-7z-compressed",
    "application/gzip",
    "application/x-tar",
    "application/x-bzip2",
    
    # Code/Development
    "application/json",
    "application/xml",
    "text/xml",
    "application/javascript",
    "text/javascript",
    "application/typescript",
    "text/x-python",
    "text/x-java-source",
    "text/x-c",
    "text/x-c++",
    "text/x-csharp",
    "application/x-yaml",
    "text/yaml",
    
    # Other
    "application/octet-stream",  # Generic binary
}

ALLOWED_EXTENSIONS = {
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp", ".rtf", ".txt", ".csv", ".md",
    ".html", ".htm", ".css",
    
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp",
    ".tiff", ".tif", ".ico", ".heic", ".heif",
    
    # Audio
    ".mp3", ".wav", ".ogg", ".aac", ".flac", ".m4a", ".weba",
    
    # Video
    ".mp4", ".mpeg", ".mpg", ".mov", ".avi", ".webm", ".ogv", ".mkv",
    
    # Archives
    ".zip", ".rar", ".7z", ".gz", ".tar", ".bz2",
    
    # Code/Development
    ".json", ".xml", ".js", ".ts", ".tsx", ".jsx", ".py", ".java",
    ".c", ".cpp", ".cs", ".h", ".hpp", ".yaml", ".yml", ".go",
    ".rs", ".rb", ".php", ".swift", ".kt", ".sh", ".bash",
}

# In-memory storage for file metadata
file_metadata = {}

def cleanup_old_files():
    """Background task to clean up expired files"""
    while True:
        current_time = datetime.utcnow()
        expired_files = []
        
        # Find expired files
        for file_id, metadata in list(file_metadata.items()):
            if current_time > metadata["expires_at"]:
                expired_files.append(file_id)
        
        # Remove expired files
        for file_id in expired_files:
            file_path = UPLOAD_FOLDER / file_id
            if file_path.exists():
                file_path.unlink()
            file_metadata.pop(file_id, None)
        
        # Sleep for 1 minute before next cleanup
        time.sleep(60)

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

@app.post("/upload")
async def upload_file(
    file: UploadFile,
    file_extension: Optional[str] = Form(None),
    mime_type: Optional[str] = Form(None)
):
    """Upload a file and get a shareable link
    
    Args:
        file: The file to upload
        file_extension: Optional file extension to use for validation (e.g., '.pdf', '.jpg')
        mime_type: Optional MIME type to use for validation (e.g., 'application/pdf', 'image/jpeg')
    """
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    # Use provided file extension or extract from filename
    if file_extension:
        file_ext = file_extension.lower() if file_extension.startswith('.') else f'.{file_extension.lower()}'
    else:
        file_ext = Path(file.filename).suffix.lower()
    
    # Validate file extension
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file_ext}' not allowed. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    
    # Use provided MIME type or fall back to file's content type
    content_type_to_validate = mime_type if mime_type else file.content_type
    
    # Validate MIME type
    if content_type_to_validate and content_type_to_validate not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Content type '{content_type_to_validate}' not allowed"
        )
    
    # Generate unique ID
    file_id = str(uuid.uuid4())
    file_path = UPLOAD_FOLDER / file_id
    
    # Save file with size validation
    try:
        total_size = 0
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(8192):  # Read in 8KB chunks
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    # Delete partial file
                    buffer.close()
                    if file_path.exists():
                        file_path.unlink()
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size is {MAX_FILE_SIZE / (1024 * 1024):.0f}MB"
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        # Clean up on error
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")
    
    # Store metadata
    expires_at = datetime.utcnow() + timedelta(seconds=FILE_LIFETIME)
    file_metadata[file_id] = {
        "original_filename": file.filename,
        "content_type": mime_type if mime_type else file.content_type,
        "uploaded_at": datetime.utcnow(),
        "expires_at": expires_at,
        "file_size": total_size,
        "file_extension": file_ext
    }
    
    # Return the download URL with extension
    return {
        "file_id": file_id,
        "download_url": f"/download/{file_id}{file_ext}",
        "expires_at": expires_at.isoformat(),
        "original_filename": file.filename,
        "file_size": total_size
    }

@app.get("/download/{file_id:path}")
async def download_file(file_id: str):
    """Download a file by its ID (with optional extension in URL)"""
    # Strip extension from file_id if present
    clean_file_id = file_id
    if '.' in file_id:
        # Extract the UUID part (before any extension)
        parts = file_id.split('.')
        clean_file_id = parts[0]
    
    file_path = UPLOAD_FOLDER / clean_file_id
    
    # Check if file exists and hasn't expired
    if not file_path.exists() or clean_file_id not in file_metadata:
        raise HTTPException(status_code=404, detail="File not found or has expired")
    
    metadata = file_metadata[clean_file_id]
    
    # Force the correct file extension on the downloaded filename
    original_filename = metadata["original_filename"]
    stored_extension = metadata.get("file_extension", "")
    
    # Check if original filename already has the correct extension
    if stored_extension and not original_filename.lower().endswith(stored_extension.lower()):
        # Remove any existing extension and add the correct one
        filename_without_ext = Path(original_filename).stem
        download_filename = f"{filename_without_ext}{stored_extension}"
    else:
        download_filename = original_filename
    
    return FileResponse(
        file_path,
        filename=download_filename,
        media_type="application/octet-stream"
    )

@app.get("/")
async def root():
    return {"message": "Temporary File Share API - Use /upload to upload files and /download/{id} to download them"}

if __name__ == "__main__":
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
