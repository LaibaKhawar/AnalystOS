import {
  ChartLineUpIcon,
  ChatCenteredTextIcon,
  DatabaseIcon,
  FileTextIcon,
  FlaskIcon,
  SquaresFourIcon,
  TableIcon,
  type Icon,
} from '@phosphor-icons/react'

export interface NavItem {
  to: string
  label: string
  icon: Icon
  match: (path: string) => boolean
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
  { to: '/reports', label: 'Reports', icon: FileTextIcon, match: (p) => p.startsWith('/reports') },
  { to: '/evaluations', label: 'Evaluations', icon: FlaskIcon, match: (p) => p.startsWith('/evaluations') },
]

export const ANALYTICS_ICON = ChartLineUpIcon
