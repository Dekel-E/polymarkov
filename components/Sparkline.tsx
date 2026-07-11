"use client";

export default function Sparkline({
  points,
  width = 260,
  height = 48,
}: {
  points: [number, number][];
  width?: number;
  height?: number;
}) {
  if (points.length < 2) return null;
  const prices = points.map(([, p]) => p);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const path = points
    .map(([, p], i) => {
      const x = (i / (points.length - 1)) * width;
      const y = height - ((p - min) / range) * (height - 6) - 3;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const rising = prices[prices.length - 1] >= prices[0];
  return (
    <svg width={width} height={height} className="overflow-visible" aria-hidden>
      <path d={path} fill="none" stroke={rising ? "#34d399" : "#f87171"} strokeWidth="1.5" />
    </svg>
  );
}
