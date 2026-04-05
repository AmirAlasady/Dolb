# in nodes/services.py

from django.conf import settings
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
import concurrent.futures
import uuid

# These imports must correctly point to your client, repository, and model files.
from nodes_internals.clients import ProjectServiceClient, ModelServiceClient, ToolServiceClient, MemoryServiceClient, RAGServiceClient  #KnowledgeServiceClient
from .repository import NodeRepository
from .models import Node, NodeStatus

class NodeService:
    """
    The service layer for handling all business logic related to Nodes.
    This is the definitive, synchronous, multi-threaded version.
    """
    def __init__(self):
        # Instantiate all dependencies. In a larger app, this would use dependency injection.
        self.node_repo = NodeRepository()

        # Instantiate all microservice clients.
        self.project_client = ProjectServiceClient()
        self.model_client = ModelServiceClient()
        self.tool_client = ToolServiceClient()
        self.memory_client = MemoryServiceClient()
        self.rag_client = RAGServiceClient()        


    def _validate_resources(self, jwt_token: str, project_id: str, configuration: dict):
        """
        Runs all validation checks against other microservices in parallel using a thread pool.
        """
        # If validation is disabled in settings, skip this entire process.
        if not settings.NODE_SERVICE_VALIDATION_ENABLED:
            return
            
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = []
            
            # --- Submit All Validation Tasks Concurrently ---

            # Task 1: Check project ownership.
    #-->>>>>>>>>>>>>>>>>>     
            futures.append(executor.submit(self.project_client.authorize_user, jwt_token, project_id))
    #-->>>>>>>>>>>>>>>>>>        


            # Task 2: Validate the AI Model.
            model_id = configuration.get("model_config", {}).get("model_id")
            if not model_id:
                raise ValidationError("Configuration must include 'model_config' with a 'model_id'.")
            futures.append(executor.submit(self.model_client.validate_model, jwt_token, model_id))


            # Task 3: Validate the Tools.
            tool_config = configuration.get("tool_config", {})
            if "tool_ids" in tool_config and tool_config["tool_ids"]:
                futures.append(
                    executor.submit(
                        self.tool_client.validate_tools,
                        jwt_token,
                        tool_config["tool_ids"]
                    )
                )

            memory_config = configuration.get("memory_config", {})
            if memory_config.get("is_enabled") and memory_config.get("bucket_id"):
                bucket_id = memory_config["bucket_id"]
                futures.append(
                    executor.submit(
                        self.memory_client.validate_buckets,
                        jwt_token,
                        [bucket_id] # The validation endpoint expects a list
                    )
                )
                
            rag_config = configuration.get("rag_config", {})
            if rag_config.get("is_enabled") and rag_config.get("collection_id"):
                collection_id = rag_config["collection_id"]
                futures.append(
                    executor.submit(
                        self.rag_client.validate_collections,
                        jwt_token,
                        [collection_id] # Validation endpoint expects a list
                    )
                )

            # --- Wait for all tasks to complete and check for any failures ---
            for future in concurrent.futures.as_completed(futures):
                # future.result() will do nothing if the task succeeded, but will
                # re-raise any exception (like PermissionDenied, NotFound) that
                # occurred in the thread, causing this entire method to fail.
                future.result()


    def get_nodes_for_project(self, *, project_id: uuid.UUID, user_id: uuid.UUID, jwt_token: str) -> list[Node]:
        """
        The use case for listing all nodes in a project.
        It first authorizes project-level access, then fetches the data.
        """
        # Step 1: Authorize that the user can even view this project's contents.
        self.project_client.authorize_user(jwt_token, str(project_id))
        
        # Step 2: If authorized, retrieve the nodes from the local database.
        return self.node_repo.find_by_project(project_id)



    def _generate_config_template_from_capabilities(self, model_id: str, capabilities: list) -> dict:
        """
        Generates a valid, empty configuration template based on a model's capabilities.
        """
        master_config = {"model_config": {"model_id": str(model_id)}}
        if "text" in capabilities:
            master_config["memory_config"] = {"is_enabled": False, "bucket_id": None}
            master_config["rag_config"] = {"is_enabled": False, "collection_id": None}
        if "tool_use" in capabilities:
            master_config["tool_config"] = {"tool_ids": []}
        # Add more capability-based configurations here...
        return master_config

    def create_draft_node(self, *, jwt_token: str, user_id: uuid.UUID, project_id: uuid.UUID, name: str) -> Node:
        # 1. Authorize project ownership BEFORE creating anything.
        self.project_client.authorize_user(jwt_token, str(project_id))

        # 2. If authorized, create the draft node.
        # The repository will save it with status='draft' and empty config by default.
        return self.node_repo.create(
            project_id=project_id,
            owner_id=user_id,
            name=name
        )

    # --- NEW METHOD: STAGE 2 ---
    def configure_node_model(self, *, jwt_token: str, node: Node, model_id: uuid.UUID) -> Node:
        """
        Configures or reconfigures a node with a new model.
        This process is "forward-looking" and resilient to the old model being deleted.
        """
        # 1. Fetch NEW model's capabilities. This is the only external call needed.
        #    It also validates user access to the new model.
        new_capabilities = self.model_client.get_model_capabilities(jwt_token, str(model_id))
        
        # 2. Generate the ideal, valid template for the NEW model.
        new_template = self._generate_config_template_from_capabilities(model_id, new_capabilities)
        
        # 3. Get the OLD configuration from the node's own storage.
        #    We trust this as the user's last known good configuration.
        old_config = node.configuration
        
        # 4. Perform best-effort migration of user settings onto the new template.
        final_config = new_template.copy()
        
        # Migrate parameters (always safe to carry over)
        if old_config.get("model_config", {}).get("parameters"):
            final_config["model_config"]["parameters"] = old_config["model_config"]["parameters"]

        # Migrate memory config IF the new template supports it
        if "memory_config" in final_config and "memory_config" in old_config:
            final_config["memory_config"] = old_config["memory_config"]

        # Migrate RAG config IF the new template supports it
        if "rag_config" in final_config and "rag_config" in old_config:
            final_config["rag_config"] = old_config["rag_config"]
        
        # Migrate tools IF the new template supports them
        if "tool_config" in final_config and "tool_config" in old_config:
            final_config["tool_config"] = old_config["tool_config"]
        
        # 5. Save the result. This action always "heals" the node to an ACTIVE state.
        return self.node_repo.update(
            node=node,
            name=node.name,
            configuration=final_config,
            status=NodeStatus.ACTIVE
        )

    # --- UPDATED METHOD: FINAL UPDATE ---
    def update_node(self, *, jwt_token: str, node: Node, name: str, configuration: dict) -> Node:
        # --- VALIDATION GAUNTLET ---

        # 1. Fetch the node's TRUSTED configuration template from the DB.
        trusted_config = node.configuration
        trusted_model_id = trusted_config.get("model_config", {}).get("model_id")

        # 2. Prevent Model Change (Problem 2)
        submitted_model_id = configuration.get("model_config", {}).get("model_id")
        if submitted_model_id and submitted_model_id != trusted_model_id:
            raise ValidationError("Changing the model is not allowed through this endpoint. Please use the '/configure-model' endpoint instead.")

        # 3. Validate Submitted Structure (Problem 1 - Arbitrary Injection)
        #    Ensure the user is not submitting keys that are not in the trusted template.
        for key in configuration:
            if key not in trusted_config:
                raise ValidationError(f"Configuration key '{key}' is not supported by the current model.")

        # 4. Deep Merge and Final Validation
        #    Start with a copy of the trusted config and update it with user values.

        if "rag_config" in configuration:
            rag_config = configuration.get("rag_config", {})
            if rag_config.get("is_enabled") and not rag_config.get("collection_id"):
                raise ValidationError({
                    "rag_config": "RAG is enabled, but no 'collection_id' was provided."
                })
            
        final_config = trusted_config.copy()
        
        # Update parameters
        if "parameters" in configuration.get("model_config", {}):
            final_config["model_config"]["parameters"] = configuration["model_config"]["parameters"]
        
        # Update memory, RAG, tools, etc.
        if "memory_config" in final_config and "memory_config" in configuration:
            final_config["memory_config"] = configuration["memory_config"]
        if "rag_config" in final_config and "rag_config" in configuration:
            final_config["rag_config"] = configuration["rag_config"]
        if "tool_config" in final_config and "tool_config" in configuration:
            final_config["tool_config"] = configuration["tool_config"]
        
        # 5. Perform final cross-service validation on the merged data
        #    This checks if the provided tool_ids, bucket_ids, etc. are valid.
        self._validate_resources(jwt_token, str(node.project_id), final_config)
            
        # 6. If all validations pass, save the changes.
        return self.node_repo.update(
            node=node,
            name=name,
            configuration=final_config,
            status=NodeStatus.ACTIVE
        )
        
    def delete_node(self, node: Node):
        """
        The use case for deleting a node. The view handles ownership check.
        This service delegates the deletion to the repository.
        """
        self.node_repo.delete(node)