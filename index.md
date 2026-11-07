---
title: Configuration Management Database
---

The **CMDB** project grew out of the operational requirements of a small lab. It includes the following features.

## Machine Discovery

The CMDB scans the LAN for machines and maintains a database inventory of the results. The default gateway is treated as a special device and is classified as PROD and assigned the CMDB name `GATEWAY`.

## Application Discovery

The CMDB is part of the [Bear & Moose](https://www.osoyalce.com/) family of software. This includes [BMForge](https://bmforge.osoyalce.com). The BMForge project is basically a SDLC framework that integrates AI into the workflow. BMForge software includes tags for the CMDB discovery process. In this way, the CMDB can detect if a registered application is deployed on the network.

Registering a new BMForge application in the CMDB is trivial. The new application name is entered and that's it. The CMDB will proceed to scan all of the registered devices to see if the application is installed. It simply appears in the CNDB inventory.

BMForge applications have a unique name, a specific version number, and a unique release codename. These are discovered and displayed by the CMDB.

### Application Ports

Many applications listen on specific port numbers. If the application is a BMForge project, then the application will include this information. The CMDB scans this from deployed BMForge applications and uses it to display the port numbers that are currently in use within the LAN environment.

## Machine Classification

The CMDB application defines 4 categories of machines: PROD, QA, DEV, and Unclassified. All discovered machines are initially put into the unclassified category. When the CMDB discovers an unclassified device it performs a more intensive scan for services and saves the results. These results are available on the CMDB Inventory page, in the details pane, when an unclassified machine is selected. This helps to identify devices like printers, cell phones etc.

## Patching

The CMDB includes a simple patching interface that supports Debian Linux. Discovered Debian machines automatically appear on the **Patching** screen. The CMDB provides an interface to define a cron job to execute automatic, scheduled patching.

Patching is a blanket `apt -y update` and is followed by a reboot.

## Backups

A machine appears on the **Backups** page when it contains an eligible backup target:

- Hosts with MariaDB automatically appear in the CMDB.
- The CMDB support per-database, cron driven, scheduled backups.
- The CMDB supports automatic configuration of BMForge application backups, including application databases.
- Backup Vault: successful backup records remain visible even after the machine is removed from the inventory.

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
