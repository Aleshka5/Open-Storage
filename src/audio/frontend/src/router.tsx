import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom';
import App from './App';
import { Shell } from './components/Shell';

const router = createBrowserRouter([
  {
    path: '/',
    element: <Shell />,
    children: [{ index: true, element: <App /> }],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
