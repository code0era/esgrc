import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('renders the friendly label for a known status', () => {
    render(<StatusBadge status="COMPLETED" />)
    expect(screen.getByText('Completed')).toBeInTheDocument()
  })

  it('maps domain statuses (risk / compliance) to their labels + classes', () => {
    const { container } = render(<StatusBadge status="non_compliant" />)
    expect(screen.getByText('Non-Compliant')).toBeInTheDocument()
    expect(container.querySelector('.badge-danger')).not.toBeNull()
  })

  it('falls back to the raw status text (badge-muted) for an unknown status', () => {
    const { container } = render(<StatusBadge status="totally_unknown" />)
    expect(screen.getByText('totally_unknown')).toBeInTheDocument()
    expect(container.querySelector('.badge-muted')).not.toBeNull()
  })

  it('hides the icon when showIcon={false}', () => {
    const { container } = render(<StatusBadge status="open" showIcon={false} />)
    expect(screen.getByText('Open')).toBeInTheDocument()
    expect(container.querySelector('svg')).toBeNull()
  })

  it('spins the icon for in-progress states', () => {
    const { container } = render(<StatusBadge status="RUNNING" />)
    expect(container.querySelector('svg.animate-spin')).not.toBeNull()
  })
})
