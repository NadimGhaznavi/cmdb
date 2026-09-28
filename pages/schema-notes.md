---
title: Schema Notes
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

This page records non-obvious database constraints and implementation decisions.

## Deployment owner consistency

`DeployedComponent.machine` and its inherited `ModelElement.namespace` must
identify the same Machine. The database enforces this with:

```sql
FOREIGN KEY (id, machine) REFERENCES ModelElement (id, namespace)
```

The supporting unique index on `ModelElement(id, namespace)` allows the pair
to be referenced. The separate foreign key from `DeployedComponent.machine`
to `Machine.id` ensures that the owner is a Machine.

Both deployment key columns are required. A deployment therefore cannot use a
parent with a null owner. Inserts or updates that make the references disagree
are rejected, including direct SQL changes to either table. Other model
elements may still have a null namespace.

Create the parent with its machine namespace before inserting the deployment.
Foreign keys are checked immediately; changing only one ownership reference
is rejected even inside a transaction. The scanner already writes the matching
values in this order.

This constraint is part of the fresh-install schema. Apply it through the
current uninstall/install workflow; no record migration is provided.


## Tagged values and OS definitions

`TaggedValue.modelElement` references the owning ModelElement. The unique key
`(modelElement, tag)` enforces CWM's one-value-per-tag rule for an attached tag.
Tag names use a binary collation so their casing is significant. TaggedValue
has its own technical ID; it does not inherit from ModelElement.

The scanner includes `VERSION_CODENAME` in software-definition matching. Hosts
with matching release fields and codenames share the same definition and tag.
A changed codename selects or creates a separate definition rather than changing
one already used by other machines. Missing codename data is not invented.
The scanner recognizes both Nmap's `OS` classification and host-reported `linux`
as OS deployments at `/`, so successive observations update the same deployment.
