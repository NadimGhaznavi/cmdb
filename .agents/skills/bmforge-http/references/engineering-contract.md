---
title: Engineering Contract
lang: en
locale: en-US
language_name: English
translation_key: bmforge-engineering-contract
---

**The smallest clear implementation that satisfies the contract wins.** BMForge is for the applications actually being built, not an imagined enterprise platform.

## Implementation authorization gate

**Discussion is not authorization to implement.** Read-only investigation,
requirements conversations, design alternatives and proposed specifications
may proceed without implementation approval. Do not change project files,
install dependencies, run migrations or perform other mutating implementation
steps until the user clearly authorizes the agreed scope. A direct instruction
to implement, fix or apply a change counts; no magic phrase is required. If
a conversational response leaves the intent to proceed unclear, ask.

Once authorized, implement and test within that scope without seeking
permission for each file. Pause for material scope expansions, new dependencies
or unapproved architectural choices. Implementation approval is separate from
permission to commit, push, release or deploy.

## Required behaviour

1. **Implement only requested capability.** Reuse the chosen patterns and the project's existing conventions. Do not add generic frameworks, brokers, caches, background supervisors, feature switches, or other infrastructure without a concrete requirement.
2. **Validate at trust boundaries.** Check untrusted network input, configuration, credentials and external protocol messages at entry. Reject invalid external requests predictably. Do not duplicate those checks throughout trusted internal code.
3. **Trust internal contracts.** Once an invariant or validated contract is established, rely on it. An impossible internal state is a defect, not an invitation to manufacture a fallback.
4. **Fail fast and visibly.** Missing required resources, invalid startup configuration, failed binds, and broken internal invariants should produce an actionable error and stop the affected operation or service. Never fabricate success.
5. **Handle real distributed failures.** For required remote operations, use the necessary timeout, acknowledgement, and error reporting. Recovery and retries must be explicit, bounded, and justified by the operation's semantics, not added reflexively.
6. **Catch exceptions only to act.** Handle a known external error, release owned resources, add useful context, or perform specified recovery. Otherwise let it propagate. Do not blanket-catch exceptions, silently swallow errors, or return fake defaults.
7. **Test contracts, not speculation.** Verify normal behaviour, named acceptance checks, meaningful trust-boundary failures, and required startup/shutdown conditions. Keep tests proportional to the component.
8. **Classify by responsibility.** Follow [Activity / Interface / Entity]({{ site.baseurl }}{% link pages/classification.md %}): interface classes bridge technology or domain data access, activity classes orchestrate application operations, and entities hold values. Do not blend SQL, workflow and entity state into one class.
9. **Preserve approved runtime choices.** Component module inventories are binding. [Display visualization choices]({{ site.baseurl }}{% link pages/component-visualization.md %}) are likewise fixed by actual chart, map or graph requirements, not by Codex preferences. Do not replace or add infrastructure libraries, drivers or frameworks to solve a task without user approval and an updated component specification. Configure the known pattern rather than re-architecting it.

10. **Maintain the changelog for every completed change.** Update `CHANGELOG.md` under `## [Unreleased]` in the same task for code, tests, documentation, configuration, and maintenance, however small. Make `### Summary` the default for any meaningful feature, fix, or operational improvement, even when it stands alone; keep one summary per section. Follow [Changelog Maintenance]({{ site.baseurl }}{% link pages/changelog-maintenance.md %}).

## What failure should look like

| Situation | Contract-driven response |
| --- | --- |
| Public HTTP client sends malformed JSON | Return a clear 4xx response; keep serving valid requests. |
| Required HTTP port is already occupied | Report the bind error and abort startup. |
| Internal code violates an established invariant | Raise a meaningful error; don't continue with guessed values. |
| Required ZeroMQ exchange times out | Report failure to the caller; retry only if the application contract explicitly permits it. |
| Database transaction fails | Roll back that transaction and propagate the error; never report a successful commit. |

A health check reports actual application state; it is not a mandate to build a self-healing system. Follow [Application Health Checks]({{ site.baseurl }}{% link pages/health-checks.md %}): one existing interface, no monitoring background workers, and no direct CMDB-to-MariaDB probe. Security at exposed boundaries is mandatory where applicable, but redundant internal validation is not security.

Every new project must also satisfy the [Installation Lifecycle contract]({{ site.baseurl }}{% link pages/component-installation.md %}): install, upgrade and uninstall must work for the application's actual distribution topology. A successful install leaves a readable version/ownership record under its application-owned `/opt/prod` directory. Bootstrapped deployment stubs are **not proof** that the app can be installed.

## Scope gate for Codex

For applications with more than one service, create an executable `scripts/services` supporting `start` and `stop`. Run the application's start/stop commands sequentially in an explicit order. Keep it simple; no dependency awareness is required.

Before adding nontrivial defensive logic or an additional layer, identify **the requirement or observed failure it solves**. If none exists, omit it. Prefer an understandable, observable failure over code that quietly limps forward.

The [component blueprints]({{ site.baseurl }}{% link pages/component-blueprints.md %}) define specific behaviours; [CMDB compliance]({{ site.baseurl }}{% link pages/cmdb-compliance.md %}) and the other existing processes govern deployment. A component skill must follow this contract, not replace it.

---

[Back to BMForge]({{ site.baseurl }}{% link index.md %})
