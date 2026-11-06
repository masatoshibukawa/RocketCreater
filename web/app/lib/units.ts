/** Heights and masses that read at any scale, from a 20 m bottle flight to a 400 km orbit.
 * No imports, so that node can run the tests of this file directly. */

const num = (value: number, digits: number): string =>
  value.toLocaleString("ja-JP", { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** Metres below 1 km, kilometres from there on. */
export function fmtAltitude(m: number): string {
  if (!Number.isFinite(m)) return "-";
  const [value, unit] = Math.abs(m) >= 1000 ? [m / 1000, "km"] : [m, "m"];
  return `${num(value, Number.isInteger(value) ? 0 : 1)} ${unit}`;
}

/** Grams below 1 kg, kilograms from there on. */
export function fmtMass(kg: number): string {
  if (!Number.isFinite(kg)) return "-";
  if (Math.abs(kg) < 1) return `${num(kg * 1000, 0)} g`;
  return `${num(kg, Number.isInteger(kg) ? 0 : Math.abs(kg) < 10 ? 3 : 1)} kg`;
}
