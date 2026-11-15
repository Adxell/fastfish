export function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export function percentOf(cents: number, percent: number): number {
  return Math.round((cents * percent) / 100);
}
