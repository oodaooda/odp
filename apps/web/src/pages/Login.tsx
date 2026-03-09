import { useState } from "react";

interface LoginProps {
  onLogin: (token: string) => void;
}

export default function Login({ onLogin }: LoginProps) {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) return;
    setLoading(true);
    setError("");

    try {
      const res = await fetch("/projects/default/tasks", {
        headers: { Authorization: `Bearer ${token.trim()}` },
      });
      if (res.status === 401) {
        setError("Invalid token. Check your API token and try again.");
        setLoading(false);
        return;
      }
      // Token is valid — store and proceed.
      localStorage.setItem("odp_token", token.trim());
      onLogin(token.trim());
    } catch {
      setError("Cannot reach the ODP server. Is it running?");
    }
    setLoading(false);
  };

  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      minHeight: "100vh", background: "var(--bg-base)",
    }}>
      <div className="card" style={{ width: 400, padding: 32 }}>
        <h1 style={{ fontSize: 24, marginBottom: 4 }}>ODP</h1>
        <p className="text-muted" style={{ marginBottom: 24 }}>
          Orchestrated Dev Platform
        </p>
        <form onSubmit={handleSubmit}>
          <label className="text-sm text-muted" style={{ display: "block", marginBottom: 6 }}>
            API Token
          </label>
          <input
            type="password"
            style={{
              width: "100%", boxSizing: "border-box",
              background: "var(--bg-input)", border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)", padding: "10px 12px",
              color: "var(--text-primary)", fontSize: 14, outline: "none",
              marginBottom: 12,
            }}
            placeholder="Enter your API token..."
            value={token}
            onChange={(e) => setToken(e.target.value)}
            autoFocus
          />
          {error && (
            <p style={{ color: "var(--accent-red)", fontSize: 13, marginBottom: 12 }}>
              {error}
            </p>
          )}
          <button
            className="btn btn-primary"
            style={{ width: "100%", padding: "10px 0" }}
            disabled={loading || !token.trim()}
          >
            {loading ? "Verifying..." : "Sign In"}
          </button>
        </form>
        <p className="text-muted text-sm" style={{ marginTop: 16 }}>
          Set <code>ODP_API_TOKEN</code> on the server to enable auth.
          Without it, no token is required.
        </p>
      </div>
    </div>
  );
}
