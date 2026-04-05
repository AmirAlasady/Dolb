# MS5/messaging/event_publisher.py
from .rabbitmq_client import rabbitmq_client

class InferenceJobPublisher:
    def publish_job(self, job_payload: dict):
        # This is a standard job, it goes to a 'topic' exchange. No change needed.
        rabbitmq_client.publish(
            exchange_name='inference_exchange',
            routing_key='inference.job.start',
            body=job_payload,
            exchange_type='topic' # Explicitly stating the default is good practice
        )

    def publish_cancellation_request(self, job_id: str, user_id: str):
        # --- THE FIX IS HERE ---
        # This is a broadcast, so we explicitly tell the client to
        # declare the exchange as 'fanout'.
        rabbitmq_client.publish(
            exchange_name='job_control_fanout_exchange',
            routing_key='job.cancellation.requested', # routing_key is ignored by fanout
            body={"job_id": job_id, "user_id": user_id},
            exchange_type='fanout' # <-- THIS IS THE CRITICAL CHANGE
        )
        # --- END OF FIX ---

inference_job_publisher = InferenceJobPublisher()