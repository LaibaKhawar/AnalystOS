/** Props that link a tab panel to its ContinuousTabs trigger. */
export function tabPanelProps(prefix: string, id: string) {
  return { role: 'tabpanel' as const, id: `${prefix}-panel-${id}`, 'aria-labelledby': `${prefix}-tab-${id}` }
}
