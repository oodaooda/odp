import type { TaskState } from "../api/types";

const STATES: TaskState[] = ["INIT", "DISPATCH", "COLLECT", "VALIDATE", "COMMIT/ROLLBACK" as TaskState];
const STATE_ORDER: Record<string, number> = {
  INIT: 0,
  DISPATCH: 1,
  COLLECT: 2,
  VALIDATE: 3,
  COMMIT: 4,
  ROLLBACK: 4,
};

export default function StateTimeline({ current }: { current: TaskState }) {
  const idx = STATE_ORDER[current] ?? -1;

  return (
    <div className="timeline">
      {STATES.map((s, i) => {
        const reached = i <= idx;
        const isCurrent = i === idx;
        return (
          <div key={s} className="timeline-step">
            <span
              className={`timeline-dot ${reached ? "reached" : ""} ${isCurrent ? "current" : ""}`}
            />
            <span className="timeline-label">{s}</span>
            {i < STATES.length - 1 && (
              <span className={`timeline-line ${i < idx ? "reached" : ""}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
