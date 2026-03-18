import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Component } from "react";
export default class ErrorBoundary extends Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }
    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }
    componentDidCatch(error, info) {
        console.error("Overlay error:", error, info);
    }
    render() {
        if (this.state.hasError) {
            return (_jsxs("div", { style: {
                    padding: 20,
                    background: "#1a0a0a",
                    color: "#f87171",
                    borderRadius: 12,
                    margin: 20,
                    fontFamily: "Malgun Gothic, sans-serif",
                }, children: [_jsx("div", { style: { fontSize: 24, marginBottom: 8 }, children: "(x_x)" }), _jsxs("div", { style: { fontSize: 14 }, children: ["\uC5D0\uB7EC \uBC1C\uC0DD: ", this.state.error?.message] }), _jsx("button", { onClick: () => this.setState({ hasError: false, error: null }), style: {
                            marginTop: 12, padding: "8px 16px", borderRadius: 8,
                            border: "1px solid #f87171", background: "transparent",
                            color: "#f87171", cursor: "pointer", fontFamily: "inherit",
                        }, children: "\uB2E4\uC2DC \uC2DC\uB3C4" })] }));
        }
        return this.props.children;
    }
}
