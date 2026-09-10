"use client";
// iOS Badge component — tint-colored pill
// Usage: <Badge color="blue">Local</Badge>

interface BadgeProps {
  children: React.ReactNode;
  color?: "blue" | "green" | "red" | "orange" | "yellow" | "purple" | "neutral";
  size?: "sm" | "md";
  className?: string;
}

const colorMap = {
  blue:    "bg-[rgba(10,132,255,0.15)] text-[#0A84FF]",
  green:   "bg-[rgba(48,209,88,0.15)] text-[#30D158]",
  red:     "bg-[rgba(255,69,58,0.15)] text-[#FF453A]",
  orange:  "bg-[rgba(255,159,10,0.15)] text-[#FF9F0A]",
  yellow:  "bg-[rgba(255,214,10,0.15)] text-[#FFD60A]",
  purple:  "bg-[rgba(191,90,242,0.15)] text-[#BF5AF2]",
  neutral: "bg-[rgba(142,142,147,0.18)] text-[rgba(235,235,245,0.60)]",
};

export function Badge({
  children,
  color = "neutral",
  size = "md",
  className = "",
}: BadgeProps) {
  const sizeClass = size === "sm" ? "px-1.5 py-px text-[10px]" : "px-2 py-0.5 text-[11px]";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md font-semibold tracking-tight whitespace-nowrap ${sizeClass} ${colorMap[color]} ${className}`}
    >
      {children}
    </span>
  );
}
