import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './fonts.css';
import './theme.css';
import './app.css';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AppRouter } from './router';

// The boundary is outside the router: a render error anywhere in the tree must show a message,
// not a blank page.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <AppRouter />
    </ErrorBoundary>
  </StrictMode>,
);
