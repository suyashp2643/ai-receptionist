/** A simple, honest architecture diagram — plain boxes and arrows built
 * with SVG, describing the real request flow, not a misleading animation
 * or a stock "AI brain" illustration. */
export function ArchitectureDiagram() {
  const boxes = [
    { x: 10, y: 10, w: 160, h: 60, label: "Visitor's browser", sub: "Embedded widget" },
    { x: 220, y: 10, w: 160, h: 60, label: "Public widget API", sub: "Capability-token scoped" },
    { x: 430, y: 10, w: 160, h: 60, label: "Conversation engine", sub: "Retrieval + safety + Mock AI" },
    { x: 220, y: 120, w: 160, h: 60, label: "Your knowledge base", sub: "FAQs & documents" },
    { x: 430, y: 120, w: 160, h: 60, label: "Structured records", sub: "Contacts, enquiries, appointments" },
    { x: 640, y: 65, w: 160, h: 60, label: "Operations dashboard", sub: "Your staff" },
  ];
  return (
    <svg
      viewBox="0 0 830 210"
      className="w-full"
      role="img"
      aria-label="Diagram: a visitor's browser talks to the public widget API, which uses the conversation engine, grounded in your knowledge base, to produce structured records that appear in your operations dashboard for staff."
    >
      {boxes.map((b) => (
        <g key={b.label}>
          <rect
            x={b.x}
            y={b.y}
            width={b.w}
            height={b.h}
            rx={10}
            fill="#171b2e"
            stroke="#2a2f4a"
            strokeWidth={1.5}
          />
          <text x={b.x + b.w / 2} y={b.y + 26} textAnchor="middle" fill="#fff" fontSize="13" fontWeight={600}>
            {b.label}
          </text>
          <text x={b.x + b.w / 2} y={b.y + 44} textAnchor="middle" fill="#9ca3c2" fontSize="11">
            {b.sub}
          </text>
        </g>
      ))}
      {/* arrows */}
      <defs>
        <marker id="arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#8b5cf6" />
        </marker>
      </defs>
      <line x1="170" y1="40" x2="215" y2="40" stroke="#8b5cf6" strokeWidth="2" markerEnd="url(#arrowhead)" />
      <line x1="380" y1="40" x2="425" y2="40" stroke="#8b5cf6" strokeWidth="2" markerEnd="url(#arrowhead)" />
      <line x1="300" y1="70" x2="300" y2="115" stroke="#22d3ee" strokeWidth="2" markerEnd="url(#arrowhead)" />
      <line x1="510" y1="70" x2="510" y2="115" stroke="#22d3ee" strokeWidth="2" markerEnd="url(#arrowhead)" />
      <line x1="590" y1="130" x2="635" y2="95" stroke="#8b5cf6" strokeWidth="2" markerEnd="url(#arrowhead)" />
    </svg>
  );
}
