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
