import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useRef } from "react";

cytoscape.use(fcose);

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
};

const colors: Record<string, string> = {
  course: "#1f7a5f",
  lecture: "#245f73",
  moment: "#9a6a20",
  concept: "#8a3f78",
  formula: "#536d1f",
  visual_evidence: "#64748b"
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
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const cy = cytoscape({
      container: ref.current,
      elements: [
        ...nodes.map((node) => ({ data: { ...node, size: node.type === "concept" ? 38 : node.type === "lecture" ? 46 : 32 } })),
        ...edges.map((edge, index) => ({ data: { id: `e${index}`, ...edge } }))
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": (ele: any) => colors[String(ele.data("type"))] || "#334155",
            width: "data(size)",
            height: "data(size)",
            label: (ele: any) => {
              const type = String(ele.data("type"));
              const label = String(ele.data("label") || "");
              return type === "moment" || type === "visual_evidence" ? "" : label.length > 34 ? `${label.slice(0, 31)}...` : label;
            },
            color: "#142033",
            "font-size": "11px",
            "text-background-color": "#ffffff",
            "text-background-opacity": 0.9,
            "text-background-padding": "3px",
            "text-margin-y": -9,
            "text-wrap": "wrap",
            "text-max-width": "120px",
            "border-width": 2,
            "border-color": "#ffffff",
            "overlay-opacity": 0
          }
        },
        {
          selector: "edge",
          style: {
            width: (ele: any) => Math.max(1, Number(ele.data("weight") || 0.4) * 2.5),
            "line-color": "#b7c4d4",
            "target-arrow-color": "#b7c4d4",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            opacity: 0.72,
            label: "",
            "font-size": "9px"
          }
        },
        {
          selector: "node:selected",
          style: {
            "border-width": 5,
            "border-color": "#111827"
          }
        }
      ] as any,
      minZoom: 0.22,
      maxZoom: 2.8
    });
    cy.layout({
      name: "fcose",
      quality: "default",
      animate: true,
      animationDuration: 450,
      randomize: false,
      fit: true,
      padding: 70,
      nodeRepulsion: 9000,
      idealEdgeLength: 130,
      edgeElasticity: 0.24,
      nestingFactor: 0.9,
      gravity: 0.16,
      nodeDimensionsIncludeLabels: true
    } as any).run();
    cy.on("tap", "node", (event) => {
      const data = event.target.data();
      onSelect(data as GraphNode);
    });
    const timer = window.setTimeout(() => cy.fit(undefined, 70), 700);
    return () => {
      window.clearTimeout(timer);
      cy.destroy();
    };
  }, [nodes, edges, onSelect]);

  return <div className="cyto-graph" ref={ref} />;
}
