The Assistant is not a chatbot. It is a mission control system for
Gemini-powered advertising engineering, built on the Google Antigravity agent
framework (v3.0.0).

## The big picture: Solve the high-compliance friction problem

The fundamental problem this Assistant solves is cognitive overload and
technical toil.

The Google Ads API is one of the most powerful---but also one of the most
complex---APIs available. It features strict versioning, a unique query language
(GAQL), deeply nested protocol buffer structures, and rigorous safety
requirements. A developer often spends a significant percentage of their time
fighting the API by debugging gRPC errors, looking up field compatibility, and
fixing linter issues instead of building actual business logic.

The Assistant solves this in version 3.0.0 by introducing an **agentic design**
powered by specialized, test-backed **skills**. It acts as an automated expert
middleware, handling the toil of version validation, schema discovery, and code
linting, which lets the developer operate at the level of intent rather than
syntax.

## The analogy: The specialized research and diagnostic lab

Think of the assistant as a high-tech research lab for a surgeon.

- **The surgeon (the developer)**: You know exactly what operation needs to be performed (e.g., "I need to analyze PMax performance").
- **The lab equipment (the API):** These are the powerful tools needed to perform the surgery, but they are sophisticated and require exact calibration.
- **The lab assistant (this tool)** : Before you touch the patient, the lab assistant uses specialized **Skills** to:
  1. **Check the manuals** : Auto-verifies the latest "medical protocols" (API versioning) and inspects resource structures on the fly (`inspect_object`).
  2. **Pre-test the tools: Executes "dry runs"** on your surgical plans using live API validation (`validate_gaql`) to catch errors before they happen.
  3. **Sterilize the environment:** Cleans and formats your code using strict linter pipelines (`Ruff` linting) so it doesn't cause an "infection" (system error).
  4. **Monitor the vitals** : Watches for "complications" (API exceptions) and runs advanced diagnostic workflows for complex operations like offline conversions (`troubleshoot_conversions`).
  5. **Explains concepts**: It explains complex concepts in everyday language with real world analogies.

## Interconnectedness: The "safety-first" bridge

The Assistant functions as a bridge connecting four distinct "worlds" within
your project, governed by a controlling contract (`AGENTS.md`):

- **The user context:** It listens to your high-level goals and translates them into a technical strategy.
- **The local workspace:** It has "eyes and hands" in your project directory. It can read existing code and write new code for later use, maintaining strict isolation.
- **The Google Ads API:** It communicates with the live API to fetch real-time schemas, metadata, and performance data. It "knows" what fields are valid because it asks the API directly.
- **The safety gatekeepers:** It is hard-wired to follow strict protocols. It won't let you run a script if it hasn't been linted, and it won't let you send a query if it hasn't passed a programmatic validation check.

## What the Assistant actually does

In plain terms, the assistant is your safeguard and accelerator.

- **It prevents mistakes:** It checks your "homework" (code and queries) before it ever hits the live API, stopping errors before they happen.
- **It knows the map**: It understands the "geography" of the Google Ads API---where the data lives and how to get it efficiently.
- **It automates the boring stuff:** It writes the boilerplate code, formats your reports, and handles the "plumbing" of a client library.
- **It troubleshoots complex workflows:** With v3.0.0, it can run deep diagnostics on offline conversion uploads and configure complex campaign structures like Performance Max listing filters.
- **It stays current:** Because the Assistant searches for the latest release notes and documentation, it ensures you aren't using old rules for a new API version.
- **The holistic takeaway:** The Google Ads API Developer Assistant is a strategic partner that transforms a "developer versus API" struggle into a "developer + AI" collaboration, ensuring every piece of code is safe, idiomatic, and architecturally sound.