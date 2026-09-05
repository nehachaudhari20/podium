import { NavLink } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  BookOpen,
  FlaskConical,
  LayoutDashboard,
  Settings,
  ShieldAlert,
  Users,
  Wallet,
  ScrollText,
  X,
} from 'lucide-react'
import { cn } from '@/lib/format'

const primary = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/recovery', label: 'Recovery', icon: Activity },
  { to: '/customers', label: 'Customers', icon: Users },
  { to: '/revenue-risks', label: 'Revenue Risk', icon: ShieldAlert },
]

const intelligence = [
  { to: '/learning', label: 'Learning', icon: BookOpen },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
]

const tools = [
  { to: '/simulator', label: 'Simulator', icon: FlaskConical },
  { to: '/audit', label: 'Audit Log', icon: ScrollText },
]

function NavSection({
  label,
  items,
  onNavigate,
}: {
  label?: string
  items: typeof primary
  onNavigate?: () => void
}) {
  return (
    <div className="space-y-1">
      {label && (
        <div className="px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-wider text-ink-400">
          {label}
        </div>
      )}
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition',
              isActive
                ? 'bg-podium-50 text-podium-700'
                : 'text-ink-600 hover:bg-ink-100 hover:text-ink-900',
            )
          }
        >
          <item.icon className="h-4 w-4 shrink-0" />
          {item.label}
        </NavLink>
      ))}
    </div>
  )
}

export function Sidebar({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  return (
    <>
      <div
        className={cn(
          'fixed inset-0 z-40 bg-ink-900/30 transition lg:hidden',
          open ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-ink-200 bg-white transition-transform lg:static lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-ink-100 px-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-podium-600 text-sm font-bold text-white">
              P
            </div>
            <div>
              <div className="text-sm font-semibold text-ink-900">Podium</div>
              <div className="text-[11px] text-ink-400">Revenue Recovery</div>
            </div>
          </div>
          <button
            type="button"
            className="rounded-md p-1 text-ink-500 hover:bg-ink-100 lg:hidden"
            onClick={onClose}
            aria-label="Close sidebar"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-3">
          <NavSection items={primary} onNavigate={onClose} />
          <div className="my-3 border-t border-ink-100" />
          <NavSection items={intelligence} onNavigate={onClose} />
          <div className="my-3 border-t border-ink-100" />
          <NavSection items={tools} onNavigate={onClose} />
        </nav>

        <div className="border-t border-ink-100 p-3">
          <NavLink
            to="/settings"
            onClick={onClose}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition',
                isActive
                  ? 'bg-podium-50 text-podium-700'
                  : 'text-ink-600 hover:bg-ink-100 hover:text-ink-900',
              )
            }
          >
            <Settings className="h-4 w-4" />
            Settings
          </NavLink>
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-ink-50 px-3 py-2 text-xs text-ink-500">
            <Wallet className="h-3.5 w-3.5" />
            Adaptive recovery intelligence
          </div>
        </div>
      </aside>
    </>
  )
}
