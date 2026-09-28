"use strict";

let refreshing = false;

async function refreshMachines() {
  if (refreshing) return;
  refreshing = true;
  const refresh = document.getElementById("refresh-button");
  const edit = document.getElementById("edit-button");
  const picker = document.getElementById("machine-picker");
  const status = document.getElementById("graph-status");
  const pickerWasDisabled = picker.disabled;
  refresh.disabled = edit.disabled = picker.disabled = true;
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
    refresh.disabled = edit.disabled = false;
    picker.disabled = pickerWasDisabled;
    refresh.textContent = "Refresh";
  }
}

document.getElementById("refresh-button").addEventListener("click", refreshMachines);

function machineLabel(machine) {
  const shortName = machine.hostName ? machine.hostName.split(".")[0] : "";
  return shortName ? shortName.charAt(0).toUpperCase() + shortName.slice(1) : machine.ipAddress;
}

function machineOption(machine) {
  return machine.hostName ? `${machine.hostName} (${machine.ipAddress})` : machine.ipAddress;
}

function compareMachines(left, right) {
  const leftName = left.hostName ? left.hostName.split(".")[0] : "";
  const rightName = right.hostName ? right.hostName.split(".")[0] : "";
  if (Boolean(leftName) !== Boolean(rightName)) return leftName ? -1 : 1;
  const nameOrder = leftName.localeCompare(rightName, undefined, { sensitivity: "base" });
  if (nameOrder) return nameOrder;
  return left.ipAddress.localeCompare(right.ipAddress, undefined, { numeric: true });
}

function localTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const pad = number => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
    + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

async function loadMachines() {
  const status = document.getElementById("graph-status");
  const picker = document.getElementById("machine-picker");
  const details = document.getElementById("machine-details");
  const editButton = document.getElementById("edit-button");
  const saveButton = document.getElementById("save-button");
  const cancelButton = document.getElementById("cancel-button");
  const refreshButton = document.getElementById("refresh-button");
  const hostnameInput = document.getElementById("hostname-input");
  const hostnameText = document.getElementById("detail-hostName");
  const editStatus = document.getElementById("edit-status");
  let selectedNode = null;
  let editing = false;
  let saving = false;
  try {
    if (typeof cytoscape !== "function") {
      throw new Error("The machine graph could not be loaded. Refresh to try again.");
    }
    const response = await fetch("/api/machines", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Machines are unavailable. Refresh to try again.");
    }
    const { machines } = await response.json();
    if (!machines.length) {
      status.textContent = "No machines discovered yet.";
      return;
    }
    const graph = cytoscape({
      container: document.getElementById("machine-graph"),
      elements: machines.map(machine => ({ data: {
        ...machine, id: machine.ipAddress, label: machineLabel(machine),
      } })),
      style: [
        { selector: "node", style: {
          "background-color": "#082b17", "border-color": "#4ade80", "border-width": 2,
          "width": 160, "height": 160, "label": "data(label)", "color": "#fff",
          "font-size": 16, "font-weight": "bold", "text-valign": "center", "text-halign": "center",
          "text-wrap": "wrap", "text-max-width": 110, "text-overflow-wrap": "anywhere",
        } },
        { selector: "node[?hostName]", style: {
          "shape": "round-rectangle", "width": 160, "height": 80,
        } },
        { selector: "node:selected", style: {
          "background-color": "#14532d", "border-color": "#fff", "border-width": 3,
        } },
        { selector: "node[!hostName]", style: {
          "background-color": "#3f454b", "border-color": "#9ca3af",
        } },
        { selector: "node[!hostName]:selected", style: {
          "background-color": "#5b626a", "border-color": "#fff",
        } },
      ],
      layout: { name: "circle", padding: 40, nodeDimensionsIncludeLabels: true },
      selectionType: "single",
      minZoom: 0.1,
      maxZoom: 3,
    });
    function selectMachine(node) {
      if (editing || refreshing) return;
      selectedNode = node;
      graph.nodes().unselect();
      node.select();
      picker.value = node.id();
      for (const field of ["ipAddress", "macAddress", "hostName", "site", "deployedComponent", "createdOn", "updatedOn"]) {
        const value = field === "createdOn" || field === "updatedOn"
          ? localTimestamp(node.data(field)) : node.data(field) ?? "—";
        document.getElementById(`detail-${field}`).textContent = value;
      }
      details.hidden = false;
      editButton.hidden = false;
      editStatus.textContent = "";
    }
    graph.on("tap", "node", event => selectMachine(event.target));
    function updatePicker() {
      const selected = picker.value;
      while (picker.options.length > 1) picker.remove(1);
      const records = graph.nodes().map(node => node.data()).sort(compareMachines);
      for (const machine of records) {
        const option = document.createElement("option");
        option.value = machine.ipAddress;
        option.textContent = machineOption(machine);
        picker.append(option);
      }
      picker.value = selected;
    }
    updatePicker();
    picker.disabled = false;
    picker.addEventListener("change", () => {
      if (picker.value) {
        selectMachine(graph.getElementById(picker.value));
      } else {
        graph.nodes().unselect();
        details.hidden = true;
        selectedNode = null;
        editButton.hidden = true;
      }
    });
    function setEditing(value) {
      editing = value;
      hostnameInput.hidden = !value;
      hostnameText.hidden = value;
      editButton.hidden = value || !selectedNode;
      saveButton.hidden = !value;
      cancelButton.hidden = !value;
      picker.disabled = value;
      refreshButton.disabled = value;
      graph.autounselectify(value);
    }
    editButton.addEventListener("click", () => {
      hostnameInput.value = selectedNode.data("hostName") ?? "";
      editStatus.textContent = "";
      setEditing(true);
      hostnameInput.focus();
    });
    cancelButton.addEventListener("click", () => {
      if (saving) return;
      setEditing(false);
      editStatus.textContent = "";
      editButton.focus();
    });
    saveButton.addEventListener("click", async () => {
      if (saving || !hostnameInput.reportValidity()) return;
      saving = true;
      saveButton.disabled = cancelButton.disabled = refreshButton.disabled = hostnameInput.disabled = true;
      editStatus.textContent = "Saving…";
      try {
        const response = await fetch("/api/machines/hostname", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ipAddress: selectedNode.id(), hostName: hostnameInput.value }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not save the hostname.");
        const machine = result.machine;
        selectedNode.data({ ...machine, label: machineLabel(machine) });
        updatePicker();
        setEditing(false);
        selectMachine(selectedNode);
        editStatus.textContent = "Hostname saved.";
        editButton.focus();
      } catch (error) {
        editStatus.textContent = error.message || "Could not save the hostname. Try again.";
      } finally {
        saving = false;
        saveButton.disabled = cancelButton.disabled = refreshButton.disabled = hostnameInput.disabled = false;
      }
    });
    hostnameInput.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === "Escape") {
        event.preventDefault();
        (event.key === "Enter" ? saveButton : cancelButton).click();
      }
    });
    new ResizeObserver(() => {
      graph.resize();
      graph.layout({ name: "circle", padding: 40, nodeDimensionsIncludeLabels: true }).run();
    }).observe(document.getElementById("machine-graph"));
    status.textContent = "";
  } catch (error) {
    status.textContent = error.message || "Machines could not be loaded. Refresh to try again.";
  }
}

const lastRefresh = document.getElementById("last-refresh");
lastRefresh.textContent = localTimestamp(lastRefresh.dateTime);
loadMachines();
