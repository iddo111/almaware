POSITION: KESHEV 2 must use (a) + (c) in combination: OpenMutexW probe *and* journal freshness, with the verdict hardwired into the startup path before any capture initialization.  

REASONS:  
- (a) provides immediate, low-latency confirmation of A’s *active* presence via its unique mutex—no process scanning overhead or false positives from zombie PIDs.  
- (c) adds resilience: if A crashes mid-capture (mutex held but dead), journal heartbeat freshness catches stale state; 60s heartbeat makes N=120s safe.  
- (b) is unreliable (PID reuse, obfuscated cmdline) and (d) risks device contention—even read-only probing can perturb live capture.  

RISKS:  
- Mutex may persist after A’s crash (though rare—kernel cleans up on process exit). Mitigated by (c)’s heartbeat check.  
- Journal file corruption could yield false-negative freshness; mitigated by validating JSON structure and fallback to (a) alone if unreadable.  

Verdict must be *structural*: the startup routine must `return False` *before* attempting device open or thread creation—no conditional guard later in the pipeline.