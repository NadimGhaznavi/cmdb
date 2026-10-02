"use strict";

let refreshing = false;
let backupFilesRequest = 0;
let patchingTimer;
let patchingRequest = 0;
let patchReportRequest = 0;
let initialUptimePending = false;

function elapsedTime(seconds) {
  const pad = value => String(value).padStart(2, "0");
  return `${pad(Math.floor(seconds / 3600))}:${pad(Math.floor(seconds / 60) % 60)}:${pad(seconds % 60)}`;
}

function backupSize(bytes) {
  if (bytes == null) return '---';
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB'];
  let unit = 0;
  while (bytes >= 1024 && unit < units.length - 1) {
    bytes /= 1024;
    unit += 1;
  }
  return `${unit === 0 ? bytes : bytes.toFixed(1)} ${units[unit]}`;
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
      for (const value of [localTimestamp(file.backupTime), elapsedTime(file.elapsedSeconds), machineLabel(file), file.databaseName, file.filename, backupSize(file.sizeBytes)]) {
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
        element.querySelector('[data-field="expression"]').value = database.expression || '0 12 * * *';
        element.querySelector('[data-field="expression"]').setAttribute('aria-label', `Cron schedule for ${name} on ${host}`);
        element.querySelector('[data-field="retention"]').value = database.retention || "1-week";
        element.querySelector('[data-action="update"]').addEventListener("click", () => updateSchedule(element, database.modelElement));
        element.querySelector('[data-field="lastBackup"]').textContent = database.lastBackup
          ? localTimestamp(database.lastBackup) : "---";
        const button = element.querySelector('[data-action="backup"]');
        button.addEventListener("click", () => backupNow(element, database.modelElement));
        const remove = element.querySelector('[data-action="delete-database"]');
        remove.disabled = name.toLowerCase() === 'cmdb';
        if (remove.disabled) remove.title = 'The CMDB database cannot be deleted.';
        remove.addEventListener('click', () => deleteDatabase(element, database, host));
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

async function deleteDatabase(row, database, host) {
  const confirmation = window.prompt(`Permanently drop database ${database.databaseName} on ${host}? This deletes its data. Type the database name to confirm:`);
  if (confirmation === null) return;
  const status = row.querySelector('.backup-row-status');
  if (confirmation !== database.databaseName) {
    updateText(status, 'Database name did not match. Nothing was deleted.');
    return;
  }
  const controls = [...row.querySelectorAll('button, input, select')];
  const states = controls.map(control => control.disabled);
  controls.forEach(control => { control.disabled = true; });
  updateText(status, 'Deleting database…');
  try {
    const response = await fetch(`/api/databases/${database.modelElement}`, {
      method: 'DELETE', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmation }), signal: AbortSignal.timeout(60000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not delete database.');
    await loadBackups();
  } catch (error) {
    updateText(status, error.message);
    controls.forEach((control, index) => { control.disabled = states[index]; });
  }
}

async function updateSchedule(row, modelElement) {
  const button = row.querySelector('[data-action="update"]');
  const enabled = row.querySelector('[data-field="enabled"]');
  const retention = row.querySelector('[data-field="retention"]');
  const expression = row.querySelector('[data-field="expression"]');
  const status = row.querySelector('.schedule-row-status');
  const settings = { modelElement, enabled: enabled.checked, expression: expression.value, retention: retention.value };
  button.disabled = enabled.disabled = retention.disabled = expression.disabled = true;
  status.textContent = "Saving schedule…";
  try {
    const response = await fetch('/api/backup-schedules', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings), signal: AbortSignal.timeout(15000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not save the schedule.");
    status.textContent = result.schedule.enabled ? "Schedule saved." : "Schedule disabled.";
  } catch (error) {
    status.textContent = `${error.message} Reopen Backups to check saved settings before retrying.`;
  } finally {
    button.disabled = enabled.disabled = retention.disabled = expression.disabled = false;
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

document.getElementById('add-application-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.getElementById('add-application');
  if (button.disabled) return;
  const input = document.getElementById('application-name');
  const name = input.value.trim();
  const status = document.getElementById('add-application-status');
  if (!name) {
    status.textContent = 'Enter an application name.';
    input.focus();
    return;
  }
  button.disabled = true;
  input.disabled = true;
  status.textContent = 'Adding application…';
  try {
    const response = await fetch('/api/applications', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }), signal: AbortSignal.timeout(15000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Application could not be added.');
    status.textContent = `Application “${result.name}” added.`;
    input.value = '';
  } catch (error) {
    status.textContent = error.message || 'Application could not be added.';
  } finally {
    button.disabled = false;
    input.disabled = false;
  }
});

let applicationsRequest = 0;

let applicationRows = [];
let applicationSort = 'host';
let applicationDescending = false;
const applicationCollator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

function renderApplications() {
  const body = document.getElementById('application-rows');
  body.replaceChildren();
  const compare = (left, right, field) => applicationCollator.compare(left[field] ?? '', right[field] ?? '');
  const rows = [...applicationRows].sort((left, right) => {
    const order = compare(left, right, applicationSort) || compare(left, right, 'host')
      || compare(left, right, 'application') || compare(left, right, 'version')
      || compare(left, right, 'pathname');
    return applicationDescending ? -order : order;
  });
  for (const application of rows) {
    const row = document.createElement('tr');
    for (const value of [application.host, application.application, application.version, application.pathname]) {
      const cell = document.createElement('td');
      cell.textContent = value ?? '—';
      row.append(cell);
    }
    body.append(row);
  }
  for (const button of document.querySelectorAll('[data-application-sort]')) {
    const selected = button.dataset.applicationSort === applicationSort;
    if (selected) button.closest('th').setAttribute('aria-sort', applicationDescending ? 'descending' : 'ascending');
    else button.closest('th').removeAttribute('aria-sort');
    button.querySelector('span').textContent = selected ? (applicationDescending ? ' ▼' : ' ▲') : '';
  }
}

for (const button of document.querySelectorAll('[data-application-sort]')) {
  button.addEventListener('click', () => {
    const field = button.dataset.applicationSort;
    applicationDescending = field === applicationSort ? !applicationDescending : false;
    applicationSort = field;
    renderApplications();
  });
}

async function loadApplications() {
  const request = ++applicationsRequest;
  const status = document.getElementById('applications-status');
  applicationRows = [];
  renderApplications();
  status.textContent = 'Loading applications…';
  try {
    const response = await fetch('/api/machines', { cache: 'no-store', signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error('Applications are unavailable. Reopen Applications to try again.');
    const { machines, softwareDeployments } = await response.json();
    if (request !== applicationsRequest) return;
    const hosts = new Map(machines.map(machine => [machine.id, machine]));
    applicationRows = softwareDeployments.map(deployment => {
      const name = deployment.name || deployment.subtype || deployment.type || 'Unknown application';
      return {
        host: hosts.has(deployment.machine) ? machineLabel(hosts.get(deployment.machine)) : `Machine ${deployment.machine}`,
        application: name[0].toUpperCase() + name.slice(1),
        version: deployment.version,
        pathname: deployment.pathname,
      };
    });
    renderApplications();
    status.textContent = applicationRows.length ? '' : 'No deployed applications recorded yet.';
  } catch (error) {
    if (request !== applicationsRequest) return;
    status.textContent = error.message || 'Applications could not be loaded. Reopen Applications to try again.';
  }
}

function showPage() {
  clearTimeout(patchingTimer);
  ++patchingRequest;
  const page = ['applications', 'patching', 'backups'].includes(window.location.hash.slice(1))
    ? window.location.hash.slice(1) : 'inventory';
  const backups = page === 'backups';
  const patching = page === 'patching';
  initialUptimePending = patching;
  for (const name of ['inventory', 'applications', 'patching', 'backups']) {
    document.getElementById(`${name}-heading`).hidden = page !== name;
    document.getElementById(`${name}-page`).hidden = page !== name;
    const link = document.getElementById(name === 'backups' ? 'page-link' : `${name}-link`);
    if (page === name) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  document.getElementById('inventory-footer').hidden = page !== 'inventory';
  document.title = page === 'inventory' ? 'CMDB' : `${page[0].toUpperCase() + page.slice(1)} — CMDB`;
  if (page === 'applications') loadApplications();
  if (patching) loadPatchingHosts();
  if (backups) {
    loadBackups();
    loadBackupFiles();
  }
}

function updateText(element, value) {
  if (element.textContent !== value) element.textContent = value;
}

function updatePatchRows(body, items, render) {
  const existing = new Map([...body.rows].map(row => [row.dataset.id, row]));
  items.forEach((item, index) => {
    const key = String(item.id);
    let row = existing.get(key);
    const isNew = !row;
    if (isNew) {
      row = document.createElement('tr');
      row.dataset.id = key;
    }
    render(row, item, isNew);
    if (body.rows[index] !== row) body.insertBefore(row, body.rows[index] || null);
    existing.delete(key);
  });
  for (const row of existing.values()) row.remove();
}

async function queuePatch(row, identity) {
  const button = row.querySelector('[data-action="patch"]');
  const status = row.querySelector('.patch-row-status');
  updateText(status, 'Queuing patch job…');
  button.disabled = true;
  row.dataset.submitting = 'true';
  clearTimeout(patchingTimer);
  ++patchingRequest;
  try {
    const response = await fetch('/api/patching', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ machine: identity }), signal: AbortSignal.timeout(15000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not queue patch job.');
    updateText(status, 'Queued');
    delete row.dataset.submitting;
    if (window.location.hash === '#patching') loadPatchingHosts();
  } catch (error) {
    updateText(status, `${error.message} Reopen Patching to check job status.`);
    delete row.dataset.submitting;
    button.disabled = false;
  }
}

async function loadPatchingHosts() {
  clearTimeout(patchingTimer);
  loadPatchReport();
  const request = ++patchingRequest;
  const status = document.getElementById('patching-status');
  const body = document.getElementById('patching-hosts');
  try {
    const response = await fetch('/api/patching/hosts', { cache: 'no-store', signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error('Debian hosts are unavailable. Retrying…');
    const { hosts } = await response.json();
    if (request !== patchingRequest) return;
    hosts.sort((left, right) => machineLabel(left).localeCompare(machineLabel(right)));
    updatePatchRows(body, hosts, (row, host, isNew) => {
      if (isNew) {
        const name = document.createElement('td');
        const uptime = document.createElement('td');
        uptime.dataset.field = 'uptime';
        uptime.textContent = '---';
        const enabledCell = document.createElement('td');
        const enabled = document.createElement('input');
        enabled.type = 'checkbox';
        enabled.dataset.field = 'scheduleEnabled';
        enabled.setAttribute('aria-label', `Enable scheduled patching for ${machineLabel(host)}`);
        enabled.addEventListener('change', () => { row.dataset.scheduleDirty = 'true'; });
        enabledCell.append(enabled);
        const scheduleCell = document.createElement('td');
        const expression = document.createElement('input');
        expression.type = 'text';
        expression.size = 20;
        expression.maxLength = 255;
        expression.dataset.field = 'expression';
        expression.setAttribute('aria-label', `Cron schedule for ${machineLabel(host)}`);
        expression.addEventListener('input', () => { row.dataset.scheduleDirty = 'true'; });
        scheduleCell.append(expression);
        const actions = document.createElement('td');
        const buttons = document.createElement('div');
        buttons.className = 'backup-actions';
        const update = document.createElement('button');
        update.type = 'button';
        update.textContent = 'Update';
        update.dataset.action = 'schedule';
        update.addEventListener('click', () => savePatchSchedule(row, host.id));
        const button = document.createElement('button');
        button.type = 'button';
        button.dataset.action = 'patch';
        button.textContent = 'Patch Now';
        button.addEventListener('click', () => queuePatch(row, host.id));
        const progress = document.createElement('td');
        progress.className = 'patch-row-status';
        progress.setAttribute('role', 'status');
        buttons.append(update, button);
        actions.append(buttons);
        row.append(name, uptime, enabledCell, scheduleCell, actions, progress);
      }
      updateText(row.cells[0], machineLabel(host));
      if (!row.dataset.scheduleDirty && !row.dataset.scheduleSaving) {
        const enabled = row.querySelector('[data-field="scheduleEnabled"]');
        enabled.checked = Boolean(host.schedule?.enabled);
        setCronExpression(row, host.schedule?.expression || '');
      }
      const button = row.querySelector('[data-action="patch"]');
      const disabled = Boolean(row.dataset.submitting) || ['queued', 'patching', 'rebooting'].includes(host.job?.status);
      if (button.disabled !== disabled) button.disabled = disabled;
      const labels = { queued: 'Queued', patching: 'Applying updates…', rebooting: 'Waiting for reboot and verification…', succeeded: 'Patched and reboot verified.', failed: 'Patch failed' };
      const jobState = JSON.stringify(host.job ? [host.job.id, host.job.status, host.job.error] : null);
      if (jobState !== row.patchJobState) {
        row.patchJobState = jobState;
        const active = ['queued', 'patching', 'rebooting'].includes(host.job?.status);
        // A repeated poll is not a new message; historical outcomes live in Patch Report.
        if (host.job && (!isNew || active)) {
          updateText(row.querySelector('.patch-row-status'), labels[host.job.status] + (host.job.error ? `: ${host.job.error}` : ''));
        }
      }
    });
    updateText(status, hosts.length ? 'Each successful patch job includes a reboot, even when no updates are available.' : 'No Debian hosts discovered yet.');
    if (initialUptimePending) {
      initialUptimePending = false;
      refreshUptime();
    }
    if (hosts.some(host => ['queued', 'patching', 'rebooting'].includes(host.job?.status))) {
      patchingTimer = setTimeout(loadPatchingHosts, 5000);
    }
  } catch (error) {
    if (request !== patchingRequest) return;
    updateText(status, error.message);
    patchingTimer = setTimeout(loadPatchingHosts, 5000);
  }
}

function setCronExpression(row, value) {
  const expression = row.querySelector('[data-field="expression"]');
  if (expression.value !== value) expression.value = value;
}

async function savePatchSchedule(row, machine) {
  const enabled = row.querySelector('[data-field="scheduleEnabled"]');
  const expression = row.querySelector('[data-field="expression"]');
  const button = row.querySelector('[data-action="schedule"]');
  const status = row.querySelector('.patch-row-status');
  row.dataset.scheduleSaving = 'true';
  enabled.disabled = button.disabled = true;
  expression.disabled = true;
  updateText(status, 'Saving schedule…');
  try {
    const response = await fetch('/api/patch-schedules', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ machine, enabled: enabled.checked, expression: expression.value }),
      signal: AbortSignal.timeout(15000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Could not save patch schedule.');
    enabled.checked = Boolean(result.schedule.enabled);
    setCronExpression(row, result.schedule.expression);
    delete row.dataset.scheduleDirty;
    // Discard any host response started before this save completed.
    ++patchingRequest;
    updateText(status, enabled.checked ? 'Schedule saved.' : 'Schedule disabled.');
    if (window.location.hash === '#patching') loadPatchingHosts();
  } catch (error) {
    updateText(status, error.message);
  } finally {
    delete row.dataset.scheduleSaving;
    enabled.disabled = button.disabled = false;
    expression.disabled = false;
  }
}

async function refreshUptime() {
  const button = document.getElementById('refresh-uptime');
  if (button.disabled) return;
  const status = document.getElementById('uptime-status');
  const rows = [...document.querySelectorAll('#patching-hosts tr')];
  let failures = 0;
  const count = rows.length;
  button.disabled = true;
  updateText(status, 'Refreshing uptime…');
  async function worker() {
    while (rows.length) {
      const row = rows.shift();
      const cell = row.querySelector('[data-field="uptime"]');
      const rowStatus = row.querySelector('.patch-row-status');
      updateText(rowStatus, 'Refreshing uptime…');
      try {
        const response = await fetch(`/api/patching/hosts/${row.dataset.id}/uptime`, { cache: 'no-store', signal: AbortSignal.timeout(15000) });
        if (!response.ok) throw new Error('Uptime unavailable');
        const { uptimeSeconds: seconds } = await response.json();
        const uptime = seconds < 60 ? `${Math.floor(seconds)} secs`
          : seconds < 3600 ? `${Math.floor(seconds / 60)} min`
          : seconds < 86400 ? `${(seconds / 3600).toFixed(1)} hours`
          : `${(seconds / 86400).toFixed(1)} days`;
        updateText(cell, uptime);
        updateText(rowStatus, 'Uptime refreshed');
      } catch (error) {
        failures++;
        updateText(cell, 'Unavailable');
        updateText(rowStatus, 'Host unavailable');
      }
    }
  }
  try {
    await Promise.all(Array.from({ length: Math.min(4, count) }, worker));
    updateText(status, !count ? 'No Debian hosts to refresh.' : failures ? `Uptime refreshed; ${failures} host(s) unavailable.` : 'Uptime refreshed.');
  } finally {
    button.disabled = false;
  }
}

document.getElementById('refresh-uptime').addEventListener('click', refreshUptime);

async function loadPatchReport() {
  const request = ++patchReportRequest;
  const status = document.getElementById('patch-report-status');
  const body = document.getElementById('patch-report-rows');
  try {
    const response = await fetch('/api/patching/report', { cache: 'no-store', signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error('Patch report is unavailable. Reopen Patching to try again.');
    const { runs } = await response.json();
    if (request !== patchReportRequest) return;
    updatePatchRows(body, runs, (row, run, isNew) => {
      if (isNew) {
        for (let index = 0; index < 5; index++) row.append(document.createElement('td'));
      }
      const values = [localTimestamp(run.patchTime), machineLabel(run),
        run.elapsedSeconds == null ? '---' : elapsedTime(run.elapsedSeconds),
        { queued: 'Queued', patching: 'Patching', rebooting: 'Rebooting', succeeded: 'Succeeded', failed: 'Failed' }[run.status],
        run.error || '---'];
      values.forEach((value, index) => updateText(row.cells[index], value));
    });
    updateText(status, runs.length ? 'Most recent 100 patch runs, newest first.' : 'No patch runs yet.');
  } catch (error) {
    if (request !== patchReportRequest) return;
    updateText(status, error.message);
  }
}

window.addEventListener("hashchange", showPage);
showPage();

async function refreshMachines(address = null, applicationsOnly = false) {
  if (refreshing) return;
  refreshing = true;
  const refresh = document.getElementById("refresh-button");
  const rescan = document.getElementById("rescan-machine");
  const applications = document.getElementById("rescan-applications");
  const status = document.getElementById(applicationsOnly ? "application-scan-status" : "graph-status");
  refresh.disabled = true;
  rescan.disabled = true;
  applications.disabled = true;
  const button = applicationsOnly ? applications : address ? rescan : refresh;
  button.textContent = "Scanning…";
  status.textContent = applicationsOnly ? "Scanning applications…"
    : address ? `Scanning ${address}…` : "Scanning the LAN…";
  try {
    const endpoint = applicationsOnly ? "/api/applications/scan"
      : address ? `/api/machines/${address}/scan` : "/api/scan";
    const response = await fetch(endpoint, { method: "POST", signal: AbortSignal.timeout(15000) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not start a scan.");
    while (true) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      const response = await fetch("/api/scan", { cache: "no-store", signal: AbortSignal.timeout(15000) });
      const scan = await response.json();
      if (!response.ok) throw new Error(scan.error || "Could not check the scan.");
      if (scan.completedScanId >= result.scanId) {
        if (scan.error) throw new Error(scan.error);
        if (address) sessionStorage.setItem('rescan-machine', address);
        window.location.reload();
        return;
      }
    }
  } catch (error) {
    status.textContent = error.message || "Scan failed. Try again.";
  } finally {
    refreshing = false;
    refresh.disabled = false;
    rescan.disabled = false;
    applications.disabled = false;
    applications.textContent = "Re-Scan Applications";
    rescan.textContent = "Re-Scan";
    refresh.textContent = "Refresh";
  }
}

document.getElementById("refresh-button").addEventListener("click", () => refreshMachines());
document.getElementById("rescan-applications").addEventListener("click", () => refreshMachines(null, true));
document.getElementById("rescan-machine").addEventListener("click", event => {
  refreshMachines(event.currentTarget.dataset.address);
});

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
  const name = system.name || system.subtype || system.type || "Software";
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
  const theme = getComputedStyle(document.documentElement);
  const palette = Object.fromEntries(["background", "surface", "text", "border", "selection", "danger",
    "software-surface", "software-unnamed", "software-selection", "software-danger"]
    .map(color => [color, theme.getPropertyValue(`--${color}`).trim()]));
  const status = document.getElementById("graph-status");
  const details = document.getElementById("machine-details");
  const selectionDetails = document.getElementById("selection-details");
  const softwareDetails = document.getElementById("software-details");
  const environment = document.getElementById("machine-environment");
  const update = document.getElementById("update-machine");
  const environmentStatus = document.getElementById("machine-environment-status");
  let selectedMachine = null;
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
      elements.push({ data: { ...machine, machineId: machine.id, id: machine.ipAddress, label: machineLabel(machine) },
        classes: machine.reachable === false ? "machine down" : "machine", position: center });
      systems.forEach((system, offset) => {
        elements.push({ data: { ...system, id: `deployment-${system.id}`,
          parent: machine.ipAddress, label: softwareLabel(system) }, classes: "software",
          selectable: false, grabbable: false,
          position: { x: center.x, y: center.y + (offset - (systems.length - 1) / 2) * 110 } });
      });
    });
    const graph = cytoscape({
      container: document.getElementById("machine-graph"),
      elements,
      style: [
        { selector: "node", style: {
          "background-color": palette.surface, "border-color": palette.border, "border-width": 2,
          "width": 160, "height": 160, "label": "data(label)", "color": palette.text,
          "font-size": 24, "font-weight": "bold", "text-valign": "center", "text-halign": "center",
          "text-wrap": "wrap", "text-max-width": 110, "text-overflow-wrap": "anywhere",
        } },
        { selector: ".machine[?hostName]", style: {
          "shape": "round-rectangle", "width": 160, "height": 80,
        } },
        { selector: "node:selected", style: {
          "background-color": palette.selection, "border-color": palette.selection, "border-width": 3,
          "color": palette.text,
        } },
        { selector: ".machine[!hostName]", style: {
          "background-color": palette.text, "border-color": palette.border, "color": palette.background,
        } },
        { selector: ".machine[!hostName]:selected", style: {
          "background-color": palette.selection, "border-color": palette.selection, "color": palette.text,
        } },
        { selector: ".machine:parent", style: {
          "shape": "round-rectangle", "padding": 35,
          "text-valign": "top", "text-margin-y": 27, "text-max-width": 300,
        } },
        { selector: ".software", style: {
          "shape": "round-rectangle", "width": 300, "height": 90,
          "background-color": palette["software-surface"], "border-color": palette.border, "color": palette.text,
          "text-max-width": 280,
        } },
        { selector: ".machine[!hostName] > .software", style: {
          "background-color": palette["software-unnamed"], "color": palette.background,
        } },
        { selector: ".machine.down", style: {
          "background-color": palette.danger, "border-color": palette.border, "color": palette.text,
        } },
        { selector: ".machine.down > .software", style: {
          "background-color": palette["software-danger"], "border-color": palette.border, "color": palette.text,
        } },
        { selector: ".machine.down:selected", style: {
          "border-color": palette.selection, "border-width": 3,
        } },
        { selector: ".machine:selected > .software", style: {
          "background-color": palette["software-selection"], "border-color": palette.selection, "color": palette.text,
        } },
        { selector: ".machine.down:selected > .software", style: {
          "background-color": palette["software-danger"],
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
      selectedMachine = node;
      environment.value = node.data("taggedValue")?.find(tag => tag.tag === "DeploymentEnvironment")?.value
        ?? "unclassified";
      environmentStatus.textContent = "";
      for (const field of ["ipAddress", "macAddress", "hostName", "createdOn", "updatedOn"]) {
        const value = field === "createdOn" || field === "updatedOn"
          ? localTimestamp(node.data(field)) : node.data(field) ?? "—";
        document.getElementById(`detail-${field}`).textContent = value;
      }
      selectionDetails.hidden = false;
      details.open = true;
      document.getElementById("rescan-machine").dataset.address = node.id();
      document.getElementById("machine-heading").textContent = `Machine: ${machineLabel(node.data())}`;
      softwareDetails.replaceChildren();
      const template = document.getElementById("software-detail-template");
      const systems = node.children(".software").map(child => child.data()).sort(compareSoftware);
      for (const system of systems) {
        const section = template.content.cloneNode(true);
        const type = system.name || system.type || "Unknown";
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
    update.addEventListener("click", async () => {
      if (!selectedMachine || update.disabled) return;
      const node = selectedMachine;
      const value = environment.value;
      update.disabled = true;
      environment.disabled = true;
      environmentStatus.textContent = "Saving…";
      try {
        const response = await fetch("/api/machines/environment", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ machine: node.data("machineId"), environment: value }),
          signal: AbortSignal.timeout(15000),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not save the environment. Try again.");
        const tags = (node.data("taggedValue") || []).filter(tag => tag.tag !== "DeploymentEnvironment");
        if (result.environment !== "unclassified") {
          tags.push({ tag: "DeploymentEnvironment", value: result.environment, modelElement: node.data("machineId") });
        }
        node.data("taggedValue", tags);
        if (selectedMachine === node) {
          environment.value = result.environment;
          environmentStatus.textContent = "Environment saved.";
        }
      } catch (error) {
        if (selectedMachine === node) {
          environmentStatus.textContent = error.message || "Could not save the environment. Try again.";
        }
      } finally {
        update.disabled = false;
        environment.disabled = false;
      }
    });
    graph.on("tap", "node", event => {
      if (refreshing) return;
      const node = event.target;
      selectMachine(node.hasClass("software") ? node.parent() : node);
    });
    const rescanned = sessionStorage.getItem('rescan-machine');
    sessionStorage.removeItem('rescan-machine');
    if (rescanned && graph.getElementById(rescanned).length) {
      selectMachine(graph.getElementById(rescanned));
    }
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
