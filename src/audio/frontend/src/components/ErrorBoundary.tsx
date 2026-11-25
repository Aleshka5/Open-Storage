// Last-resort guard: an uncaught error in render unmounts the whole React tree and leaves a
// blank page — the user then has to reload manually and cannot even tell what happened.
// The boundary turns that into a readable message with a Reload button (chat-and-player.md,
// «If the interface crashes»).

import { Component, type ErrorInfo, type ReactNode } from 'react';
import { strings } from '../strings';

export interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Nothing to report it to, but the console keeps the trace for a bug report.
    console.error('UI crashed:', error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="crash-state" role="alert">
        <h1 className="crash-title">{strings['error.crash_title']}</h1>
        <p className="crash-hint">{strings['error.crash_hint']}</p>
        <p className="crash-detail">{error.message}</p>
        <button type="button" className="btn" onClick={() => window.location.reload()}>
          {strings['error.crash_reload']}
        </button>
      </div>
    );
  }
}

export default ErrorBoundary;
