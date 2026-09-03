export interface ChartSeries {
  label: string;
  color: string;
  values: number[];
}

/** A small, dependency-free SVG bar chart. Renders only values already
 * present in the data passed to it — no interpolation, no fabricated
 * comparison series. Includes a visually-hidden textual summary so the
 * data is available to screen readers and to anyone who prefers reading
 * numbers over parsing bars. */
export function SimpleBarChart({
  dates,
  series,
  height = 140,
}: {
  dates: string[];
  series: ChartSeries[];
  height?: number;
}) {
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  const barGroupWidth = 100 / Math.max(1, dates.length);

  return (
    <div>
      <svg viewBox={`0 0 100 ${height}`} preserveAspectRatio="none" className="w-full" style={{ height }} role="img" aria-hidden="true">
        {dates.map((_, dayIndex) => {
          const groupX = dayIndex * barGroupWidth;
          const barWidth = barGroupWidth / (series.length + 1);
          return series.map((s, seriesIndex) => {
            const value = s.values[dayIndex] ?? 0;
            const barHeight = (value / max) * (height - 4);
            return (
              <rect
                key={`${dayIndex}-${seriesIndex}`}
                x={groupX + barWidth * (seriesIndex + 0.5)}
                y={height - barHeight}
                width={Math.max(0.5, barWidth * 0.8)}
                height={barHeight}
                fill={s.color}
              />
            );
          });
        })}
      </svg>
      <div className="flex gap-4 mt-2 text-xs text-neutral-500">
        {series.map((s) => (
          <span key={s.label} className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-sm" style={{ background: s.color }} aria-hidden="true" />
            {s.label}
          </span>
        ))}
      </div>
      <table className="sr-only">
        <caption>Daily counts by date</caption>
        <thead>
          <tr>
            <th>Date</th>
            {series.map((s) => (
              <th key={s.label}>{s.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {dates.map((date, i) => (
            <tr key={date}>
              <td>{date}</td>
              {series.map((s) => (
                <td key={s.label}>{s.values[i] ?? 0}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
