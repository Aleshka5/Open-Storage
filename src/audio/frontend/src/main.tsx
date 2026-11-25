import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './theme.css';
import './app.css';
import App from './App';
import { ErrorBoundary } from './components/ErrorBoundary';

// The boundary is outside App: a render error anywhere in the tree must show a message,
// not a blank page.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
