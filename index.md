---
title: Configuration Management Database
---

The **CMDB** project grew out of the operational requirements of a small Linux lab. It discovers machines and deployed applications on a local network, maintains an inventory of the results, and provides tools for patching and backups.

## Machine Discovery

CMDB scans the local area network (LAN) for machines and maintains a persistent inventory of the results. Subsequent scans refresh the observed status of inventoried devices. The default gateway is treated as a special device: it is named `GATEWAY` and automatically classified as **PROD**.

## Application Discovery

CMDB is part of the [Bear & Moose](https://www.osoyalce.com/) family of software, which includes [BMForge](https://bmforge.osoyalce.com/), a software development life cycle (SDLC) framework that integrates AI into the development workflow. Applications built with BMForge can include `CMDB_*` declarations that make their deployments discoverable by CMDB.

Registering an application is straightforward: enter its name on the **Applications** page. CMDB checks the inventoried machines for an installed copy and, when one is detected, automatically records the deployment in its inventory.

Discovered application details include the name and version, along with any declared release codename, software classification, data components, and database references.

### Application Ports

Applications can declare their default network listeners through `CMDB_NETWORK`. CMDB collects those declarations from deployed applications and displays the associated host, application, service name, and port number on the **Network** page.

These are **declared listener defaults**, not a live measurement of which ports are currently open.

## Machine Classification

CMDB groups machines into four categories: **PROD**, **QA**, **DEV**, and **Unclassified**. Newly discovered machines begin as Unclassified, with the exception of the default gateway.

When CMDB finds an unclassified device, it performs a more intensive Nmap service scan and saves the raw output. The evidence is available from the device's details pane on the **Inventory** page, helping administrators identify printers, tablets, phones, and other unfamiliar equipment before assigning a classification.

## Patching

CMDB includes a patching interface for Debian Linux. Discovered Debian machines automatically appear on the **Patching** page, where an administrator can run a patch job on demand or configure automatic, cron-scheduled patching for each host.

A patch job refreshes package information, installs available package upgrades, removes obsolete packages, and then reboots the machine. CMDB verifies that the host has returned after the reboot and records the outcome.

## Backups

Machines with eligible backup targets appear on the **Backups** page. CMDB supports both on-demand backups and per-target, cron-scheduled backups with configurable retention.

- **MariaDB:** CMDB discovers MariaDB instances and their eligible user databases, which can be backed up individually.
- **Application data:** Applications declaring filesystem components and database references through `CMDB_COMPONENTS` and `CMDB_DATABASES` make those backup targets available for configuration.
- **Backup Vault:** Successful database dumps and application directory archives are listed in the vault. Backup records and files remain available even after the associated machine is removed from the inventory.

---

# Legacy Site

## Links

* [Port Numbers]({{ site.baseurl }}{% link pages/port-numbers.md %})
* [autofs]({{ site.baseurl }}{% link autofs.md %})
* [/opt/prod/xmrig/xmrig-mode.sh]({{ site.baseurl }}{% link pages/xmrig-mode.sh.md %})

## Project

* [Server installation]({{ site.baseurl }}{% link pages/installation.md %})
* [Network discovery]({{ site.baseurl }}{% link pages/discovery.md %})
* [App discovery settings]({{ site.baseurl }}{% link pages/app-discovery.md %})
* [CMDB_NETWORK app developer guide]({{ site.baseurl }}{% link pages/cmdb-network.md %})
* [Debian patching]({{ site.baseurl }}{% link pages/patching.md %})
* [CMDB server]({{ site.baseurl }}{% link pages/server.md %})
* [Schema notes]({{ site.baseurl }}{% link pages/schema-notes.md %})
* [Project mission]({{ site.baseurl }}{% link pages/project-mission.md %})
* [Site development]({{ site.baseurl }}{% link pages/development.md %})
* [Coding guidelines]({{ site.baseurl }}{% link pages/coding-guidelines.md %})
* [Release management]({{ site.baseurl }}{% link pages/releases.md %})
* [Changelog]({{ site.baseurl }}{% link CHANGELOG.md %})
