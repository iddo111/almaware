> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# Rollback

This scaffold makes no node or network changes, so deleting its isolated staged
copy is sufficient before deployment. Never delete the source/base checkpoint
or dataset as part of rollback.

For a future bounded qualification run:

1. Stop only the recorded run ID with the launcher-created PID or scheduler job
   ID. Do not use broad process-name kills.
2. Preserve the final log, preflight JSON, package lock, fabric counters,
   gradient proof, and checkpoint hash manifests.
3. Move the incomplete output directory to a run-ID quarantine directory on the
   same filesystem. Do not overwrite a previous run.
4. Confirm pre-existing services and fabric routes still have their preflight
   identities and behavior.
5. Restore distributed training state only under the same recorded parallelism.
   Restore a portable model only from a consolidated checkpoint that passed the
   tensor-hash gate.

Abort triggers include OOM, NaN/Inf, NCCL timeout, fabric fallback, unexpected
rank count, thermal threshold, filesystem reserve breach, a frozen parameter,
missing gradient coverage, or an unplanned model/data digest.

Rollback is **UNVERIFIED** until tested during the 2B qualification.
