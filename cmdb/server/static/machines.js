"use strict";

let refreshing = false;
let backupFilesRequest = 0;

function elapsedTime(seconds) {
  const pad = value => String(value).padStart(2, "0");
  return `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor(seconds / 60) % 60)}:${pad(seconds % 60)}`;
}

async function loadBackupFiles() {
  const request = ++backupFilesRequest;
  const status = document.getElementById("backup-files-status");
  const body = document.getElementById("backup-files-rows");
  status.textContent = "Loading backup files…";
  try {
    const response = await fetch("/api/backups/files", { cache: "no-store", signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error("Backup files are unavailable. Reopen Backups to try again.");
    const { files, directory } = await response.json();
    if (request !== backupFilesRequest) return;
    document.querySelector('#backup-directory span').textContent = directory;
    body.replaceChildren();
    for (const file of files) {
      const row = document.createElement("tr");
      row.dataset.backupId = file.id;
      for (const value of [localTimestamp(file.backupTime), elapsedTime(file.elapsedSeconds), machineLabel(file), file.databaseName, file.filename]) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      }
      const state = document.createElement('td');
      state.dataset.field = 'fileStatus';
      state.textContent = '---';
      const actions = document.createElement('td');
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.textContent = 'Delete Record';
      remove.hidden = true;
      remove.addEventListener('click', () => deleteBackupRecord(row, file.id));
      actions.append(remove);
      row.append(state, actions);
      body.append(row);
    }
    status.textContent = files.length ? "" : "No backup files yet.";
  } catch (error) {
    if (request !== backupFilesRequest) return;
    body.replaceChildren();
    status.textContent = error.message || "Backup files could not be loaded.";
  }
}

async function scanBackupFiles() {
  const button = document.getElementById('scan-backup-files');
  const status = document.getElementById('backup-files-status');
  const request = backupFilesRequest;
  button.disabled = true;
  status.textContent = 'Scanning backup files…';
  for (const row of document.querySelectorAll('#backup-files-rows tr')) {
    row.querySelector('[data-field="fileStatus"]').textContent = '---';
    row.querySelector('button').hidden = true;
  }
  try {
    const response = await fetch('/api/backups/files/scan', { method: 'POST', signal: AbortSignal.timeout(45000) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not scan backup files.');
    if (request !== backupFilesRequest) return;
    const statuses = new Map(result.files.map(file => [String(file.id), file.status]));
    for (const row of document.querySelectorAll('#backup-files-rows tr')) {
      const state = statuses.get(row.dataset.backupId) || '---';
      row.querySelector('[data-field="fileStatus"]').textContent = state;
      row.querySelector('button').hidden = state !== 'Missing';
    }
    status.textContent = 'Filesystem scan complete.';
  } catch (error) {
    if (request === backupFilesRequest) status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function deleteBackupRecord(row, identity) {
  const button = row.querySelector('button');
  const status = document.getElementById('backup-files-status');
  button.disabled = true;
  try {
    const response = await fetch(`/api/backups/files/${identity}`, { method: 'DELETE', signal: AbortSignal.timeout(45000) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not delete the backup record.');
    row.remove();
    status.textContent = 'Backup record deleted.';
    loadBackups();
  } catch (error) {
    status.textContent = error.message;
    button.disabled = false;
  }
}

document.getElementById('scan-backup-files').addEventListener('click', scanBackupFiles);

async function loadBackups() {
  const status = document.getElementById("backups-status");
  const body = document.getElementById("backup-hosts");
  body.replaceChildren();
  status.textContent = "Loading databases…";
  try {
    const response = await fetch("/api/backups", { cache: "no-store", signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error("Databases are unavailable. Return to Inventory and try again.");
    const { databases, hosts: databaseHosts } = await response.json();
    const hosts = new Map(databaseHosts.map(host => [host.machine, host]));
    const groups = new Map(databaseHosts.map(host => [host.machine, []]));
    for (const database of databases) {
      hosts.set(database.machine, database);
      if (!groups.has(database.machine)) groups.set(database.machine, []);
      groups.get(database.machine).push(database);
    }
    const sortedHosts = [...groups.keys()].sort((left, right) =>
      machineLabel(hosts.get(left)).localeCompare(machineLabel(hosts.get(right))));
    const template = document.getElementById("backup-host-template");
    const rowTemplate = document.getElementById("backup-row-template");
    for (const id of sortedHosts) {
      const names = groups.get(id).sort((left, right) => left.databaseName.localeCompare(right.databaseName));
      const host = machineLabel(hosts.get(id));
      const section = template.content.cloneNode(true);
      section.querySelector("summary").textContent = `${host} - ${names.length} DB${names.length === 1 ? "" : "s"}`;
      section.querySelector("table").setAttribute("aria-label", `${host} database backups`);
      section.querySelector(".backup-table-scroll").setAttribute("aria-label", `${host} backup settings`);
      for (const database of names) {
        const name = database.databaseName;
        const row = rowTemplate.content.cloneNode(true);
        row.querySelector('[data-field="database"]').textContent = name;
        row.querySelector('[data-field="enabled"]').setAttribute("aria-label", `Enable backups for ${name} on ${host}`);
        row.querySelector('[data-field="retention"]').setAttribute("aria-label", `Retention for ${name} on ${host}`);
        const element = row.querySelector("tr");
        element.querySelector('[data-field="enabled"]').checked = Boolean(database.enabled);
        element.querySelector('[data-field="retention"]').value = database.retention || "1-week";
        element.querySelector('[data-action="update"]').addEventListener("click", () => updateSchedule(element, database.modelElement));
        element.querySelector('[data-field="lastBackup"]').textContent = database.lastBackup
          ? localTimestamp(database.lastBackup) : "---";
        const button = element.querySelector('[data-action="backup"]');
        button.addEventListener("click", () => backupNow(element, database.modelElement));
        section.querySelector("tbody").append(row);
        if (database.latestBackup) element.dataset.backupId = database.latestBackup;
      }
      section.querySelector(".backup-empty").hidden = names.length > 0;
      section.querySelector(".backup-table-scroll").hidden = names.length === 0;
      body.append(section);
      for (const row of body.querySelectorAll("tr[data-backup-id]")) {
        const identity = row.dataset.backupId;
        delete row.dataset.backupId;
        watchBackup(row, identity);
      }
    }
    status.textContent = groups.size ? "" : "No databases discovered yet.";
  } catch (error) {
    status.textContent = error.message || "Databases could not be loaded. Return to Inventory and try again.";
  }
}

async function updateSchedule(row, modelElement) {
  const button = row.querySelector('[data-action="update"]');
  const enabled = row.querySelector('[data-field="enabled"]');
  const retention = row.querySelector('[data-field="retention"]');
  const status = row.querySelector('.schedule-row-status');
  const settings = { modelElement, enabled: enabled.checked, frequency: "daily", retention: retention.value };
  button.disabled = enabled.disabled = retention.disabled = true;
  status.textContent = "Saving schedule…";
  try {
    const response = await fetch('/api/backup-schedules', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings), signal: AbortSignal.timeout(15000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not save the schedule.");
    status.textContent = result.schedule.enabled ? "Daily schedule saved." : "Schedule disabled.";
  } catch (error) {
    status.textContent = `${error.message} Reopen Backups to check saved settings before retrying.`;
  } finally {
    button.disabled = enabled.disabled = retention.disabled = false;
  }
}

async function backupNow(row, modelElement) {
  const button = row.querySelector('[data-action="backup"]');
  const status = row.querySelector(".backup-row-status");
  button.disabled = true;
  status.textContent = "Processing backup job...";
  try {
    const response = await fetch("/api/backups", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ modelElement }), signal: AbortSignal.timeout(15000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not start the backup.");
    await watchBackup(row, result.backupId, true);
  } catch (error) {
    status.textContent = `${error.message} Reopen Backups to check the recorded status before retrying.`;
    button.disabled = false;
  }
}

async function watchBackup(row, identity, refreshFiles = false) {
  const button = row.querySelector('[data-action="backup"]');
  const status = row.querySelector(".backup-row-status");
  button.disabled = true;
  try {
    while (row.isConnected) {
      const response = await fetch(`/api/backups/${identity}`, { cache: "no-store", signal: AbortSignal.timeout(15000) });
      const backup = await response.json();
      if (!response.ok) throw new Error(backup.error || "Could not read backup status.");
      if (backup.status === "succeeded") {
        row.querySelector('[data-field="lastBackup"]').textContent = localTimestamp(backup.completedOn);
        status.textContent = "Backup completed.";
        if (refreshFiles) loadBackupFiles();
        return;
      }
      if (backup.status === "failed") {
        status.textContent = `Backup failed: ${backup.error || "Unknown error."}`;
        return;
      }
      status.textContent = "Processing backup job...";
      refreshFiles = true;
      button.textContent = "Backing up…";
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  } catch (error) {
    status.textContent = `${error.message} Reopen Backups to check again.`;
  } finally {
    button.disabled = false;
    button.textContent = "Backup Now";
  }
}

function showPage() {
  const backups = window.location.hash === "#backups";
  document.getElementById("backups-heading").hidden = !backups;
  document.getElementById("inventory-heading").hidden = backups;
  document.getElementById("inventory-page").hidden = backups;
  document.getElementById("inventory-footer").hidden = backups;
  document.getElementById("backups-page").hidden = !backups;
  const link = document.getElementById("page-link");
  link.textContent = backups ? "Inventory" : "Backups";
  link.href = backups ? "#inventory" : "#backups";
  document.title = backups ? "Backups — CMDB" : "CMDB";
  if (backups) {
    loadBackups();
    loadBackupFiles();
  }
}

window.addEventListener("hashchange", showPage);
showPage();

async function refreshMachines() {
  if (refreshing) return;
  refreshing = true;
  const refresh = document.getElementById("refresh-button");
  const status = document.getElementById("graph-status");
  refresh.disabled = true;
  refresh.textContent = "Scanning…";
  status.textContent = "Scanning the LAN…";
  try {
    const response = await fetch("/api/scan", { method: "POST", signal: AbortSignal.timeout(15000) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not start a scan.");
    while (true) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      const response = await fetch("/api/scan", { cache: "no-store", signal: AbortSignal.timeout(15000) });
      const scan = await response.json();
      if (!response.ok) throw new Error(scan.error || "Could not check the scan.");
      if (scan.completedScanId >= result.scanId) {
        if (scan.error) throw new Error(scan.error);
        window.location.reload();
        return;
      }
    }
  } catch (error) {
    status.textContent = error.message || "Scan failed. Try again.";
  } finally {
    refreshing = false;
    refresh.disabled = false;
    refresh.textContent = "Refresh";
  }
}

document.getElementById("refresh-button").addEventListener("click", refreshMachines);

function machineLabel(machine) {
  const shortName = machine.hostName ? machine.hostName.split(".")[0] : "";
  return shortName ? shortName.charAt(0).toUpperCase() + shortName.slice(1) : machine.ipAddress;
}

function localTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const pad = number => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
    + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function softwareLabel(system) {
  const name = system.subtype || system.type || "Software";
  const title = name.charAt(0).toUpperCase() + name.slice(1);
  const version = system.subtype === "MariaDB"
    ? system.version?.match(/^(?:5\.5\.5-)?(\d+\.\d+\.\d+)/)?.[1] || system.version
    : system.version;
  return title + (system.codename ? ` (${system.codename})` : "")
    + (version ? ` ${version}` : "");
}

function renderDatabases(cell, names) {
  const systemNames = ["mysql", "information_schema", "performance_schema", "sys"];
  const isSystem = name => systemNames.includes(name.toLowerCase());
  const userDatabases = names.filter(name => !isSystem(name));
  const systemDatabases = names.filter(isSystem).sort((left, right) =>
    systemNames.indexOf(left.toLowerCase()) - systemNames.indexOf(right.toLowerCase()));
  for (const group of [userDatabases, systemDatabases]) {
    for (const name of group) {
      const line = document.createElement("div");
      line.textContent = name;
      cell.append(line);
    }
    if (group === userDatabases && group.length) cell.append(document.createElement("hr"));
  }
}

function compareSoftware(left, right) {
  const order = system => ["OS", "linux"].includes(system.type) ? 0
    : system.type === "DBMS" && system.subtype === "MariaDB" ? 1 : 2;
  return order(left) - order(right) || left.id - right.id;
}

async function loadMachines() {
  const status = document.getElementById("graph-status");
  const details = document.getElementById("machine-details");
  const selectionDetails = document.getElementById("selection-details");
  const softwareDetails = document.getElementById("software-details");
  try {
    if (typeof cytoscape !== "function") {
      throw new Error("The machine graph could not be loaded. Refresh to try again.");
    }
    const response = await fetch("/api/machines", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Machines are unavailable. Refresh to try again.");
    }
    const { machines, softwareDeployments = [] } = await response.json();
    if (!machines.length) {
      status.textContent = "No machines discovered yet.";
      return;
    }
    const elements = [];
    const radius = Math.max(300, machines.length * 380 / (2 * Math.PI));
    machines.forEach((machine, index) => {
      const angle = 2 * Math.PI * index / machines.length - Math.PI / 2;
      const center = { x: radius * Math.cos(angle), y: radius * Math.sin(angle) };
      const systems = softwareDeployments.filter(system => system.machine === machine.id)
        .sort(compareSoftware);
      elements.push({ data: { ...machine, id: machine.ipAddress, label: machineLabel(machine) },
        classes: "machine", position: center });
      systems.forEach((system, offset) => {
        elements.push({ data: { ...system, id: `deployment-${system.id}`,
          parent: machine.ipAddress, label: softwareLabel(system) }, classes: "software",
          selectable: false, grabbable: false,
          position: { x: center.x, y: center.y + (offset - (systems.length - 1) / 2) * 80 } });
      });
    });
    const graph = cytoscape({
      container: document.getElementById("machine-graph"),
      elements,
      style: [
        { selector: "node", style: {
          "background-color": "#082b17", "border-color": "#4ade80", "border-width": 2,
          "width": 160, "height": 160, "label": "data(label)", "color": "#fff",
          "font-size": 16, "font-weight": "bold", "text-valign": "center", "text-halign": "center",
          "text-wrap": "wrap", "text-max-width": 110, "text-overflow-wrap": "anywhere",
        } },
        { selector: ".machine[?hostName]", style: {
          "shape": "round-rectangle", "width": 160, "height": 80,
        } },
        { selector: "node:selected", style: {
          "background-color": "#14532d", "border-color": "#fff", "border-width": 3,
        } },
        { selector: ".machine[!hostName]", style: {
          "background-color": "#3f454b", "border-color": "#9ca3af",
        } },
        { selector: ".machine[!hostName]:selected", style: {
          "background-color": "#5b626a", "border-color": "#fff",
        } },
        { selector: ".machine:parent", style: {
          "shape": "round-rectangle", "padding": 35,
          "text-valign": "top", "text-margin-y": 27, "text-max-width": 240,
        } },
        { selector: ".software", style: {
          "shape": "round-rectangle", "width": 230, "height": 60,
          "background-color": "#123c29", "border-color": "#4ade80",
          "text-max-width": 210,
        } },
      ],
      layout: { name: "preset", padding: 40 },
      selectionType: "single",
      minZoom: 0.1,
      maxZoom: 3,
    });
    function selectMachine(node) {
      if (refreshing) return;
      graph.nodes().unselect();
      node.select();
      for (const field of ["ipAddress", "macAddress", "hostName", "createdOn", "updatedOn"]) {
        const value = field === "createdOn" || field === "updatedOn"
          ? localTimestamp(node.data(field)) : node.data(field) ?? "—";
        document.getElementById(`detail-${field}`).textContent = value;
      }
      selectionDetails.hidden = false;
      details.open = true;
      document.getElementById("machine-heading").textContent = `Machine: ${machineLabel(node.data())}`;
      softwareDetails.replaceChildren();
      const template = document.getElementById("software-detail-template");
      const systems = node.children(".software").map(child => child.data()).sort(compareSoftware);
      for (const system of systems) {
        const section = template.content.cloneNode(true);
        const type = system.type || "Unknown";
        const title = type === "linux" ? "Linux" : type === "DBMS" ? "RDBMS" : type;
        section.querySelector("summary").textContent = `Software System: ${title}`;
        for (const cell of section.querySelectorAll("[data-field]")) {
          if (cell.dataset.field === "codename" && system.subtype === "MariaDB") {
            cell.closest("tr").remove();
          } else if (cell.dataset.field === "databases") {
            if (system.subtype !== "MariaDB") {
              cell.closest("tr").remove();
            } else if (system.databases?.length) {
              renderDatabases(cell, system.databases);
            } else {
              cell.textContent = "—";
            }
          } else {
            cell.textContent = system[cell.dataset.field] ?? "—";
          }
        }
        softwareDetails.append(section);
      }
    }
    graph.on("tap", "node", event => {
      if (refreshing) return;
      const node = event.target;
      selectMachine(node.hasClass("software") ? node.parent() : node);
    });
    new ResizeObserver(() => {
      graph.resize();
      graph.fit(undefined, 40);
    }).observe(document.getElementById("machine-graph"));
    status.textContent = "";
  } catch (error) {
    status.textContent = error.message || "Machines could not be loaded. Refresh to try again.";
  }
}

const lastRefresh = document.getElementById("last-refresh");
lastRefresh.textContent = localTimestamp(lastRefresh.dateTime);
loadMachines();
