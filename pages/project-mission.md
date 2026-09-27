---
title: Project Mission
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

CMDB documents the configuration of the project owner's network and services.
It provides a central reference for port assignments, shared filesystems,
maintenance commands, and operational scripts.

## Scope

Keep configuration references readable and actionable: explain what a service
does, where its configuration lives, and how to perform the documented task.
State limitations when records are incomplete or may be out of date.

CMDB is a static documentation site built with Jekyll and published through
GitHub Pages at [cmdb.osoyalce.com](https://cmdb.osoyalce.com). Its source files
are the configuration record; changes to documentation do not apply changes
to the machines being documented.

The site shares the Minimal Mistakes theme and development conventions used
by MyCount. Its [release process]({{ site.baseurl }}{% link pages/releases.md %})
provides versioned snapshots of the documentation and site setup.
