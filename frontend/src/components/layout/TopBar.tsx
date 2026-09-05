import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Bell, Menu, Search } from 'lucide-react'
import { services } from '@/services'
import type { AppNotification, SearchResult } from '@/types/domain'
import { formatINR } from '@/lib/format'
import { cn } from '@/lib/format'

export function TopBar({ onMenu }: { onMenu: () => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [searchOpen, setSearchOpen] = useState(false)
  const [notifications, setNotifications] = useState<AppNotification[]>([])
  const [notifOpen, setNotifOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const navigate = useNavigate()
  const searchRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    services.notifications.list().then(setNotifications)
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearchOpen(true)
        document.getElementById('global-search')?.focus()
      }
      if (e.key === 'Escape') {
        setSearchOpen(false)
        setNotifOpen(false)
        setProfileOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      return
    }
    const handle = window.setTimeout(() => {
      services.search.search(query).then(setResults)
    }, 120)
    return () => window.clearTimeout(handle)
  }, [query])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setSearchOpen(false)
      }
    }
    window.addEventListener('mousedown', onClick)
    return () => window.removeEventListener('mousedown', onClick)
  }, [])

  const unread = notifications.filter((n) => !n.read).length

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-ink-200 bg-white/95 px-4 backdrop-blur">
      <button
        type="button"
        className="rounded-md p-2 text-ink-600 hover:bg-ink-100 lg:hidden"
        onClick={onMenu}
        aria-label="Open sidebar"
      >
        <Menu className="h-5 w-5" />
      </button>

      <div className="relative flex-1" ref={searchRef}>
        <div className="relative max-w-xl">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
          <input
            id="global-search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setSearchOpen(true)
            }}
            onFocus={() => setSearchOpen(true)}
            placeholder="Search customers, cases, invoices…"
            className="w-full rounded-lg border border-ink-200 bg-ink-50 py-2 pl-9 pr-16 text-sm text-ink-800 placeholder:text-ink-400 focus:border-podium-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-podium-100"
            aria-label="Global search"
          />
          <kbd className="pointer-events-none absolute right-2 top-1/2 hidden -translate-y-1/2 rounded border border-ink-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-ink-400 sm:inline">
            ⌘K
          </kbd>
        </div>

        {searchOpen && (query.trim() || results.length > 0) && (
          <div className="absolute left-0 right-0 top-full z-50 mt-2 max-w-xl overflow-hidden rounded-xl border border-ink-200 bg-white shadow-panel">
            {results.length === 0 ? (
              <div className="px-4 py-6 text-center text-sm text-ink-500">
                {query.trim() ? 'No matching results' : 'Type to search'}
              </div>
            ) : (
              <ul className="max-h-80 overflow-y-auto py-1">
                {results.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-ink-50"
                      onClick={() => {
                        setSearchOpen(false)
                        setQuery('')
                        navigate(r.href)
                      }}
                    >
                      <div>
                        <div className="text-sm font-medium text-ink-900">{r.title}</div>
                        <div className="text-xs text-ink-500">
                          {r.type} · {r.subtitle}
                        </div>
                      </div>
                      {r.amount !== undefined && (
                        <div className="text-sm font-medium text-ink-700">
                          {formatINR(r.amount)}
                        </div>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span className="hidden items-center rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-amber-700 sm:inline-flex">
          Test Mode
        </span>

        <div className="relative">
          <button
            type="button"
            className="relative rounded-md p-2 text-ink-600 hover:bg-ink-100"
            onClick={() => {
              setNotifOpen((v) => !v)
              setProfileOpen(false)
            }}
            aria-label="Notifications"
          >
            <Bell className="h-5 w-5" />
            {unread > 0 && (
              <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-podium-600" />
            )}
          </button>
          {notifOpen && (
            <div className="absolute right-0 top-full z-50 mt-2 w-80 overflow-hidden rounded-xl border border-ink-200 bg-white shadow-panel">
              <div className="border-b border-ink-100 px-4 py-2.5 text-sm font-semibold text-ink-900">
                Notifications
              </div>
              <ul className="max-h-80 overflow-y-auto">
                {notifications.map((n) => (
                  <li key={n.id}>
                    <Link
                      to={n.href}
                      onClick={() => {
                        services.notifications.markRead(n.id)
                        setNotifications((prev) =>
                          prev.map((x) => (x.id === n.id ? { ...x, read: true } : x)),
                        )
                        setNotifOpen(false)
                      }}
                      className={cn(
                        'block px-4 py-3 hover:bg-ink-50',
                        !n.read && 'bg-podium-50/40',
                      )}
                    >
                      <div className="text-sm font-medium text-ink-900">{n.title}</div>
                      <div className="text-xs text-ink-500">{n.body}</div>
                      <div className="mt-1 text-[11px] text-ink-400">{n.createdAt}</div>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="relative">
          <button
            type="button"
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-ink-100"
            onClick={() => {
              setProfileOpen((v) => !v)
              setNotifOpen(false)
            }}
            aria-label="User menu"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-ink-800 text-xs font-semibold text-white">
              OP
            </div>
            <div className="hidden text-left sm:block">
              <div className="text-xs font-semibold text-ink-800">Ops Lead</div>
              <div className="text-[11px] text-ink-400">Merchant Admin</div>
            </div>
          </button>
          {profileOpen && (
            <div className="absolute right-0 top-full z-50 mt-2 w-48 overflow-hidden rounded-xl border border-ink-200 bg-white py-1 shadow-panel">
              <Link
                to="/settings"
                className="block px-3 py-2 text-sm text-ink-700 hover:bg-ink-50"
                onClick={() => setProfileOpen(false)}
              >
                Settings
              </Link>
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm text-ink-700 hover:bg-ink-50"
                onClick={() => setProfileOpen(false)}
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
