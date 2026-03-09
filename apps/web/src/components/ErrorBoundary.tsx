import { Component } from "react";
import type { ReactNode, ErrorInfo } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            padding: 40,
            textAlign: "center",
          }}
        >
          <h2 style={{ color: "var(--accent-red)", marginBottom: 12 }}>
            Something went wrong
          </h2>
          <p className="text-muted" style={{ marginBottom: 16 }}>
            {this.state.error.message}
          </p>
          <button
            className="btn btn-primary"
            onClick={() => {
              this.setState({ error: null });
              window.location.reload();
            }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
