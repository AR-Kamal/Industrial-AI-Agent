# FANUC retrieval evaluation — human-review worksheet

Status: 20 cases are human-approved and `FANUC-R002` remains `pending_review`.
This worksheet does not establish a production relevance threshold.

Flags use `S` for safety-critical, `E` for exact identifier, `N` for numeric
or standards, and `U` for expected unsupported/abstention.

| Case | Question | Proposed chapter | Proposed section | Proposed acceptable chunks | Flags | Unambiguous? | Review concern |
|---|---|---|---|---|---|---|---|
| FANUC-R001 | Who is allowed to work inside the safety fence? | 1 FANUC ROBOT SYSTEM | 1.3 WORKING PERSON — PERSONNEL ROLES AND INSIDE-FENCE AUTHORIZATION | `CHK-C-ff5058e949ac92f8922d1c88eb3cc6` | S | Yes | Confirm role wording and whether the Chapter 3 entry-procedure chunk should also be acceptable. |
| FANUC-R002 | What is SRVO-199? | — | — | — | E | No | `SRVO-199` is not literal in the 101 eligible chunks. Do not approve unless support and an exact locator are independently confirmed; otherwise reclassify/remove. |
| FANUC-R003 | What does T1 mode do? | 3 SAFETY DEVICES | 3.3.1 OPERATING MODES — T1 MODE | `CHK-C-9ecb3abbd9b3770550a9840e9c8b54` | S, E | Yes | Verify that the complete T1 definition is sufficient. |
| FANUC-R004 | What maximum speed applies in T1 mode? | 3 SAFETY DEVICES | 3.3.1 OPERATING MODES — T1 MODE | `CHK-C-9ecb3abbd9b3770550a9840e9c8b54` | S, E, N | Yes | Verify the stored `250mm/sec` wording and desired normalized display. |
| FANUC-R005 | What training is required before operating or maintaining the robot? | 1 FANUC ROBOT SYSTEM | 1.3.1 ROBOT TRAINING — REQUIRED TRAINING CONTENT | `CHK-C-dadb210942c7a5b841e519d61b7e50`, `CHK-R-dc0bd8a616b4bf71705f8eb93f535f` | S | Partly | Two complementary passages exist; reviewer must decide whether either alone is acceptable. |
| FANUC-R006 | What sequence is required before entering the safety fence? | 3 SAFETY DEVICES | 3.7 THE SAFETY SEQUENCE FOR FENCE ENTRY — AUTHORIZED PERSONNEL AND PROCEDURE | `CHK-C-61aeb1853c8b567ae132c1f06e852f` | S | Yes | Safety reviewer must verify the numbered procedure and whether adjacent continuation chunks are needed. |
| FANUC-R007 | Which emergency stop devices does the robot have? | 3 SAFETY DEVICES | 3.2 EMERGENCY STOP — DEVICES AND EXTERNAL INPUT | `CHK-C-f8d0222ed2fec9a24da5452c67a47d` | S | Yes | Confirm the question is limited to devices described by this handbook. |
| FANUC-R008 | What happens when the deadman switch is released or hard-gripped? | 3 SAFETY DEVICES | 3.4 DEADMAN SWITCH — ENABLING FUNCTION AND OPERATION LIMIT | `CHK-C-c4d73f4ab53fc28cb5a6a5c7cdefc1` | S | Yes | Confirm terminology and immediate-stop wording. |
| FANUC-R009 | What does T2 mode do? | 3 SAFETY DEVICES | 3.3.1 OPERATING MODES — T2 MODE | `CHK-C-d765da8ae3fe69591e950fc8322c26` | S, E | Yes | Verify optional-mode qualification and controller-manual limitation. |
| FANUC-R010 | When is automatic operation permitted? | 4 GENERAL CAUTIONS | 4.7 AUTOMATIC OPERATION — PRECONDITIONS | `CHK-C-81b12bc95d59ec0061f153086e62cc` | S | Yes | Confirm whether the adjacent personnel-clearance warning should also be acceptable. |
| FANUC-R011 | What is the difference between Power-Off Stop and Controlled Stop? | 3 SAFETY DEVICES | 3.1 STOP TYPE OF ROBOT — CONTROLLED-STOP DIFFERENCES AND LIMITATIONS | `CHK-C-b439d949bf60b44ca8b8b0fd2d3bc2`, `CHK-C-9322004230507e9f17e96fce694656` | S, E | Partly | Definitions and comparison are split; reviewer must confirm acceptable alternatives and required rank. |
| FANUC-R012 | What controls are required when troubleshooting inside the safeguarded space? | 4 GENERAL CAUTIONS | 4.5 TROUBLE SHOOTING — INSIDE-SPACE AUTHORIZATION AND CONTROLS | `CHK-C-540cb876cfd0989ee53d4269a641d1` | S | Yes | Confirm this case should remain limited to inside-space troubleshooting. |
| FANUC-R013 | Where should robot maintenance be performed when possible? | 4 GENERAL CAUTIONS | 4.8 MAINTENANCE — PROGRAM, TRAINING AND OUTSIDE-SPACE WORK | `CHK-C-c444bdcddee4bee9261b912d02f20b` | S | Yes | Confirm the predetermined arm-position qualification is represented adequately. |
| FANUC-R014 | Which safety devices and conditions are included in the daily checks? | 5 DAILY MAINTENANCE | 5.1 MECHANICAL UNIT — DAILY CHECK ITEMS | `CHK-C-be810d2ed68fc0279532a83d0c9e89` | S | Yes | Verify scope against the model-specific manuals referenced by the handbook. |
| FANUC-R015 | Which robot safety standard is listed for CE marking? | 1 FANUC ROBOT SYSTEM | 1.4 RELEVANT STANDARDS — APPLICABLE STANDARDS | `CHK-C-6b451b198b94cd69d3dddb919b8b5d` | E, N | Yes | Confirm whether the expected wording is specifically `EN ISO 10218-1` rather than the broader ISO 10218 family. |
| FANUC-R016 | Which emergency stop devices must remain functional during programming? | 4 GENERAL CAUTIONS | 4.3.2 DURING PROGRAMMING — OTHER EQUIPMENT AND EMERGENCY STOPS | `CHK-C-e276b97dfa4199658103326ea45f74` | S | Yes | Human-reviewed wording narrowed to the exact supported fact; the locator states that all robot system emergency stop devices must remain functional. |
| FANUC-R017 | What must be done before maintenance inside the safeguarded space? | 4 GENERAL CAUTIONS | 4.8 MAINTENANCE — SAFEGUARDED-SPACE ENTRY PROCEDURE | `CHK-C-38281a7b04dfed06e292f682f27ca2` | S | Yes | Safety reviewer must verify procedure completeness and relation to Section 3.7. |
| FANUC-N001 | What is the weather forecast for tomorrow? | — | — | — | U | Yes | Confirm as an approved negative only; no source locator should be added. |
| FANUC-N002 | What is the current price of gold? | — | — | — | U | Yes | Confirm as an approved negative only; it is time-sensitive and outside scope. |
| FANUC-N003 | Who won the latest football match? | — | — | — | U | Yes | Confirm as an approved negative only; it is outside scope. |
| FANUC-N004 | How do I bake a chocolate cake? | — | — | — | U | Yes | Confirm as an approved negative only; it is outside scope. |

## Reviewer actions

The approved cases have been reviewed against the handbook. Resolve
`FANUC-R002` before approval because the proposed exact identifier is not
present literally in the eligible corpus.
