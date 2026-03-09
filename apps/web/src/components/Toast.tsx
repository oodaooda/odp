import { useState, useCallback, useEffect, createContext, useContext } from "react";
import type { ReactNode } from "react";

interface ToastItem {
  id: number;
  message: string;
  type: "info" | "success" | "error" | "warning";
}

interface ToastContextValue {
  toast: (message: string, type?: ToastItem["type"]) => void;
}

const ToastContext = createContext<ToastContextValue>({
  toast: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

let nextId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const toast = useCallback((message: string, type: ToastItem["type"] = "info") => {
    const id = nextId++;
    setItems((prev) => [...prev, { id, message, type }]);
  }, []);

  // Auto-dismiss after 4s
  useEffect(() => {
    if (items.length === 0) return;
    const timer = setTimeout(() => {
      setItems((prev) => prev.slice(1));
    }, 4000);
    return () => clearTimeout(timer);
  }, [items]);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div
        style={{
          position: "fixed",
          bottom: 24,
          right: 24,
          display: "flex",
          flexDirection: "column",
          gap: 8,
          zIndex: 9999,
          pointerEvents: "none",
        }}
      >
        {items.map((item) => (
          <div
            key={item.id}
            style={{
              padding: "10px 18px",
              borderRadius: "var(--radius-sm)",
              fontSize: 13,
              fontWeight: 500,
              color: "#fff",
              background:
                item.type === "success"
                  ? "var(--accent-green)"
                  : item.type === "error"
                  ? "var(--accent-red)"
                  : item.type === "warning"
                  ? "var(--accent-orange)"
                  : "var(--accent-blue)",
              boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
              animation: "toast-in 0.2s ease-out",
              pointerEvents: "auto",
            }}
          >
            {item.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
