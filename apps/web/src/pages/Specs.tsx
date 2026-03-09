import { useParams } from "react-router-dom";

const SPEC_DOCS = [
  { id: "01_PRD", title: "Product Requirements Document", desc: "Defines the product vision, user personas, and feature requirements" },
  { id: "02_SRD", title: "System Requirements Document", desc: "Multi-process reliability, performance, security, scalability, observability" },
  { id: "03_PDR", title: "Preliminary Design Review", desc: "High-level architecture, component boundaries, technology choices" },
  { id: "04_ICD", title: "Interface Control Document", desc: "Redis schemas, Postgres models, API contracts between components" },
  { id: "05_DDR", title: "Detailed Design Review", desc: "State machine, retry logic, git operations, workspaces, memory model" },
  { id: "06_VV_PLAN", title: "Verification & Validation Plan", desc: "Test strategy, gate criteria, evidence requirements per phase" },
  { id: "07_SECURITY", title: "Security Architecture", desc: "Threat model, auth/RBAC design, secret management, path traversal prevention" },
  { id: "08_DECISIONS", title: "Design Decisions & Trade-offs", desc: "ADRs for key architectural choices and their rationale" },
  { id: "09_RUNBOOK", title: "Operations Runbook", desc: "Incident response, common failure modes, recovery procedures" },
  { id: "10_SLOS", title: "Service Level Objectives", desc: "Latency, throughput, availability targets and measurement" },
  { id: "11_CONFIG_SECRETS", title: "Configuration & Secrets", desc: "Environment variables, token management, deployment config" },
  { id: "12_HANDOFF", title: "Handoff Documentation", desc: "Knowledge transfer, onboarding guide, known issues" },
];

const MILESTONES = [
  { id: "M1", title: "Orchestrator Lifecycle + Gated Flow", status: "complete" },
  { id: "M2", title: "Agent Execution + Infrastructure", status: "complete" },
  { id: "M3", title: "Agent Memory + Promotion Workflow", status: "complete" },
  { id: "M4", title: "Chat Compaction + Vector Index", status: "complete" },
  { id: "M5", title: "Embeddings + Git Hardening + UI", status: "complete" },
  { id: "M6", title: "Retrieval + Merge Automation + UI", status: "complete" },
  { id: "M7", title: "Production Hardening", status: "complete" },
  { id: "M8", title: "UI Parity with Prototypes", status: "complete" },
  { id: "M9", title: "React SPA Frontend", status: "complete" },
  { id: "M10", title: "Frontend Polish & Real-Time", status: "in-progress" },
  { id: "M11", title: "Agent Orchestration End-to-End", status: "planned" },
  { id: "M12", title: "Production Deployment", status: "planned" },
];

export default function Specs() {
  const { projectId: _ } = useParams();

  return (
    <>
      <div className="page-header">
        <h2>Specs & Milestones</h2>
      </div>

      {/* Milestones */}
      <div className="card mb-20">
        <h3>Milestones</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Title</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {MILESTONES.map((m) => (
              <tr key={m.id}>
                <td className="mono" style={{ fontWeight: 600 }}>{m.id}</td>
                <td>{m.title}</td>
                <td>
                  <span
                    className={`status ${
                      m.status === "complete"
                        ? "status-passed"
                        : m.status === "in-progress"
                        ? "status-running"
                        : "status-pending"
                    }`}
                  >
                    {m.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Spec documents */}
      <div className="card">
        <h3>Specification Documents (12-Doc Stack)</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>File</th>
              <th>Title</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {SPEC_DOCS.map((s) => (
              <tr key={s.id}>
                <td className="mono" style={{ fontWeight: 500 }}>{s.id}.md</td>
                <td>{s.title}</td>
                <td className="text-muted">{s.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
