# app/ — Next.js App Router Pages

## Routes (9 pages)
| Path | File | Purpose |
|------|------|---------|
| `/` | `page.tsx` | Landing page |
| `/agents` | `agents/page.tsx` (880L) | Agent chat interaction + streaming |
| `/agent-selector` | `agent-selector/page.tsx` (744L) | Multi-agent selection UI |
| `/dashboard` | `dashboard/page.tsx` | User dashboard |
| `/patents` | `patents/page.tsx` | Patent application list |
| `/patents/[id]` | `patents/[id]/page.tsx` | Single patent detail |
| `/knowledge` | `knowledge/page.tsx` | Knowledge base browser |
| `/settings` | `settings/page.tsx` | User settings |
| `/login` | `login/page.tsx` | Auth page |

## Layout
- Root: `layout.tsx` — Navbar + ToastProvider + global CSS
- No nested layouts — all pages share root layout

## Data Fetching
- Client-side fetching via `fetch()` or custom hooks (NO server components / RSC)
- SSE for real-time agent thinking display (agents page)
- Standard REST calls for CRUD

## Key Patterns
- `"use client"` on all interactive pages
- Forms: controlled components with `useState`
- State: React context (ToastProvider), no global state library
