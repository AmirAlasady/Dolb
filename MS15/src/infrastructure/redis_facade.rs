use async_trait::async_trait;
use anyhow::{Result, Context};
use redis::{Client, aio::ConnectionManager, AsyncCommands};

use crate::domain::models::{RuleBlueprint, DataPacket, GraphSnapshot};
use crate::domain::enums::{RuleStatus, RunStatus};
use crate::interfaces::storage_trait::StorageFacade;

// =========================================================================
// Redis Key Helpers
// =========================================================================
fn key_snapshot(run_id: &str) -> String {
    format!("ms15:run:{}:snapshot", run_id)
}
fn key_proj(run_id: &str, projection_id: &str) -> String {
    format!("ms15:run:{}:proj:{}", run_id, projection_id)
}
fn key_rule_status(run_id: &str, rule_id: &str) -> String {
    format!("ms15:run:{}:rule:{}:status", run_id, rule_id)
}
fn key_rule_lock(run_id: &str, rule_id: &str) -> String {
    format!("ms15:run:{}:rule:{}:lock", run_id, rule_id)
}
fn key_node_anchor(run_id: &str, node_id: &str) -> String {
    format!("ms15:run:{}:node:{}:anchored", run_id, node_id)
}
// --- Loop state keys ---
fn key_loop_iter(run_id: &str, rule_id: &str) -> String {
    format!("ms15:run:{}:loop:{}:iter", run_id, rule_id)
}
fn key_loop_baseline(run_id: &str, rule_id: &str) -> String {
    format!("ms15:run:{}:loop:{}:baseline", run_id, rule_id)
}
fn key_rule_attempts(run_id: &str, rule_id: &str) -> String {
    format!("ms15:run:{}:rule:{}:attempts", run_id, rule_id)
}

// =========================================================================
// RedisAdapter
// =========================================================================
pub struct RedisAdapter {
    conn: ConnectionManager,
}

impl RedisAdapter {
    pub fn new(url: &str) -> Result<Self> {
        let client = Client::open(url)
            .context("Failed to create Redis client")?;
        // Use tokio's current runtime handle to run the async connection setup
        let conn = tokio::task::block_in_place(|| {
            tokio::runtime::Handle::current().block_on(ConnectionManager::new(client))
        }).context("Failed to create Redis connection manager")?;

        Ok(Self { conn })
    }
}

// =========================================================================
// StorageFacade implementation
// =========================================================================
#[async_trait]
impl StorageFacade for RedisAdapter {

    // ---- Blueprint / Snapshot ----

    async fn save_blueprint(&self, run_id: &str, snapshot: &GraphSnapshot) -> Result<()> {
        let key = key_snapshot(run_id);
        let json = serde_json::to_string(snapshot)?;
        let mut conn = self.conn.clone();
        conn.set::<_, _, ()>(&key, &json).await
            .context("Redis SET snapshot failed")?;
        
        // TTL Refresh
        let _ = redis::cmd("EXPIRE").arg(&key).arg(3600).query_async::<_, ()>(&mut conn).await;
        
        println!("  📦 Saved snapshot to {}", key);
        Ok(())
    }

    async fn get_full_snapshot(&self, run_id: &str) -> Result<GraphSnapshot> {
        let key = key_snapshot(run_id);
        let mut conn = self.conn.clone();
        let json_opt: Option<String> = conn.get(&key).await
            .context("Redis GET snapshot failed")?;
            
        let json = json_opt.ok_or_else(|| anyhow::anyhow!("Snapshot not found for run {}", run_id))?;
            
        let snapshot: GraphSnapshot = serde_json::from_str(&json)
            .context("Failed to deserialize GraphSnapshot from Redis")?;
        Ok(snapshot)
    }

    async fn get_rule_blueprint(&self, run_id: &str, rule_id: &str) -> Result<RuleBlueprint> {
        let snapshot = self.get_full_snapshot(run_id).await?;
        snapshot.rules.get(rule_id)
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("Rule {} not found in snapshot for run {}", rule_id, run_id))
    }

    async fn get_node_rules(&self, run_id: &str, node_id: &str) -> Result<Vec<String>> {
        let snapshot = self.get_full_snapshot(run_id).await?;
        let rule_ids: Vec<String> = snapshot.rules.values()
            .filter(|r| r.owner_node_id == node_id)
            .map(|r| r.id.clone())
            .collect();
        Ok(rule_ids)
    }

    async fn get_routes(&self, run_id: &str, rule_id: &str) -> Result<Vec<String>> {
        let snapshot = self.get_full_snapshot(run_id).await?;
        Ok(snapshot.routes.get(rule_id).cloned().unwrap_or_default())
    }

    // ---- Projection Data ----

    async fn push_data_to_projection(&self, run_id: &str, projection_id: &str, packet: &DataPacket) -> Result<()> {
        let key = key_proj(run_id, projection_id);
        let json = serde_json::to_string(packet)?;
        let mut conn = self.conn.clone();
        conn.rpush::<_, _, ()>(&key, &json).await
            .context("Redis RPUSH projection data failed")?;
        
        // TTL Refresh
        let _ = redis::cmd("EXPIRE").arg(&key).arg(3600).query_async::<_, ()>(&mut conn).await;

        println!("  📥 Pushed data to {}", key);
        Ok(())
    }

    async fn has_input_data(&self, run_id: &str, projection_id: &str) -> Result<bool> {
        let key = key_proj(run_id, projection_id);
        let mut conn = self.conn.clone();
        let len: i64 = conn.llen(&key).await
            .context("Redis LLEN failed")?;
        Ok(len > 0)
    }

    async fn get_input_data(&self, run_id: &str, projection_id: &str) -> Result<Vec<DataPacket>> {
        let key = key_proj(run_id, projection_id);
        let mut conn = self.conn.clone();
        let items: Vec<String> = conn.lrange(&key, 0, -1).await
            .context("Redis LRANGE failed")?;
        
        let packets: Vec<DataPacket> = items.iter()
            .filter_map(|s| serde_json::from_str(s).ok())
            .collect();
        Ok(packets)
    }

    // ---- Rule Status ----

    async fn get_rule_status(&self, run_id: &str, rule_id: &str) -> Result<RuleStatus> {
        let key = key_rule_status(run_id, rule_id);
        let mut conn = self.conn.clone();
        let val: Option<String> = conn.get(&key).await
            .context("Redis GET rule status failed")?;
        
        match val.as_deref() {
            Some("DISPATCHED") => Ok(RuleStatus::Dispatched),
            Some("COMPLETED")  => Ok(RuleStatus::Completed),
            Some("FAILED")     => Ok(RuleStatus::Failed),
            _                  => Ok(RuleStatus::Idle), // Default: not started yet
        }
    }

    async fn set_rule_status(&self, run_id: &str, rule_id: &str, status: RuleStatus) -> Result<()> {
        let key = key_rule_status(run_id, rule_id);
        let val = match status {
            RuleStatus::Idle       => "IDLE",
            RuleStatus::Dispatched => "DISPATCHED",
            RuleStatus::Completed  => "COMPLETED",
            RuleStatus::Failed     => "FAILED",
        };
        let mut conn = self.conn.clone();
        conn.set::<_, _, ()>(&key, val).await
            .context("Redis SET rule status failed")?;
        
        // TTL Refresh
        let _ = redis::cmd("EXPIRE").arg(&key).arg(3600).query_async::<_, ()>(&mut conn).await;

        println!("  🏷️  Rule {} status -> {}", rule_id, val);
        Ok(())
    }

    // ---- Locking ----

    async fn lock_rule(&self, run_id: &str, rule_id: &str) -> Result<bool> {
        let key = key_rule_lock(run_id, rule_id);
        let mut conn = self.conn.clone();
        // SETNX returns true if the key was set (we got the lock)
        let was_set: bool = redis::cmd("SET")
            .arg(&key)
            .arg("locked")
            .arg("NX")    // Only set if not exists
            .arg("EX")    // Expire
            .arg(300)     // 5 min TTL (safety net)
            .query_async(&mut conn)
            .await
            .unwrap_or(false);
        
        if was_set {
            println!("  🔒 Locked rule {}", rule_id);
        } else {
            println!("  ⏭️  Rule {} already locked, skipping", rule_id);
        }
        Ok(was_set)
    }

    async fn unlock_rule(&self, run_id: &str, rule_id: &str) -> Result<()> {
        let key = key_rule_lock(run_id, rule_id);
        let mut conn = self.conn.clone();
        conn.del::<_, ()>(&key).await
            .context("Redis DEL rule lock failed")?;
        println!("  🔓 Unlocked rule {} for retry", rule_id);
        Ok(())
    }

    // ---- User Identity ----

    async fn save_run_user_id(&self, run_id: &str, user_id: &str) -> Result<()> {
        let key = format!("ms15:run:{}:user_id", run_id);
        let mut conn = self.conn.clone();
        conn.set::<_, _, ()>(&key, user_id).await
            .context("Redis SET user_id failed")?;
        
        // TTL Refresh
        let _ = redis::cmd("EXPIRE").arg(&key).arg(3600).query_async::<_, ()>(&mut conn).await;

        println!("  👤 Saved user_id '{}' for run {}", user_id, run_id);
        Ok(())
    }

    async fn get_run_user_id(&self, run_id: &str) -> Result<String> {
        let key = format!("ms15:run:{}:user_id", run_id);
        let mut conn = self.conn.clone();
        let user_id: String = conn.get(&key).await
            .context("Redis GET user_id failed")?;
        Ok(user_id)
    }

    // ---- Run Status ----

    async fn set_run_status(&self, run_id: &str, status: RunStatus) -> Result<()> {
        let key = format!("ms15:run:{}:status", run_id);
        let val = match status {
            RunStatus::Seeding   => "SEEDING",
            RunStatus::Running   => "RUNNING",
            RunStatus::Completed => "COMPLETED",
            RunStatus::Failed    => "FAILED",
            RunStatus::Canceled  => "CANCELED",
        };
        let mut conn = self.conn.clone();
        conn.set::<_, _, ()>(&key, val).await
            .context("Redis SET run status failed")?;
        
        // Refresh TTL on status change
        let _ = redis::cmd("EXPIRE").arg(&key).arg(3600).query_async::<_, ()>(&mut conn).await;
        
        println!("  📊 Run {} status -> {}", run_id, val);
        Ok(())
    }

    async fn get_run_status(&self, run_id: &str) -> Result<RunStatus> {
        let key = format!("ms15:run:{}:status", run_id);
        let mut conn = self.conn.clone();
        let val: Option<String> = conn.get(&key).await
            .context("Redis GET run status failed")?;
        match val.as_deref() {
            Some("SEEDING")   => Ok(RunStatus::Seeding),
            Some("RUNNING")   => Ok(RunStatus::Running),
            Some("COMPLETED") => Ok(RunStatus::Completed),
            Some("FAILED")    => Ok(RunStatus::Failed),
            Some("CANCELED")  => Ok(RunStatus::Canceled),
            _                 => Ok(RunStatus::Seeding),
        }
    }

    async fn cleanup_run(&self, run_id: &str) -> Result<()> {
        let pattern = format!("ms15:run:{}:*", run_id);
        let mut conn = self.conn.clone();
        
        // 1. Find all keys for this run
        let keys: Vec<String> = redis::cmd("KEYS")
            .arg(&pattern)
            .query_async(&mut conn)
            .await?;
        
        if !keys.is_empty() {
            // 2. Delete them
            conn.del::<_, ()>(&keys).await?;
            println!("  🧹 Cleaned up {} keys for run {}", keys.len(), run_id);
        }
        
        Ok(())
    }

    async fn get_rule_attempt_count(&self, run_id: &str, rule_id: &str) -> Result<u32> {
        let key = format!("ms15:run:{}:rule:{}:attempts", run_id, rule_id);
        let mut conn = self.conn.clone();
        let count: Option<u32> = conn.get(&key).await.unwrap_or(None);
        Ok(count.unwrap_or(0))
    }

    async fn incr_rule_attempt_count(&self, run_id: &str, rule_id: &str) -> Result<u32> {
        let key = format!("ms15:run:{}:rule:{}:attempts", run_id, rule_id);
        let mut conn = self.conn.clone();
        let new_count: u32 = redis::cmd("INCR")
            .arg(&key)
            .query_async(&mut conn)
            .await
            .context("Redis INCR rule attempts failed")?;
        // Keep attempt counters alive as long as the snapshot
        let _ = redis::cmd("EXPIRE").arg(&key).arg(3600).query_async::<_, ()>(&mut conn).await;
        Ok(new_count)
    }

    // ---- Anchor Gate ----

    async fn set_node_anchored(&self, run_id: &str, node_id: &str) -> Result<()> {
        let key = key_node_anchor(run_id, node_id);
        let mut conn = self.conn.clone();
        conn.set::<_, _, ()>(&key, "1").await
            .context("Redis SET node anchor failed")?;
        let _ = redis::cmd("EXPIRE").arg(&key).arg(3600).query_async::<_, ()>(&mut conn).await;
        println!("  ⚓ Node {} anchored for run {}", node_id, run_id);
        Ok(())
    }

    async fn is_node_anchored(&self, run_id: &str, node_id: &str) -> Result<bool> {
        let key = key_node_anchor(run_id, node_id);
        let mut conn = self.conn.clone();
        let val: Option<String> = conn.get(&key).await
            .context("Redis GET node anchor failed")?;
        Ok(val.is_some())
    }

    // ---- Loop / Iteration State ----

    async fn get_loop_iteration(&self, run_id: &str, rule_id: &str) -> Result<u32> {
        let key = key_loop_iter(run_id, rule_id);
        let mut conn = self.conn.clone();
        let count: Option<u32> = conn.get(&key).await.unwrap_or(None);
        Ok(count.unwrap_or(0))
    }

    async fn incr_loop_iteration(&self, run_id: &str, rule_id: &str) -> Result<u32> {
        let key = key_loop_iter(run_id, rule_id);
        let mut conn = self.conn.clone();
        let new_val: u32 = redis::cmd("INCR")
            .arg(&key)
            .query_async(&mut conn)
            .await
            .context("Redis INCR loop iteration failed")?;
        let _ = redis::cmd("EXPIRE").arg(&key).arg(3600).query_async::<_, ()>(&mut conn).await;
        Ok(new_val)
    }

    async fn save_loop_baseline(&self, run_id: &str, rule_id: &str, payload: &str) -> Result<()> {
        let key = key_loop_baseline(run_id, rule_id);
        let mut conn = self.conn.clone();
        // NX = Only set if not exists (store once, never overwrite)
        let set: bool = redis::cmd("SET")
            .arg(&key)
            .arg(payload)
            .arg("NX")
            .query_async(&mut conn)
            .await
            .unwrap_or(false);
        if set {
            let _ = redis::cmd("EXPIRE").arg(&key).arg(3600).query_async::<_, ()>(&mut conn).await;
            println!("  🧩 Saved loop baseline for controller rule {}", rule_id);
        }
        Ok(())
    }

    async fn get_loop_baseline(&self, run_id: &str, rule_id: &str) -> Result<String> {
        let key = key_loop_baseline(run_id, rule_id);
        let mut conn = self.conn.clone();
        let val: Option<String> = conn.get(&key).await
            .context("Redis GET loop baseline failed")?;
        val.ok_or_else(|| anyhow::anyhow!("No baseline found for controller rule {} in run {}", rule_id, run_id))
    }

    async fn reset_rule_for_refire(&self, run_id: &str, rule_id: &str) -> Result<()> {
        let mut conn = self.conn.clone();
        // 1. Clear the status back to Idle
        conn.del::<_, ()>(&key_rule_status(run_id, rule_id)).await
            .context("Redis DEL rule status (reset) failed")?;
        // 2. Remove the lock so the evaluator can re-acquire it
        conn.del::<_, ()>(&key_rule_lock(run_id, rule_id)).await
            .context("Redis DEL rule lock (reset) failed")?;
        // 3. Reset attempt count so retry budget is fresh for next iteration
        conn.del::<_, ()>(&key_rule_attempts(run_id, rule_id)).await
            .context("Redis DEL rule attempts (reset) failed")?;
        println!("  🔄 Rule {} reset to Idle for next loop iteration", rule_id);
        Ok(())
    }
}
