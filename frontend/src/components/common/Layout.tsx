import type { ReactNode } from 'react';
import AppShell from '../../layouts/AppShell';

interface LayoutProps {
  children?: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return <AppShell>{children}</AppShell>;
}
