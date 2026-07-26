# Learning note 01: Models propose; contracts decide

The language model never creates public citations. It selects a quote ID from a
per-request allowed set and proposes short claims. Local code resolves that ID
to an exact quote and trusted source metadata, then checks policy and structure.
This division makes failures inspectable and prevents a fluent draft from
silently becoming evidence.

The validator is intentionally modest: exact text membership is decidable;
semantic entailment is not. Human-reviewed cases therefore remain a separate
release gate.
