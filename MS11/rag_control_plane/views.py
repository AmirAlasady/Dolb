# MS11/rag_control_plane/views.py

from rest_framework import generics, views, status, permissions
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
import logging
import chromadb
from django.conf import settings

from .models import KnowledgeCollection, FileCollectionLink
from .serializers import KnowledgeCollectionSerializer, FileLinkSerializer
from messaging.event_publisher import rag_event_publisher
from .permissions import IsCollectionOwner
from rag_internals.clients import ProjectServiceClient












# It's good practice to get a logger instance for your views
logger = logging.getLogger(__name__)

class CollectionListCreateView(generics.ListCreateAPIView):
    """
    Handles two actions for a specific project:
    - GET /projects/{project_id}/collections/ -> Lists all collections in the project.
    - POST /projects/{project_id}/collections/ -> Creates a new collection in the project.
    """
    serializer_class = KnowledgeCollectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        Filters collections to only show those owned by the current user
        and belonging to the project specified in the URL.
        """
        project_id = self.kwargs['project_id']
        return KnowledgeCollection.objects.filter(owner_id=self.request.user.id, project_id=project_id)

    def perform_create(self, serializer):
        """
        Before creating the collection, this method authorizes that the user
        actually owns the project they are trying to create the collection in.
        """
        project_id = self.kwargs['project_id']
        try:
            ProjectServiceClient().authorize_user(str(self.request.auth), str(project_id))
            # If authorization is successful, save the new collection with ownership details.
            serializer.save(owner_id=self.request.user.id, project_id=project_id)
        except Exception as e:
            # Re-raise exceptions from the client (like PermissionDenied, NotFound)
            # so DRF can format them into a proper 4xx response.
            raise e

class CollectionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Handles GET, PUT, PATCH, and DELETE for a single KnowledgeCollection instance.
    """
    serializer_class = KnowledgeCollectionSerializer
    permission_classes = [permissions.IsAuthenticated, IsCollectionOwner]
    queryset = KnowledgeCollection.objects.all()

    def destroy(self, request, *args, **kwargs):
        """
        Overrides the default delete behavior to gracefully handle deletion of
        both the vector store collection and the local database record.
        """
        # get_object() handles fetching the instance and checking ownership permissions.
        instance = self.get_object()
        collection_id_to_cleanup = str(instance.pk)
        owner_id = str(instance.owner_id)
        vector_collection_name = instance.vector_store_collection_name

        # --- THE DEFINITIVE FIX IS HERE ---
        # Step 1: Attempt to delete the collection from the vector store.
        try:
            chroma_client = chromadb.HttpClient(
                host=settings.CHROMA_DB_HOST,
                port=settings.CHROMA_DB_PORT
            )
            logger.info(f"Attempting to delete ChromaDB collection: {vector_collection_name}")
            
            # This is the core of the fix: We wrap the deletion in its own
            # try/except block to gracefully handle the case where it's already gone.
            try:
                chroma_client.delete_collection(name=vector_collection_name)
                logger.info(f"Successfully deleted ChromaDB collection: {vector_collection_name}")
            except Exception as chroma_exc:
                # This exception is often a ValueError in chromadb-client if the collection doesn't exist.
                # We log it as a warning, not a critical error, because our goal is to ensure it's gone.
                logger.warning(f"Could not delete ChromaDB collection '{vector_collection_name}', it might have been already deleted. Details: {chroma_exc}")
        
        except Exception as e:
            # This outer block catches connection errors to ChromaDB itself.
            logger.error(f"Failed to connect to ChromaDB to attempt deletion for collection '{vector_collection_name}': {e}", exc_info=True)
            # We can decide whether to proceed or fail here. Proceeding is often better.
        # --- END OF FIX ---
        
        # Step 2: Perform the primary database deletion. This is the source of truth.
        self.perform_destroy(instance)
        
        # Step 3: After successful local deletion, publish the event.
        try:
            rag_event_publisher.publish_collection_deleted(
                collection_id=collection_id_to_cleanup,
                owner_id=owner_id
            )
        except Exception as e:
            logger.critical(f"CRITICAL: KnowledgeCollection {collection_id_to_cleanup} was deleted, but event publishing failed: {e}", exc_info=True)
            
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    

class FileLinkCreateView(views.APIView):
    """
    Handles POST requests to link an existing file (from MS10) to a
    KnowledgeCollection, which triggers the ingestion process.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, collection_id):
        collection = get_object_or_404(KnowledgeCollection, id=collection_id)
        
        # Manually check ownership as this is not a generic DRF view.
        if str(collection.owner_id) != str(request.user.id):
            return Response({"error": "You do not have permission to modify this collection."}, status=status.HTTP_403_FORBIDDEN)

        serializer = FileLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_id = serializer.validated_data['file_id']
        
        # get_or_create is idempotent: it won't create a duplicate link.
        link, created = FileCollectionLink.objects.get_or_create(
            collection=collection,
            file_id=file_id,
            defaults={'status': FileCollectionLink.IngestionStatus.PENDING}
        )

        # If the file is already linked and processed, just inform the user.
        if not created and link.status == FileCollectionLink.IngestionStatus.COMPLETED:
            return Response({"message": "This file has already been successfully ingested into this collection."}, status=status.HTTP_200_OK)
        
        # If the link was just created or is in a retryable state, trigger the ingestion.
        link.status = FileCollectionLink.IngestionStatus.PENDING
        link.save()

        # Publish the event to the message bus for the MS12 worker to consume.
        try:
            rag_event_publisher.publish_ingestion_requested(
                link_id=str(link.id),
                collection_id=str(collection.id),
                vector_store_collection_name=collection.vector_store_collection_name,
                file_id=str(file_id),
                user_id=str(request.user.id),
                strategy_type=collection.strategy_type,
                config=collection.config
            )
        except Exception as e:
            logger.error(f"Failed to publish ingestion request for file {file_id} to collection {collection_id}: {e}", exc_info=True)
            # Update the status to 'error' if publishing fails, so the user knows something went wrong.
            link.status = FileCollectionLink.IngestionStatus.ERROR
            link.save()
            return Response({"error": "Could not start the ingestion process due to a messaging system error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"status": "pending", "message": "File ingestion process has been started."}, status=status.HTTP_202_ACCEPTED)
    




class FileLinkDeleteView(views.APIView):
    """
    Deletes the link between a file and a collection, and removes the file's
    data from the vector store.
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, collection_id, file_id):
        collection = get_object_or_404(KnowledgeCollection, id=collection_id)
        # Manually check ownership of the parent collection
        if str(collection.owner_id) != str(request.user.id):
            return Response({"error": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
            
        link = get_object_or_404(FileCollectionLink, collection=collection, file_id=file_id)
        
        try:
            # 1. Delete data from ChromaDB
            chroma_client = chromadb.HttpClient(host=settings.CHROMA_DB_HOST, port=settings.CHROMA_DB_PORT)
            vector_collection = chroma_client.get_collection(name=collection.vector_store_collection_name)
            
            logger.info(f"Deleting vectors from collection '{collection.vector_store_collection_name}' where source_file_id is '{str(file_id)}'")
            vector_collection.delete(where={"source_file_id": str(file_id)})
            
            # 2. Delete the link from our database
            link.delete()
            
            return Response(status=status.HTTP_204_NO_CONTENT)
            
        except Exception as e:
            logger.error(f"Error deleting file link for file {file_id} from collection {collection_id}: {e}", exc_info=True)
            return Response({"error": "An internal error occurred while removing the file from the collection."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CollectionClearView(views.APIView):
    """
    Deletes all file links and clears all data from a collection's vector store,
    but leaves the collection metadata intact.
    """
    permission_classes = [permissions.IsAuthenticated, IsCollectionOwner]

    def post(self, request, collection_id):
        collection = get_object_or_404(KnowledgeCollection, id=collection_id)
        # Use the standard permission class to check ownership of the collection
        self.check_object_permissions(request, collection)
        
        try:
            # 1. Delete all data from ChromaDB
            # The safest way is to delete and re-create the collection
            chroma_client = chromadb.HttpClient(host=settings.CHROMA_DB_HOST, port=settings.CHROMA_DB_PORT)
            logger.warning(f"Clearing all data from ChromaDB collection: {collection.vector_store_collection_name}")
            chroma_client.delete_collection(name=collection.vector_store_collection_name)
            chroma_client.create_collection(name=collection.vector_store_collection_name)
            
            # 2. Delete all links from our database for this collection
            links = FileCollectionLink.objects.filter(collection=collection)
            logger.info(f"Deleting {links.count()} file links from database for collection {collection_id}")
            links.delete()
            
            return Response({"status": "success", "message": "Collection has been cleared."}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error clearing collection {collection_id}: {e}", exc_info=True)
            return Response({"error": "An internal error occurred while clearing the collection."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)