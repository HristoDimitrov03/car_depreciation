export function ordinaryLeastSquares(
  xs: number[],
  ys: number[],
): { slope: number; intercept: number } | null {
  const n = Math.min(xs.length, ys.length);
  if (n < 2) {
    return null;
  }

  let sumX = 0;
  let sumY = 0;
  let sumXY = 0;
  let sumXX = 0;
  for (let i = 0; i < n; i += 1) {
    const x = xs[i];
    const y = ys[i];
    sumX += x;
    sumY += y;
    sumXY += x * y;
    sumXX += x * x;
  }

  const denom = n * sumXX - sumX * sumX;
  if (denom === 0) {
    return null;
  }

  const slope = (n * sumXY - sumX * sumY) / denom;
  const intercept = (sumY - slope * sumX) / n;
  return { slope, intercept };
}

export function trendlinePoints(
  xs: number[],
  ys: number[],
): { x: number; y: number }[] {
  const fit = ordinaryLeastSquares(xs, ys);
  if (!fit) {
    return [];
  }
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  return [
    { x: minX, y: fit.intercept + fit.slope * minX },
    { x: maxX, y: fit.intercept + fit.slope * maxX },
  ];
}
