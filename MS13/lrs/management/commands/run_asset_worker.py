import pika, json, time, os, shutil, traceback, logging
from pathlib import Path
from django import db
from django.core.management.base import BaseCommand
from django.conf import settings
from huggingface_hub import snapshot_download
from lrs.models import LocalModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - WORKER - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def process_download_job(payload: dict):
    model_id = payload.get("model_id")
    huggingface_id = payload.get("huggingface_id")
    
    logger.info(f"--- [JOB {model_id}] STARTING for model: {huggingface_id} ---")
    model_record = None

    try:
        # STEP 1: DB FETCH
        logger.info(f"[JOB {model_id}] STEP 1: Fetching record from DB...")
        model_record = LocalModel.objects.get(id=model_id)
        logger.info(f"[JOB {model_id}] SUCCESS: Record found.")

        # STEP 2: IMMEDIATE STATUS UPDATE
        model_record.status = LocalModel.Status.DOWNLOADING
        model_record.error_message = None
        model_record.save()
        logger.info(f"[JOB {model_id}] SUCCESS: Status set to DOWNLOADING in DB.")

        # STEP 3: TOKEN CHECK
        hf_token = os.getenv('HUGGING_FACE_HUB_TOKEN')
        if not hf_token: raise ValueError("HUGGING_FACE_HUB_TOKEN is not set.")
        logger.info(f"[JOB {model_id}] SUCCESS: HF Token found.")
        
        # STEP 4: PERMISSION & PATH CHECK
        storage_path = Path(settings.MODEL_STORAGE_PATH)
        logger.info(f"[JOB {model_id}] STEP 4: Checking permissions for storage path: {storage_path}")
        if not storage_path.exists():
            storage_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"[JOB {model_id}] Storage path created.")
        
        test_file = storage_path / f"permission_test_{model_id}.tmp"
        test_file.touch()
        test_file.unlink()
        logger.info(f"[JOB {model_id}] SUCCESS: Write permissions confirmed for {storage_path}.")
        
        final_model_path = storage_path / huggingface_id

        # STEP 5: DOWNLOAD
        logger.info(f"[JOB {model_id}] STEP 5: Starting download for '{huggingface_id}'...")
        snapshot_download(
            repo_id=huggingface_id, token=hf_token, local_dir=str(final_model_path),
            local_dir_use_symlinks=False, resume_download=True
        )
        logger.info(f"[JOB {model_id}] SUCCESS: snapshot_download function completed.")

        # STEP 6: FINAL DB UPDATE PREPARATION
        logger.info(f"[JOB {model_id}] STEP 6: Preparing to save final state...")
        model_record.local_path = str(final_model_path)
        model_record.status = LocalModel.Status.DOWNLOADED
        model_record.error_message = None
        logger.info(f"--- [JOB {model_id}] SUCCEEDED. ---")

    except Exception as e:
        logger.critical(f"--- [JOB {model_id}] FAILED AT STEP in try block ---", exc_info=True)
        if model_record:
            model_record.status = LocalModel.Status.ERROR
            model_record.error_message = traceback.format_exc()
    finally:
        logger.info(f"[JOB {model_id}] --- Entering FINALLY block ---")
        if model_record:
            try:
                model_record.save()
                logger.info(f"[JOB {model_id}] SUCCESS: Final status '{model_record.status}' saved to database.")
            except Exception as db_err:
                logger.critical(f"[JOB {model_id}] FATAL: Final database save FAILED: {db_err}", exc_info=True)
        
        db.connections.close_all()
        logger.info(f"[JOB {model_id}] Database connections closed.")


class Command(BaseCommand):
    help = 'Runs the LRS Asset Worker to download models from Hugging Face.'

    def handle(self, *args, **options):
        rabbitmq_url = settings.RABBITMQ_URL
        self.stdout.write(self.style.SUCCESS("--- LRS Asset Worker (MS14) ---"))

        while True:
            try:
                # 1. Establish the connection
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                channel = connection.channel()

                # 2. Set up the queue and binding (same as before)
                channel.exchange_declare(exchange='lrs_events', exchange_type='topic', durable=True)
                queue_name = 'lrs_download_queue'
                channel.queue_declare(queue=queue_name, durable=True)
                channel.queue_bind(exchange='lrs_events', queue=queue_name, routing_key='lrs.model.download.requested')

                self.stdout.write(self.style.SUCCESS(' [*] Worker is waiting for download requests.'))

                # 3. Define the callback within this scope
                def callback(ch, method, properties, body):
                    try:
                        payload = json.loads(body)
                        process_download_job(payload)
                    except Exception as e:
                        logger.error(f"Critical error processing job: {e}", exc_info=True)
                    finally:
                        # Acknowledge the message regardless of outcome
                        ch.basic_ack(delivery_tag=method.delivery_tag)

                # 4. Start consuming
                channel.basic_consume(queue=queue_name, on_message_callback=callback)
                channel.start_consuming()

            # 5. The key change: This exception is now more specific.
            # If start_consuming() is interrupted by a connection loss,
            # the outer while True loop will simply try to reconnect from scratch.
            except (pika.exceptions.AMQPConnectionError, pika.exceptions.StreamLostError) as e:
                self.stderr.write(self.style.ERROR(f'Connection to RabbitMQ lost: {e}. Retrying in 5 seconds...'))
                time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('Worker stopped by user.'))
                break
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'An unexpected critical error occurred in the main loop: {e}. Retrying...'))
                time.sleep(5)