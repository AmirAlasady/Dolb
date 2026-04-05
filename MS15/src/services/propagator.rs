use std::sync::Arc;
use anyhow::{Result, Context};
use std::time::{SystemTime, UNIX_EPOCH};
use crate::domain::enums::{RuleStatus, RunStatus};
use crate::domain::models::{InferenceResultMessage, EvalCheckMessage, GraphSnapshot};
use crate::domain::logic::{get_downstream_projections, create_result_packet, find_rules_affected_by_projection};
use crate::interfaces::storage_trait::StorageFacade;
use crate::interfaces::messaging_trait::MessagingFacade;

/// Maximum times a non-terminal rule is retried before being permanently marked Failed.
/// This handles transient LLM / TGI errors (e.g. "Value out of range", 500s).
const MAX_RULE_RETRIES: u32 = 3;

pub struct PropagatorService<S, M> {
    storage: Arc<S>,
    messaging: Arc<M>,
}

impl<S, M> Clone for PropagatorService<S, M> {
    fn clone(&self) -> Self {
        Self {
            storage: self.storage.clone(),
            messaging: self.messaging.clone(),
        }
    }
}

impl<S: StorageFacade, M: MessagingFacade> PropagatorService<S, M> {
    pub fn new(storage: Arc<S>, messaging: Arc<M>) -> Self {
        Self { storage, messaging }
    }

    /// Check if ALL rules in the graph have reached a terminal state (Completed or Failed),
    /// and if so, mark the run as COMPLETED.
    ///
    /// This must be called after EVERY rule finishes (terminal or not) because:
    /// - A terminal rule may finish BEFORE non-terminal rules catch up (we correctly wait).
    /// - The LAST non-terminal rule to finish must also trigger the check, since the terminal
    ///   rule's check was already skipped for being "not ready yet" at that time.
    ///
    /// Loop-awareness: controller rules in `Idle` state during an active loop iteration are
    /// NOT considered done — they will re-fire when the next iteration triggers them.
    async fn check_and_close_run(
        &self,
        run_id: &str,
        just_finished_rule_id: &str,
        snapshot: &GraphSnapshot,
    ) -> Result<()> {
        // Skip if run is already closed
        match self.storage.get_run_status(run_id).await {
            Ok(RunStatus::Completed) | Ok(RunStatus::Failed) | Ok(RunStatus::Canceled) => {
                return Ok(());
            }
            _ => {}
        }

        let total = snapshot.rules.len();
        let terminal_count = snapshot.rules.values().filter(|r| r.is_terminal).count();
        println!(
            "🔍 Completion check after rule {} | Total: {} / Terminal: {}",
            &just_finished_rule_id[..8.min(just_finished_rule_id.len())],
            total,
            terminal_count
        );

        let mut all_terminals_done = true;
        let mut any_still_running = false;
        let mut all_rules_settled = true;

        for (rid, rule) in &snapshot.rules {
            // ALWAYS read the current status from Redis.
            // We cannot use the "just finished = Completed" shortcut because the
            // home-run block in step 8 may have RESET this rule to Idle (loop body
            // rules are reset for the next iteration). Reading stale status here
            // would make the check think loop body rules are settled when they're not.
            let s = self.storage.get_rule_status(run_id, rid).await?;

            let is_done = matches!(s, RuleStatus::Completed | RuleStatus::Failed);
            let is_still_running = matches!(s, RuleStatus::Dispatched);

            if !is_done {
                all_rules_settled = false;
            }

            // --- Loop-awareness for controller rules ---
            // A controller rule that is `Idle` could be:
            //   (a) Not yet reached (run is still early) → still running
            //   (b) Mid-loop, reset to Idle waiting for next iteration trigger → loop is active, still running
            //   (c) Before the run started — same as (a)
            // In all cases where iteration count > 0 and status is Idle,
            // the loop is active and we should NOT close the run.
            let is_active_looping_idle = if matches!(s, RuleStatus::Idle) && rule.is_controller() {
                let iter = self.storage.get_loop_iteration(run_id, rid).await.unwrap_or(0);
                iter > 0  // iter > 0 means at least one iteration has completed; loop is in progress
            } else {
                false
            };

            if rule.is_terminal {
                print!("  - [TERMINAL] {} ({}): {:?}", &rid[..8.min(rid.len())], rule.name, s);
                if !is_done {
                    println!(" ← NOT DONE");
                    all_terminals_done = false;
                } else {
                    println!(" ✓");
                }
            }

            if is_still_running || is_active_looping_idle {
                println!(
                    "  - [{}] {} ({}) still {:?}{} — holding run open",
                    if rule.is_terminal { "TERMINAL!" } else { "NON-TERM" },
                    &rid[..8.min(rid.len())], rule.name, s,
                    if is_active_looping_idle { " (looping)" } else { "" }
                );
                any_still_running = true;
            }
        }

        let is_finished = if terminal_count > 0 {
            all_terminals_done && !any_still_running
        } else {
            // If there are no terminal rules, the graph is a complete sandbox/batch trace.
            // We MUST wait for every single rule to settle (Completed or Failed) AND
            // ensure no rule is actively looping (Dispatched or Idle-but-in-a-loop).
            all_rules_settled && !any_still_running
        };

        if is_finished {
            println!("🎉 All rules settled. Graph COMPLETED for run {}.", run_id);
            self.storage.set_run_status(run_id, RunStatus::Completed).await?;
        } else {
            println!(
                "  ⏳ Not closing yet: terminals_done={} any_still_running={} all_settled={}",
                all_terminals_done, any_still_running, all_rules_settled
            );
        }

        Ok(())
    }

    /// Check if a given projection is feedback-family (has FBI ancestry).
    /// A projection is feedback-family if it has a direct FBI source OR any of its
    /// child/ancestor projections have a FBI source.
    fn is_feedback_family_projection(snapshot: &GraphSnapshot, proj_id: &str) -> bool {
        if let Some(p) = snapshot.projections.get(proj_id) {
            if p.source_fbi_id.is_some() {
                return true;
            }
            return p.children_ids.iter().any(|cid| Self::is_feedback_family_projection(snapshot, cid));
        }
        false
    }

    /// Check if a projection belongs specifically to a given controller's feedback loop.
    ///
    /// A projection belongs to controller C's loop if its FBI ancestry (source_fbi_id chain)
    /// traces back to a FBI channel whose source_node_id == controller_node_id.
    ///
    /// IMPORTANT: source_fbi_id on a ProjectionBlueprint is an FBI *channel* ID (in
    /// snapshot.fbis), NOT a projection ID. FBI.source_node_id = the controller node.
    ///
    /// This prevents cross-loop interference: when C fires a home-run and resets loop
    /// body rules, it must NOT reset rules that belong to a different controller X's loop,
    /// even if those rules are also feedback-family.
    fn is_projection_in_controller_loop(
        snapshot: &GraphSnapshot,
        proj_id: &str,
        controller_node_id: &str,
    ) -> bool {
        if let Some(p) = snapshot.projections.get(proj_id) {
            // source_fbi_id is the ID of an FBI channel (in snapshot.fbis).
            // The FBI channel's source_node_id tells us WHICH controller sent the feedback.
            if let Some(fbi_channel_id) = &p.source_fbi_id {
                if let Some(fbi) = snapshot.fbis.get(fbi_channel_id) {
                    if fbi.source_node_id == controller_node_id {
                        return true;
                    }
                }
            }
            // children_ids are the parent/ancestor projections from which this one was derived.
            // Recursing into them propagates the taint-tracing upward through the derivation tree.
            return p.children_ids.iter().any(|cid| {
                Self::is_projection_in_controller_loop(snapshot, cid, controller_node_id)
            });
        }
        false
    }

    pub async fn process_result(&self, msg: InferenceResultMessage) -> Result<()> {
        let run_id = &msg.run_id;
        let rule_id = &msg.rule_id;

        // Check if run is canceled
        if let Ok(RunStatus::Canceled) = self.storage.get_run_status(run_id).await {
            println!("🛑 Run {} is CANCELED. Skipping propagation for rule {}.", run_id, rule_id);
            return Ok(());
        }

        println!("📥 Processing result for run={}, rule={}, status={}", run_id, rule_id, msg.status);

        // 1. Idempotency Check
        let current_status = self.storage.get_rule_status(run_id, rule_id).await?;
        if current_status == RuleStatus::Completed {
            println!("  ⏭️ Rule {} already completed. Ignoring duplicate result.", rule_id);
            return Ok(());
        }

        // 2. Load Blueprint
        let snapshot = match self.storage.get_full_snapshot(run_id).await {
            Ok(s) => s,
            Err(e) => {
                if e.to_string().contains("Snapshot not found") {
                    println!("  ⏭️ Snapshot missing for run {} (likely cleaned up). Ignoring result for rule {}.", run_id, rule_id);
                    return Ok(());
                }
                return Err(e);
            }
        };
        let rule_bp = snapshot.rules.get(rule_id).context("Rule missing from snapshot")?;

        // 3. Handle Failure — with retry logic for transient LLM errors
        if !msg.status.eq_ignore_ascii_case("success") {
            let attempt = self.storage.incr_rule_attempt_count(run_id, rule_id).await?;
            println!("  ❌ Rule {} FAILED (attempt {}/{}): {:?}", rule_id, attempt, MAX_RULE_RETRIES, msg.error);

            if attempt < MAX_RULE_RETRIES {
                println!(
                    "  🔄 Retrying rule {} (attempt {}/{}) after transient failure...",
                    rule_id, attempt, MAX_RULE_RETRIES
                );
                // Reset status and lock so evaluator can re-dispatch
                self.storage.set_rule_status(run_id, rule_id, RuleStatus::Idle).await?;
                self.storage.unlock_rule(run_id, rule_id).await?;

                let eval_msg = EvalCheckMessage {
                    run_id: run_id.clone(),
                    rule_id: rule_id.clone(),
                    trigger_source: Some(format!("Retry attempt {}/{}", attempt, MAX_RULE_RETRIES)),
                };
                self.messaging.publish_eval_check(eval_msg).await?;
                println!("  📬 Published retry eval check for rule {}", rule_id);
                return Ok(());
            }

            println!("  💀 Rule {} permanently FAILED after {} attempts.", rule_id, MAX_RULE_RETRIES);
            self.storage.set_rule_status(run_id, rule_id, RuleStatus::Failed).await?;

            // Even on permanent failure, check if this was the last rule holding the run open.
            self.check_and_close_run(run_id, rule_id, &snapshot).await?;
            return Ok(());
        }

        // 4. Route successful result downstream
        let target_projections = get_downstream_projections(&snapshot, rule_id);
        println!("  🔀 Rule {} routes to {} downstream projections", rule_id, target_projections.len());

        let now = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
        let payload_val = msg.payload.clone().unwrap_or_else(|| serde_json::json!({}));
        let packet = create_result_packet(payload_val.clone(), rule_id, &rule_bp.owner_node_id);
        let mut final_packet = packet;
        final_packet.produced_at = now;

        // 4a. CONTROLLER BASELINE RECORDING
        // If this is a controller rule (FBO outputs), save the input payload as the SLICE_X0
        // baseline on first fire. NX semantics in Redis ensure this only stores once even on
        // concurrent duplicate deliveries.
        if rule_bp.is_controller() {
            let baseline_str = serde_json::to_string(&payload_val)?;
            self.storage.save_loop_baseline(run_id, rule_id, &baseline_str).await?;
        }

        // 5. Fan-Out: write data and wake downstream rules
        for dest_proj_id in &target_projections {
            self.storage.push_data_to_projection(run_id, dest_proj_id, &final_packet).await?;

            let affected_rules = find_rules_affected_by_projection(&snapshot, dest_proj_id);
            println!("  📤 Projection {} wakes {} rules", dest_proj_id, affected_rules.len());

            for affected_rule_id in affected_rules {
                let eval_msg = EvalCheckMessage {
                    run_id: run_id.clone(),
                    rule_id: affected_rule_id.clone(),
                    trigger_source: Some(format!("Upstream Rule {}", rule_id)),
                };
                self.messaging.publish_eval_check(eval_msg).await?;
                println!("  📬 Published eval check for rule {}", affected_rule_id);
            }
        }

        // 6. Mark this rule Completed
        self.storage.set_rule_status(run_id, rule_id, RuleStatus::Completed).await?;
        println!("  ✅ Rule {} completed successfully", rule_id);

        // 7. ANCHOR PROMOTION
        // If this was a forward-family rule (all inputs are FFI/seed, none are FBI),
        // mark the node as anchored. This unblocks feedback-family rules on the same
        // node from firing on subsequent eval checks.
        // Anchor is idempotent — setting it again on re-runs is harmless.
        if rule_bp.is_forward_family(&snapshot) {
            self.storage.set_node_anchored(run_id, &rule_bp.owner_node_id).await?;
        }

        // 8. HOME RUN DETECTION
        //
        // A home run occurs when data arriving at a CONTROLLER NODE was produced by
        // a rule in the LOOP BODY (not the controller itself). Specifically:
        //   (a) The rule that just completed is NOT the controller (skip self-detection)
        //   (b) The destination projection is feedback-family (has FBI ancestry)
        //   (c) The destination projection lives on the controller's own node
        //   (d) The FBI at the root traces back to the controller's FBO
        //
        // In our A→B→C example: after B's R5 fires, data is written to C's projection
        // `B[A[~C[...]]]`. C is the controller's node. The projection has ~C ancestry.
        // → HOME RUN for R3 (iteration complete).
        //
        // CRITICAL: When R3 itself fires, its FBO output goes to A's FBI projection.
        // That is the EMISSION, not the home run. We must NOT trigger home-run logic
        // for the controller's own result — only for the loop body's return.
        //
        // Guard: also bail if the run is already COMPLETED to prevent zombie processing
        // from in-flight results that arrive after the graph has finished.

        // Skip home-run entirely if this rule IS a controller — controllers emit feedback,
        // they don't receive home runs from their own output.
        println!(
            "  🔎 HOME RUN CHECK: rule {} is_controller={} | {} target_projections",
            &rule_id[..8.min(rule_id.len())], rule_bp.is_controller(), target_projections.len()
        );
        if !rule_bp.is_controller() {
            // Guard: check if the run was already marked completed by a prior concurrent result
            let run_still_active = match self.storage.get_run_status(run_id).await {
                Ok(RunStatus::Running) => true,
                Ok(other) => {
                    println!("  ⚠️ HOME RUN SKIPPED: run status is {:?}, not Running", other);
                    false
                },
                Err(e) => {
                    println!("  ⚠️ HOME RUN SKIPPED: failed to get run status: {:?}", e);
                    false
                },
            };

            if run_still_active {
                for dest_proj_id in &target_projections {
                    if let Some(proj) = snapshot.projections.get(dest_proj_id) {
                        // Is this projection feedback-family?
                        let is_fb = Self::is_feedback_family_projection(&snapshot, dest_proj_id);
                        println!(
                            "    📍 Checking proj {} on node {} | feedback_family={} | source_fbi={:?} | children={:?}",
                            &dest_proj_id[..8.min(dest_proj_id.len())],
                            &proj.owner_node_id[..8.min(proj.owner_node_id.len())],
                            is_fb,
                            proj.source_fbi_id.as_ref().map(|s| &s[..8.min(s.len())]),
                            proj.children_ids.iter().map(|c| &c[..8.min(c.len())]).collect::<Vec<_>>()
                        );
                        if !is_fb {
                            continue;
                        }

                        // The destination projection must be on the CONTROLLER'S node.
                        // If the projection is on some intermediate node, it's just mid-loop transit.
                        // Find the controller rule whose node matches this projection's owner node.
                        let ctrl_rule = snapshot.rules.values().find(|r| {
                            r.is_controller() && r.owner_node_id == proj.owner_node_id
                        });

                        println!(
                            "    🎯 Feedback proj on node {} — matching controller: {:?}",
                            &proj.owner_node_id[..8.min(proj.owner_node_id.len())],
                            ctrl_rule.as_ref().map(|r| (&r.id[..8.min(r.id.len())], &r.name))
                        );

                        if let Some(ctrl) = ctrl_rule {
                            let ctrl_id = ctrl.id.clone();
                            let new_iter = self.storage.incr_loop_iteration(run_id, &ctrl_id).await?;
                            let completed_iter = new_iter - 1; // 0-indexed: iter 0 just completed

                            println!(
                                "🏠 HOME RUN for controller {} (iteration {} just completed)",
                                &ctrl_id[..8.min(ctrl_id.len())], completed_iter
                            );

                            // Check forced exit condition
                            let force_exit = ctrl.max_iterations
                                .map(|max| new_iter >= max)
                                .unwrap_or(false);

                            if force_exit {
                                println!(
                                    "🏁 Controller {} reached max_iterations ({}). Loop EXITED.",
                                    &ctrl_id[..8.min(ctrl_id.len())], ctrl.max_iterations.unwrap()
                                );
                                // Controller stays Completed. Run completion check will close it.
                            } else {
                                // CONTINUE: reset controller for next iteration
                                println!(
                                    "🔁 Controller {} continuing to iteration {}",
                                    &ctrl_id[..8.min(ctrl_id.len())], new_iter
                                );

                                // 1. Reset controller rule state to Idle (clears lock + attempt count too)
                                self.storage.reset_rule_for_refire(run_id, &ctrl_id).await?;

                                // 1b. Reset ONLY the loop body rules that belong to THIS controller's loop.
                                // We must NOT reset rules from other controllers' loops (e.g., if X and C
                                // both feed back to A, resetting C should not touch rX-homerun which
                                // belongs to X's loop).
                                //
                                // A rule belongs to THIS controller's loop if at least one of its input
                                // projections traces its FBI ancestry back to THIS controller's node.
                                let ctrl_node_id = ctrl.owner_node_id.clone();
                                for (rid, rbp) in &snapshot.rules {
                                    if rid == &ctrl_id { continue; } // skip the controller itself
                                    if rbp.is_controller() { continue; } // skip other controllers
                                    
                                    // Check if this rule's inputs are in THIS controller's loop
                                    let is_this_loops_body = rbp.input_projection_ids.iter().any(|pid| {
                                        Self::is_projection_in_controller_loop(&snapshot, pid, &ctrl_node_id)
                                    });
                                    
                                    if is_this_loops_body {
                                        self.storage.reset_rule_for_refire(run_id, rid).await?;
                                        println!(
                                            "  🔄 Loop body rule {} ({}) reset to Idle for controller {} iteration {}",
                                            &rid[..8.min(rid.len())], rbp.name,
                                            &ctrl_id[..8.min(ctrl_id.len())], new_iter
                                        );
                                    } else if rbp.input_projection_ids.iter().any(|pid| {
                                        Self::is_feedback_family_projection(&snapshot, pid)
                                    }) {
                                        println!(
                                            "  ⏭️ Skipping reset of {} ({}) — feedback-family but belongs to a DIFFERENT loop",
                                            &rid[..8.min(rid.len())], rbp.name
                                        );
                                    }
                                }

                                // 2. Write the CLIPPED payload (SLICE_X0) to the controller's input projections
                                //    so it fires again with the stable baseline, not the ever-growing chain.
                                let baseline_str = match self.storage.get_loop_baseline(run_id, &ctrl_id).await {
                                    Ok(s) => s,
                                    Err(_) => {
                                        // Fallback: use current payload if baseline was never stored
                                        serde_json::to_string(&payload_val)?
                                    }
                                };
                                let clipped_payload: serde_json::Value = serde_json::from_str(&baseline_str)
                                    .unwrap_or_else(|_| payload_val.clone());

                                let clipped_packet = create_result_packet(
                                    clipped_payload,
                                    &ctrl_id,
                                    &ctrl.owner_node_id,
                                );

                                // Write the clipped value to each of the controller's input projections
                                for input_proj_id in &ctrl.input_projection_ids {
                                    self.storage.push_data_to_projection(run_id, input_proj_id, &clipped_packet).await?;
                                }

                                // 3. Publish eval check for the controller so it wakes up
                                let eval_msg = EvalCheckMessage {
                                    run_id: run_id.clone(),
                                    rule_id: ctrl_id.clone(),
                                    trigger_source: Some(format!("HomeRun iteration-{} clipped", completed_iter)),
                                };
                                self.messaging.publish_eval_check(eval_msg).await?;
                                println!(
                                    "  📬 Published eval check for controller {} (clipped loop re-fire)",
                                    &ctrl_id[..8.min(ctrl_id.len())]
                                );
                            }
                        }
                    }
                }
            }
        }

        // 9. Completion gate — runs after EVERY successful rule, not just terminals.
        //
        // Why: if the terminal rule finishes while non-terminal sibling rules are still
        // DISPATCHED, we correctly hold the run open. But we must ALSO check when those
        // non-terminal rules finish later, or the run stays RUNNING forever.
        self.check_and_close_run(run_id, rule_id, &snapshot).await?;

        Ok(())
    }
}