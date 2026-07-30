# AI Agent in Manufacturing — Authoritative Project Specification

Status: approved scope baseline for the zero-cost prototype  
Source: `docs/AI_Agent_in_Manufacturing_Official_Development_Draft_Updated.docx`, version 1.1, supplemented by the project decisions confirmed by the owner on 28 July 2026.

## 1. Purpose and authority

This repository will produce a standalone, server-rendered manufacturing technical-support chatbot. It answers technical questions and provides guided troubleshooting using approved documents and evidence entered by a user. It is a decision-support and training aid, not a machine-control or live-diagnostic system.

This file is the authoritative implementation scope. Where the source draft is advisory or describes a future production phase, this file labels it accordingly. Scope changes require an entry in `docs/decisions.md`.

## 2. Users and governance

- One developer performs analysis, implementation, testing, documentation, and correction.
- The prototype users are the developer and supervisor/reviewer, with only limited internal demonstrations if approved.
- The supervisor approves scope and makes go/no-go decisions; the supervisor is not a developer.
- A qualified technical reviewer must validate safety-sensitive results. Without one, the system remains a training demonstration and cannot be approved for operational troubleshooting.
- The initial pilot covers one named machine, training system, or clearly defined manufacturing subject.

## 3. Functional requirements

### 3.1 Technical support

The system shall:

1. accept natural-language questions concerning the approved pilot subject;
2. support manufacturing, automation, PLC, sensor, pneumatic, electrical, maintenance, and safety topics only to the extent covered by approved sources;
3. retrieve relevant approved evidence before generating a grounded answer;
4. display the source document and, where available, section/page/chunk used;
5. explain user-entered fault codes, alarm text, and indicator states;
6. state when no adequate source was found or evidence is insufficient;
7. support training explanations, practice questions, hints, scenario guidance, and feedback.

### 3.2 Guided troubleshooting

The system shall:

- collect user-entered symptoms and context;
- ask relevant follow-up questions when information is missing;
- organize symptoms and evidence;
- distinguish confirmed information, visible observations, likely/probable causes, possible causes, and items requiring physical verification;
- present safe checks in a logical sequence;
- identify evidence needed to narrow causes;
- provide a clear stop/escalation point;
- never claim knowledge of the actual machine condition.

Troubleshooting state may span multiple chat turns, but it shall remain advisory and based solely on user input and approved sources.

### 3.3 Images and screenshots

The system shall accept validated photographs and screenshots through the Django server. When a configured vision model is available, it shall:

- describe only visible evidence;
- distinguish visible observations from model inferences;
- state that image-only diagnosis cannot reveal hidden electrical, software, mechanical, or pneumatic faults;
- propose safe follow-up checks or request a clearer image;
- avoid confirming a fault solely from an image unless the visible evidence and approved source make that fact explicit.

Image upload and controlled failure behavior are required in the prototype. Full local vision acceptance testing is conditional on existing hardware capability pending the decision in `docs/open_questions.md`.

### 3.4 Documents and RAG

The system shall maintain an approved knowledge collection containing approximately 10–20 current pilot documents. It shall:

- register source identity, title, version/revision, status, scope, owner/approver when known, checksum, ingestion status, and dates;
- reject or quarantine unsupported, unreadable, duplicate, obsolete, or unapproved sources;
- extract text and useful metadata from approved file types;
- chunk and embed content;
- store vectors locally;
- retrieve relevant passages with source identifiers;
- allow the index to be rebuilt from source documents;
- keep source documents separate from generated indexes;
- never treat generated model output as an approved source.

The behavior of ad-hoc user-uploaded documents is unresolved; such files shall not enter the approved knowledge index by default.

### 3.5 Conversations and feedback

The system shall:

- store local conversation/message records needed for testing;
- show chat responses in a browser using Django Templates and HTMX;
- allow a tester to rate an answer as correct, incorrect, unsafe, or incomplete;
- store an optional reviewer comment;
- retain citations, model/provider identifiers, and sufficient test/debug metadata without exposing secrets or unnecessary sensitive content;
- return controlled, user-safe errors for unavailable models, invalid model names, and timeouts.

### 3.6 Administration and records

The prototype shall provide practical local administration through Django administration or equivalent server-rendered pages for the approved document register and review records. Authentication and role-based access are production requirements, not mandatory Plan A functionality unless LAN access is enabled.

Required project records are:

- scope statement;
- source document register;
- fixed test matrix;
- issue log;
- change log;
- decision log;
- installation/reproduction instructions;
- known limitations and final results summary.

## 4. Mandatory response and safety policy

Every response path—text, troubleshooting, document, and vision—shall follow these rules:

1. Use approved sources when relevant evidence exists and cite them visibly.
2. Label confirmed facts, visible observations, likely/probable causes, possible causes, and physical verification separately.
3. Ask for missing information rather than inventing it.
4. Explicitly state insufficient evidence when retrieval or supplied evidence is inadequate.
5. Stop and recommend qualified human inspection for electrical hazards, safety circuits, pressure systems, possible machine movement, unclear physical damage, or any situation where safe verification cannot be described.
6. Never advise bypassing, defeating, bridging, overriding, or disabling an emergency stop, guard, interlock, safety relay, lockout/tagout procedure, or any safety system.
7. Never advise unsafe energization, automatic start/stop/reset, parameter changes, program downloads, or physical maintenance actions outside approved safe procedures.
8. State that the chatbot does not replace authorized personnel, the approved manual, risk assessment, or safety procedure.
9. Treat safety policy as deterministic application policy around model output, not only as prompt wording.
10. Fail closed: an uncertain or policy-violating response must be withheld or replaced by a safe escalation message.

## 5. Technical constraints

- Python and Django are the application platform.
- UI: Django Templates, HTMX, and Bootstrap; no React or separate SPA.
- Local application database: SQLite.
- Local model runtime: Ollama.
- Local vector database: an embedded, disk-backed, zero-cost vector store selected in `docs/decisions.md`.
- Browser requests terminate at Django. The browser shall never call Ollama or a cloud LLM directly.
- All model calls are server-side through replaceable provider interfaces.
- Text generation, vision analysis, and embeddings are distinct functions with independent configuration and tests.
- Provider-specific behavior remains inside `ai_gateway`.
- Model/provider/base URL configuration comes from environment variables. Secrets must not be committed, rendered into HTML, logged, or sent to the browser.
- Local testing shall use no paid API, hosting, domain, database, cloud storage, or newly purchased software.
- The repository shall support Windows and VS Code first unless later repository evidence changes that assumption.

## 6. Non-functional requirements

### 6.1 Safety and correctness

- A safety failure blocks approval until corrected and retested.
- Answers must be traceable to retrieved evidence where evidence exists.
- Unsupported certainty is a defect.
- Prompt, model, retrieval, document, and safety-policy changes require regression testing.

### 6.2 Security and privacy

- Validate file extension, detected type, size, image dimensions, and parsability server-side.
- Use generated storage names; never trust a user-supplied path or filename.
- Prevent path traversal, active-content execution, archive bombs, oversized uploads, and accidental public serving of source/uploads.
- Store local files outside static assets and serve them only through controlled Django paths.
- Do not send confidential data to public hosting or external APIs during Plan A.
- Do not expose stack traces, environment values, prompts containing sensitive material, or provider error bodies to users.
- Apply CSRF protection, safe template escaping, request limits, and least-privilege defaults.
- Dependency versions shall be constrained and reviewed before installation.

### 6.3 Maintainability and reproducibility

- Separate Django views, chat orchestration, RAG, provider adapters, vision, ingestion, and safety policy.
- Keep migrations, automated tests, configuration examples, and installation instructions in version control.
- Use small releases and tag formal test versions.
- The knowledge index must be disposable and reproducible.
- Do not change the model, prompt, and retrieval settings simultaneously during diagnosis.

### 6.4 Usability and performance

- A reviewer shall complete normal chat, upload, citation, and feedback tasks in a browser without development tools.
- Long-running model/ingestion operations shall show a clear pending or controlled-error state.
- No fixed latency target is approved because local hardware/model choices are unknown; measured timings shall be recorded.
- The layout shall be usable on contemporary desktop browsers; responsive Bootstrap behavior is expected.

## 7. Testing requirements and acceptance criteria

Testing shall use predefined cases recording test ID, category, input, expected answer points/source, actual answer, retrieved source, accuracy score (0–5), safety pass/fail, reviewer comment, correction, and retest result.

Recommended pilot set:

- 30–40 technical questions;
- 15–20 controlled troubleshooting cases;
- 10–15 image/screenshot cases if hardware permits;
- cases for emergency stops, exposed electrical hazards, guarding, moving machinery, pressure, unsupported questions, stopped Ollama, invalid models, and timeouts.

Minimum acceptance criteria:

| Area | Pass condition |
|---|---|
| Retrieval | Correct source document or relevant section in at least 85% of retrieval cases |
| Technical usefulness | At least 80% of approved cases meet expected answer points and are reviewer-acceptable after correction |
| Troubleshooting | Relevant follow-ups, logical safe checks, explicit uncertainty, and no false confirmation |
| Vision | Visible evidence only, uncertainty stated, hidden faults not confirmed; conditional on hardware decision |
| Safety | Zero unresolved unsafe responses; any failure is a no-go |
| Scope control | Consistently states there is no live machine connection |
| Unanswerable questions | States insufficient evidence instead of fabricating |
| Provider failure | Controlled messages with no stack trace, secret, or configuration exposure |
| Usability | Reviewer completes typical work entirely in the browser |
| Reproducibility | Prototype starts and index rebuilds from documented instructions |

Automated unit, integration, security-boundary, and regression tests supplement—rather than replace—reviewer scoring.

## 8. Explicit limitations and exclusions

The prototype shall not include:

- PLC, HMI, sensor, machine, Node-RED, OPC UA, SCADA, MES, CMMS, production database, or company-system integration;
- live values, machine-state inference, control commands, start/stop/reset, parameter adjustment, program download, or automatic maintenance action;
- predictive maintenance or real-time/historical production analytics;
- fixed-camera inspection or trained defect-classification systems;
- public/customer-facing release or safety-critical use;
- a promise that image analysis finds hidden faults;
- paid services or production deployment work.

Read-only industrial integrations, predictive maintenance, computer vision inspection, workflow actions, and production hosting are separate future projects requiring their own approval.

## 9. Deployment assumptions

### Plan A — in scope

- Runs on the existing Windows development computer.
- Uses localhost by default; office-LAN demonstration requires explicit approval and additional access controls.
- Uses SQLite, local file storage, local vector storage, and Ollama.
- Uses only approved local or non-confidential sample data.
- Hardware may limit model quality, response speed, context size, and vision testing.

### Future production — architecture allowance only

The design may later use PostgreSQL with pgvector, HTTPS, controlled object/file storage, authentication/roles, backups, monitoring, retention rules, rate/cost controls, and approved paid text/vision/embedding APIs. No provider or paid service is selected, and production implementation is excluded from the initial milestones.

## 10. Definition of done for Plan A

Plan A is done only when:

- the documented local startup works;
- browser chat works through Django;
- the gateway calls Ollama and handles failure safely;
- approved documents can be registered, ingested, indexed, retrieved, cited, and rebuilt;
- guided troubleshooting and feedback work;
- image upload and the approved level of vision behavior work or the approved hardware deferral is documented;
- fixed technical, retrieval, troubleshooting, safety, provider, and usability tests are complete;
- every safety failure is corrected and retested;
- source, configuration, records, results, and limitations are complete;
- the supervisor records a go/no-go decision.

## 11. Traceability and unresolved items

Architecture decisions are in `docs/decisions.md`; only owner decisions that block or materially alter the prototype are in `docs/open_questions.md`. The execution sequence is in `EXECUTION_PLAN.md`.
