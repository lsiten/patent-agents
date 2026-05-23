# components/ — React Component Library

## Organization
```
components/
├── ui/          (11 files) — Generic reusable UI primitives
├── layout/      (3 files)  — Page-level layout components
└── workflow/    (2 files)  — Patent workflow-specific components
```

## UI Primitives
| Component | Purpose |
|-----------|---------|
| `Button`, `Input`, `Textarea` | Form controls |
| `Card` | Container with consistent padding/shadow |
| `Badge` | Status labels |
| `Tabs` | Tab navigation |
| `Toast` | Notification system (wraps `ToastProvider`) |
| `Skeleton`, `LoadingState` | Loading indicators |
| `EmptyState` | Empty data placeholder |
| `CodeBlock` | Code display with syntax highlight |

## Layout Components
| Component | Used In |
|-----------|---------|
| `Navbar` | Root layout — navigation + auth state |
| `Footer` | Page footer |
| `Hero` | Landing page hero section |

## Workflow Components
| Component | Purpose |
|-----------|---------|
| `steps.tsx` | Multi-step patent workflow progress |
| `results.tsx` | Workflow results display |

## Conventions
- All components are default-exported (consistent with Next.js conventions)
- TypeScript props interfaces co-located in same file
- No component library (shadcn, MUI) — hand-rolled Tailwind
- No storybook — visual testing via browser only
