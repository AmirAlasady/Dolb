

#  Mega AI Platform - Microservices Architecture Documentation
<img width="1471" height="796" alt="image" src="https://github.com/user-attachments/assets/121f526f-9fc9-4b8e-8e11-7e128cef0bbf" />

## Topics Table

**1. Executive Overview**
*   1.1 System Purpose & Business Capabilities
*   1.2 Domain-Driven Design (DDD) & Bounded Contexts
*   1.3 High-Level Architecture Flow

**2. Service Overview (Bounded Contexts & Domain Boundaries)**
*   **Identity & Organization Domain**
    *   MS1 (Auth Service): Identity & JWT Issuance
    *   MS2 (Project Service): Workspace & Resource Grouping
*   **AI Asset & Runtime Domain**
    *   MS3 (Model Service): Global & Private AI Model Configurations
    *   MS13 (Local Runtime Service): Local HuggingFace Model Orchestration (TGI)
*   **Agent & Graph Control Domain**
    *   MS4 (Node Service): AI Agent / Node Configuration
    *   MS14 (Graph Control Plane): Topology, Routing Rules & Triggers
    *   MS15 (Graph Execution Engine): High-Concurrency Rust Evaluation Engine
*   **Inference & Execution Domain**
    *   MS5 (Inference Orchestrator): Context Gathering & Job Dispatching
    *   MS6 (Inference Executor): LangChain/LLM Processing & Tool Calling
    *   MS8 (Results Service): Real-Time WebSocket Streaming
*   **Context & Capability Domain**
    *   MS7 (Tool Service): Dynamic Tool Execution & Human-in-the-Loop (HITL)
    *   MS9 (Memory Service): Conversation History & Context Buffers
    *   MS10 (Data Service): File Storage (S3/MinIO) & Document Parsing
    *   MS11 (RAG Control Plane): Vector DB (ChromaDB) Management
    *   MS12 (RAG Ingestion Worker): Async Chunking & Embedding

**3. Integration Patterns & Communication**
*   3.1 Synchronous Internal Communication (gRPC)
*   3.2 Asynchronous Event-Driven Communication (RabbitMQ)
*   3.3 Real-Time Client Communication (WebSockets, Channels, FastAPI)

**4. Data Architecture & Consistency**
*   4.1 Database-per-Service Pattern (SQLite/PostgreSQL)
*   4.2 Distributed Transactions & Saga Pattern (Resource Cleanup)
*   4.3 Ephemeral State & Lock Management (Redis)

**5. API Specifications & Contracts**
*   5.1 Authentication & Authorization Strategy (Stateless JWT)
*   5.2 Public REST APIs vs. Internal APIs
*   5.3 Backward Compatibility & Versioning

**6. Operational Guide (DevSecOps)**
*   6.1 Deployment Automation & Containerization (Docker)
*   6.2 Centralized Logging & Observability
*   6.3 Security Protocols & Secrets Management

---

## 1. Executive Overview

### 1.1 System Purpose & Business Capabilities
The platform is a highly scalable, distributed enterprise AI orchestration system. It enables users to configure custom AI agents ("Nodes"), equip them with contextual capabilities (Tools, Memory, RAG, File parsing), and string them together into complex, autonomous logic circuits ("Graphs"). 

The system is designed to support both standard cloud-based LLMs (OpenAI, Google, Anthropic) and locally hosted, privacy-first open-source models via Text Generation Inference (TGI). It features strict Human-in-the-loop (HITL) security policies, robust asynchronous execution, and real-time streaming feedback to clients.

### 1.2 Domain-Driven Design (DDD) & Bounded Contexts
The architecture strictly adheres to Domain-Driven Design (DDD) principles. The monolithic concept of an "AI Agent" has been decomposed into highly cohesive, loosely coupled microservices (MS1 through MS15), each owned by specific domain boundaries:

*   **Loose Coupling:** Services do not share databases. Data required by multiple services is passed via secure gRPC calls or asynchronous RabbitMQ events.
*   **Single Responsibility Principle:** For example, **MS11** (RAG Control Plane) manages the metadata of vector collections, while **MS12** (RAG Ingestion Worker) handles the heavy CPU/GPU task of embedding generation, and **MS10** (Data Service) handles the physical file extraction.
*   **State Separation:** Configuration state (Django/SQLite/Postgres) is strictly separated from runtime execution state (**MS15** uses Rust and Redis to manage high-throughput, ephemeral graph execution states).

### 1.3 High-Level Architecture Flow

The system utilizes a polyglot microservices architecture combining **Python (Django & FastAPI)** for control planes and integrations, and **Rust (Axum & Tokio)** for high-performance state machine evaluation.

1.  **Client Interaction & Auth:** Clients authenticate via **MS1**, receiving a stateless JWT. All subsequent REST API calls to bounded contexts (e.g., **MS2** for Projects, **MS4** for Nodes, **MS14** for Graphs) are authorized via this JWT.
2.  **Resource Configuration:** Users build complex AI pipelines by linking Nodes (**MS4**) with Models (**MS3/MS13**), Tools (**MS7**), Memory (**MS9**), and Knowledge Bases (**MS11**).
3.  **Graph Execution:** When a Graph is triggered (via Webhook, Schedule, or UI in **MS14**), the topology is serialized into a blueprint and sent to the **MS15** Execution Engine.
4.  **State Machine & Orchestration:** **MS15** (Rust) uses Redis to track node state, evaluating rules and routing logic. When a Node is ready, MS15 dispatches an `InferenceRequestMessage` to **MS5**.
5.  **Inference Pipeline:** **MS5** acts as the orchestrator. It uses high-speed **gRPC** calls to gather the necessary context (Chat History from MS9, Vector chunks from MS11, File data from MS10) and sends a massive, compiled payload to **MS6** (Inference Executor).
6.  **Action & Streaming:** **MS6** runs the LangChain agent loop. If the agent calls a tool, MS6 triggers **MS7**, which can halt execution to request human approval via WebSockets. As the LLM generates tokens, MS6 streams them to RabbitMQ, where **MS8** picks them up and pushes them to the user via WebSockets.
7.  **Distributed Consistency:** If a user deletes their account (**MS1**) or a project (**MS2**), RabbitMQ fan-out events trigger the **Saga Pattern**, ensuring all downstream services (**MS3, MS4, MS7, MS9, MS10, MS11, MS14**) clean up their respective database records and physical assets (S3 buckets, ChromaDB collections, Docker containers) idempotently.

# 📚 API Specifications & Integration Contracts

This document outlines the exact API specifications, schemas, and contracts for all microservices in the Mega AI Platform. It is designed following Domain-Driven Design (DDD) to ensure clear boundaries and contracts between services.

---

## 🔒 5.1 Authentication, Authorization, & Backward Compatibility

**Authentication Strategy:**
*   **Method:** Stateless JSON Web Tokens (JWT).
*   **Header Requirement:** All protected endpoints require the header: `Authorization: Bearer <your_jwt_token>`.
*   **Decentralized Verification:** MS1 issues the JWT. MS2–MS15 independently verify the token using a shared `JWT_SECRET_KEY` and validate the `issuer` claim (`https://ms1.auth-service.com`).
*   **Identity Claim:** The token payload includes `user_id`, mapping to `TokenUser.id` across all services.

**Backward Compatibility & Versioning:**
*   **URI Versioning:** All APIs strictly use URI versioning (e.g., `/api/v1/`). Breaking changes require a bump to `/api/v2/` while keeping `/api/v1/` operational until deprecation.
*   **Extensibility:** JSON schemas are designed to ignore unknown fields (Open-Closed Principle), allowing non-breaking additive updates.

---

## 🧍 MS1: Identity & Auth Service (`accounts`)

Manages user identity, registration, JWT issuance, and account lifecycle (Soft Deletion Saga).

### 1. `POST /ms1/api/v1/auth/register/`
*   **Description:** Registers a new user account.
*   **Request Body (application/json):**
    ```json
    {
      "email": "user@example.com",
      "username": "johndoe",
      "password": "SecurePassword123!",
      "password2": "SecurePassword123!"
    }
    ```
*   **Response (201 Created):** `{ "email": "user@example.com", "username": "johndoe" }`

### 2. `POST /ms1/api/v1/auth/token/`
*   **Description:** Authenticates user and returns JWT pair. Includes custom claims (`username`, `is_staff`).
*   **Request Body:** `{ "email": "user@example.com", "password": "SecurePassword123!" }`
*   **Response (200 OK):** `{ "access": "eyJhbG...", "refresh": "eyJhbG..." }`

### 3. `POST /ms1/api/v1/auth/token/refresh/`
*   **Description:** Rotates the refresh token (Blacklists old, issues new).
*   **Request Body:** `{ "refresh": "eyJhbG..." }`
*   **Response (200 OK):** `{ "access": "...", "refresh": "..." }`

### 4. `GET /ms1/api/v1/auth/me/`
*   **Description:** Retrieves the authenticated user's profile.
*   **Response (200 OK):** `{ "id": "uuid", "email": "user@...", "username": "johndoe", "is_active": true, "date_joined": "2024-01-01T..." }`

### 5. `PUT /ms1/api/v1/auth/me/`
*   **Description:** Updates current user's password.
*   **Request Body:** `{ "current_password": "...", "new_password": "..." }`
*   **Response (200 OK):** `{ "detail": "Password updated successfully." }`

### 6. `DELETE /ms1/api/v1/auth/me/`
*   **Description:** Initiates the asynchronous User Deletion Saga across all microservices. Soft-deletes user immediately, blacklists tokens, and publishes `user.deletion.initiated`.
*   **Response (202 Accepted):** `{ "message": "Your account deletion request has been received and is being processed." }`
*   **Response (409 Conflict):** If saga is already running.

---

## 📁 MS2: Project Service (`project`)

Workspaces serving as the primary authorization boundary for all AI resources.

### 1. `POST /ms2/api/v1/projects/`
*   **Description:** Create a new project.
*   **Request Body:**
    ```json
    {
      "name": "My Workspace",
      "metadata": { "department": "AI Research" }
    }
    ```
*   **Response (201 Created):** `{ "id": "uuid", "name": "My Workspace", "owner_id": "uuid", "created_at": "...", "metadata": {...} }`

### 2. `GET /ms2/api/v1/projects/`
*   **Description:** List all projects owned by the authenticated user.
*   **Response (200 OK):** `[ { "id": "uuid", "name": "...", "owner_id": "..." } ]`

### 3. `GET /ms2/api/v1/projects/<uuid>/`
*   **Description:** Retrieve details of a specific project.
*   **Response (200 OK):** Project JSON object.

### 4. `PUT / PATCH /ms2/api/v1/projects/<uuid>/`
*   **Description:** Update project details.
*   **Request Body:** `{ "name": "Updated Name", "metadata": {} }`

### 5. `DELETE /ms2/api/v1/projects/<uuid>/`
*   **Description:** Initiates the asynchronous Project Deletion Saga. Flags project as `pending_deletion` and publishes `project.deletion.initiated`.
*   **Response (202 Accepted):** `{ "message": "Project deletion process has been successfully initiated." }`

### 6. *Internal* `GET /ms2/internal/v1/projects/<uuid>/authorize`
*   **Description:** Internal endpoint used by MS4, MS9, MS10, MS11, MS14 to verify if the user (via forwarded JWT) owns the project.
*   **Response:** `204 No Content` (Authorized), `403 Forbidden` (Denied), `404 Not Found`.

---

## 🧠 MS3: Model Service (`aimodels`)

Manages AI Model Configurations. Admins configure `ProviderSchemas` (templates), and users instantiate them into unified `AIModel` configurations.

### Admin Setup (Django Admin)
*   Admins create a `ProviderSchema` (e.g., `openai`). They provide a `credentials_schema` (defining `api_key`) and `model_blueprints` (defining models like `gpt-4o`, required parameters, and capabilities `[text, vision, tool_use]`).

### 1. `GET /ms3/api/v1/models/`
*   **Description:** List all models available to the user (System Models + User's Private Models).
*   **Response (200 OK):** Returns array of models. System models show full config; User models have secrets (like API keys) masked (`********`).

### 2. `POST /ms3/api/v1/models/`
*   **Description:** User creates a custom model instance using a simple input format. The system intercepts this via the "Assembly Line" pattern, looks up the Admin Blueprint, and compiles a full backward-compatible JSON schema.
*   **Request Body:**
    ```json
    {
      "name": "My Personal GPT",
      "provider": "openai",
      "model_name": "gpt-4o",
      "credentials": { "api_key": "sk-proj-0000000000000000000000000000000000000000" },
      "parameters": { "temperature": 0.7 }
    }
    ```
*   **Response (201 Created):** Full compiled model schema.

### 3. `GET /ms3/api/v1/models/<uuid>/`
*   **Description:** Retrieve a specific model.

### 4. `PUT /ms3/api/v1/models/<uuid>/`
*   **Description:** Update a model. `provider` and `model_name` cannot be changed.
*   **Request Body:** `{ "name": "Updated", "credentials": {...}, "parameters": {...} }`
*   **Side-Effect:** If `capabilities` change structurally due to backend blueprint updates, MS3 publishes `model.capabilities.updated`.

### 5. `DELETE /ms3/api/v1/models/<uuid>/`
*   **Description:** Deletes a user model and publishes `model.deleted` to notify MS4 (Node Service) to deactivate dependent nodes.

---

## 🤖 MS4: Node Service (`nodes`)

Nodes are AI Agents. Building a node is a two-stage process (Draft -> Elevate) to ensure validation against models.

### 1. `POST /ms4/api/v1/nodes/draft/`
*   **Description:** (STAGE 1) Creates a draft placeholder node.
*   **Request Body:** `{ "name": "Research Agent", "project_id": "uuid" }`
*   **Response (201 Created):** Node created with `status: "draft"` and empty configuration.

### 2. `POST /ms4/api/v1/nodes/<uuid>/configure-model/`
*   **Description:** (STAGE 2) Elevates the node. MS4 contacts MS3 via gRPC to fetch the model's capabilities, generates a capability-aligned configuration template (e.g., exposing `rag_config` only if the model supports `text`), and heals the node to `active` status.
*   **Request Body:** `{ "model_id": "ms3-model-uuid" }`
*   **Response (200 OK):** Elevated node with compiled JSON `configuration`.

### 3. `GET /ms4/api/v1/projects/<project_id>/nodes/`
*   **Description:** List nodes within a project.

### 4. `PUT /ms4/api/v1/nodes/<uuid>/`
*   **Description:** Update node configuration (adding RAG, Tools, Memory).
*   **Validation:** Prohibits changing `model_config.model_id` (must use `/configure-model/`). Cross-validates all resource IDs synchronously via gRPC (Checks MS7 for Tools, MS9 for Memory, MS11 for RAG).
*   **Request Body:**
    ```json
    {
      "name": "Updated Agent",
      "configuration": {
        "model_config": { "parameters": {"temperature": 0.5} },
        "tool_config": { "tool_ids": ["ms7-tool-uuid"] },
        "memory_config": { "is_enabled": true, "bucket_id": "ms9-bucket-uuid" },
        "rag_config": { "is_enabled": true, "collection_id": "ms11-col-uuid" }
      }
    }
    ```

### 5. `DELETE /ms4/api/v1/nodes/<uuid>/`
*   **Description:** Deletes a node. If `is_used_in_graph` is True, notifies MS14 via Webhook to detach it.

---

## 🧰 MS7: Tool Service (`tools`)

Manages Tool definitions, Webhook routing, and Human-In-The-Loop (HITL) policies.

### 1. `POST /ms7/api/v1/tools/`
*   **Description:** Create a standard user tool (Webhook).
*   **Request Body:**
    ```json
    {
      "name": "send_slack_message",
      "tool_type": "standard",
      "is_sensitive": true,
      "definition": {
        "name": "send_slack_message",
        "description": "Sends a message to Slack.",
        "parameters": { "type": "object", "properties": { "message": {"type": "string"} }, "required": ["message"] },
        "execution": { "type": "webhook", "method": "POST", "url": "https://hooks.slack.com/..." }
      }
    }
    ```

### 2. `GET / PUT / DELETE /ms7/api/v1/tools/<uuid>/`
*   **Description:** Standard CRUD operations. Owner constrained.

### 3. `GET / PUT / PATCH /ms7/api/v1/policy/`
*   **Description:** Manages the user's HITL bypass policy.
*   **Request Body (PATCH):** `{ "auto_approve_all": false, "auto_approved_tool_ids": ["uuid-of-trusted-tool"] }`

### 4. `GET /ms7/api/v1/hitl/pending/`
*   **Description:** Fetches all pending HITL requests requiring human approval for the calling user.
*   **Response (200 OK):** `{"pending_approvals": [{"approval_token": "...", "tool_name": "...", "tool_args": {...}}], "count": 1}`

### 5. `POST /ms7/api/v1/hitl/<approval_token>/approve/` (and `/deny/`)
*   **Description:** Resolves a pending HITL request. Used by the frontend when a user clicks "Approve" on the WebSocket toast.

---

## 🧠 MS9: Memory Service (`memory`)

Conversation history and context buffers.

### 1. `POST /ms9/api/v1/buckets/`
*   **Description:** Create a new memory bucket.
*   **Request Body:** `{ "name": "Chat Session", "project_id": "uuid", "memory_type": "conversation_buffer_window", "config": {"k": 10} }`

### 2. `POST /ms9/api/v1/buckets/<uuid>/clear/`
*   **Description:** Deletes all `Message` records within a bucket.

### 3. `GET /ms9/api/v1/buckets/<uuid>/messages/`
*   **Description:** List all messages inside a bucket.

### 4. `POST /ms9/api/v1/buckets/<uuid>/export/`
*   **Description:** Compiles all history into a structured JSON file.
*   **Response:** File Download `HttpResponse` with `Content-Disposition: attachment`.

### 5. `POST /ms9/api/v1/buckets/import/`
*   **Description:** Recreates a bucket from an exported JSON file.
*   **Request:** `multipart/form-data`. Fields: `file`, `project_id`.

---

## 📚 MS11: RAG Control Plane (`rag_control_plane`)

Vector database collections metadata and file linking.

### 1. `POST /ms11/api/v1/projects/<project_id>/collections/`
*   **Description:** Create a new ChromaDB collection wrapper.
*   **Request Body:** `{ "name": "Company Docs", "description": "...", "strategy_type": "vector_db" }`

### 2. `POST /ms11/api/v1/collections/<collection_id>/add_file/`
*   **Description:** Links a file (from MS10) to this collection. This triggers `rag.ingestion.requested` for MS12.
*   **Request Body:** `{ "file_id": "ms10-file-uuid" }`
*   **Response (202 Accepted):** File Collection Link created with status `pending`.

### 3. `DELETE /ms11/api/v1/collections/<collection_id>/files/<file_id>/`
*   **Description:** Unlinks a file and synchronously deletes its vectors from ChromaDB where `source_file_id == file_id`.

### 4. `POST /ms11/api/v1/collections/<collection_id>/clear/`
*   **Description:** Deletes and recreates the physical ChromaDB collection, removing all embeddings, and drops all file links from the database.

---

## 💾 MS10: Data Service (`data`)

Raw file storage (S3/MinIO) and metadata tracking.

### 1. `POST /ms10/api/v1/projects/<project_id>/files/`
*   **Description:** Uploads a user file to S3, securely determines Mimetype using `python-magic` with extension overrides for Office docs, and stores metadata.
*   **Request Type:** `multipart/form-data`. Field: `file`.
*   **Response (201 Created):** `{ "id": "uuid", "filename": "...", "mimetype": "application/pdf", "size_bytes": 1024 }`

### 2. `GET / DELETE /ms10/api/v1/files/<uuid>/`
*   **Description:** Retrieve metadata or physically delete the file from object storage.

### 3. *Internal* `POST /ms10/api/v1/projects/<project_id>/upload_generated/`
*   **Description:** Used by MS6 (Executor) to upload LLM-generated images (e.g., from DALL-E or Diffusers) directly to the user's project.

---

## 🕸️ MS14: Graph Control Plane (`graphcontrol`)

Manages the complex relational topology of Graphs, Nodes, Edges, Rules, and Triggers.

### 1. Graph & Node CRUD
*   `POST /ms14/api/v1/graphs/`: Create Graph (`name`, `project_id`).
*   `POST /ms14/api/v1/nodes/`: Create GNode. Set `is_start: true` for entry points (auto-generates Seed Projection).
*   `POST /ms14/api/v1/nodes/<uuid>/attach-ms4/`: Links an MS4 Agent to this GNode.
*   `POST /ms14/api/v1/nodes/<uuid>/detach-ms4/`: Unlinks MS4 Agent.

### 2. Edges
*   `POST /ms14/api/v1/edges/`: Connects two GNodes.
    *   *Auto-Classification:* MS14 runs a BFS graph traversal. If `source` is reachable from `dest` via forward edges, it classifies as `FEEDBACK`, provisioning `FBO`/`FBI` buffers. Otherwise, `FORWARD`, provisioning `FFO`/`FFI` buffers.

### 3. Rules & Logic
*   `POST /ms14/api/v1/rules/`: Creates a logic gate.
    *   **Body:** `graph_id`, `owner_node_id`, `firing_mode` (SINGLE, AND, OR), `is_terminal`, `is_router`, `input_projection_ids`, `output_ffo_ids`, `output_fbo_ids`, `post_loop_ffo_ids`, `max_iterations`, `is_agent_controlled_loop`.
    *   **Constraints:** Cannot have both FFO and FBO. Terminal cannot have outputs. Router must have >=2 FFOs.
*   `PATCH /ms14/api/v1/rules/<id>/prompt-template/`: Updates the LLM instructions.
    *   **Body:** `{ "template_text": "...", "system_prompt_template": "..." }`

### 4. Graph Snapshot
*   `GET /ms14/api/v1/graph-snapshots/<uuid>/`: Compiles the highly-optimized JSON snapshot of the entire graph, sent to MS15 during execution.

### 5. Triggers
*   `POST /ms14/api/v1/triggers/webhook/`: Creates a Webhook trigger. Returns `webhook_secret` ONCE.
*   `POST /ms14/api/v1/triggers/scheduled/`: Creates a Cron trigger (`cron_expression`, `scheduled_payload`).
*   `POST /ms14/api/v1/triggers/<id>/fire/<secret>/`: **Execution Endpoint**. External systems POST their seeds `{ "node_id": "seed text" }` here. Once all start nodes are seeded, MS14 dispatches to MS15.

---

## ⚡ MS15: Graph Execution Engine (Rust)

High-performance Tokio/Axum state machine.

### 1. `POST /run`
*   **Description:** Starts execution. Called internally by MS14. Saves Snapshot to Redis, seeds projections, and fires initial `EvalCheckMessage` to RabbitMQ.
*   **Request Body:** `{ "graph_id": "uuid", "inputs": { "node_id_1": "text" } }`
*   **Response (200 OK):** `run_id` string.

### 2. `GET /run/<run_id>/status`
*   **Description:** Polls the real-time execution status of a graph run.
*   **Response:**
    ```json
    {
      "run_id": "uuid",
      "run_status": "RUNNING",
      "anchored_nodes": {"node_id": true},
      "loop_states": {"rule_id": 2},
      "rules": [
        {
          "rule_id": "...",
          "name": "...",
          "status": "DISPATCHED",
          "attempt_count": 1
        }
      ]
    }
    ```

### 3. `POST /run/<run_id>/cancel`
*   **Description:** Terminates execution. Sets Redis state to Canceled and wipes buffers.

---

## 🚀 MS5 / MS6 / MS8: Execution Pipeline

While MS14/MS15 control the *Graph*, MS5/MS6/MS8 handle single *Node Inferences*.

### 1. `POST /ms5/api/v1/nodes/<node_id>/infer/` (MS5)
*   **Description:** Start an inference job. (MS15 invokes this behind the scenes via RabbitMQ, but it can be hit directly for single-node tests).
*   **Request Body:**
    ```json
    {
      "prompt": "Analyze this data",
      "inputs": [{"type": "file_id", "id": "ms10-uuid"}],
      "output_config": { "mode": "streaming", "persist_inputs_in_memory": true }
    }
    ```
*   **Response (202 Accepted):** `{ "job_id": "uuid", "websocket_ticket": "ws_ticket_abc..." }`

### 2. `DELETE /ms5/api/v1/jobs/<job_id>/` (MS5)
*   **Description:** Cancels an active inference job. Publishes a fan-out cancellation request to all MS6 workers.

### 3. `WS /ws/results/?ticket=<ticket>` (MS8)
*   **Description:** Connect to MS8 via WebSockets using the ticket obtained from MS5.
*   **Flow:** MS8 consumes the ticket, retrieves cached chunks from Redis, replays them, and then streams live chunks as MS6 executes the LangChain operations.

---

## 🖥️ MS13: Local Runtime Service (LRS)

Manages HuggingFace TGI (Text Generation Inference) Docker containers. Admin only.

### 1. `POST /ms13/api/v1/lrs/models/`
*   **Description:** Initiates async download of a HuggingFace model.
*   **Request Body:** `{ "huggingface_id": "meta-llama/Llama-2-7b-chat-hf" }`

### 2. `POST /ms13/api/v1/lrs/models/<uuid>/deploy/`
*   **Description:** Spawns Docker TGI container(s). Calls MS3 to fetch TGI configuration blueprints.
*   **Request Body:** `{ "instances": 1 }`

### 3. `POST /ms13/gateway/ms13/api/v1/infer` (Gateway)
*   **Description:** Load-balanced proxy endpoint. MS6 calls this when a node is configured to use a local `lrs` model provider. Supports standard TGI payload structure + Server-Sent Events (SSE) streaming.


Of course. This is the core of the system's design. Here is the complete and extremely detailed documentation on the Data Architecture, system-wide flows, and the novel graph engine architecture, structured as requested.

---

# Data Architecture & System Design Documentation

This document provides a comprehensive breakdown of the platform's data architecture, domain-driven design, and the intricate flows that define its functionality. It is the definitive guide for understanding how services own their data, evolve their schemas, and maintain consistency in a distributed environment.

## 4. Data Architecture: Database per Service, Schema Evolution & Consistency

### 4.1 Guiding Principle: The Database-per-Service Pattern

The entire platform is built upon the **Database-per-Service** pattern. This is a foundational principle of our microservices architecture, enforcing strict boundaries and autonomy.

*   **Exclusive Ownership:** Each microservice (e.g., MS1, MS2, MS3) has its own dedicated database schema and is the sole owner and operator of that data. No other service is permitted to access another service's database directly.
*   **Implementation:** For this system, we use a **private-tables-per-service** approach within a single database instance (SQLite in development, easily migratable to a schema-per-service model in PostgreSQL for production). This provides logical separation while simplifying local development.
*   **Data Access:** All cross-service data access occurs exclusively through well-defined APIs (REST), high-performance internal contracts (gRPC), or asynchronous events (RabbitMQ). This encapsulation is non-negotiable.
*   **Technological Autonomy:** While currently standardized on Django ORM with SQLite, this pattern allows any service to be rewritten with a different technology stack (e.g., Go with PostgreSQL, Node.js with MongoDB) without impacting any other service, as long as the API/event contracts are maintained.

### 4.2 Schema Evolution Strategy

*   **Mechanism:** Schema changes are managed via **Django Migrations**. Each service maintains its own `migrations` directory within its primary Django app (e.g., `accounts/migrations`, `project/migrations`).
*   **Process:** When a developer modifies a `models.py` file, they run `python manage.py makemigrations` and `python manage.py migrate` within that service's context.
*   **CI/CD Integration:** The CI/CD pipeline for each service is responsible for running its migrations against its dedicated database schema during deployment, ensuring that code and schema are always in sync. This automated process prevents manual errors and ensures backward-compatible changes are applied safely.

---

## 🏛️ Architecture Breakdown: Services, Models, and Logic

This section details the specific data architecture for each microservice.

### MS1: Auth Service (Identity & Organization Domain)
*   **Primary Responsibility:** Manages user identity, credentials, JWT issuance, and the User Deletion Saga.
*   **Database Technology:** SQLite (Production: PostgreSQL).
*   **Core Data Models:**
    | Table (`accounts_user`) | Type | Description |
    | :--- | :--- | :--- |
    | `id` | UUID (PK) | Unique user identifier, used as `user_id` claim in JWT. |
    | `email` | Varchar | User's unique email and login username. |
    | `username` | Varchar | Unique, user-facing display name. |
    | `password` | Varchar | Hashed password. |
    | `is_active` | Boolean | **Crucial for Saga Pattern.** Used for soft-deletion. |
    | `is_staff` | Boolean | Grants access to Django Admin for system management. |
*   **Data Consistency Model:**
    *   **Local:** Fully `ACID` compliant for all user-related operations within its own database.
    *   **Distributed:** Acts as the **Saga Orchestrator** for user deletion. When a `DELETE /me/` request is received, it initiates an eventually consistent cleanup process across all other services.

### MS2: Project Service (Identity & Organization Domain)
*   **Primary Responsibility:** Manages Projects, which act as top-level containers and authorization boundaries for all other resources (Nodes, Tools, etc.).
*   **Database Technology:** SQLite (Production: PostgreSQL).
*   **Core Data Models:**
    | Table (`project_project`) | Type | Description |
    | :--- | :--- | :--- |
    | `id` | UUID (PK) | Unique project identifier. |
    | `owner_id` | UUID (FK) | **Foreign Key** to `accounts_user.id` in MS1. Enforced by application logic. |
    | `name` | Varchar | User-defined name for the project. |
    | `status` | Varchar | Tracks saga state (`active`, `pending_deletion`). |
    | `metadata` | JSON | Flexible key-value store for project-specific info. |
*   **Data Consistency Model:**
    *   **Local:** Fully `ACID`.
    *   **Distributed:** Orchestrates the Project Deletion Saga.

### MS3: AI Model Service (AI Asset & Runtime Domain)
*   **Primary Responsibility:** Manages AI model configurations, separating Admin-defined templates from user-instantiated models.
*   **Database Technology:** SQLite (Production: PostgreSQL).
*   **Core Data Models:**
    | Table (`aimodels_providerschema`) | Type | Description |
    | :--- | :--- | :--- |
    | `provider_id` | Varchar (PK) | Unique ID like "openai", "google", "lrs". |
    | `credentials_schema` | JSON | JSON Schema defining required credentials (e.g., `api_key`). |
    | `model_blueprints` | JSON | Array of model definitions (e.g., `gpt-4o`, its params, capabilities). |
    | Table (`aimodels_aimodel`) | Type | Description |
    | `id` | UUID (PK) | Unique model configuration ID. |
    | `owner_id` | UUID | User who owns this private configuration. `NULL` for system models. |
    | `provider` | Varchar | Links to `ProviderSchema` (e.g., "openai"). |
    | `is_system_model` | Boolean | `True` for admin-managed templates. |
    | `configuration` | JSON | **Unified Schema.** Contains the full, compiled JSON schema with parameters and default credential values (secrets are encrypted at rest in production). |
    | `capabilities` | JSON | List of features (`text`, `vision`, `tool_use`) inherited from the blueprint. |
*   **Data Consistency Model:**
    *   **Local:** Fully `ACID`. The "Assembly Line" pattern in the `save()` method ensures that every `AIModel` record is always internally consistent with a `ProviderSchema` blueprint before being saved.
    *   **Distributed:** `Saga Participant`. Listens for `user.deletion.initiated` to clean up user-owned models.

### MS4: Node Service (Agent & Graph Control Domain)
*   **Primary Responsibility:** Defines an "AI Agent" by linking an AI Model (from MS3) with its operational context (Tools, Memory, RAG).
*   **Database Technology:** SQLite (Production: PostgreSQL).
*   **Core Data Models:**
    | Table (`nodes_node`) | Type | Description |
    | :--- | :--- | :--- |
    | `id` | UUID (PK) | Unique Node identifier, passed to MS15 for execution. |
    | `owner_id` | UUID | User who owns this node configuration. |
    | `project_id` | UUID | The project this node belongs to. |
    | `status` | Varchar | Lifecycle state (`draft`, `active`, `inactive`). |
    | `is_used_in_graph`| Boolean | `True` if linked to a GNode in MS14, preventing accidental deletion. |
    | `configuration` | JSON | **The Node's DNA.** A JSON object containing `model_config` (with `model_id`), `tool_config`, `memory_config`, and `rag_config`. |
*   **Data Consistency Model:**
    *   **Local:** Fully `ACID`.
    *   **Distributed:** `Saga Participant`. Listens for `project.deletion.initiated` to delete all nodes in a project. It also listens for dependency deletion events (e.g., `model.deleted`, `tool.deleted`) to proactively mark its nodes as `inactive` or `altered`.

### MS7: Tool Service (Context & Capability Domain)
*   **Primary Responsibility:** Manages executable tools and Human-in-the-Loop (HITL) security policies.
*   **Database Technology:** SQLite (Production: PostgreSQL) + **Redis** for HITL state.
*   **Core Data Models:**
    | Table (`tools_tool`) | Type | Description |
    | :--- | :--- | :--- |
    | `id` | UUID (PK) | Unique tool identifier. |
    | `owner_id` | UUID | User who owns this custom tool. `NULL` for system tools. |
    | `is_system_tool` | Boolean | `True` if it's a built-in tool (e.g., `search_web`). |
    | `is_sensitive` | Boolean | If `True`, triggers the HITL approval flow before execution. |
    | `definition` | JSON | OpenAPI-like schema defining the tool's `name`, `description`, `parameters`, and `execution` (e.g., webhook URL or internal function pointer). |
    | Table (`tools_usertoolpolicy`) | Type | Description |
    | `user_id` | UUID (Unique) | The user this policy applies to. |
    | `auto_approve_all` | Boolean | Global override to bypass HITL for this user. |
    | `auto_approved_tool_ids` | JSON | A list of specific tool UUIDs to bypass HITL. |
*   **Data Consistency Model:**
    *   **Local:** `ACID` for tool and policy definitions.
    *   **HITL State:** Uses **Redis** for managing the ephemeral state of pending approval requests, ensuring fast, non-blocking waits for the gRPC servicer.
    *   **Distributed:** `Saga Participant`.

### MS9: Memory Service (Context & Capability Domain)
*   **Primary Responsibility:** Manages persistent conversation histories.
*   **Database Technology:** SQLite (Production: PostgreSQL) + **Redis** for idempotency.
*   **Core Data Models:**
    | Table (`memory_memorybucket`) | Type | Description |
    | :--- | :--- | :--- |
    | `id` | UUID (PK) | Unique bucket identifier. |
    | `owner_id` | UUID | User owner. |
    | `project_id` | UUID | Project scope. |
    | `memory_type` | Varchar | Strategy (`conversation_buffer_window`, `conversation_summary`). |
    | `config` | JSON | Strategy-specific settings (e.g., `{"k": 10}`). |
    | Table (`memory_message`) | Type | Description |
    | `id` | UUID (PK) | Unique message identifier. |
    | `bucket_id` | UUID (FK) | The bucket this message belongs to. |
    | `content` | JSON | Rich, multimodal message content (e.g., `[{"type": "text", "text": "Hi"}, {"type": "file_ref", "file_id": "uuid"}]`). |
    | `idempotency_key` | Varchar | **Crucial for Consistency.** Stores the `job_id` from MS6 to prevent duplicate message history entries if an event is processed twice. |
*   **Data Consistency Model:**
    *   **Local:** `ACID` with `select_for_update` and unique constraints (`idempotency_key`) to ensure atomic and idempotent message appends from the RabbitMQ worker.
    *   **Distributed:** `Saga Participant`.

### MS10: Data Service (Context & Capability Domain)
*   **Primary Responsibility:** Manages file metadata and physical storage abstraction (S3/MinIO).
*   **Database Technology:** SQLite (Production: PostgreSQL) + **MinIO/S3** for blob storage.
*   **Core Data Models:**
    | Table (`data_storedfile`) | Type | Description |
    | :--- | :--- | :--- |
    | `id` | UUID (PK) | Unique file identifier. |
    | `owner_id`, `project_id`| UUID | Ownership and scope. |
    | `filename` | Varchar | Original user-provided filename. |
    | `mimetype` | Varchar | Reliably detected MIME type. |
    | `storage_path` | Varchar | The object key in the S3 bucket (e.g., `uploads/<proj>/<user>/<uuid>-file.pdf`). |
*   **Data Consistency Model:**
    *   **Local:** `ACID` for metadata.
    *   **Distributed:** `Saga Participant`. The project cleanup worker first deletes files from S3, then transactionally deletes the metadata records.

### MS11: RAG Control Plane (Context & Capability Domain)
*   **Primary Responsibility:** Manages metadata for vector store collections and the links to ingested files.
*   **Database Technology:** SQLite (Production: PostgreSQL) + **ChromaDB** for vector storage.
*   **Core Data Models:**
    | Table (`rag_control_plane_knowledgecollection`) | Type | Description |
    | :--- | :--- | :--- |
    | `id` | UUID (PK) | Unique collection identifier. |
    | `owner_id`, `project_id`| UUID | Ownership and scope. |
    | `vector_store_collection_name` | Varchar | The unique technical name used in ChromaDB (e.g., `coll_...`). |
    | Table (`rag_control_plane_filecollectionlink`) | Type | Description |
    | `id` | UUID (PK) | Unique link identifier. |
    | `collection_id` | UUID (FK) | The collection this link belongs to. |
    | `file_id` | UUID | **Foreign Key** to `data_storedfile.id` in MS10. |
    | `status` | Varchar | Ingestion state (`pending`, `ingesting`, `completed`, `error`). |
*   **Data Consistency Model:**
    *   **Local:** `ACID`.
    *   **Distributed:** `Saga Participant`. The cleanup worker deletes collections from ChromaDB before deleting the local metadata.

### MS13: Local Runtime Service (AI Asset & Runtime Domain)
*   **Primary Responsibility:** Orchestrates the lifecycle of local TGI Docker containers.
*   **Database Technology:** SQLite (Production: PostgreSQL) + **Redis** for service discovery.
*   **Core Data Models:**
    | Table (`lrs_localmodel`) | Type | Description |
    | :--- | :--- | :--- |
    | `id` | UUID (PK) | Unique local model reference. |
    | `huggingface_id` | Varchar | e.g., "meta-llama/Llama-2-7b-chat-hf". |
    | `status` | Varchar | Lifecycle (`not_installed`, `downloading`, `downloaded`, `active`). |
    | `local_path` | Varchar | Absolute path on the host where model files are stored. |
    | Table (`lrs_modelinstance`) | Type | Description |
    | `id` | UUID (PK) | Unique running instance. |
    | `local_model_id`| UUID (FK) | The model this instance is running. |
    | `container_id` | Varchar | The Docker container ID. |
    | `internal_endpoint`| Varchar | The container's internal IP and port (e.g., `http://172.17.0.2:80`). |
    | `health_check_url` | Varchar | The public-facing URL (e.g., `http://localhost:49153`). Used by the gateway. |
*   **Data Consistency Model:** `ACID`. Uses **Redis** as a service discovery mechanism for the Inference Gateway.

### MS14: Graph Control Plane (Agent & Graph Control Domain)
*   **Primary Responsibility:** Manages the relational topology of AI workflows (Graphs, Nodes, Edges, Rules, Projections, Triggers). This is the "source of truth" for graph blueprints.
*   **Database Technology:** SQLite (Production: PostgreSQL).
*   **Core Data Models (Simplified):**
    | Table | Key Fields | Description |
    |:---|:---|:---|
    | `graphcontrol_graph` | `id`, `project_id`, `name` | The top-level container for a workflow. |
    | `graphcontrol_gnode` | `id`, `graph_id`, `ms4_node_id`, `is_start` | A vertex in the graph, optionally linked to an MS4 Agent. |
    | `graphcontrol_edge` | `source_node_id`, `dest_node_id`, `edge_type` | A directed connection, auto-classified as `FORWARD` or `FEEDBACK`. |
    | `graphcontrol_ffi` / `fbi` | `owner_node_id`, `source_node_id` | Input buffers (mailboxes) auto-created by edges. |
    | `graphcontrol_ffo` / `fbo`| `owner_node_id`, `dest_node_id` | Output buffers (outboxes) auto-created by edges. |
    | `graphcontrol_projection` | `id`, `owner_node_id`, `ffi_id`, `fbi_id`, `created_by_rule_id` | A semantic data context (e.g., `B[A[I]]`). Represents a specific piece of information available at a node. |
    | `graphcontrol_rule` | `id`, `owner_node_id`, `firing_mode`, `is_terminal`, `is_router` | A logic gate that consumes Projections and produces new data. |
    | `graphcontrol_ruleinput` | `rule_id`, `projection_id` | A join table with a **unique constraint** on `projection_id`, enforcing the "Single-Use Input" law. |
    | `graphcontrol_graphtrigger`| `id`, `graph_id`, `trigger_type`, `cron_expression`| Defines how a graph execution is initiated (Webhook or Schedule).|
*   **Data Consistency Model:** Fully `ACID`. Uses complex `on_delete` logic and transaction blocks to ensure that deleting an edge or rule correctly cascades and cleans up all dependent "ghost" wiring (Projections, Rule Inputs, etc.).

### Other Services (Stateless/Data-Light)
*   **MS5 (Inference Orchestrator):** Fully stateless.
*   **MS6 (Inference Executor):** Fully stateless.
*   **MS8 (Results Service):** Stateless application logic. Uses **Redis** for temporary message caching and ticket validation.
*   **MS12 (RAG Ingestion Worker):** Fully stateless worker.
*   **MS15 (Graph Execution Engine):** The Rust application is fully stateless. All graph execution state (run status, rule status, projection data, locks) is stored externally in **Redis**, making the engine horizontally scalable and resilient.

---

## 🌊 Core System & User Flows

### Flow 1: Complete User Journey - Building and Running a Graph

1.  **Authentication (MS1):** User calls `POST /ms1/api/v1/auth/token/` to get a JWT.
2.  **Project Creation (MS2):** User calls `POST /ms2/api/v1/projects/` to create "My RAG Project".
3.  **File Upload (MS10):** User calls `POST /ms10/api/v1/projects/{proj_id}/files/` to upload `company_faq.pdf`. MS10 stores it in S3 and creates a `StoredFile` metadata record.
4.  **RAG Collection (MS11):**
    *   User calls `POST /ms11/api/v1/projects/{proj_id}/collections/` to create "FAQ Knowledge Base".
    *   User calls `POST /ms11/api/v1/collections/{coll_id}/add_file/` with `{"file_id": "..."}`.
    *   MS11 creates a `FileCollectionLink` and publishes `rag.ingestion.requested` to RabbitMQ.
    *   **MS12** (Ingestion Worker) consumes the event, calls **MS10** via gRPC to get the parsed text, chunks it, embeds it, and indexes it into ChromaDB.
5.  **Agent (Node) Creation (MS4):**
    *   User calls `POST /ms4/api/v1/nodes/draft/` to create "FAQ Agent".
    *   User calls `POST /ms4/api/v1/nodes/{node_id}/configure-model/` with `{"model_id": "..."}`.
    *   User calls `PUT /ms4/api/v1/nodes/{node_id}/` to link the RAG collection: `{"configuration": {"rag_config": {"is_enabled": true, "collection_id": "..."}}}`. MS4 validates ownership by calling MS11's internal API.
6.  **Graph Construction (MS14):**
    *   User calls `POST /ms14/api/v1/graphs/` to create "My RAG Graph".
    *   User calls `POST /ms14/api/v1/nodes/` to create a GNode, setting `is_start: true` and linking it to the "FAQ Agent" (`ms4_node_id`). MS14 calls MS4 to "claim" the node.
    *   User calls `POST /ms14/api/v1/rules/` to create a simple terminal rule on the start node that uses the "Seed" projection (`I`).
7.  **Execution (MS14 -> MS15 -> MS5 -> MS6 -> MS8):**
    *   User provides a seed question in the UI and clicks "Run". The UI calls `POST /ms14/api/v1/triggers/{trigger_id}/fire/{secret}/`.
    *   **MS14** validates the request and POSTs the graph blueprint and seeds to **MS15**'s `/run` endpoint.
    *   **MS15** saves the blueprint to Redis, seeds the start node projection, and publishes an `EvalCheckMessage` for the terminal rule.
    *   **MS15**'s Evaluator worker consumes the message, sees the rule is ready, and publishes an `InferenceRequestMessage`.
    *   **MS5** consumes this, calls MS4 (gRPC) for node config, MS11 (gRPC) for RAG chunks, assembles the full context, and publishes the job to **MS6**.
    *   **MS6** executes the LLM call.
    *   **MS6** publishes `inference.result.final` to RabbitMQ.
    *   **MS8**'s consumer pushes the result to Redis and the user's WebSocket.
    *   **MS15**'s Propagator worker consumes the result, marks the terminal rule `Completed`, and sees the graph is finished, updating the run status in Redis.

---

## 💡 The Novelty of the MS14/MS15 Graph Architecture

The Graph Control Plane (MS14) and Execution Engine (MS15) represent the core innovation of this platform. It is not merely a Directed Acyclic Graph (DAG) system; it is a **Turing-complete state machine designed to execute complex, cyclic, and conditional AI workflows**.

### Key Architectural Concepts:

1.  **Topology vs. Logic Separation:**
    *   **Topology (MS14 Models):** `GNode` and `Edge` define the physical structure.
    *   **Logic (MS14 Models):** `Rule`, `Projection`, and `PromptTemplate` define the computational logic *within* each GNode. This separation allows the same graph topology to be reconfigured with different behaviors without changing its structure.

2.  **The "Digital Circuit" Analogy:**
    *   **GNodes** are like integrated circuits (ICs) on a motherboard.
    *   **Edges** are the copper traces connecting them.
    *   **FFI/FFO/FBI/FBO Buffers** are the input/output pins on each IC.
    *   **Projections** are the semantic signals carried on the wires (e.g., `B[A[I]]` is the signal on the wire leading into Node C, representing "the output of B, which processed the output of A, which processed the initial Seed `I`").
    *   **Rules** are the logic gates *inside* the IC that decide what to do when signals arrive at the input pins.

3.  **Cyclic Execution via Feedback Channels (`FBI`/`FBO`):**
    *   Standard DAGs cannot loop. Our architecture explicitly supports cycles by classifying edges.
    *   When an `Edge` is created that closes a cycle, it's marked as `FEEDBACK`.
    *   This automatically provisions a **Feed-Backward Output (FBO)** on the source (controller) node and a **Feed-Backward Input (FBI)** on the destination (loop body) node.
    *   A rule on the controller node can be configured to write its output to the `FBO`. This data is then available to the loop body node via a special `~Controller[...]` projection, allowing the graph to "go backward" and re-evaluate a previous step with new context.
    *   This enables sophisticated patterns like **iterative refinement, self-correction, and multi-step agentic reasoning.**

4.  **Turing Completeness:**
    The combination of three features grants the system Turing completeness, allowing it to model any computable function:
    *   **State:** The system maintains state in Redis (`DataPacket`s in Projection buffers).
    *   **Looping:** Controller rules with `FBO` outputs can create infinite (`max_iterations: null`) or bounded (`max_iterations: N`) loops. The `is_agent_controlled_loop` flag allows the LLM itself to break the loop by emitting a special token.
    *   **Conditional Branching:** A `Rule` marked `is_router: true` instructs the LLM to choose which of its `FFO` outputs to send data to, enabling dynamic, content-aware routing.

5.  **Stateless, Scalable Execution (MS15):**
    *   The entire graph state (the blueprint, rule statuses, data packets) is externalized to Redis.
    *   The **MS15 Rust Engine** is completely stateless. It simply reads state from Redis, performs a logical operation (e.g., `check_rule_readiness`), and writes new state or publishes an event.
    *   This means you can run dozens of MS15 `worker-evaluator` and `worker-propagator` instances in parallel. They will all work on the same shared Redis state without conflict, thanks to atomic operations like `SETNX` for rule locking. This provides massive horizontal scalability for handling thousands of concurrent graph runs.
  
    *   Of course. Here is the comprehensive and extremely detailed Operational Guide for the Mega AI Platform, covering deployment, containerization, monitoring, and troubleshooting procedures.

---

# 6. Operational Guide (DevSecOps)

This guide provides the standard operating procedures for deploying, managing, and troubleshooting the Mega AI Platform microservices. Adherence to these protocols is critical for maintaining system stability, scalability, and security.

---

## 6.1 Deployment Automation & Containerization

The entire platform is designed to be deployed as a set of containerized services, managed by a container orchestrator like Docker Compose (for development) or Kubernetes (for production).

### 6.1.1 Dockerization Strategy

*   **Dockerfile per Service:** Each microservice (MS1-MS15, except for the Rust services) has its own `Dockerfile`. This ensures that dependencies are isolated and build processes are self-contained.
*   **Multi-Stage Builds:** Production Dockerfiles should use multi-stage builds to minimize image size. A `builder` stage installs dependencies and compiles assets, and a final lightweight `runner` stage copies only the necessary application code and artifacts.
*   **Standardized Base Images:** Python services are built on `python:3.11-slim-bullseye` to maintain consistency and reduce security vulnerabilities. Rust services are built using the official `rust:latest` image with a `cargo-chef` layer for cached dependency builds.
*   **Environment Configuration:** All configuration is injected via environment variables (`.env` file or orchestrator secrets), never hard-coded into the image. This is crucial for security and flexibility across different environments (dev, staging, prod).

**Example Dockerfile for a Django Service (e.g., MS2 - Project Service):**
```dockerfile
# Stage 1: Build Stage
FROM python:3.11-slim-bullseye AS builder

WORKDIR /app

# Install system dependencies (e.g., for psycopg2)
RUN apt-get update && apt-get install -y --no-cache-deps gcc libpq-dev

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---
# Stage 2: Final Runtime Stage
FROM python:3.11-slim-bullseye AS final

WORKDIR /app

# Copy installed dependencies from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy the application code
COPY . .

# Run database migrations and collect static files on startup
# CMD becomes an entrypoint script
CMD ["sh", "-c", "python manage.py migrate && gunicorn MS2.wsgi:application --bind 0.0.0.0:8000"]
```

### 6.1.2 CI/CD Pipeline (Conceptual using GitHub Actions)

Each service has its own CI/CD pipeline defined in `.github/workflows/`. The pipeline automates testing, security scanning, and deployment.

**Pipeline Stages:**
1.  **Trigger:** On push to `main` branch or on creation of a release tag.
2.  **Lint & Test:**
    *   Run static analysis tools (`black`, `flake8`, `mypy` for Python; `clippy` for Rust).
    *   Execute unit and integration tests (`pytest`, `cargo test`).
    *   Fail the pipeline if any tests or lint checks fail.
3.  **Security Scan:**
    *   Scan application dependencies for known vulnerabilities (e.g., using `trivy` or `snyk`).
    *   Scan the `Dockerfile` for security misconfigurations.
    *   Perform static application security testing (SAST) on the codebase.
4.  **Build & Push:**
    *   Build the Docker image for the service.
    *   Tag the image with the Git commit SHA and `latest`.
    *   Log in to a container registry (e.g., Docker Hub, AWS ECR, GitHub Container Registry).
    *   Push the tagged image to the registry.
5.  **Deploy:**
    *   (For Kubernetes) Use `kubectl` or a GitOps tool like ArgoCD to apply the updated Kubernetes manifest, which points to the new image tag. The orchestrator will perform a rolling update to ensure zero-downtime deployment.
    *   (For Docker Compose) SSH into the server, pull the latest image, and run `docker-compose up -d --no-deps <service_name>`.

### 6.1.3 Kubernetes Deployment (Production)

In a production environment, each service is deployed as a **Deployment** with a corresponding **Service** and **HorizontalPodAutoscaler (HPA)**.

**Key Manifest Components:**
*   **Deployment:** Defines the desired state of the application, including the number of replicas, the Docker image to use, and resource requests/limits (CPU, memory).
*   **Service:** Provides a stable network endpoint (ClusterIP) for the service, allowing other services within the cluster to communicate with it via a consistent DNS name (e.g., `http://ms2-project-service`).
*   **Ingress:** For services that need to be exposed to the outside world (e.g., MS1's REST API), an Ingress resource maps external HTTP/S traffic to the internal service.
*   **ConfigMap & Secret:** Environment variables are managed through ConfigMaps (for non-sensitive data) and Secrets (for sensitive data like `JWT_SECRET_KEY`, database passwords). These are mounted into the pods as environment variables.
*   **HorizontalPodAutoscaler (HPA):** Automatically scales the number of pods for a deployment based on observed metrics like CPU utilization or custom metrics (e.g., requests per second).

---

## 6.2 Centralized Logging, Monitoring, and Alerting

A distributed system is impossible to manage without robust observability. We employ a centralized stack to aggregate logs and metrics from all services.

### 6.2.1 Centralized Logging (The ELK/EFK Stack)

*   **Architecture:**
    1.  **Fluentd/Fluent Bit (The "F" in EFK):** Deployed as a **DaemonSet** on each Kubernetes node. It automatically tails the container logs from all pods running on that node.
    2.  **Elasticsearch (The "E"):** A powerful search and analytics engine. Fluentd forwards all log entries to a central Elasticsearch cluster. Each log entry is enriched with metadata, including the service name, pod name, and Kubernetes namespace.
    3.  **Kibana (The "K"):** A web UI for searching, analyzing, and visualizing the log data stored in Elasticsearch.
*   **Standard Log Format:** All services MUST log structured JSON to `stdout`. This allows for easy parsing and powerful filtering in Kibana.
    *   **Python:** The standard `logging` library is configured to use a JSON formatter.
    *   **Rust:** The `tracing` and `tracing-subscriber` crates are used with a JSON output format.
*   **Correlation ID:** Every external request that enters the system (e.g., at MS1 or MS14) is assigned a unique **Correlation ID**. This ID is passed in the headers of all subsequent internal API/gRPC calls and included in all log messages related to that request. This allows developers to trace a single user action across multiple services in Kibana by filtering on `correlation_id`.

### 6.2.2 Monitoring & Alerting (Prometheus & Grafana)

*   **Architecture:**
    1.  **Prometheus:** A time-series database and monitoring system. It "pulls" metrics from HTTP endpoints exposed by each service.
        *   **Python Services:** The `django-prometheus` library automatically exposes key metrics (request latency, error rates, database performance).
        *   **Rust Services:** The `prometheus` crate is used to expose custom metrics.
    2.  **Grafana:** A visualization tool that queries Prometheus. We build dashboards to monitor key performance indicators (KPIs) for each service.
    3.  **Alertmanager:** A component of Prometheus that handles alerts. We define rules in Prometheus (e.g., "if the 5xx error rate for MS5 exceeds 5% for 5 minutes, fire an alert"). Alertmanager then sends notifications to a designated channel (e.g., Slack, PagerDuty).
*   **Key Monitored Metrics:**
    *   **RED Metrics:** Rate (requests per second), Errors (5xx error rate), Duration (request latency percentiles: p50, p90, p99).
    *   **Resource Utilization:** CPU and Memory usage for each pod.
    *   **RabbitMQ:** Queue depth (a high number indicates a bottleneck or failing consumer), and message publish/consume rates.
    *   **Database:** Connection pool usage, query latency, and transaction rates.

---

## 6.3 Troubleshooting Procedures

### Scenario 1: User reports "Something went wrong" after an action.
1.  **Ask for a timeframe:** Get the approximate time the error occurred.
2.  **Trace in Kibana:** Search Kibana for logs around that timeframe. If the user's `user_id` is known, filter by `user_id`.
3.  **Find the Correlation ID:** Identify the log entry for the initial API request (e.g., `POST /ms4/api/v1/nodes/`). Extract the `correlation_id` from this log message.
4.  **Filter by Correlation ID:** Change your Kibana filter to `correlation_id: "the-extracted-id"`. You will now see the entire lifecycle of that single request as it traversed from MS4 to MS3, MS7, etc.
5.  **Identify the failing service:** The log stream will show the request flow. The last service to log a successful entry before an error log is often the one that made the failing call. The first service to log a 5xx error is the source of the problem.
6.  **Examine the error:** The error log will contain the full stack trace and error message, pinpointing the exact line of code or external dependency (e.g., "Connection refused to MS7") that failed.

### Scenario 2: Grafana alert fires for high queue depth in `rag_ingestion_queue`.
1.  **Identify the Consumer:** This queue is consumed by **MS12 (RAG Ingestion Worker)**.
2.  **Check Consumer Logs:** Go to Kibana and filter by `service_name: "ms12-ingestion-worker"`.
3.  **Look for Errors:** Are the workers repeatedly crashing? Look for error logs related to:
    *   **ChromaDB Connection:** "Failed to connect to chromadb..."
    *   **Embedding Model:** "Could not load SentenceTransformer model..." (This might happen on a cold start if the model isn't cached).
    *   **Data Service gRPC Calls:** "gRPC error fetching content for file..."
4.  **Check Consumer Resources:** Go to the Kubernetes dashboard or Grafana. Are the MS12 pods `OOMKilled` (Out of Memory)? This can happen if a very large PDF is being processed. If so, increase the memory limits for the MS12 deployment.
5.  **Check RabbitMQ Management UI:** Verify that messages are in the queue and that consumers are connected. If no consumers are connected, it means the MS12 pods are all dead or in a crash loop.

### Scenario 3: `POST /ms14/api/v1/rules/` returns "A Rule cannot be both a Terminal Rule and a Router."
1.  **Identify the Source:** This is a `ValidationError` from the Django backend of **MS14**.
2.  **Check the Code:** The error message is very specific. Open `MS14/graphcontrol/models.py`.
3.  **Locate the Validation Logic:** Find the `clean()` method within the `Rule` model. You will see the exact `if self.is_terminal and self.is_router:` check that raises this exception.
4.  **Resolve:** This is a client-side error. The frontend or calling client is sending an invalid combination of flags. The fix is in the client's logic, not the backend. The backend is correctly enforcing its domain rules.

### Scenario 4: User reports a new Graph Run is stuck in "Seeding" or "Running" state.
1.  **Get the `run_id`:** Ask the user for the run ID from the UI.
2.  **Check MS15 API Logs:** Filter Kibana for `service_name: "ms15-api"` and `run_id: "the-run-id"`. This will show if the initial `/run` request was successful.
3.  **Check MS15 Worker Logs:** Filter Kibana for `service_name: "ms15-evaluator-worker"` and `service_name: "ms15-propagator-worker"`.
4.  **Trace the Flow in Logs:**
    *   Did the Evaluator receive the initial `EvalCheckMessage`?
    *   Did it determine a rule was ready and publish an `InferenceRequestMessage`?
    *   Did the Propagator receive an `InferenceResultMessage` from MS6?
5.  **Inspect Redis State:** Use `redis-cli` to inspect the state for that run.
    *   `KEYS "ms15:run:<run_id>:*"`: List all keys for the run.
    *   `GET "ms15:run:<run_id>:rule:<rule_id>:status"`: Check the status of a specific rule.
    *   `LRANGE "ms15:run:<run_id>:proj:<proj_id>" 0 -1`: See what data is in a projection's buffer.
6.  **Common Cause:** If a rule is `DISPATCHED` but never `COMPLETED`, the problem is likely in the MS5/MS6 pipeline. If a rule is `IDLE` but should be ready, check its input projections in Redis. One of them is likely empty, meaning an upstream rule failed to propagate its result.


---

# 3. Integration Patterns & Communication

This section defines the standardized patterns for communication between microservices, client-to-service interaction, and the strategies for handling errors and ensuring system resilience. The platform employs a hybrid communication model, selecting the right tool for each job to balance performance, reliability, and developer experience.

---

## 3.1 Service-to-Service Communication (Internal)

Internal communication is the backbone of the platform, enabling the complex orchestration required for graph execution. We use two primary patterns: high-performance synchronous calls for immediate data needs and robust asynchronous events for decoupling and long-running tasks.

### 3.1.1 High-Performance Synchronous Communication: gRPC

**When to Use:**
*   For request/response interactions where the calling service **must** have an immediate, strongly-typed answer to proceed.
*   For frequent, low-latency calls between services, especially during the critical path of inference orchestration (MS5).
*   For internal-only APIs that are not exposed to the public.

**Implementation Details:**
*   **Protocol:** gRPC over HTTP/2.
*   **Schema Definition:** API contracts are strictly defined in **Protocol Buffers (`.proto`) files** located in each service's `internals/protos` directory. This is the **source of truth** for the contract.
*   **Code Generation:** A `manage.py generate_protos` command uses `grpcio-tools` to auto-generate both the server-side "servicer" stubs and client-side stubs in Python. This eliminates manual boilerplate and ensures type safety.
*   **Error Handling:** gRPC uses status codes to signal outcomes. Our services map application-level exceptions to gRPC status codes in a standardized way:
    *   `PermissionDenied` (DRF) -> `grpc.StatusCode.PERMISSION_DENIED`
    *   `NotFound` (DRF) -> `grpc.StatusCode.NOT_FOUND`
    *   `ValidationError` (DRF) -> `grpc.StatusCode.INVALID_ARGUMENT`
    *   Unhandled Python `Exception` -> `grpc.StatusCode.INTERNAL`
*   **Service Discovery:** In a Kubernetes environment, gRPC clients connect to other services using their internal DNS names (e.g., `ms4-node-service:50051`). The actual pod IP is resolved by Kubernetes' CoreDNS.

**Example Flow (MS5 Orchestrator):**
When MS5 receives an inference job, it needs to gather context *immediately*. It cannot proceed without this data.
1.  **MS5 -> MS4 (Node Service):** MS5's `NodeServiceClient` makes a `GetNodeDetails` gRPC call to MS4's `NodeServicer`. This is a synchronous, blocking call. MS4 authorizes the user and returns the full node `configuration`.
2.  **MS5 -> MS3 (Model Service):** MS5's `ModelServiceClient` makes a `GetModelConfiguration` gRPC call to MS3.
3.  **MS5 -> MS9, MS10, MS11:** Concurrently, MS5 makes gRPC calls to get conversation history, file content, and RAG chunks.
    *   These parallel calls are managed by a `ThreadPoolExecutor` (Python) or `tokio::spawn` (Rust) to minimize total latency.
    *   If any single gRPC call fails (e.g., with `PERMISSION_DENIED`), the entire orchestration process fails immediately, and an error is published.

### 3.1.2 Decoupled Asynchronous Communication: RabbitMQ

**When to Use:**
*   For **fire-and-forget** commands where the publisher does not need an immediate response.
*   For long-running, resource-intensive background tasks (e.g., model downloads, file ingestion).
*   For fanning out events to multiple interested consumers (e.g., Saga pattern).

**Implementation Details:**
*   **Broker:** RabbitMQ.
*   **Message Format:** All messages are **JSON**, ensuring language interoperability.
*   **Exchanges:** We use two primary exchange types:
    *   **`topic` Exchange:** For routing messages based on a "routing key." This is the default for most command-based messaging. Consumers bind their queues to specific keys (e.g., `rag.ingestion.requested`).
    *   **`fanout` Exchange:** For broadcasting a message to *all* queues bound to it, regardless of the routing key. This is used for critical system-wide events like job cancellations (`job_control_fanout_exchange`).
*   **Key Exchanges & Routing Keys:**
    | Exchange | Type | Routing Key Example | Description | Publisher | Consumer(s) |
    |:---|:---|:---|:---|:---|:---|
    | `user_events` | Topic | `user.deletion.initiated` | User account lifecycle events for the Saga pattern. | MS1 | MS2, MS3, MS4, MS7... |
    | `project_events` | Topic | `project.deletion.initiated` | Project lifecycle events for the Saga pattern. | MS2 | MS4, MS9, MS10, MS11, MS14 |
    | `resource_events` | Topic | `model.deleted`, `rag.collection.deleted` | Notifications about resource changes for dependency management. | MS3, MS11 | MS4 |
    | `lrs_events` | Topic | `lrs.model.download.requested` | Commands for the LRS asset worker. | MS13 | MS13 (worker) |
    | `rag_events` | Topic | `rag.ingestion.requested` | Commands for the RAG ingestion worker. | MS11 | MS12 |
    | `inference_exchange`| Topic | `inference.job.start` | Dispatches fully-formed inference jobs. | MS5 | MS6 |
    | `results_exchange` | Topic | `inference.result.streaming.{job_id}` | Real-time streaming output from the executor. | MS6 | MS8 |
    | `job_control_fanout_exchange` | Fanout| *N/A* | Broadcasts job cancellation requests to all running MS6 workers. | MS5 | All MS6 instances |
*   **Idempotency:** Consumers are designed to be idempotent. The `run_context_update_worker` in MS9 uses an `idempotency_key` (the `job_id`) to prevent duplicate message history entries if a message is delivered more than once.
*   **Error Handling:** If a worker fails to process a message due to a transient error (e.g., database deadlock), it should **Nack (Negative Acknowledge)** the message, causing RabbitMQ to requeue it for another attempt. For permanent failures (e.g., malformed JSON), the worker should **Ack (Acknowledge)** the message to remove it from the queue and prevent infinite processing loops, while logging a critical error. Production deployments would include a **Dead-Letter Queue (DLQ)** to automatically route un-processable messages for manual inspection.

---

## 3.2 External & Client Communication

### 3.2.1 API Gateway Pattern (Conceptual)

While the services are deployed independently, from a client's perspective, they appear as a unified API. This is achieved conceptually through a reverse proxy or API Gateway (e.g., NGINX, Traefik, Kong).

*   **Role:** The gateway acts as the single entry point for all external traffic.
*   **Routing:** It routes incoming requests to the appropriate microservice based on the URL path.
    *   `https://api.yourdomain.com/ms1/api/v1/*` -> Routes to the MS1 container.
    *   `https://api.yourdomain.com/ms2/api/v1/*` -> Routes to the MS2 container.
    *   `https://api.yourdomain.com/ws/results/` -> Routes WebSocket traffic to the MS8 container.
*   **Cross-Cutting Concerns:** The gateway is the ideal place to handle cross-cutting concerns like SSL termination, global rate limiting, and request logging. It can also perform initial JWT validation before forwarding the token to the backend services.

### 3.2.2 Real-Time Client Communication: WebSockets

**When to Use:** For pushing real-time, bidirectional updates from the server to a specific client without the client needing to poll.

**Implementation Details:**
*   **MS7 (HITL Service):** Uses **Django Channels** and `channels_redis`. When a sensitive tool needs approval, the gRPC servicer publishes an event to a user-specific Redis channel (`hitl_user_{user_id}`). The `HITLConsumer` is subscribed to this channel and pushes the approval request down the corresponding WebSocket to the user's frontend.
*   **MS8 (Results Service):** Uses **FastAPI WebSockets**. When a user initiates a streaming inference job, MS5 returns a single-use `websocket_ticket`. The client connects to MS8 with this ticket. MS8 validates and consumes the ticket against Redis, then maps the `job_id` to the WebSocket connection. The `RabbitMQConsumer` in MS8 listens for streaming results from MS6 and uses the `ConnectionManager` to forward messages to the correct WebSocket. This decouples the HTTP-based execution world from the WebSocket-based streaming world.

---

## 3.3 Error Handling Strategies & Resilience

Resilience is built into the architecture through a combination of patterns.

### 3.3.1 Timeouts & Retries

*   **HTTP/gRPC Clients:** All internal service clients (`httpx`, `grpc`) are configured with aggressive timeouts (e.g., 10-15 seconds). This prevents a single slow service from causing a cascading failure.
*   **Messaging Consumers:** RabbitMQ workers implement a retry loop with exponential backoff for connection failures to the broker, ensuring they can recover from transient network issues or broker restarts.

### 3.3.2 Circuit Breaker Pattern (Conceptual)

In a high-load production environment, a Circuit Breaker pattern would be implemented in the internal service clients.
*   **Function:** If a service (e.g., MS7) starts consistently failing or timing out, the circuit breaker in the calling service (e.g., MS4) will "trip."
*   **Behavior:** For a configured period (e.g., 30 seconds), all subsequent calls from MS4 to MS7 will fail immediately without making a network request. This gives the failing service time to recover and prevents the calling service from wasting resources on doomed requests. After the timeout, the breaker moves to a "half-open" state, allowing a single request through. If it succeeds, the breaker closes; if it fails, it remains open.

### 3.3.3 The Saga Pattern for Distributed Consistency

The Saga pattern is the primary mechanism for maintaining data consistency across services for long-running business transactions.

*   **Type:** Choreography-based Saga. There is no central orchestrator; services listen for events and react independently.
*   **User Deletion Flow:**
    1.  **Initiation (MS1):** User calls `DELETE /ms1/api/v1/auth/me/`. MS1 performs a **soft-delete** (`is_active = False`) within a local transaction and publishes a `user.deletion.initiated` event to the `user_events` exchange.
    2.  **Participation (MS2-MS14):** Each service has a dedicated worker (e.g., `run_user_cleanup_worker.py`) that consumes this event. It performs its local cleanup (e.g., MS4 deletes all nodes owned by that `user_id`).
    3.  **Confirmation:** After completing its cleanup, each service publishes a confirmation event (e.g., `resource.for_user.deleted.ProjectService`, `resource.for_user.deleted.AIModelService`) to the same `user_events` exchange.
    4.  **Finalization (MS1):** A separate worker in MS1 (`run_user_saga_finalizer.py`) listens for all confirmation events. It tracks the state in the `UserSaga` and `UserSagaStep` database tables. When all expected services have confirmed, it performs the **hard-delete** of the `User` record from its database, completing the saga.
*   **Idempotency:** All cleanup workers are idempotent. If they receive the same `user.deletion.initiated` event twice, re-running the deletion logic (`.filter(user_id=...).delete()`) will have no adverse effect.
*   **Resilience:** If a service is down, the message remains in its queue. When the service comes back online, it will process the backlog of deletion requests, eventually leading to system consistency. If a finalizer doesn't receive a confirmation within a timeout, it can flag the saga as "failed" for manual intervention.
