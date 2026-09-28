"use strict";

async function loadMachines() {
  const status = document.getElementById("graph-status");
  const picker = document.getElementById("machine-picker");
  const details = document.getElementById("machine-details");
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
      elements: machines.map(machine => {
        const shortName = machine.hostName ? machine.hostName.split(".")[0] : "";
        const name = shortName ? shortName.charAt(0).toUpperCase() + shortName.slice(1) : "";
        return { data: {
          ...machine,
          id: machine.ipAddress,
          label: name || machine.ipAddress,
        } };
      }),
      style: [
        { selector: "node", style: {
          "background-color": "#14532d", "border-color": "#4ade80", "border-width": 2,
          "width": 160, "height": 160, "label": "data(label)", "color": "#fff",
          "font-size": 18, "font-weight": "bold", "text-valign": "center", "text-halign": "center",
          "text-wrap": "wrap", "text-max-width": 110, "text-overflow-wrap": "anywhere",
        } },
        { selector: "node:selected", style: {
          "background-color": "#166534", "border-color": "#fff", "border-width": 3,
        } },
      ],
      layout: { name: "circle", padding: 40, nodeDimensionsIncludeLabels: true },
      selectionType: "single",
      minZoom: 0.1,
      maxZoom: 3,
    });
    function selectMachine(node) {
      graph.nodes().unselect();
      node.select();
      picker.value = node.id();
      for (const field of ["ipAddress", "hostName", "site", "deployedComponent", "createdOn", "updatedOn"]) {
        document.getElementById(`detail-${field}`).textContent = node.data(field) ?? "—";
      }
      details.hidden = false;
    }
    graph.on("tap", "node", event => selectMachine(event.target));
    for (const machine of machines) {
      const option = document.createElement("option");
      option.value = machine.ipAddress;
      option.textContent = machine.hostName ? `${machine.hostName} (${machine.ipAddress})` : machine.ipAddress;
      picker.append(option);
    }
    picker.disabled = false;
    picker.addEventListener("change", () => {
      if (picker.value) {
        selectMachine(graph.getElementById(picker.value));
      } else {
        graph.nodes().unselect();
        details.hidden = true;
      }
    });
    new ResizeObserver(() => {
      graph.resize();
      graph.layout({ name: "circle", padding: 40, nodeDimensionsIncludeLabels: true }).run();
    }).observe(document.getElementById("machine-graph"));
    status.textContent = `${machines.length} machine${machines.length === 1 ? "" : "s"} · Select a node to view details`;
  } catch (error) {
    status.textContent = error.message || "Machines could not be loaded. Refresh to try again.";
  }
}

loadMachines();
