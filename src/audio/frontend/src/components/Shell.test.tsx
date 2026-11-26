import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { Shell } from './Shell';

function renderShell() {
  const router = createMemoryRouter([{ path: '/', element: <Shell /> }], { initialEntries: ['/'] });
  return render(<RouterProvider router={router} />);
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('{}', { status: 401, headers: { 'Content-Type': 'application/json' } })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Shell', () => {
  it('shows the hub sign-in when the API answers 401', async () => {
    renderShell();
    expect(await screen.findByRole('link', { name: 'Sign in' })).toBeTruthy();
    expect(screen.getByText('Open this site through the hub. Audio does not handle sign-in.')).toBeTruthy();
    expect(screen.getByRole('radiogroup', { name: 'Theme' })).toBeTruthy();
    const signIn = screen.getByRole('link', { name: 'Sign in' });
    expect(signIn.getAttribute('href')).toContain('https://filenkov.store/auth?return_to=');
  });
});
