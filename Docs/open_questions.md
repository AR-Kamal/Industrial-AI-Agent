# Owner Decisions Required

Only decisions that materially block or change the zero-cost prototype are listed here.

## OQ-001 — What is the single pilot subject?

Name the one machine, training system, or tightly bounded manufacturing topic for Plan A. This determines the accepted sources, domain vocabulary, test set, and what counts as out of scope.

Required before: document preparation and domain acceptance-test authoring.

My answer: we will focus on a sprcific machine, such as robotic arm Fanuc, and Rexroth mMS4.0, etc... not general topic.

## OQ-002 — What may an ordinary chat document upload do?

Choose the approved behavior:

1. analyze a document only within the current conversation, without adding it to the knowledge base; or
2. submit it as a candidate that remains unavailable to retrieval until explicitly reviewed and approved.

Direct automatic ingestion into the approved knowledge base is not recommended. Until decided, chat uploads shall be temporary and shall not enter the index.

Required before: implementing general document upload and retention behavior.

My answer: 1 looks ok

## OQ-003 — Is working local vision a mandatory Plan A acceptance gate?

The draft requires image/screenshot support but also permits local vision to be deferred when the existing computer cannot run a suitable model. Decide whether:

- image upload, validation, and explicit “vision unavailable” behavior are sufficient for Plan A when hardware is inadequate; or
- Plan A cannot pass until actual local vision cases pass.

This decision should follow a hardware inventory and one time-boxed Ollama vision-model feasibility test; it does not authorize paid APIs or hardware purchases.

Required before: finalizing Plan A go/no-go criteria.

My answer: this looks fine (image upload, validation, and explicit “vision unavailable” behavior are sufficient for Plan A when hardware is inadequate;)

## OQ-004 — Who is the qualified technical reviewer?

Identify the person or role authorized to validate safety-sensitive expected answers and review failures. If none is available, confirm that the prototype remains a training demonstration and is not approved for operational troubleshooting.

Required before: safety test-set approval and any operational-use claim.

My answer: for now, it will be used with our organization only, so, the prototype remains a training demonstration.
