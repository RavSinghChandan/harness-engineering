# Harness Engineering — Module 4
# Topic: Retrieval in the Loop

---

## 1. Intuition

Classic RAG retrieves once, at the start, and hopes the query was good enough.
An agent does not have to guess. It can search, read the results, realise it
asked the wrong question, and search again.

That changes the engineering problem. In classic RAG you tune the retriever. In
an agent you design the *retrieval tool* — and the biggest risk moves from
"missed the right chunk" to "filled the context window with near-duplicates".

---

## 2. Core Concept

### Retrieval as a tool, not a pre-step

```python
def search_docs(query: str, limit: int = 5) -> str:
    """Search the documentation. Returns titles and snippets.

    Use `read_doc` to get the full text of a result you need.
    Prefer several specific searches over one broad one.
    """
```

Two design decisions are doing the work here.

**Search returns snippets, not documents.** Titles plus two lines each. Five
results cost maybe 300 tokens instead of 20,000. The model decides what is worth
reading in full.

**Reading is a second tool.** `read_doc(doc_id)` fetches one document. The
agent pays for full text only when it has decided the document matters.

This two-step shape — cheap survey, expensive fetch — is the single most useful
pattern in agentic retrieval, and it applies far beyond documents: file listing
then file read, database schema then query, directory tree then source file.

### The duplicate problem

An agent that searches five times gets overlapping results, and the same chunk
lands in context three times. It wastes tokens, and repetition also biases the
model toward whatever got repeated.

Deduplicate inside the tool, across the whole session:

```python
class SessionRetriever:
    def __init__(self, index):
        self.index = index
        self.seen: set[str] = set()          # doc ids returned this session

    def search(self, query: str, limit: int = 5) -> str:
        hits = self.index.search(query, limit=limit * 3)
        fresh = [h for h in hits if h.doc_id not in self.seen][:limit]

        if not fresh:
            return ("No new results. Everything matching this query has already "
                    "been returned. Try a different query, or work with what you have.")

        for h in fresh:
            self.seen.add(h.doc_id)
        return "\n".join(f"[{h.doc_id}] {h.title}\n  {h.snippet}" for h in fresh)
```

The "no new results" message matters as much as the dedup. Without it the agent
keeps searching, gets the same thing back, and cannot tell it is stuck.

### Grounding the answer

An agent that retrieves should cite. Not for politeness — so the claim is
checkable:

```python
def read_doc(doc_id: str) -> str:
    """Read one document in full. Cite it as [doc_id] in your answer."""
    doc = index.get(doc_id)
    if doc is None:
        return f"Error: no document {doc_id!r}. Use search_docs to find valid ids."
    return f"[{doc_id}] {doc.title}\n\n{doc.text}"
```

Putting the id in the returned text — not only in the schema description — makes
citation the path of least resistance. The model copies what is in front of it.

---

## 3. When Retrieval Should Not Be a Tool

Retrieval-as-a-tool costs a turn. If the answer is *always* in one known place,
just put it in the prompt:

| Situation | Approach |
|---|---|
| Small, always-relevant corpus | Put it in the system prompt |
| Large corpus, one clear query | Classic RAG, retrieve once up front |
| Large corpus, query unclear until you look | Retrieval as a tool |
| Multi-hop ("find X, then find Y about X") | Retrieval as a tool — the only option |

The tool form earns its extra turns when the *second* query depends on the first
result. That is exactly what classic RAG cannot do.

---

## 4. Trade-offs

**Agentic retrieval is slower and dearer.** Three searches and two reads is five
model calls. For a simple lookup that is waste.

**The model may stop too early.** It finds something plausible and answers.
Countermeasure: say in the tool description that important claims should be
confirmed from more than one document.

**The model may search forever.** Countermeasure: a per-run retrieval budget,
enforced by the harness, not requested in a prompt:

```python
if self.searches_done >= self.max_searches:
    return "Search budget exhausted. Answer with what you have, or say what is missing."
```

Note the phrasing: it tells the model what to do next. "Error: limit reached"
would leave it guessing.

---

## 5. Production Notes

- **Cap retrieved tokens per run**, not just per call. Ten searches at 300
  tokens is fine; ten full documents is not.
- **Deduplicate across the session** and say so when nothing is new.
- **Return ids in the text**, so citation is the easy path.
- **Log every query and which results were then read.** Queries that retrieve
  and are never read tell you the snippets are unhelpful.
- **Watch the ratio of searches to reads.** Many searches, few reads means the
  index is not answering the questions being asked.

---

## 6. What To Say Out Loud

> "In an agent, retrieval is a tool rather than a pre-step, which lets the second
> query depend on the first result — the multi-hop case classic RAG cannot do.
> I split it in two: search returns titles and snippets so a survey costs a few
> hundred tokens, and a separate read tool fetches full text only for documents
> the model has decided matter. Results are deduplicated across the whole
> session, and when nothing new comes back the tool says so explicitly, because
> otherwise the agent keeps re-searching without realising it is stuck. There is
> a retrieval budget enforced in code, and when it trips the message tells the
> model to answer with what it has."

---

## 7. Check Yourself

1. Why split search and read into two tools?
2. Why does deduplication need to be session-wide?
3. When is classic single-shot RAG the better choice?
4. Why should a budget message say what to do next?

→ Next: [`prompt-caching-economics.md`](prompt-caching-economics.md)
