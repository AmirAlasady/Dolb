# MS10/data/services.py

import os
import uuid
import magic
from django.core.files.uploadedfile import UploadedFile
from django.core.files.storage import default_storage
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

from .models import StoredFile
from data_internals.clients import ProjectServiceClient

class DataService:
    """
    The service layer for handling all business logic related to StoredFile objects.
    This includes authorization, file storage operations, and intelligent
    mimetype detection for Office documents.
    """
    def __init__(self):
        self.project_client = ProjectServiceClient()

    def list_files_for_project(self, *, project_id: uuid.UUID, user_id: uuid.UUID, jwt_token: str):
        """
        Lists all files for a project after verifying the user's ownership of that project.
        """
        self.project_client.authorize_user(jwt_token, str(project_id))
        return StoredFile.objects.filter(project_id=project_id, owner_id=user_id)

    def create_file(self, *, owner_id: uuid.UUID, project_id: uuid.UUID, file_obj: UploadedFile, jwt_token: str) -> StoredFile:
        """
        The core logic for uploading a file. It performs the following steps:
        1. Authorizes the user against the project via the Project Service.
        2. Sanitizes the filename for security.
        3. Saves the file to the configured object storage (e.g., MinIO/S3).
        4. Reliably determines the file's mimetype using a two-step process
           to correctly identify Office documents.
        5. Creates a metadata record in the local database.
        """
        # 1. Authorize project ownership BEFORE doing anything else.
        self.project_client.authorize_user(jwt_token, str(project_id))
        
        # 2. Define a secure storage path and sanitize the filename.
        safe_filename = os.path.basename(file_obj.name)
        storage_path = f"uploads/{project_id}/{owner_id}/{uuid.uuid4()}-{safe_filename}"
        
        # 3. Save the file to our object storage.
        try:
            actual_path = default_storage.save(storage_path, file_obj)
        except Exception as e:
            raise ValidationError(f"Could not save file to storage backend: {e}")
        
        # --- DEFINITIVE FIX FOR OFFICE DOCUMENT MIMETYPES ---
        # 4a. Primary Check (Content-Based): Use python-magic for security.
        file_obj.seek(0)
        detected_mimetype = magic.from_buffer(file_obj.read(2048), mime=True)
        file_obj.seek(0)

        final_mimetype = detected_mimetype
        
        # 4b. Secondary Check (Extension-Based Override): If magic reports a generic
        #     ZIP file, we check the extension to identify specific Office formats.
        if detected_mimetype == 'application/zip':
            # Get the lowercased file extension (e.g., '.docx', '.pptx')
            file_extension = os.path.splitext(safe_filename)[1].lower()
            
            if file_extension == '.docx':
                final_mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            elif file_extension == '.pptx':
                final_mimetype = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            elif file_extension == '.xlsx':
                final_mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            
            # If it's a ZIP but not a known Office extension, we keep 'application/zip'.
        # --- END OF MIMETYPE FIX ---

        # 5. Create the metadata record in the database using the final, corrected mimetype.
        stored_file = StoredFile.objects.create(
            owner_id=owner_id,
            project_id=project_id,
            filename=safe_filename,
            mimetype=final_mimetype, # <-- Using the corrected mimetype
            size_bytes=file_obj.size,
            storage_path=actual_path
        )
        return stored_file

    def delete_file(self, *, file_instance: StoredFile, user_id: uuid.UUID):
        """
        Deletes a file after explicitly verifying ownership.
        """
        # 1. Authorize: Ensure the user requesting the deletion is the actual owner.
        if str(file_instance.owner_id) != str(user_id):
            raise PermissionDenied("You do not have permission to delete this file.")

        # 2. Delete the physical file from object storage.
        if default_storage.exists(file_instance.storage_path):
            default_storage.delete(file_instance.storage_path)
            
        # 3. Delete the metadata record from our database.
        file_instance.delete()