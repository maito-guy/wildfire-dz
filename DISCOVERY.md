# Discovery: from idea to spec

This is the first phase of every project. The AI interviews the owner until
`SPEC.md` describes everything needed to plan and build the product: every
feature, option, constraint, assumption, and acceptance test. No repository
setup, no issues, and no code happen in this phase.

**Starts:** the kit has been dropped into a folder and `SPEC.md` does not
exist, or `PROGRESS.md` section 1 says "Phase: discovery".
**Ends:** the owner approves `SPEC.md` (section 6). Then planning starts
(`PROJECT_MANAGEMENT_RULES.md` section 3).

## 1. Stance

- **Grill, don't transcribe.** The owner's first description is a starting
  point, not a spec. Probe every vague word ("fast", "simple", "secure",
  "users"), ask what happens when things fail, and look for the cases the owner
  has not thought about.
- **Never invent requirements.** The AI may *suggest* features, options, or a
  stack, but each suggestion is labelled as one and only enters the spec when
  the owner accepts it.
- **Assume nothing from earlier projects.** Language, framework, hosting,
  tools, and conventions are decided here, for this project.
- **Recommend, then let the owner decide.** For each real choice, give 2-4
  options with trade-offs and say which one you recommend and why. A default
  the owner accepts is still a decision and is recorded as one.
- **Be concrete.** Turn every requirement into something testable: inputs,
  outputs, limits, timings, error behaviour.

## 2. How to run the interview

1. **Open.** Ask the owner to describe the idea in their own words: what it
   is, who it is for, and why it should exist. Ask whether they already have
   preferences (stack, hosting, budget, deadline) or existing material
   (notes, mockups, a similar product) to start from.
2. **Create `SPEC.md` early** from the template in section 5, with what is
   known and every unknown marked `[QUESTION]`. Update it after every topic, so
   the owner can read the current state at any time and a new session can
   resume from the file.
3. **Go topic by topic** through the coverage map (section 3), in an order that
   fits the product. Ask **3-5 related questions per turn**, never a wall of
   twenty. Use multiple-choice questions where the options are known.
4. **Summarise back** after each topic: "Here is what I wrote for X; correct
   me." Contradictions between topics are raised immediately.
5. **Track what is open.** Every unanswered point stays in the spec as
   `[QUESTION]`; every answer the AI filled in with a default the owner did not
   explicitly confirm stays as `[ASSUMPTION]`. Both are listed in the spec's
   open-items section.
6. **Pass twice.** After the first pass over all topics, do a second pass that
   walks through the main user flows end to end and through each failure case,
   asking only about gaps found that way.
7. **Close** with the review in section 6.

Record the phase and progress in `PROGRESS.md` section 1 (for example "Phase:
discovery, topics 1-7 done, 4 open questions"), so the interview can continue
in a later session.

## 3. Coverage map

Every topic must be addressed in the spec, even if the answer is "not
applicable" or "out of scope for v1".

| # | Topic | Questions to settle |
| --- | --- | --- |
| 1 | Problem and goals | What problem, for whom, why now; what success looks like; how it will be measured |
| 2 | Users and roles | Who uses it; roles and permissions; how many; technical level; how they access it |
| 3 | Scope | What is in v1; explicit non-goals; what is deferred to later versions |
| 4 | Features | For each feature: purpose, trigger, inputs, behaviour, outputs, limits, edge cases, errors |
| 5 | User flows | The main end-to-end journeys, step by step, including the unhappy paths |
| 6 | Interfaces | UI, CLI, API, bot, or device; screens or commands; messages and wording; accessibility; languages |
| 7 | Data | Entities and fields; where data lives; lifetime and deletion; import/export; migrations |
| 8 | Integrations | External services, APIs, hardware, accounts; their limits, costs, failure modes, and who owns the credentials |
| 9 | Environments | Where it runs (devices, OS, browser, server, cloud); network; who administers it |
| 10 | Stack | Languages, frameworks, storage, and key libraries; owner preferences; the AI's recommendation with reasons |
| 11 | Configuration and options | Every setting: name, meaning, default, allowed values, who changes it and how |
| 12 | Security and privacy | Authentication, authorization, secrets and where they live, personal data, threat model, abuse cases |
| 13 | Reliability and failure handling | What can fail; what the product does in each case; retries, timeouts, recovery; what must never happen |
| 14 | Performance and scale | Expected load, response times, data sizes, limits |
| 15 | Operations | Install, deploy, upgrade, backup, monitoring, logs, alerts; who operates it |
| 16 | Testing and acceptance | How each feature is proven; the end-to-end acceptance test plan; what needs the real environment |
| 17 | Constraints | Budget, deadlines, licences, legal or compliance requirements, things that are already fixed |
| 18 | Prerequisites | What the owner must provide or set up before or during development (accounts, devices, domains, keys) |
| 19 | Delivery | Milestone preferences, what an early usable version looks like, how the owner wants to review progress |
| 20 | Risks and unknowns | What could make the project fail; what needs a spike or prototype first |
| 21 | Future ideas | Wanted later but explicitly not in v1 |

## 4. Spec writing rules

- Numbered sections, so issues and decisions can cite them ("spec §6.2").
- Requirements use **must** (required), **should** (expected unless a reason is
  recorded), **may** (optional). Each one is testable.
- Every feature has acceptance criteria and its failure behaviour.
- Every configurable value appears once, in the configuration section, with
  its default.
- Every decision taken during the interview goes in the decisions log with the
  reason and the alternatives that were rejected.
- Mark `[QUESTION]` for open points and `[ASSUMPTION]` for unconfirmed
  defaults, inline where they apply, and list both in the open-items section.
- Define product terms once in the glossary and use them consistently.
- No secrets in the spec. Name what is secret and where it will live instead.
- Keep implementation detail out unless it is a real constraint (an API that
  must be used, a platform that is fixed). The planning phase decides the rest.

## 5. Spec template

```markdown
# <Product name>: specification

**Status:** draft | approved (YYYY-MM-DD)
**Owner:** <name>

## 1. Summary
One paragraph: what it is, for whom, and the problem it solves.

## 2. Decisions log
| # | Decision | Reason | Rejected alternatives |
| --- | --- | --- | --- |

## 3. Goals and non-goals
### 3.1 Goals (with how success is measured)
### 3.2 Non-goals
### 3.3 Later versions

## 4. Users and roles

## 5. Glossary

## 6. Features
### 6.1 <Feature>
- Purpose:
- Trigger / inputs:
- Behaviour:
- Outputs:
- Limits and edge cases:
- Failure behaviour:
- Acceptance criteria:

## 7. User flows
### 7.1 <Flow> (happy path, then each unhappy path)

## 8. Interfaces
Screens, commands, endpoints, messages and their exact wording where it matters.

## 9. Data
Entities, fields, storage, retention, deletion, migration.

## 10. Integrations
For each external system: purpose, interface, limits, cost, failure modes, credentials owner.

## 11. Architecture and stack
Components, how they talk, where each runs; languages, frameworks, storage, key libraries, with reasons.

## 12. Configuration
| Setting | Meaning | Default | Allowed values | Secret? |
| --- | --- | --- | --- | --- |

## 13. Security and privacy
Authentication, authorization, secrets and where they live, personal data, threat model.

## 14. Reliability and failure handling
| Failure | Detection | Product behaviour | User sees |
| --- | --- | --- | --- |

## 15. Performance and scale

## 16. Operations
Install, deploy, upgrade, backup, monitoring, logging.

## 17. Environments and prerequisites
Where it runs, and everything the owner must provide or set up, with when it is needed.

## 18. Testing and acceptance plan
How each feature is verified; the end-to-end acceptance tests; which need the real environment.

## 19. Delivery
Suggested milestones and what the first usable version contains.

## 20. Risks and unknowns

## 21. Open items
Every remaining `[QUESTION]` and `[ASSUMPTION]`, with where it appears. Empty at approval.
```

## 6. Exit review

Before asking for approval:

1. Walk the coverage map: each topic is answered or explicitly marked not
   applicable / out of scope.
2. Walk each user flow and each failure case against the features: nothing a
   flow needs is missing.
3. Check that every feature has acceptance criteria and that the acceptance
   plan covers every feature.
4. Resolve or explicitly accept every `[QUESTION]` and `[ASSUMPTION]`: the
   open-items section is empty, or each remaining item has the owner's "accept
   as written".
5. Show the owner a short summary (features, stack, environments, the main
   decisions, what is out of scope) and ask for approval.

On approval: set the spec status to approved with the date, record "Spec
approved" in `PROGRESS.md` (section 3.1 decision and section 5 log), set
section 1 to "Phase: planning", and continue with
`PROJECT_MANAGEMENT_RULES.md` section 3.

Later changes to an approved spec go through the owner: propose the change,
update the spec and its decisions log, then update or add the affected issues.
