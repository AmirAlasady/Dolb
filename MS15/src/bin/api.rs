use axum::{
    routing::{get, post},
    extract::{State, Json, Path},
    http::{StatusCode, HeaderMap},
    Router,
};
use tower_http::cors::{CorsLayer, Any};
use std::sync::Arc;
use std::net::SocketAddr;
use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use dotenv::dotenv;
use std::env;
use jsonwebtoken::{decode, DecodingKey, Validation, Algorithm};

use ms15::infrastructure::{redis_facade::RedisAdapter, rabbitmq_facade::RabbitMQAdapter};
use ms15::services::trigger::TriggerService;
use ms15::interfaces::storage_trait::StorageFacade;
use ms15::domain::enums::RunStatus;

// =========================================================================
// JWT Claims — must match what MS1 puts in the token
// =========================================================================
#[derive(Debug, Serialize, Deserialize)]
struct Claims {
    /// Subject: the user's ID (optional — MS1 may use user_id instead)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sub: Option<String>,
    /// Issuer
    #[serde(skip_serializing_if = "Option::is_none")]
    pub iss: Option<String>,
    /// Expiry (Unix timestamp)
    pub exp: usize,
    /// Issued-at
    #[serde(skip_serializing_if = "Option::is_none")]
    pub iat: Option<usize>,
    /// Any extra fields the token may carry (e.g. user_id, email, role)
    #[serde(flatten)]
    pub extra: HashMap<String, Value>,
}

// =========================================================================
// App State
// =========================================================================
struct AppState {
    trigger_service: TriggerService<RedisAdapter, RabbitMQAdapter>,
    storage: Arc<RedisAdapter>,
    jwt_secret: String,
    jwt_issuer: String,
}

#[derive(Deserialize)]
struct RunRequest {
    graph_id: String,
    inputs: HashMap<String, Value>,
}

#[derive(Serialize)]
struct RunStatusResponse {
    run_id: String,
    run_status: String,
    rules: Vec<RuleStatusEntry>,
    anchored_nodes: HashMap<String, bool>,
    /// Maps rule_id → completed loop iteration count (only present for controller rules)
    loop_states: HashMap<String, u32>,
}

#[derive(Serialize)]
struct RuleStatusEntry {
    rule_id: String,
    id: String,           // alias for rule_id for frontend convenience
    name: String,
    owner_node: String,
    owner_node_name: String,
    status: String,
    is_terminal: bool,
    is_controller: bool,
    firing_mode: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    max_iterations: Option<u32>,
    /// How many times this rule has been dispatched (attempt count)
    attempt_count: u32,
}

// =========================================================================
// JWT Verification Helper
// =========================================================================
fn verify_jwt(token: &str, secret: &str, expected_issuer: &str) -> Result<Claims, String> {
    let mut validation = Validation::new(Algorithm::HS256);
    // Only require exp — check iss manually below so tokens without iss still work
    validation.set_required_spec_claims(&["exp"]);
    validation.validate_exp = true;

    let key = DecodingKey::from_secret(secret.as_bytes());

    let claims = decode::<Claims>(token, &key, &validation)
        .map(|data| data.claims)
        .map_err(|e| format!("Invalid token: {}", e))?;

    // If the token carries an issuer, it must match ours
    if let Some(ref iss) = claims.iss {
        if iss != expected_issuer {
            return Err(format!("Invalid issuer '{}', expected '{}'", iss, expected_issuer));
        }
    }

    Ok(claims)
}

// =========================================================================
// Main
// =========================================================================
#[tokio::main]
async fn main() {
    dotenv().ok();
    tracing_subscriber::fmt::init();

    // 1. Config
    let redis_url   = env::var("REDIS_URL").expect("REDIS_URL must be set");
    let rabbit_url  = env::var("RABBITMQ_URL").expect("RABBITMQ_URL must be set");
    let ms14_url    = env::var("MS14_URL").expect("MS14_URL must be set");
    let port        = env::var("PORT").unwrap_or_else(|_| "3000".to_string());
    let jwt_secret  = env::var("JWT_SECRET_KEY").expect("JWT_SECRET_KEY must be set");
    let jwt_issuer  = env::var("JWT_ISSUER").expect("JWT_ISSUER must be set");

    // 2. Infrastructure
    let redis  = Arc::new(RedisAdapter::new(&redis_url).expect("Failed to connect to Redis"));
    let rabbit = Arc::new(RabbitMQAdapter::new(&rabbit_url).await.expect("Failed to connect to RabbitMQ"));

    // 3. Service Injection
    let trigger_service = TriggerService::new(redis.clone(), rabbit, ms14_url);

    let state = Arc::new(AppState { trigger_service, storage: redis, jwt_secret, jwt_issuer });

    // 4. CORS — allow the MS14 UI to call us
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    // 5. Routes
    let app = Router::new()
        .route("/health", get(health_check))
        .route("/run", post(start_run))
        .route("/run/:run_id/status", get(get_run_status))
        .route("/run/:run_id/cancel", post(cancel_run))
        .layer(cors)
        .with_state(state);

    // 6. Run Server
    let addr: SocketAddr = format!("0.0.0.0:{}", port).parse().unwrap();
    println!("🚀 MS15 API listening on {}", addr);
    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

// =========================================================================
// Handlers
// =========================================================================
async fn health_check() -> &'static str {
    "OK"
}

async fn start_run(
    headers: HeaderMap,
    State(state): State<Arc<AppState>>,
    Json(payload): Json<RunRequest>,
) -> Result<String, (StatusCode, String)> {

    // 1. Extract Bearer token
    let auth_header = headers.get("Authorization")
        .and_then(|h| h.to_str().ok())
        .ok_or((StatusCode::UNAUTHORIZED, "Missing Authorization header".to_string()))?;

    let jwt_token = if auth_header.starts_with("Bearer ") {
        &auth_header[7..]
    } else {
        auth_header
    };

    // 2. Verify the token with our shared secret
    let claims = verify_jwt(jwt_token, &state.jwt_secret, &state.jwt_issuer)
        .map_err(|e| {
            eprintln!("JWT verification failed: {}", e);
            (StatusCode::UNAUTHORIZED, e)
        })?;

    // 3. Extract user_id from claims: check sub first, then extra.user_id
    let user_id = claims.sub.clone()
        .or_else(|| claims.extra.get("user_id").and_then(|v| v.as_str().map(String::from)))
        .unwrap_or_else(|| "unknown".to_string());
    
    println!("--> Authenticated user: {}", user_id);

    // 4. Token is valid — pass it through to MS14 (for MS14's own auth)
    match state.trigger_service.start_run(payload.graph_id, payload.inputs, jwt_token, &user_id).await {
        Ok(run_id) => Ok(run_id),
        Err(e) => {
            eprintln!("Run start failed: {:?}", e);
            Err((StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to start run: {}", e)))
        }
    }
}

/// GET /run/:run_id/status — returns current rule-by-rule status of a graph execution
async fn get_run_status(
    State(state): State<Arc<AppState>>,
    Path(run_id): Path<String>,
) -> Result<Json<RunStatusResponse>, (StatusCode, String)> {
    
    // 1. Read run status
    let run_status = state.storage.get_run_status(&run_id).await
        .map(|s| format!("{:?}", s).to_uppercase())
        .unwrap_or_else(|_| "UNKNOWN".to_string());

    // 2. Read snapshot to get all rules + node names
    let snapshot = state.storage.get_full_snapshot(&run_id).await
        .map_err(|e| (StatusCode::NOT_FOUND, format!("Run not found: {}", e)))?;

    // 3. For each rule, read its status from Redis
    let mut rules = Vec::new();
    for (rule_id, rule_bp) in &snapshot.rules {
        let status = state.storage.get_rule_status(&run_id, rule_id).await
            .map(|s| format!("{:?}", s))
            .unwrap_or_else(|_| "Unknown".to_string());

        let node_name = snapshot.nodes.get(&rule_bp.owner_node_id)
            .map(|n| n.name.clone())
            .unwrap_or_else(|| rule_bp.owner_node_id.clone());

        let firing_mode = format!("{:?}", rule_bp.firing_mode);

        let attempt_count = state.storage.get_rule_attempt_count(&run_id, rule_id).await.unwrap_or(0);

        rules.push(RuleStatusEntry {
            rule_id: rule_id.clone(),
            id: rule_id.clone(),
            name: rule_bp.name.clone(),
            owner_node: rule_bp.owner_node_id.clone(),
            owner_node_name: node_name,
            status,
            is_terminal: rule_bp.is_terminal,
            is_controller: rule_bp.is_controller(),
            firing_mode,
            max_iterations: rule_bp.max_iterations,
            attempt_count,
        });
    }

    // 4. For each node, read its anchored status
    let mut anchored_nodes = HashMap::new();
    for node_id in snapshot.nodes.keys() {
        let is_anchored = state.storage.is_node_anchored(&run_id, node_id).await.unwrap_or(false);
        anchored_nodes.insert(node_id.clone(), is_anchored);
    }

    // 5. For each controller rule, read its loop iteration count
    let mut loop_states = HashMap::new();
    for (rule_id, rule_bp) in &snapshot.rules {
        if rule_bp.is_controller() {
            let iter = state.storage.get_loop_iteration(&run_id, rule_id).await.unwrap_or(0);
            loop_states.insert(rule_id.clone(), iter);
        }
    }

    Ok(Json(RunStatusResponse {
        run_id,
        run_status,
        rules,
        anchored_nodes,
        loop_states,
    }))
}

async fn cancel_run(
    State(state): State<Arc<AppState>>,
    Path(run_id): Path<String>,
) -> Result<String, (StatusCode, String)> {
    println!("🛑 Received cancellation request for run {}", run_id);
    
    // 1. Mark as Canceled
    state.storage.set_run_status(&run_id, RunStatus::Canceled).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to set status: {}", e)))?;
    
    // 2. Cleanup Redis keys
    state.storage.cleanup_run(&run_id).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, format!("Failed to cleanup: {}", e)))?;

    Ok("OK".to_string())
}