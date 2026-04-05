# MS11/rag_internals/servicer.py

import grpc
import logging
import chromadb
from django.conf import settings
from sentence_transformers import SentenceTransformer

from . import rag_pb2, rag_pb2_grpc
from rag_control_plane.models import KnowledgeCollection, FileCollectionLink # <-- Import FileCollectionLink

logging.basicConfig(level=logging.INFO, format='%(asctime)s - MS11-gRPC - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Embedding model is loaded once on startup
try:
    EMBEDDING_MODEL = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    logger.info(f"Successfully loaded embedding model: {settings.EMBEDDING_MODEL_NAME}")
except Exception as e:
    logger.critical(f"FATAL: Could not load embedding model! {e}", exc_info=True)
    EMBEDDING_MODEL = None

# --- THE FIX: The servicer now implements BOTH service interfaces ---
class RAGServicer(rag_pb2_grpc.RAGServiceServicer, rag_pb2_grpc.RAGInternalServiceServicer):
    def __init__(self):
        if not EMBEDDING_MODEL:
            raise RuntimeError("Embedding model is not available.")
        self.chroma_client = chromadb.HttpClient(
            host=settings.CHROMA_DB_HOST,
            port=settings.CHROMA_DB_PORT
        )

    # --- This is the original, unchanged method for MS5 ---
    def RetrieveRelevantChunks(self, request, context):
        logger.info(f"gRPC [RetrieveChunks]: Received request for collection '{request.collection_id}'.")
        try:
            collection_meta = KnowledgeCollection.objects.get(id=request.collection_id, owner_id=request.user_id)
            vector_collection = self.chroma_client.get_collection(name=collection_meta.vector_store_collection_name)
            query_embedding = EMBEDDING_MODEL.encode(request.query).tolist()
            results = vector_collection.query(query_embeddings=[query_embedding], n_results=request.top_k or 3)
            
            response = rag_pb2.RetrieveResponse()
            documents = results.get('documents', [[]])[0]
            metadatas = results.get('metadatas', [[]])[0]
            distances = results.get('distances', [[]])[0]

            for content, meta, score in zip(documents, metadatas, distances):
                # Ensure metadata is a dict of strings
                safe_meta = {str(k): str(v) for k, v in meta.items()} if meta else {}
                chunk = rag_pb2.DocumentChunk(content=content, metadata=safe_meta, score=score)
                response.chunks.append(chunk)

            logger.info(f"gRPC [RetrieveChunks]: Found {len(response.chunks)} relevant chunks.")
            return response

        except KnowledgeCollection.DoesNotExist:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Knowledge collection not found or permission denied.")
            return rag_pb2.RetrieveResponse()
        except Exception as e:
            logger.error(f"gRPC [RetrieveChunks]: Internal error for collection '{request.collection_id}': {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("An internal error occurred in the RAG service.")
            return rag_pb2.RetrieveResponse()

    # --- THIS IS THE NEW METHOD for MS12 ---
    def UpdateFileLinkStatus(self, request, context):
        """
        Handles the internal request from the MS12 worker to update the status
        of a file ingestion process.
        """
        link_id = request.link_id
        new_status = request.status
        logger.info(f"gRPC [UpdateStatus]: Received request to update link '{link_id}' to status '{new_status}'.")
        
        try:
            # Find the link and update its status.
            # Using .update() is efficient.
            updated_count = FileCollectionLink.objects.filter(id=link_id).update(status=new_status)
            
            if updated_count == 0:
                logger.warning(f"gRPC [UpdateStatus]: Link with ID '{link_id}' not found.")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"FileCollectionLink with ID '{link_id}' not found.")
                return rag_pb2.UpdateFileLinkStatusResponse(success=False)
            
            logger.info(f"gRPC [UpdateStatus]: Successfully updated link '{link_id}'.")
            return rag_pb2.UpdateFileLinkStatusResponse(success=True)

        except Exception as e:
            logger.error(f"gRPC [UpdateStatus]: Internal error for link '{link_id}': {e}", exc_info=True)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("An internal error occurred while updating status.")
            return rag_pb2.UpdateFileLinkStatusResponse(success=False)