import { Component, type ReactNode } from "react";

export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main className="center-state" role="alert">
      <h1>AEGIS view could not load</h1>
      <p>Your saved reports remain on the backend. Reload to reconnect.</p>
      <button onClick={() => window.location.reload()}>RELOAD AEGIS</button>
      <a href="/report">OPEN CITIZEN REPORT</a>
    </main>;
    return this.props.children;
  }
}
