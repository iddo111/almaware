**FINDING 1**  
`check()` can grant a `CaptureTicket` even when the journal detector fails.  

**WHY IT CANNOT FIRE / WHEN IT LIES**  
In the `elif m is False:` branch the code builds `InterlockVerdict(False, True, "mutex+journal", …)` **without** checking whether `journal_age()` returned `None`. If the mutex is absent *and* the journal file is unreadable (or missing), the guard that should require *both* detectors to be clean never triggers, and `grant()` will succeed.  

**FIX**  
Require `journal_age()` to be readable (i.e. not `None`) before setting `provable=True` when `m is False`.

---

**FINDING 2**  
`CaptureTicket`’s “construction‑only‑via‑grant” guard is bypassable.  

**WHY IT CANNOT FIRE / WHEN IT LIES**  
The guard relies on a private sentinel `_TICKET_TOKEN = object()`. Because the module does not hide this name (it’s a module‑level variable), any caller can import the module and pass `_TICKET_TOKEN` to `CaptureTicket.__init__`, creating a ticket without going through `InterlockVerdict.grant()`. The guard therefore never fires for a determined attacker.  

**FIX**  
Make `_TICKET_TOKEN` truly private (e.g., generate it inside `grant()` and store it in a closure) or validate the call stack instead of a shared object.

---

**FINDING 3**  
`acquire_own_mutex_or_exit()` may fail to block a duplicate KESHEV 2 instance.  

**WHY IT CANNOT FIRE / WHEN IT LIES**  
The function only treats `GetLastError() == _ERROR_ALREADY_EXISTS` as a duplicate. If `CreateMutexW` succeeds in returning a handle but `GetLastError()` reports a different error (e.g., `ERROR_ACCESS_DENIED` because the caller lacks rights to the mutex name), the code assumes it is the winner and continues, allowing two processes to run concurrently. The duplicate‑instance guard therefore cannot fire in that scenario.  

**FIX**  
Treat any non‑zero `GetLastError()` (except `ERROR_SUCCESS`) as a duplicate or fatal error, and exit accordingly.