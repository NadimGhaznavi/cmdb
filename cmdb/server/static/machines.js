"use strict";

let refreshing = false;

async function refreshMachines() {
  if (refreshing) return;
  refreshing = true;
  const refresh = document.getElementById("refresh-button");
  const edit = document.getElementById("edit-button");
  const status = document.getElementById("graph-status");
  refresh.disabled = edit.disabled = true;
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
      if (editing || refreshing) return;
      selectedNode = node;
      graph.nodes().unselect();
      node.select();
      for (const field of ["ipAddress", "macAddress", "hostName", "deployedComponent", "createdOn", "updatedOn"]) {
        const value = field === "createdOn" || field === "updatedOn"
          ? localTimestamp(node.data(field)) : node.data(field) ?? "—";
        document.getElementById(`detail-${field}`).textContent = value;
      }
      selectionDetails.hidden = false;
      details.open = true;
      document.getElementById("machine-heading").textContent = `Machine: ${machineLabel(node.data())}`;
      softwareDetails.hidden = true;
      editButton.hidden = false;
      editStatus.textContent = "";
    }
    graph.on("tap", "node", event => {
      if (editing || refreshing) return;
      const node = event.target;
      if (!node.hasClass("software")) {
        selectMachine(node);
        return;
      }
      selectMachine(node.parent());
      const type = node.data("type") || "Unknown";
      const title = type === "linux" ? "Linux" : type === "DBMS" ? "RDBMS" : type;
      document.getElementById("software-heading").textContent = `Software System: ${title}`;
      for (const field of ["type", "subtype", "supplier", "version", "codename"]) {
        document.getElementById(`software-${field}`).textContent = node.data(field) ?? "—";
      }
      softwareDetails.hidden = false;
    });
    function setEditing(value) {
      editing = value;
      hostnameInput.hidden = !value;
      hostnameText.hidden = value;
      editButton.hidden = value || !selectedNode;
      saveButton.hidden = !value;
      cancelButton.hidden = !value;
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
