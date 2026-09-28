---
title: Project Mission
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

CMDB documents the configuration of the project owner's network and services.
It provides a central reference for port assignments, shared filesystems,
maintenance commands, and operational scripts.

## Model reference

The application's data model is based on the OMG
[Common Warehouse Metamodel (CWM) 1.1 specification, Volume 1](https://www.omg.org/spec/CWM/1.1/PDF/),
particularly section 5.7, SoftwareDeployment. This is the core reference for
modeling machines, deployed components, data managers, data providers, and
provider connections.

Implement only the classes, attributes, and relationships the application needs
and has data to store. CWM is a reference for this focused subset, not a roadmap
to implement the entire specification.

Maintain a one-to-one mapping between the adopted CWM model, Python entities,
and database tables and schema. Each adopted CWM class maps to a Python entity
and a corresponding database table. Preserve the specification's names,
attribute casing, inheritance, relationships, and multiplicities across these
layers. Do not flatten or shortcut the model in ways that lose those semantics.

The initial overhead and complexity are intentional: a consistent mapping makes
the application easier to extend and its data easier to report on. This rule
applies to the subset we adopt; it does not require implementing unused parts
of CWM.

## Scope

Keep configuration references readable and actionable: explain what a service
does, where its configuration lives, and how to perform the documented task.
State limitations when records are incomplete or may be out of date.

CMDB's documentation is built with Jekyll and published through
GitHub Pages at [cmdb.osoyalce.com](https://cmdb.osoyalce.com). Its source files
are the configuration record; changes to documentation do not apply changes
to the machines being documented.

The [CMDB server]({{ site.baseurl }}{% link pages/server.md %}) provides the
foundation for a live inventory application with a MariaDB backend. It runs
as a separate systemd service on port 14444; its initial endpoints expose a
landing page and health checks.

The site shares the Minimal Mistakes theme and development conventions used
by MyCount. Its [release process]({{ site.baseurl }}{% link pages/releases.md %})
provides versioned snapshots of the documentation and site setup.
