'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BrainCircuit, FileText, Zap, Menu, X, MessageSquare, FolderKanban, Settings, GitBranch, Cog } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { clsx } from 'clsx';

const navLinks = [
  { href: '/chat', label: '对话', icon: MessageSquare },
  { href: '/patents', label: '专利管理', icon: FolderKanban },
  { href: '/agents', label: 'Agent管理', icon: Settings },
  { href: '/organization', label: '组织架构', icon: GitBranch },
  { href: '/system-config', label: '系统配置', icon: Cog },
];

export function Navbar() {
  const pathname = usePathname();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 w-full border-b border-hairline bg-canvas/95 backdrop-blur supports-[backdrop-filter]:bg-canvas/60">
      <div className="container mx-auto px-md">
        <div className="flex h-16 items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-green">
              <BrainCircuit className="h-5 w-5 text-ink" />
            </div>
            <span className="font-euclid text-heading-5 font-semibold text-ink">
              专利智脑
            </span>
          </Link>

          {/* Desktop Nav */}
          <nav className="hidden md:flex items-center gap-6">
            {navLinks.map((link) => {
              const isActive = pathname === link.href;
              const Icon = link.icon;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={clsx(
                    'flex items-center gap-1.5 font-euclid text-body-sm-medium transition-colors',
                    isActive
                      ? 'text-brand-green-dark'
                      : 'text-slate hover:text-ink'
                  )}
                >
                  <Icon className="w-4 h-4" />
                  {link.label}
                </Link>
              );
            })}
          </nav>

          <div className="hidden md:flex items-center gap-3">
            <Button size="sm" onClick={() => window.location.href = '/'}>
              开始申请
            </Button>
          </div>

          {/* Mobile Menu Button */}
          <button
            className="md:hidden p-2 rounded-md hover:bg-surface"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
          >
            {isMenuOpen ? (
              <X className="h-5 w-5 text-slate" />
            ) : (
              <Menu className="h-5 w-5 text-slate" />
            )}
          </button>
        </div>

        {/* Mobile Menu */}
        {isMenuOpen && (
          <div className="md:hidden py-md border-t border-hairline">
            <nav className="flex flex-col gap-2">
              {navLinks.map((link) => {
                const isActive = pathname === link.href;
                const Icon = link.icon;
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={() => setIsMenuOpen(false)}
                    className={clsx(
                      'flex items-center gap-2 px-md py-sm rounded-md font-euclid text-body-sm-medium transition-colors',
                      isActive
                        ? 'bg-surface-feature text-brand-green-dark'
                        : 'text-slate hover:bg-surface hover:text-ink'
                    )}
                  >
                    <Icon className="w-4 h-4" />
                    {link.label}
                  </Link>
                );
              })}
              <div className="pt-md mt-md border-t border-hairline flex flex-col gap-2">
                <Button fullWidth onClick={() => { setIsMenuOpen(false); window.location.href = '/'; }}>
                  开始申请
                </Button>
              </div>
            </nav>
          </div>
        )}
      </div>
    </header>
  );
}
