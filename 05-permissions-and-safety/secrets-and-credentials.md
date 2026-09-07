# Harness Engineering — Module 5
# Topic: Secrets and Credentials

---

## 1. Intuition

The strongest guarantee in this whole module is also the simplest:

> **A model cannot leak what it has never seen.**

Every prompt-injection defence is probabilistic. Keeping the credential out of
context is not. If the API key lives inside the tool implementation and never
enters a message, no injection, however clever, can extract it.

---

## 2. Core Concept

### The rule

Secrets live in the **tool**, never in the **context**.

```python
# WRONG -- the key is now in the transcript, the logs, and any future summary.
system = f"Use this API key when calling the service: {API_KEY}"

# RIGHT -- the model asks for a capability; the tool holds the credential.
def send_email(to: str, subject: str, body: str) -> str:
    """The model never sees SMTP_PASSWORD. It cannot leak it."""
    client = smtp_client(password=os.environ["SMTP_PASSWORD"])
    client.send(to=to, subject=subject, body=body)
    return f"Email sent to {to}."
```

The model's interface is `send_email(to, subject, body)`. The credential is an
implementation detail on the other side of that boundary.

### Where secrets leak from

| Leak path | Fix |
|---|---|
| System prompt | Never interpolate. Use tools. |
| Tool *results* | Redact before returning to the model |
| Error messages | Never include the request that failed verbatim |
| Traces and logs | Redact at the tracer (Module 6) |
| Compaction summaries | If it was in context, it may survive into the summary |
| Environment dumps | Never give the agent a `read_env` tool |

Row two catches people. A tool that returns a raw HTTP response can hand back an
`Authorization` header the model then repeats.

```python
def call_api(endpoint: str) -> str:
    response = requests.get(endpoint, headers={"Authorization": f"Bearer {TOKEN}"})
    return redact(response.text)          # the response may echo the header
```

### Scope and lifetime

Beyond hiding the secret, reduce what it can do:

- **Per-tool credentials.** The email tool holds SMTP; it does not hold your
  database password.
- **Short-lived tokens.** A 15-minute token limits the damage of any leak.
- **Least privilege.** A read-only database user for a read-only tool.
- **Per-user delegation.** The agent acts as *the user*, so it can only reach
  what that user could. This is the strongest pattern available and it makes
  most authority questions answer themselves.

---

## 3. Minimal Implementation

```python
import os
import re
from dataclasses import dataclass, field

_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),             # API keys
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"),       # bearer tokens
    re.compile(r"eyJ[A-Za-z0-9._\-]{20,}"),         # JWTs
    re.compile(r"(?i)(password|secret|api[_-]?key)\s*[=:]\s*\S+"),
]


def redact(text: str, extra: tuple[str, ...] = ()) -> str:
    """Redact anything that looks like a credential, plus known literals."""
    for value in extra:                     # exact values we know we hold
        if value and len(value) > 6:
            text = text.replace(value, "[REDACTED]")
    for pattern in _PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


@dataclass
class SecretStore:
    """Credentials never cross into model-visible code."""

    _values: dict[str, str] = field(default_factory=dict)

    def load(self, *names: str) -> None:
        for name in names:
            value = os.environ.get(name)
            if value:
                self._values[name] = value

    def use(self, name: str) -> str:
        """Only tool implementations call this. Never a prompt builder."""
        try:
            return self._values[name]
        except KeyError:
            raise RuntimeError(f"Secret {name!r} is not configured.") from None

    def scrub(self, text: str) -> str:
        """Belt and braces: strip any known literal before it reaches a model."""
        return redact(text, extra=tuple(self._values.values()))
```

`scrub` is the important one. Even if a tool accidentally returns a credential,
it is removed on the way out — you are not relying on every tool author
remembering.

---

## 4. Trade-offs

**Redaction is lossy.** A redacted error message is harder for the model — and
you — to act on. Redact aggressively on the model-facing path; keep the full
text in a secure log for humans.

**Pattern matching misses things.** Regexes catch common shapes, not your
internal token format. Add your own patterns, and rely primarily on *never
putting the secret in context* rather than on catching it later.

**Per-user delegation is work.** Threading user identity through every tool is
real effort, and it is the single best answer to "what is this agent allowed to
see?"

---

## 5. Production Notes

- **Assert in tests that no secret appears in a transcript.** Run a real task
  and grep the messages. This catches a whole class of regression.
- **Rotate anything that ever entered a prompt.** Treat it as compromised, even
  if you deleted the log — summaries and caches persist.
- **Never give the agent a shell tool with your env inherited.** One `env` call
  and everything is in context.
- **Redact at the boundary**, not at the sink. Sinks get misconfigured.
- **Short TTLs everywhere.** A leaked 15-minute token is an inconvenience; a
  leaked permanent key is an incident.

---

## 6. What To Say Out Loud

> "The strongest control I have is that a model cannot leak what it has never
> seen, so credentials live in the tool implementation and never enter context.
> The model's interface is send_email(to, subject, body); the SMTP password is
> on the other side of that boundary. Every injection defence is probabilistic,
> but this one is structural. Then I redact on the way out too, in case a tool
> returns a response that echoes a header, and I scrub known literal values
> rather than trusting patterns. And where I can, the agent acts as the user,
> so it can only reach what that user could — which makes most authority
> questions answer themselves."

---

## 7. Check Yourself

1. Why is keeping a secret out of context stronger than any injection defence?
2. Where can a secret leak from even if it was never in the system prompt?
3. Why rotate a key that merely appeared in a prompt once?
4. What does per-user delegation buy you beyond secret hygiene?

→ Next: [`human-in-the-loop.md`](human-in-the-loop.md)
