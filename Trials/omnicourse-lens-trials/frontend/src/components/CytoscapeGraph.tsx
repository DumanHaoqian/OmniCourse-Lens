import cytoscape, { Core } from "cytoscape";
import fcose from "cytoscape-fcose";
import { Maximize2, RotateCcw, Search } from "lucide-react";
import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react";

try {
  cytoscape.use(fcose);
} catch {
  // Vite hot reload can try to register the extension twice.
}

export type GraphNode = {
  id: string;
  label: string;
  type: string;
  lecture_id?: string;
  timestamp?: number;
  metadata?: Record<string, unknown>;
};

export type GraphEdge = {
  source: string;
  target: string;
  type: string;
  weight: number;
  metadata?: Record<string, unknown>;
};

const nodeTypes = ["course", "lecture", "concept", "formula", "moment", "visual_evidence"];

const typeLabels: Record<string, string> = {
  course: "Course",
  lecture: "Video",
  concept: "Concept",
  formula: "Formula",
  moment: "Moment",
  visual_evidence: "Frame"
};

const colors: Record<string, string> = {
  course: "#0f766e",
  lecture: "#2563eb",
  moment: "#b45309",
  concept: "#7c3aed",
  formula: "#16a34a",
  visual_evidence: "#64748b"
};

const edgeColors: Record<string, string> = {
  contains: "#64748b",
  appears_in: "#7c3aed",
  related_to: "#0f766e",
  prerequisite_of: "#dc2626",
  uses_formula: "#16a34a",
  shown_in_frame: "#64748b",
  explained_by: "#0284c7"
};

export default function CytoscapeGraph({
  nodes,
  edges,
  onSelect
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onSelect: (node: GraphNode) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const [query, setQuery] = useState("");
  const [activeTypes, setActiveTypes] = useState<string[]>(nodeTypes);
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showLabels, setShowLabels] = useState(true);
  const [showEdgeLabels, setShowEdgeLabels] = useState(false);

  const typeCounts = useMemo(() => {
    return nodes.reduce<Record<string, number>>((acc, node) => {
      acc[node.type] = (acc[node.type] || 0) + 1;
      return acc;
    }, {});
  }, [nodes]);

  const visibleGraph = useMemo(() => {
    const typeSet = new Set(activeTypes);
    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    let keptIds = new Set(nodes.filter((node) => typeSet.has(node.type)).map((node) => node.id));
    const normalizedQuery = query.trim().toLowerCase();

    if (normalizedQuery) {
      const matches = new Set(
        nodes
          .filter((node) => {
            const haystack = `${node.label} ${node.type} ${JSON.stringify(node.metadata || {})}`.toLowerCase();
            return haystack.includes(normalizedQuery);
          })
          .map((node) => node.id)
      );
      const expanded = new Set(matches);
      edges.forEach((edge) => {
        if (matches.has(edge.source) || matches.has(edge.target)) {
          expanded.add(edge.source);
          expanded.add(edge.target);
        }
      });
      keptIds = new Set([...keptIds].filter((id) => expanded.has(id)));
    }

    if (focusedId && nodeById.has(focusedId)) {
      const neighborhood = new Set([focusedId]);
      edges.forEach((edge) => {
        if (edge.source === focusedId || edge.target === focusedId) {
          neighborhood.add(edge.source);
          neighborhood.add(edge.target);
        }
      });
      keptIds = new Set([...keptIds].filter((id) => neighborhood.has(id)));
    }

    const graphNodes = nodes.filter((node) => keptIds.has(node.id));
    const graphEdges = edges.filter((edge) => keptIds.has(edge.source) && keptIds.has(edge.target));
    return { nodes: graphNodes, edges: graphEdges };
  }, [activeTypes, edges, focusedId, nodes, query]);

  useEffect(() => {
    if (!containerRef.current) return;
    cyRef.current?.destroy();

    const cy = cytoscape({
      container: containerRef.current,
      elements: [
        ...visibleGraph.nodes.map((node) => ({
          data: {
            ...node,
            shortLabel: compactLabel(node.label, node.type),
            size: nodeSize(node),
            color: colors[node.type] || "#334155"
          },
          classes: ""
        })),
        ...visibleGraph.edges.map((edge, index) => ({
          data: {
            id: `${edge.source}->${edge.target}:${edge.type}:${index}`,
            ...edge,
            label: edge.type.replace(/_/g, " "),
            color: edgeColors[edge.type] || "#94a3b8"
          }
        }))
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            width: "data(size)",
            height: "data(size)",
            label: (ele: any) => {
              const type = String(ele.data("type"));
              if (!showLabels && type !== "course" && type !== "lecture") return "";
              if ((type === "moment" || type === "visual_evidence") && !ele.hasClass("hovered") && !ele.hasClass("spotlight")) return "";
              return ele.data("shortLabel");
            },
            color: "#111827",
            "font-size": (ele: any) => (String(ele.data("type")) === "concept" ? 12 : 10),
            "font-weight": 700,
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.92,
            "text-background-padding": "4px",
            "text-border-color": "#dbe5ef",
            "text-border-width": 1,
            "text-border-opacity": 0.8,
            "text-margin-y": 9,
            "text-wrap": "wrap",
            "text-max-width": "128px",
            "text-valign": "bottom",
            "border-width": 2,
            "border-color": "#ffffff",
            "overlay-opacity": 0
          }
        },
        {
          selector: 'node[type = "formula"]',
          style: {
            shape: "round-rectangle",
            "font-family": "ui-monospace, SFMono-Regular, Menlo, monospace"
          }
        },
        {
          selector: 'node[type = "moment"]',
          style: {
            shape: "diamond"
          }
        },
        {
          selector: 'node[type = "visual_evidence"]',
          style: {
            shape: "tag"
          }
        },
        {
          selector: "edge",
          style: {
            width: (ele: any) => Math.max(1.1, Number(ele.data("weight") || 0.4) * 2.2),
            "line-color": "data(color)",
            "target-arrow-color": "data(color)",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "source-endpoint": "outside-to-node-or-label",
            "target-endpoint": "outside-to-node-or-label",
            opacity: 0.58,
            label: showEdgeLabels ? "data(label)" : "",
            "font-size": "8px",
            color: "#475569",
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.85,
            "text-background-padding": "2px"
          }
        },
        {
          selector: 'edge[type = "prerequisite_of"]',
          style: {
            "line-style": "dashed",
            opacity: 0.84,
            "target-arrow-shape": "triangle"
          }
        },
        {
          selector: ".dimmed",
          style: {
            opacity: 0.13,
            "text-opacity": 0.08
          }
        },
        {
          selector: "edge.dimmed",
          style: {
            opacity: 0.08
          }
        },
        {
          selector: "node.spotlight",
          style: {
            "border-color": "#0f172a",
            "border-width": 5,
            "z-index": 999
          }
        },
        {
          selector: "node.hovered",
          style: {
            label: "data(shortLabel)",
            "z-index": 998
          }
        }
      ] as any,
      minZoom: 0.18,
      maxZoom: 3.2,
      wheelSensitivity: 0.18
    });

    cy.layout({
      name: "fcose",
      quality: "default",
      animate: true,
      animationDuration: 520,
      randomize: false,
      fit: true,
      padding: 80,
      nodeRepulsion: 15000,
      idealEdgeLength: 170,
      edgeElasticity: 0.18,
      nestingFactor: 0.8,
      gravity: 0.08,
      gravityRangeCompound: 1.5,
      gravityCompound: 0.55,
      numIter: 2600,
      tile: true,
      packComponents: true,
      nodeDimensionsIncludeLabels: true
    } as any).run();

    cy.on("mouseover", "node", (event) => event.target.addClass("hovered"));
    cy.on("mouseout", "node", (event) => event.target.removeClass("hovered"));
    cy.on("tap", "node", (event) => {
      const node = event.target;
      const data = node.data() as GraphNode;
      setSelectedId(data.id);
      onSelect(data);
      highlightNeighborhood(cy, node.id());
    });
    cy.on("tap", (event) => {
      if (event.target === cy) {
        setSelectedId(null);
        cy.elements().removeClass("dimmed spotlight");
      }
    });

    const timer = window.setTimeout(() => cy.fit(undefined, 70), 680);
    cyRef.current = cy;
    return () => {
      window.clearTimeout(timer);
      cy.destroy();
      if (cyRef.current === cy) cyRef.current = null;
    };
  }, [onSelect, showEdgeLabels, showLabels, visibleGraph]);

  const fit = () => cyRef.current?.fit(undefined, 70);
  const resetFocus = () => {
    setFocusedId(null);
    setQuery("");
    cyRef.current?.elements().removeClass("dimmed spotlight");
  };
  const focusSelected = () => {
    if (selectedId) setFocusedId(selectedId);
  };

  return (
    <section className="graph-product-panel">
      <div className="graph-toolbar">
        <div className="graph-search">
          <Search size={15} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search nodes, formulas, timestamps..." />
        </div>
        <button type="button" onClick={fit}><Maximize2 size={15} /> Fit</button>
        <button type="button" onClick={focusSelected} disabled={!selectedId}>Focus</button>
        <button type="button" onClick={resetFocus}><RotateCcw size={15} /> Reset</button>
        <label className="graph-toggle"><input type="checkbox" checked={showLabels} onChange={(event) => setShowLabels(event.target.checked)} /> Labels</label>
        <label className="graph-toggle"><input type="checkbox" checked={showEdgeLabels} onChange={(event) => setShowEdgeLabels(event.target.checked)} /> Edges</label>
      </div>

      <div className="graph-type-filter">
        {nodeTypes.map((type) => (
          <button
            key={type}
            type="button"
            className={activeTypes.includes(type) ? "active" : ""}
            style={{ "--type-color": colors[type] } as CSSProperties}
            onClick={() => setActiveTypes((current) => toggleValue(current, type))}
          >
            <span />
            {typeLabels[type]}
            <strong>{typeCounts[type] || 0}</strong>
          </button>
        ))}
      </div>

      <div className="graph-canvas-wrap">
        <div className="cyto-graph" ref={containerRef} />
        <div className="graph-hud">
          {visibleGraph.nodes.length} nodes / {visibleGraph.edges.length} edges
          {focusedId && <span>Focused</span>}
        </div>
      </div>
    </section>
  );
}

function highlightNeighborhood(cy: Core, nodeId: string) {
  const node = cy.getElementById(nodeId);
  cy.elements().addClass("dimmed").removeClass("spotlight");
  node.removeClass("dimmed").addClass("spotlight");
  node.connectedEdges().removeClass("dimmed");
  node.connectedEdges().connectedNodes().removeClass("dimmed");
}

function toggleValue(values: string[], value: string) {
  if (values.includes(value)) {
    return values.filter((item) => item !== value);
  }
  return [...values, value];
}

function nodeSize(node: GraphNode) {
  const frequency = Number(node.metadata?.frequency || 1);
  const importance = Number(node.metadata?.importance || 0.45);
  if (node.type === "course") return 64;
  if (node.type === "lecture") return 54;
  if (node.type === "concept") return Math.round(30 + Math.min(22, frequency * 2.4) + importance * 10);
  if (node.type === "formula") return 42;
  if (node.type === "moment") return 25;
  if (node.type === "visual_evidence") return 22;
  return 30;
}

function compactLabel(label: string, type: string) {
  const max = type === "formula" ? 44 : type === "lecture" ? 38 : 30;
  const clean = String(label || "").replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max).replace(/\s+\S*$/, "")}...`;
}
