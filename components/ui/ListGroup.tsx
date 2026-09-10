"use client";
// iOS-style grouped list (Settings-style)
// Usage: <ListGroup header="Section title" footer="Note text"><ListRow>...</ListGroup>

interface ListGroupProps {
  children: React.ReactNode;
  header?: string;
  footer?: string;
  className?: string;
}

export function ListGroup({ children, header, footer, className = "" }: ListGroupProps) {
  return (
    <div className={`space-y-0 ${className}`}>
      {header && <p className="ios-section-header">{header}</p>}
      <div className="ios-list-group overflow-hidden">
        {children}
      </div>
      {footer && <p className="ios-section-footer">{footer}</p>}
    </div>
  );
}

interface ListRowProps {
  children?: React.ReactNode;
  onClick?: () => void;
  href?: string;
  className?: string;
  chevron?: boolean;
  leading?: React.ReactNode;
  trailing?: React.ReactNode;
  secondaryText?: string;
  title?: string;
  badge?: React.ReactNode;
}

export function ListRow({
  children,
  onClick,
  href,
  className = "",
  chevron = false,
  leading,
  trailing,
  secondaryText,
  title,
}: ListRowProps) {
  const content = (
    <>
      {leading && <div className="shrink-0">{leading}</div>}
      <div className="flex-1 min-w-0">
        {title && (
          <p className="ios-body font-normal" style={{ color: "var(--label-primary)" }}>
            {title}
          </p>
        )}
        {children && (
          <div className="ios-body" style={{ color: "var(--label-primary)" }}>
            {children}
          </div>
        )}
        {secondaryText && (
          <p className="ios-subhead mt-0.5" style={{ color: "var(--label-secondary)" }}>
            {secondaryText}
          </p>
        )}
      </div>
      {trailing && <div className="shrink-0 ml-3">{trailing}</div>}
      {chevron && (
        <svg
          className="shrink-0 ml-2"
          width="8"
          height="14"
          viewBox="0 0 8 14"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M1 1L7 7L1 13"
            stroke="rgba(142,142,147,0.4)"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      )}
    </>
  );

  const baseClass = `ios-list-row ios-list-row-hover ${chevron ? "cursor-pointer" : ""} ${className}`;

  if (href) {
    return (
      <a href={href} className={baseClass}>
        {content}
      </a>
    );
  }

  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={`${baseClass} w-full text-left`}>
        {content}
      </button>
    );
  }

  return <div className={baseClass}>{content}</div>;
}
