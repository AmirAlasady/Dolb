import pika
import json
import time
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction

from nodes.models import Node, NodeStatus
from nodes.services import NodeService

class Command(BaseCommand):
    help = 'Listens for resource events to proactively update and validate nodes.'

    def handle(self, *args, **options):
        rabbitmq_url = settings.RABBITMQ_URL
        while True:
            try:
                connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
                channel = connection.channel()

                exchange_name = 'resource_events'
                channel.exchange_declare(exchange=exchange_name, exchange_type='topic', durable=True)
                
                queue_name = 'node_dependency_update_queue'
                channel.queue_declare(queue=queue_name, durable=True)
                
                # --- THE FIX IS HERE: Add the new binding key ---
                bindings = [
                    'model.deleted',
                    'tool.deleted',
                    'model.capabilities.updated',
                    'memory.bucket.deleted', # <-- ADD THIS LINE
                    'rag.collection.deleted', # <-- NEW BINDING
                ]
                # --- END OF FIX ---
                
                for binding_key in bindings:
                    self.stdout.write(f"Binding queue '{queue_name}' to exchange '{exchange_name}' with key '{binding_key}'...")
                    channel.queue_bind(
                        exchange=exchange_name,
                        queue=queue_name,
                        routing_key=binding_key
                    )
                
                self.stdout.write(self.style.SUCCESS(' [*] Node dependency worker is waiting for messages.'))
                channel.basic_consume(queue=queue_name, on_message_callback=self.callback)
                channel.start_consuming()

            except pika.exceptions.AMQPConnectionError:
                self.stderr.write(self.style.ERROR('Connection to RabbitMQ failed. Retrying in 5 seconds...'))
                time.sleep(5)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('Worker stopped.'))
                break

    def callback(self, ch, method, properties, body):
        try:
            data = json.loads(body)
            routing_key = method.routing_key
            
            with transaction.atomic():
                if routing_key == 'model.deleted':
                    self.handle_model_deletion(data.get('model_id'))
                elif routing_key == 'tool.deleted':
                    self.handle_tool_deletion(data.get('tool_id'))
                elif routing_key == 'model.capabilities.updated':
                    self.handle_capabilities_update(data.get('model_id'), data.get('new_capabilities'))
                
  
                # --- ADD THE NEW HANDLER CALL ---
                elif routing_key == 'rag.collection.deleted':
                    self.handle_rag_collection_deletion(data.get('collection_id'))
                # --- END OF ADDITION ---


                # --- THE FIX IS HERE: Add the new handler call ---
                elif routing_key == 'memory.bucket.deleted':
                    self.handle_memory_bucket_deletion(data.get('bucket_id'))
                # --- END OF FIX ---

        except json.JSONDecodeError:
            self.stderr.write(self.style.ERROR(f"Could not decode message body: {body}"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred in callback: {e}"))
        
        ch.basic_ack(delivery_tag=method.delivery_tag)

    def handle_model_deletion(self, model_id):
        if not model_id: return
        nodes = Node.objects.select_for_update().filter(configuration__model_config__model_id=model_id)
        count = nodes.update(status=NodeStatus.INACTIVE)
        self.stdout.write(f"Inactivated {count} nodes due to deletion of model {model_id}")

    def handle_tool_deletion(self, tool_id):
        if not tool_id: return
        # Using SQLite compatible loop
        candidate_nodes = Node.objects.select_for_update().filter(
            status__in=[NodeStatus.ACTIVE, NodeStatus.ALTERED],
            configuration__has_key='tool_config',
            configuration__tool_config__has_key='tool_ids'
        )
        nodes_to_process = []
        for node in candidate_nodes:
            tool_ids = node.configuration.get('tool_config', {}).get('tool_ids', [])
            if isinstance(tool_ids, list) and tool_id in tool_ids:
                nodes_to_process.append(node)
        
        if nodes_to_process:
            for node in nodes_to_process:
                node.configuration['tool_config']['tool_ids'].remove(tool_id)
                node.status = NodeStatus.ALTERED
                node.save()
            self.stdout.write(self.style.SUCCESS(f"Altered and healed {len(nodes_to_process)} nodes for deleted tool {tool_id}"))


    def handle_capabilities_update(self, model_id, new_capabilities):
        if not model_id or new_capabilities is None:
            return
        
        service = NodeService()
        nodes_to_update = Node.objects.select_for_update().filter(configuration__model_config__model_id=model_id)
        
        if not nodes_to_update.exists():
            self.stdout.write(f"Received capability update for model {model_id}, but no nodes are using it.")
            return

        new_template = service._generate_config_template_from_capabilities(model_id, new_capabilities)

        for node in nodes_to_update:
            final_config = new_template.copy()
            old_config = node.configuration
            
            if old_config.get("model_config", {}).get("parameters"):
                final_config["model_config"]["parameters"] = old_config["model_config"]["parameters"]
            if "memory_config" in final_config and "memory_config" in old_config:
                final_config["memory_config"] = old_config["memory_config"]
            if "rag_config" in final_config and "rag_config" in old_config:
                final_config["rag_config"] = old_config["rag_config"]
            if "tool_config" in final_config and "tool_config" in old_config:
                final_config["tool_config"] = old_config["tool_config"]
            
            node.configuration = final_config
            node.status = NodeStatus.ACTIVE
            node.save()
            
        self.stdout.write(f"Proactively updated {nodes_to_update.count()} nodes for model {model_id} capability change.")
    
    # --- ADD THIS NEW HANDLER METHOD ---
    def handle_memory_bucket_deletion(self, bucket_id):

        """
        Handles the event for a deleted memory bucket.
        Finds all nodes using this bucket, clears the reference, and marks them as altered.
        """
        self.stdout.write(f"Handling memory bucket deletion for bucket ID: {bucket_id}")

        if not bucket_id: return

        # This query will work on SQLite because it's a direct equality check on a value.
        nodes_to_update = Node.objects.select_for_update().filter(
            status__in=[NodeStatus.ACTIVE, NodeStatus.ALTERED],
            configuration__memory_config__bucket_id=bucket_id
        )

        if not nodes_to_update.exists():
            return
            
        count = 0
        for node in nodes_to_update:
            # Heal the node by removing the reference
            node.configuration['memory_config']['is_enabled'] = False
            node.configuration['memory_config']['bucket_id'] = None
            # Mark the node as altered to notify the user
            node.status = NodeStatus.ALTERED
            node.save()
            count += 1
            
        self.stdout.write(self.style.SUCCESS(f"Altered and healed {count} nodes for deleted memory bucket {bucket_id}"))
    # --- END OF NEW METHOD ---

  # --- ADD THIS NEW HANDLER METHOD ---
    def handle_rag_collection_deletion(self, collection_id):
        """
        Handles the event for a deleted RAG collection.
        Finds all nodes using this collection, clears the reference, and marks them as altered.
        """
        self.stdout.write(self.style.SUCCESS(f"Handling RAG collection deletion for ID: {collection_id}"))
        if not collection_id: return

        # This query finds all nodes where the rag_config dictionary contains a 'collection_id'
        # key with the matching value.
        nodes_to_update = Node.objects.select_for_update().filter(
            status__in=[NodeStatus.ACTIVE, NodeStatus.ALTERED],
            configuration__rag_config__collection_id=collection_id
        )

        if not nodes_to_update.exists():
            self.stdout.write(f"No nodes found using RAG collection {collection_id}.")
            return
            
        count = 0
        for node in nodes_to_update:
            # Heal the node by disabling RAG and clearing the ID.
            if 'rag_config' in node.configuration:
                node.configuration['rag_config']['is_enabled'] = False
                node.configuration['rag_config']['collection_id'] = None
                # Mark the node as altered to notify the user of the change.
                node.status = NodeStatus.ALTERED
                node.save()
                count += 1
                
        self.stdout.write(self.style.SUCCESS(f"Altered and healed {count} nodes for deleted RAG collection {collection_id}"))
    # --- END OF NEW METHOD ---