---
title: CMDB_NETWORK App Developer Guide
---

[App discovery settings]({{ site.baseurl }}{% link pages/app-discovery.md %})

## Status and purpose

`CMDB_NETWORK` is the application-side standard for declaring an app's default
network listeners. Application discovery collects these declarations and stores
them on a dedicated CWM DeployedComponent for each installed application. The
Network page's Ports table reports the stored listener roles and port numbers
by host and application.

The declaration must drive the app's listener defaults, so inventory metadata
and runtime defaults have one source. MyCount and CMDB use this pattern, with
production JSON overrides resolved by `Configuration` and `Network` interfaces.
For CMDB's own production settings, see
[runtime configuration]({{ site.baseurl }}{% link pages/installation.md %}#runtime-configuration).

## Declare the listeners

Put `CMDB_NETWORK` in the app's existing constants file beside its literal
`VERSION` and other `CMDB_*` metadata. The application discovery convention is
`/opt/prod/<lowercase-name>/<lowercase-name>/constants/D<Name>.py`; for example,
CMDB uses `/opt/prod/cmdb/cmdb/constants/DCMDB.py`. See
[App discovery settings]({{ site.baseurl }}{% link pages/app-discovery.md %}#registration-and-constants-file)
for the existing registration and constants-file convention.

This fictional Example app declares two listeners:

```python
from typing import Final


class DExample:
    VERSION: Final[str] = "1.0.0"
    CMDB_NETWORK: Final[tuple[tuple[str, str, int], ...]] = (
        ("http", "0.0.0.0", 18080),
        ("backend", "127.0.0.1", 18081),
    )
```

Each entry is a literal `(use, interface, port)` tuple:

| Field | Meaning and app-side requirements |
| --- | --- |
| `use` | A unique, nonempty string identifying the listener's role. Keep it stable because configuration and consumers look it up by this name. Examples include `http`, `https`, `report`, and `backend`. |
| `interface` | An IPv4 bind address as a string. `0.0.0.0` listens on all IPv4 interfaces; `127.0.0.1` listens on loopback only. |
| `port` | An integer from 1 to 65535. Strings and booleans are invalid. |

Declare every listener owned or configured by the app, including internal
listeners and managed proxy listeners. Use direct literals at module or class
scope. Do not construct the declaration from environment variables, function
calls, other constants, or comprehensions: the discovery convention reads
constants as data without importing or executing application code.

`use` identifies a role; this tuple has no separate transport field. The current
MyCount and CMDB implementations use IPv4 addresses. Hostnames, IPv6, Unix
sockets, and transport-specific extensions are outside this documented pattern.

Outbound dependencies such as MariaDB and GeoIP retain their own connection
settings. Declare database references separately with `CMDB_DATABASES`, as
described in the
[CMDB_DATABASES guide]({{ site.baseurl }}{% link pages/cmdb-databases.md %}).
Never place credentials in `CMDB_NETWORK` or the network JSON file.

## Wire the app to the declaration

Replace the old listener host and port constants with lookups by `use`. Avoid
tuple-position lookups and duplicate fallback values. In the reference pattern:

```python
interface, port = Network.binding("http")
```

`Network.binding` returns the resolved bind address and port. Route all consumers
through the same resolver: server startup, managed proxy listeners and upstreams,
installation health checks, and any router mapping creation or cleanup.
Only include the consumers the app actually has.

For a local client such as a health check or proxy upstream, use
`Network.destination(use)`. It returns the configured address and port, replacing
the wildcard bind address `0.0.0.0` with `127.0.0.1`. Specific addresses remain
unchanged. Existing server CLI overrides such as `--host` and `--port` should
continue to work for an individual invocation.

## Production overrides

Follow the MyCount and CMDB pattern with `conf/<app>.json` beneath the production
installation directory. For the fictional Example app, a partial override is:

```json
{
  "network": {
    "http": {
      "interface": "127.0.0.1",
      "port": 19080
    }
  }
}
```

Resolve settings in this order, from lowest to highest precedence:

1. Literal `CMDB_NETWORK` defaults.
2. Production JSON overrides for known uses and fields.
3. Supported command-line overrides for that invocation.

A missing file uses the defaults. Omitted uses and fields inherit their defaults.
Reject malformed JSON, unknown uses or fields, invalid IPv4 addresses, and
invalid ports with an error identifying the file or setting. Invalid files
must not silently fall back to defaults. Read resolved configuration once per
process; restart affected processes to apply edits.

The installer should create a readable network configuration from the declaration
only when the file is missing, preserve existing files during reinstall and
upgrade, and validate configuration before stopping services. A restart command
should validate first, then apply all affected settings, including generated
proxy configuration or router mappings where applicable. Deployment health
checks must use the same resolved settings as the services they check.

The declaration describes **default inventory**, even when production JSON or CLI
arguments change the actual listener. Discovery reads the constants declaration;
it does not read production JSON, inspect CLI arguments, or probe live sockets.

## Discovery and CWM storage

Normal Inventory, Re-Scan Applications, and Add Application collect `CMDB_NETWORK`
alongside the installed application's other metadata. A valid literal `VERSION`
is still required. Constants are parsed as data and never imported or executed.

Discovery accepts a literal tuple or list of three-item tuples or lists. Uses
are trimmed, nonempty strings without control characters and must be unique
after trimming. A use is limited to 242 characters so its prefixed tag fits the
existing 255-character tag field. Interfaces must be literal IPv4 address
strings. Ports must be integers from 1 to 65535; booleans are rejected.
Computed declarations, invalid entries, and duplicate uses invalidate the whole
network declaration. Other valid application metadata can still be recorded.

| CWM element | Stored information |
| --- | --- |
| Component | Named `Network listeners`, owned by the application's SoftwareSystem release |
| DeployedComponent | Named `Network listeners`, with the application's installation pathname and the host as both `machine` and inherited `namespace` |
| DeployedComponentsUsage | Application deployment in `usingComponents`; listener deployment in `usedComponents` |
| TaggedValue | One per listener, with `tag="CMDB_NETWORK.<use>"` and a JSON array string preserving `[use, interface, port]` |

For example, `("http", "0.0.0.0", 18080)` becomes
`tag="CMDB_NETWORK.http"`, `value='["http","0.0.0.0",18080]'`. The tag's
`modelElement` references the listener deployment's inherited ModelElement ID.
These tag names and values are CMDB conventions using CWM's TaggedValue extension
mechanism. The listener is a plain DeployedComponent, without a DataManager,
DataProvider, or ProviderConnection. `Network listeners` is a scanner-managed
Component name; use other names for declared filesystem components.

Hosts running the same application release share the listener Component, while
each application deployment has its own listener DeployedComponent and tags.
Repeated scans reuse deployment and tag identities. Upgrades rebind the listener
deployment to the new release's Component without changing another host's tags.

A valid declaration refreshes the complete listener set, removing network tags
for uses no longer declared. An explicit empty tuple or list clears those tags
and retains the listener deployment. A missing, unreadable, computed, or invalid
declaration preserves the last recorded tags; existing listener deployments still
follow application release changes. Unrelated tags are preserved. Listener writes
share the application observation's transaction. Deleting the application release
removes its listener deployments, usage links, and tags through existing cleanup.

Listener deployments are excluded from the general software display and directory
backup targets. The Network page reports their stored tuples in an expanded,
collapsible Ports section with Host, Application, Service Name, and Port Number
columns. Click a heading to sort ascending or descending. The second header row
filters each column; `*` matches any text, matching ignores case, and all column
filters apply together. Blank filters also match everything. The initial order
is Host ascending, and port numbers sort numerically. Sort and filter choices
remain when switching pages within the current browser session.

This storage adds no tables or columns and does not establish runtime bindings,
reachability, transport, or client dependencies.

## Verify an app update

- Change the declaration in a test and confirm server defaults and relevant
  proxy, health-check, and router consumers follow the new address and port.
- Verify a missing config file and partial overrides resolve correctly, and
  supported CLI arguments take precedence.
- Verify invalid configuration fails clearly before restart actions, and
  reinstall or upgrade preserves an existing configuration file.
- Verify local destinations translate wildcard bindings to loopback and retain
  specific addresses.
- Verify edits take effect after restart and all affected consumers receive the
  new settings.
- Document the app's uses, production config path, and restart procedure, and
  remove replaced listener constants and hardcoded values from runtime consumers.
- Re-scan the registered application and confirm its listeners in Network's
  Ports report. Verify updates stay local to that application deployment and
  removed uses disappear after a valid declaration.
