---
title: Specification Lifecycle and Traceability
lang: en
locale: en-US
language_name: English
translation_key: bmforge-specification-lifecycle
---

BMForge defines the **current preferred contracts** for new implementations. Each application owns its implementation and may upgrade deliberately, without any runtime link to BMForge. **The current specification describes one clean target state, not a collection of legacy-compatible paths.** Older consumers adopt a new revision by deliberately refactoring their own source, deployment and tests; BMForge adds no version adapters, migration shims or legacy runtime branches. Previous specifications remain accessible through their published Git history.

## Identify the implemented contract

Every BMForge-derived component must place one literal marker in its **owning Python module**, for example DevLog's ZeroMQ server:

```python
BMFORGE_COMPONENT = {
    "id": "bmforge.zmq-server",
    "spec_version": "0.3.0",
}
```

The stable ID identifies the BMForge component; the version identifies the specification used when the implementation was built or reviewed. It is **not** the application's release version. Tag the module that owns the component, not every helper file. The declaration must use literal strings so future discovery can parse it statically with Python AST, without importing or executing application code. No BMForge runtime import is required.

A marker is a **provenance claim**, not proof of compliance. Tests establish whether the implementation satisfies that contract. Component provenance is independent of [USDP-inspired class classification]({{ site.baseurl }}{% link pages/classification.md %}), which is represented by class responsibilities and source package placement; no extra runtime metadata system is required. Each component's approved runtime-module list is part of the versioned specification; changing the infrastructure modules requires user approval and a new specification version.

## Evolving a specification

1. Investigate a failure in the consuming application. Distinguish an implementation defect from a missing or incorrect BMForge requirement.
2. For a specification gap, clarify the behaviour and add a focused acceptance or regression check.
3. Change the specification version when its required behaviour changes. Do not reuse a published version for a different contract. Preserve published versions as immutable Git-retrievable revisions or snapshots so old tags retain meaning.
4. Update the current specification page, its acceptance checks, and the [decision record]({{ site.baseurl }}{% link DECISIONS.md %}) when the change affects engineering policy or compatibility.
5. Consumers adopt the new version intentionally, test it locally, and update their own module markers.

Each component page declares its stable `component_id`, `spec_version`, and `spec_status` in page metadata; consult that page for its current revision and validation status. Component specifications are independently versioned. Keep specification revisions separate from application release versions.

## CMDB boundary and future visibility

A future CMDB application-code scanner can extract `BMFORGE_COMPONENT` markers and compare installed component versions with BMForge's catalogue. This will support both application-to-specification and specification-to-applications queries.

**This scanner and comparison report do not exist yet.** The existing `CMDB_COMPONENTS` declaration inventories persistent directories for backup and discovery; it must not be repurposed to mean BMForge architectural components.

An implementation that predates the latest specification is not automatically vulnerable or defective. Currency, tested compliance, and known security exposure are separate facts.

---

[Back to BMForge]({{ site.baseurl }}{% link index.md %})
