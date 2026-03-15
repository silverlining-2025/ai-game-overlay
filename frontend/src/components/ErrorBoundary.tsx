import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Overlay error:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: 20,
          background: "#1a0a0a",
          color: "#f87171",
          borderRadius: 12,
          margin: 20,
          fontFamily: "Malgun Gothic, sans-serif",
        }}>
          <div style={{ fontSize: 24, marginBottom: 8 }}>(x_x)</div>
          <div style={{ fontSize: 14 }}>에러 발생: {this.state.error?.message}</div>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              marginTop: 12, padding: "8px 16px", borderRadius: 8,
              border: "1px solid #f87171", background: "transparent",
              color: "#f87171", cursor: "pointer", fontFamily: "inherit",
            }}
          >
            다시 시도
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
