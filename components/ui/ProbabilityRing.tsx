"use client";
// ProbabilityRing — circular ring showing confidence / probability
// Used for accuracy display and high-confidence picks

interface ProbabilityRingProps {
  value: number;        // 0-1
  label?: string;
  sublabel?: string;
  size?: number;
  color?: string;        // CSS color
  strokeWidth?: number;
  className?: string;
}

export function ProbabilityRing({
  value,
  label,
  sublabel,
  size = 80,
  color = "var(--tint-blue)",
  strokeWidth = 6,
  className = "",
}: ProbabilityRingProps) {
  const clampedValue = Math.max(0, Math.min(1, value));
  const r = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * r;
  const dashOffset = circumference * (1 - clampedValue);
  const cx = size / 2;
  const cy = size / 2;
  const pct = (clampedValue * 100).toFixed(0);

  return (
    <div className={`flex flex-col items-center gap-1 ${className}`}>
      <div className="relative" style={{ width: size, height: size }}>
        {/* Track */}
        <svg
          width={size}
          height={size}
          style={{ transform: "rotate(-90deg)" }}
          aria-hidden="true"
        >
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke="rgba(255,255,255,0.08)"
            strokeWidth={strokeWidth}
          />
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            style={{ transition: "stroke-dashoffset 0.6s cubic-bezier(0.32,0.72,0,1)" }}
          />
        </svg>
        {/* Center text */}
        <div
          className="absolute inset-0 flex flex-col items-center justify-center"
          style={{ padding: strokeWidth }}
        >
          <span
            className="ios-headline font-bold ios-num"
            style={{ color: "var(--label-primary)" }}
          >
            {pct}
          </span>
          <span
            className="ios-caption"
            style={{ color: "var(--label-secondary)" }}
          >
            %
          </span>
        </div>
      </div>
      {label && (
        <span
          className="ios-footnote font-semibold text-center"
          style={{ color: "var(--label-secondary)" }}
        >
          {label}
        </span>
      )}
      {sublabel && (
        <span
          className="ios-caption text-center"
          style={{ color: "var(--label-tertiary)" }}
        >
          {sublabel}
        </span>
      )}
    </div>
  );
}
