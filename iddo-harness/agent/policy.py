"""
Policy engine — decides whether a task can run, needs confirmation, or is blocked.
"""
import fnmatch
import logging
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from pathlib import Path

try:
    from secrets_vault import mask_text
except ImportError:  # pragma: no cover - packaged imports
    from agent.secrets_vault import mask_text

log = logging.getLogger("harness.policy")

# v2 kinds have no real command line, so the executors synthesise one
# (`grep <path>`, `patch <path>`, `read_chunk <path>`, …). These verb lists let
# decide() apply the path-glob rules that policy.yaml has always declared under
# `auto_allow.paths.read` / `require_confirm.paths.write`. See docs/v2_spec.md §5.
READ_VERBS = frozenset(
    {"cat", "type", "head", "tail", "read", "read_chunk", "list", "ls", "dir", "grep", "glob", "watch_start", "watch_poll"}
)
WRITE_VERBS = frozenset({"write", "patch", "rm", "del", "mv", "move", "cp", "copy"})


def _path_matches(path: str, pattern: str) -> bool:
    """Glob-match a target path against a policy path pattern.

    Beyond plain `fnmatch`, this normalises the three things that bite in a
    mixed Windows/POSIX policy file: `~` and `%USERNAME%` are expanded,
    separators are unified, and a trailing `/**` also matches the root itself
    (so `D:\\CLAUDE\\**` covers `D:\\CLAUDE`). Matching is case-insensitive
    because Windows paths in policy.yaml rarely match the casing the OS reports.
    """
    expanded = os.path.expandvars(os.path.expanduser(pattern))
    norm_pat = expanded.replace("\\", "/").lower()
    norm_path = os.path.expanduser(path).replace("\\", "/").rstrip("/").lower()

    if fnmatch.fnmatchcase(norm_path, norm_pat):
        return True
    if norm_pat.endswith("/**") and norm_path == norm_pat[:-3]:
        return True
    return False


# Wrappers that carry a real command as their tail. `cmd /c format c:` used to
# sail past a `format*` block pattern because fnmatch is start-anchored, so the
# gate matched the wrapper and never saw the command. Stripping these (and
# splitting compound commands) is what makes the block list mean what it says.
_WRAPPER_PREFIXES = (
    "cmd /c", "cmd.exe /c", "cmd /k", "cmd.exe /k",
    "powershell -command", "powershell.exe -command", "powershell -c",
    "powershell -noprofile -command", "pwsh -c", "pwsh -command",
    "sh -c", "bash -c", "zsh -c", "ssh -t", "sudo", "doas",
    "nohup", "start /b", "start", "xargs", "time", "nice", "ionice",
)

# A command that chains is not the command the auto-allow list vetted.
# Operators only count OUTSIDE quotes: the `;` in
# `python -c "import sys;print(1)"` is Python, not a shell chain, and treating
# it as one made four executor tests fail -- which is exactly how a gate earns
# the reputation that gets it switched off.
_CHAIN_OPERATORS = ("&&", "||", ";", "|", "\n")
_SUBSTITUTIONS = ("`", "$(")


def _split_unquoted(text: str) -> list[str]:
    """Split *text* on shell chain operators that are not inside quotes."""
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = ""
            buf.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        matched = ""
        for op in _CHAIN_OPERATORS:
            if text.startswith(op, i):
                matched = op
                break
        if matched:
            parts.append("".join(buf))
            buf = []
            i += len(matched)
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _has_unquoted(text: str, tokens) -> bool:
    quote = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        for token in tokens:
            if text.startswith(token, i):
                return True
        i += 1
    return False


def _normalise_command(command: str) -> str:
    """Case-fold and collapse whitespace, so casing and padding cannot hide a rule.

    `Shutdown  /s` and `shutdown /s` are the same command to the operating
    system; before this they were two different strings to the gate, and only
    one of them was blocked.
    """
    text = str(command).replace("\t", " ")
    # Separators too: `D:\\CLAUDE\\x` and `d:/claude/x` are one path, and a
    # rule written with one of them used to miss the other. Patterns go
    # through this same function, so both sides always agree.
    text = text.replace("\\", "/")
    return " ".join(text.split()).lower()


def _command_variants(command: str) -> tuple[str, ...]:
    """Every form of *command* a block/confirm rule should get to see.

    The full normalised line, each segment of a compound command, and each of
    those with a shell wrapper (`cmd /c`, `bash -c`, `sudo`, ...) peeled off.
    Used for BLOCK and CONFIRM only -- never to widen AUTO.
    """
    base = _normalise_command(command)
    seen = {base}
    for part in _split_unquoted(base):
        part = part.strip().strip('"').strip("'")
        if part:
            seen.add(part)
    changed = True
    while changed:
        changed = False
        for value in tuple(seen):
            for prefix in _WRAPPER_PREFIXES:
                if value.startswith(prefix + " "):
                    tail = value[len(prefix) + 1:].strip().strip('"').strip("'")
                    if tail and tail not in seen:
                        seen.add(tail)
                        changed = True
    return tuple(sorted(seen))


def _command_matches(variants, pattern) -> bool:
    """True when any variant of the command matches the (normalised) pattern."""
    pat = _normalise_command(pattern)
    return any(fnmatch.fnmatchcase(value, pat) for value in variants)


def _is_chained(command: str) -> bool:
    """True when the line joins several commands -- never auto-allow one of those."""
    lowered = _normalise_command(command)
    if len(_split_unquoted(lowered)) > 1:
        return True
    return _has_unquoted(lowered, _SUBSTITUTIONS)


class Decision(Enum):
    AUTO = "auto"
    CONFIRM = "confirm"
    BLOCK = "block"


class PolicyEngine:
    def __init__(self, cfg, audit_log=None):
        self.cfg = cfg
        # v3 Track B: when wired up, every decision also lands in the
        # hash-chained audit log with the rule that produced it. None keeps the
        # v1/v2 behaviour of logging to the python logger only.
        self.audit_log = audit_log
        self._identity_context: ContextVar[dict] = ContextVar(
            "harness_policy_identity", default={"agent_id": "legacy", "transport": "unknown", "client_id": ""}
        )

    def _agent_profile(self, agent_id: str | None = None) -> dict:
        identity = agent_id or self._identity_context.get().get("agent_id", "legacy")
        agents = getattr(self.cfg, "agents", None) or {}
        profiles = agents.get("profiles", agents) if isinstance(agents, dict) else {}
        profile = profiles.get(identity, {}) if isinstance(profiles, dict) else {}
        return profile if isinstance(profile, dict) else {}

    @contextmanager
    def bind_task(self, task):
        try:
            from agent_identity import authenticated_agent_id
        except ImportError:  # pragma: no cover - packaged imports
            from agent.agent_identity import authenticated_agent_id
        value = {
            "agent_id": authenticated_agent_id(task),
            "transport": getattr(task, "transport", "unknown"),
            "client_id": getattr(task, "client_id", ""),
        }
        token = self._identity_context.set(value)
        try:
            yield value
        finally:
            self._identity_context.reset(token)

    def authorize_kind(self, kind: str, agent_id: str | None = None) -> tuple[Decision, str]:
        profile = self._agent_profile(agent_id)
        allowed = profile.get("allowed_kinds")
        if not allowed:
            return Decision.AUTO, "no per-agent kind restriction"
        if any(fnmatch.fnmatchcase(kind, str(pattern)) for pattern in allowed):
            return Decision.AUTO, f"agent kind allowed: {kind}"
        return Decision.BLOCK, f"agent is not allowed to run kind: {kind}"

    # -----------------------------------------------------------------------
    def decide(
        self,
        command: str,
        target_paths: list[str] | None = None,
        *,
        agent_id: str | None = None,
    ) -> tuple[Decision, str]:
        """
        Returns (decision, reason).

        Order of evaluation:
        block commands → block paths → confirm commands → **confirm write paths**
        → auto commands → **auto read paths** → default confirm.

        The two path steps are v2 additions (docs/v2_spec.md §5). They are
        additive: a v1 read verb already matched an `auto_allow.commands`
        pattern before reaching the read-path step, and a v1 write verb already
        fell through to the default CONFIRM, so no v1 decision changes.
        """
        # Vault references are matched in their masked form: `{{secret:foo}}`
        # becomes `<vault:foo>`, so the `*secret*` / `*token*` / `*password*`
        # block patterns keep rejecting a credential pasted inline while a
        # reference to the encrypted vault passes. Using the vault is the
        # sanctioned way to pass a credential — see docs/security_v3.md §3.
        cmd = mask_text(command.strip())
        verb = cmd.split(maxsplit=1)[0].lower() if cmd else ""
        # Every form a BLOCK/CONFIRM rule is entitled to see: case-folded,
        # whitespace-collapsed, split on shell chaining, wrappers peeled off.
        # AUTO deliberately does NOT use these -- widening an allow list by
        # normalisation is how a gate stops meaning anything.
        variants = _command_variants(cmd)
        profile = self._agent_profile(agent_id)

        agent_block = profile.get("block") or {}
        for pat in agent_block.get("commands", []):
            if _command_matches(variants, pat):
                return Decision.BLOCK, f"agent blocked by pattern: {pat}"
        for path in target_paths or []:
            for pat in agent_block.get("paths", {}).get("absolute_no_touch", []):
                if _path_matches(path, pat):
                    return Decision.BLOCK, f"agent path blocked: {pat}"

        # 1. blocked?
        for pat in self.cfg.block.get("commands", []):
            if _command_matches(variants, pat):
                return Decision.BLOCK, f"blocked by pattern: {pat}"

        for path in target_paths or []:
            for pat in self.cfg.block.get("paths", {}).get("absolute_no_touch", []):
                # _path_matches, not fnmatchcase: `c:/windows/system32/x` is the
                # same file as `C:\Windows\System32\x` and used to walk
                # straight through the `C:\Windows\**` rule.
                if _path_matches(path, pat):
                    return Decision.BLOCK, f"path blocked: {pat}"

        agent_confirm = profile.get("require_confirm") or {}
        for pat in agent_confirm.get("commands", []):
            if _command_matches(variants, pat):
                return Decision.CONFIRM, f"agent requires confirmation: {pat}"

        agent_auto = profile.get("auto_allow") or {}
        if profile.get("override_global_confirm", False):
            for pat in agent_auto.get("commands", []):
                if not _is_chained(cmd) and _command_matches((_normalise_command(cmd),), pat):
                    roots = agent_auto.get("paths", {}).get("write", [])
                    if verb in WRITE_VERBS and target_paths and roots:
                        if not all(any(_path_matches(path, root) for root in roots) for path in target_paths):
                            return Decision.CONFIRM, "agent write target is outside autonomous roots"
                    return Decision.AUTO, f"agent auto-allowed: {pat}"

        # 2. requires confirm?
        for pat in self.cfg.require_confirm.get("commands", []):
            if _command_matches(variants, pat):
                return Decision.CONFIRM, f"requires confirmation: {pat}"

        # 3. write verb touching a confirm-gated path?
        if verb in WRITE_VERBS:
            for path in target_paths or []:
                for pat in self.cfg.require_confirm.get("paths", {}).get("write", []):
                    if _path_matches(path, pat):
                        return Decision.CONFIRM, f"write requires confirmation: {pat}"

        # 4. auto-allowed?
        # A chained line is not the command the allow list vetted: `ls && curl
        # ... | sh` starts with `ls`. Chained lines fall through to CONFIRM.
        chained = _is_chained(cmd)
        norm = _normalise_command(cmd)
        for pat in self.cfg.auto_allow.get("commands", []):
            if not chained and _command_matches((norm,), pat):
                return Decision.AUTO, f"auto-allowed: {pat}"

        for pat in agent_auto.get("commands", []):
            if not chained and _command_matches((norm,), pat):
                return Decision.AUTO, f"agent auto-allowed: {pat}"

        # 5. read verb, and every target path sits inside an allowed read root?
        read_roots = self.cfg.auto_allow.get("paths", {}).get("read", [])
        if verb in READ_VERBS and target_paths and read_roots:
            if all(any(_path_matches(p, pat) for pat in read_roots) for p in target_paths):
                return Decision.AUTO, "auto-allowed: read path"

        # default — safety first
        return Decision.CONFIRM, "no matching rule (defaulting to confirmation)"

    # -----------------------------------------------------------------------
    def audit(self, task_id: str, command: str, decision: Decision, reason: str):
        """Log a decision, and append it to the audit chain when one is wired up.

        ``command`` is masked before it goes anywhere: this is the exact line a
        human reads later, which makes it the last place a credential should
        appear.
        """
        safe = mask_text(command)
        identity = self._identity_context.get()
        log.info(
            f"task={task_id} agent={identity.get('agent_id')} transport={identity.get('transport')} "
            f"decision={decision.value} cmd={safe!r} reason={reason}"
        )
        if self.audit_log is None:
            return
        try:
            self.audit_log.record(
                actor=str(identity.get("agent_id") or task_id),
                action=f"policy_decision:{decision.value}",
                resource=safe,
                outcome="deny" if decision is Decision.BLOCK else "ok",
                meta={
                    "rule": reason,
                    "decision": decision.value,
                    "task_id": str(task_id),
                    "agent_id": identity.get("agent_id", "legacy"),
                    "transport": identity.get("transport", "unknown"),
                    "client_id": identity.get("client_id", ""),
                },
            )
        except Exception:  # pragma: no cover - auditing must not block a task
            log.exception("audit sink failed while recording a policy decision")
