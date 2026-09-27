import { cn } from '@/lib/utils'
import { CheckCircle2, XCircle, Clock, AlertTriangle, MinusCircle, Loader2 } from 'lucide-react'
import type { RunStatus, StepStatus } from '@/store/pipeline'

type StatusType = RunStatus | StepStatus | string

const STATUS_CONFIG: Record<string, { label: string; className: string; Icon: React.ElementType }> = {
  COMPLETED:   { label:'Completed',   className:'badge-success',  Icon: CheckCircle2  },
  RUNNING:     { label:'Running',     className:'badge-primary',  Icon: Loader2       },
  PENDING:     { label:'Pending',     className:'badge-muted',    Icon: Clock         },
  FAILED:      { label:'Failed',      className:'badge-danger',   Icon: XCircle       },
  CANCELLED:   { label:'Cancelled',   className:'badge-muted',    Icon: MinusCircle   },
  SKIPPED:     { label:'Skipped',     className:'badge-muted',    Icon: MinusCircle   },
  // Compliance statuses
  compliant:      { label:'Compliant',     className:'badge-success', Icon: CheckCircle2 },
  partial:        { label:'Partial',       className:'badge-warning', Icon: AlertTriangle },
  non_compliant:  { label:'Non-Compliant', className:'badge-danger',  Icon: XCircle      },
  not_assessed:   { label:'Not Assessed',  className:'badge-muted',   Icon: Clock        },
  // Risk statuses
  open:           { label:'Open',          className:'badge-danger',  Icon: XCircle      },
  in_progress:    { label:'In Progress',   className:'badge-warning', Icon: Loader2      },
  mitigated:      { label:'Mitigated',     className:'badge-success', Icon: CheckCircle2 },
  closed:         { label:'Closed',        className:'badge-muted',   Icon: MinusCircle  },
}

interface StatusBadgeProps {
  status: StatusType
  showIcon?: boolean
  className?: string
}

export function StatusBadge({ status, showIcon = true, className }: StatusBadgeProps) {
  const cfg = STATUS_CONFIG[status] ?? { label: status, className: 'badge-muted', Icon: Clock }
  const { label, className: cls, Icon } = cfg

  return (
    <span className={cn(cls, className)}>
      {showIcon && (
        <Icon
          size={11}
          className={status === 'RUNNING' || status === 'in_progress' ? 'animate-spin' : ''}
        />
      )}
      {label}
    </span>
  )
}
