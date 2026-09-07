# Harness Engineering — Module 5
# Topic: Sandboxing and Isolation

---

## 1. Intuition

A permission check asks *"may you do this?"* A sandbox makes the question moot:
the agent physically cannot reach what is outside it.

Checks are policy. Sandboxes are physics. You want both, because a check has a
bug surface and a sandbox does not care how clever the attempt was.

---

## 2. Core Concept

### Four levels, cheapest first

| Level | Isolates | Cost | Escapes |
|---|---|---|---|
| **Path allow-list** | Filesystem | Free | Symlinks, `..`, absolute paths |
| **Subprocess + user** | Process, files | Low | Kernel bugs, shared network |
| **Container** | Filesystem, network, process | Medium | Kernel bugs, misconfiguration |
| **VM / microVM** | Nearly everything | High | Very few |

Match the level to what the agent can reach. An agent that only reads your docs
needs a path allow-list. An agent that runs model-written code needs a container
at minimum.

### The rule that matters

> **Never run model-generated code in your application process.**

Not "validate it first". Not "check for dangerous imports". A denylist of
dangerous constructs has never held, because the space of dangerous programs is
not enumerable.

### Path containment done properly

The naive version is wrong in three ways:

```python
# WRONG -- all three of these escape it.
def is_allowed(path: str) -> bool:
    return path.startswith("/workspace")
```

`"/workspace/../etc/passwd"` normalises out. A symlink inside `/workspace`
pointing at `/etc` follows out. `"/workspace-secrets"` passes the prefix test.

```python
from pathlib import Path

def resolve_inside(root: Path, candidate: str) -> Path:
    """Resolve fully, then prove the result is inside root."""
    root = root.resolve()
    target = (root / candidate).resolve()      # resolves .. AND symlinks
    if not target.is_relative_to(root):        # 3.9: str(target).startswith(str(root) + os.sep)
        raise PermissionError(
            f"Path escapes the workspace: {candidate!r} resolves outside {root}."
        )
    return target
```

Resolve first, compare after. Anything else is a bypass waiting to be found.

---

## 3. Minimal Implementation

A subprocess sandbox with the limits that actually bite:

```python
import resource
import subprocess
from pathlib import Path


def run_sandboxed(code: str, workspace: Path, timeout_s: int = 10) -> str:
    """Run untrusted code with hard limits. Never in-process."""

    def apply_limits() -> None:                 # runs in the child, pre-exec
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)   # memory
        resource.setrlimit(resource.RLIMIT_CPU, (timeout_s, timeout_s))    # cpu
        resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))                # fork bombs
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024,) * 2) # disk

    try:
        done = subprocess.run(
            ["python", "-I", "-c", code],       # -I: no site, no env, no cwd on path
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            preexec_fn=apply_limits,
            env={"PATH": "/usr/bin:/bin", "HOME": str(workspace)},  # nothing inherited
        )
    except subprocess.TimeoutExpired:
        return f"Error: execution exceeded {timeout_s}s and was terminated."

    output = (done.stdout + done.stderr)[:10_000]
    return output or "(no output)"
```

Four limits, each stopping a specific real failure: memory exhaustion, CPU
spinning, fork bombs, and filling the disk. The empty `env` matters as much as
the limits — an inherited `AWS_SECRET_ACCESS_KEY` defeats every other control.

---

## 4. Network Isolation

The most-forgotten boundary. An agent that can reach the network can exfiltrate
anything it has seen, and injection turns that into an attack.

- **Default deny.** Allow-list the few hosts a tool genuinely needs.
- **Block link-local `169.254.169.254`** — cloud instance metadata, which holds
  credentials. This is a standard target.
- **No DNS to arbitrary hosts.** Data leaves over DNS as easily as HTTP.

Container-level network policy is the practical place for this, not application
code.

---

## 5. Trade-offs

**Isolation vs. capability.** A tightly sandboxed agent cannot install a package
or call an API. Sometimes that is the point; sometimes it makes the agent
useless. Decide per tool, not globally.

**Startup cost.** A container per tool call adds hundreds of milliseconds. Reuse
a warm sandbox per *run*, and destroy it at the end — per-call is too slow, and
per-user leaks state between runs.

**Complexity.** A sandbox you configure wrongly is worse than none, because you
trust it. Test the escapes: write a test that tries `../../etc/passwd` and
asserts it fails.

---

## 6. Production Notes

- **Test your sandbox with real escape attempts.** Path traversal, symlink,
  absolute path, fork bomb, metadata endpoint. Each one a test.
- **Destroy the sandbox after each run.** State that persists between runs is a
  cross-user leak.
- **Log what the sandbox refused.** Refusals are either attacks or a UX problem.
- **Never mount your source tree read-write** into an agent sandbox.
- Put secrets in the *tool implementation*, outside the sandbox, so the sandboxed
  code can call a capability without ever seeing a credential.

---

## 7. What To Say Out Loud

> "Permission checks are policy; sandboxes are physics, and I want both because
> a check has a bug surface and a sandbox does not care how clever the attempt
> was. The rule I never break is that model-generated code does not run in my
> application process — validating it first does not work, because the space of
> dangerous programs is not enumerable. For filesystem containment I resolve the
> path fully, including symlinks, and then prove the result is inside the root;
> prefix matching is bypassable three different ways. And I isolate the network,
> because an agent that can reach out can exfiltrate anything it has seen —
> blocking the cloud metadata endpoint in particular."

---

## 8. Check Yourself

1. Why is `path.startswith("/workspace")` insufficient? Name two bypasses.
2. Why resolve before comparing rather than after?
3. What does an empty `env` protect against that resource limits do not?
4. Why block `169.254.169.254` specifically?

→ Next: [`prompt-injection-through-tools.md`](prompt-injection-through-tools.md)
