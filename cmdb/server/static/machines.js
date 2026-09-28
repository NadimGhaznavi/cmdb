"use strict";

let refreshing = false;

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
      for (const field of ["ipAddress", "macAddress", "hostName", "deployedComponent", "createdOn", "updatedOn"]) {
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
          cell.textContent = system[cell.dataset.field] ?? "—";
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
