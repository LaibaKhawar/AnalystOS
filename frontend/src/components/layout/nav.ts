import {
  BellIcon,
  CalendarDotsIcon,
  ChartLineUpIcon,
  ChatCenteredTextIcon,
  DatabaseIcon,
  FileTextIcon,
  FlaskIcon,
  SquaresFourIcon,
  TableIcon,
  UsersThreeIcon,
  type Icon,
} from '@phosphor-icons/react'

export interface NavItem {
  to: string
  label: string
  icon: Icon
  match: (path: string) => boolean
  /** Shown only to admins. */
  adminOnly?: boolean
  /** Reachable from the command palette but not listed in the sidebar (the bell links to it). */
  paletteOnly?: boolean
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: SquaresFourIcon, match: (p) => p === '/' },
  {
    to: '/datasets',
    label: 'Datasets',
    icon: TableIcon,
    match: (p) => p.startsWith('/datasets') || p.startsWith('/sources'),
  },
  { to: '/connections', label: 'Connections', icon: DatabaseIcon, match: (p) => p.startsWith('/connections') },
  { to: '/workspace', label: 'Workspace', icon: ChatCenteredTextIcon, match: (p) => p.startsWith('/workspace') },
  { to: '/schedules', label: 'Schedules', icon: CalendarDotsIcon, match: (p) => p.startsWith('/schedules') },
  { to: '/reports', label: 'Reports', icon: FileTextIcon, match: (p) => p.startsWith('/reports') },
  { to: '/evaluations', label: 'Evaluations', icon: FlaskIcon, match: (p) => p.startsWith('/evaluations') },
  { to: '/alerts', label: 'Alerts', icon: BellIcon, match: (p) => p.startsWith('/alerts'), paletteOnly: true },
  {
    to: '/admin/users',
    label: 'Users',
    icon: UsersThreeIcon,
    match: (p) => p.startsWith('/admin'),
    adminOnly: true,
  },
]

export function visibleNavItems(isAdmin: boolean, includePaletteOnly = false): NavItem[] {
  return NAV_ITEMS.filter((item) => (isAdmin || !item.adminOnly) && (includePaletteOnly || !item.paletteOnly))
}

export const ANALYTICS_ICON = ChartLineUpIcon
