# Learning note 04: Routing protects; planning resolves

Routing and planning answer different questions.

The deterministic router asks, “May this request enter the paid RAG path?” It
handles current conditions and personalized safety or medical decisions first.
Those rules are intentionally conservative because a planner trained to be
helpful must not grant itself permission to answer a high-risk request.

The planner asks, “How is this allowed request related to the collection?” It
can classify the request as likely grounded, adjacent background, or tangent
and can turn a contextual follow-up into one to three standalone search
queries. It cannot answer or cite.

```text
question + six-turn context
  -> deterministic safety boundary
  -> local capability response, when applicable
  -> structured relation and retrieval-query plan
```

This ordering also saves money: greetings and safety exits make no provider
calls. A malformed planner response fails explicitly instead of silently
searching the raw question, so the trace describes what actually happened.
