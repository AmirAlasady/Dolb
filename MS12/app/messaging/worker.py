# MS12/app/messaging/worker.py
import asyncio
import json
import aio_pika
import chromadb
from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter


from app import config
from app.logging_config import logger
from app.internals.clients import DataServiceClient, RAGInternalClient

class IngestionWorker:
    def __init__(self, prefetch_count: int = 1): # Process one heavy CPU/GPU job at a time
        self.prefetch_count = prefetch_count
        self.data_client = DataServiceClient()
        self.rag_internal_client = RAGInternalClient()
        logger.info("Loading embedding model into memory...")
        self.embedding_model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
        logger.info("Embedding model loaded successfully.")
        self.chroma_client = chromadb.HttpClient(host=config.CHROMA_DB_HOST, port=config.CHROMA_DB_PORT)

    async def process_message(self, message: aio_pika.IncomingMessage):
        payload = {}
        link_id = "unknown"
        try:
            # Don't requeue failed ingestion jobs. They should be logged and investigated.
            async with message.process(requeue=False):
                payload = json.loads(message.body.decode())
                link_id = payload.get("link_id")
                logger.info(f"--- [INGESTION JOB {link_id}] Received ---")

                # 1. Immediately update status to INGESTING
                await self.rag_internal_client.update_link_status(link_id, "ingesting")

                # 2. Get file content from MS10
                file_content_data = await self.data_client.get_file_content(
                    file_id=payload['file_id'], user_id=payload['user_id']
                )

                if file_content_data.get("type") != "text_content":
                    raise ValueError(f"Received non-text content '{file_content_data.get('type')}' for ingestion.")
                
                raw_text = file_content_data.get("content")
                if not raw_text or not raw_text.strip():
                    logger.warning(f"[{link_id}] Received empty or whitespace-only text content. Marking as complete.")
                    await self.rag_internal_client.update_link_status(link_id, "completed")
                    return

                # 3. Chunk the text
                # In a real system, chunk_size might come from payload['config']
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
                chunks = text_splitter.split_text(raw_text)
                logger.info(f"[{link_id}] Split document into {len(chunks)} chunks.")

                if not chunks:
                    logger.warning(f"[{link_id}] Document produced no chunks after splitting. Marking as complete.")
                    await self.rag_internal_client.update_link_status(link_id, "completed")
                    return

                # 4. Embed and Index the chunks in ChromaDB
                vector_collection = self.chroma_client.get_or_create_collection(name=payload['vector_store_collection_name'])
                
                logger.info(f"[{link_id}] Generating embeddings for {len(chunks)} chunks...")
                embeddings = self.embedding_model.encode(chunks, show_progress_bar=False).tolist()
                metadatas = [{"source_file_id": payload['file_id']} for _ in chunks]
                ids = [f"{link_id}_{i}" for i in range(len(chunks))]

                vector_collection.add(
                    embeddings=embeddings,
                    documents=chunks,
                    metadatas=metadatas,
                    ids=ids
                )
                logger.info(f"[{link_id}] Successfully indexed {len(chunks)} chunks into ChromaDB.")

                # 5. Update status to COMPLETED
                await self.rag_internal_client.update_link_status(link_id, "completed")
                logger.info(f"--- [INGESTION JOB {link_id}] Finished Successfully ---")

        except Exception as e:
            logger.error(f"--- [INGESTION JOB {link_id}] FAILED: {e} ---", exc_info=True)
            if link_id != "unknown":
                await self.rag_internal_client.update_link_status(link_id, "error")

    async def run(self):
        while True:
            try:
                connection = await aio_pika.connect_robust(config.RABBITMQ_URL, loop=asyncio.get_event_loop())
                async with connection:
                    channel = await connection.channel()
                    await channel.set_qos(prefetch_count=self.prefetch_count)
                    
                    exchange = await channel.declare_exchange('rag_events', aio_pika.ExchangeType.TOPIC, durable=True)
                    queue = await channel.declare_queue('rag_ingestion_queue', durable=True)
                    await queue.bind(exchange, 'rag.ingestion.requested')
                    
                    logger.info(" [*] RAG Ingestion Worker is ready and waiting for jobs.")
                    
                    async with queue.iterator() as queue_iter:
                        async for message in queue_iter:
                            asyncio.create_task(self.process_message(message))
                    
                    # This await will keep the connection alive
                    await asyncio.Event().wait()
            except aio_pika.exceptions.AMQPConnectionError as e:
                logger.error(f"RabbitMQ connection lost: {e}. Retrying in 5 seconds...")
                await asyncio.sleep(5)