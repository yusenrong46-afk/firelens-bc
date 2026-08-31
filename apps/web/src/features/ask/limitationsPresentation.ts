const BOILERPLATE = [
  /not a safety (?:assessment|determination)/i,
  /uses official records and is not/i,
  /uses stable guidance/i,
  /static corpus cannot establish/i,
  /exact source wording/i,
  /did not substitute/i,
  /general background.*not verified against the FireLens corpus/i,
  /requested high-risk guidance has no reviewed structured claim/i,
];

export function splitLimitations(items: string[]): {
  material: string[];
  boilerplate: string[];
} {
  const material: string[] = [];
  const boilerplate: string[] = [];
  for (const item of items) {
    if (BOILERPLATE.some((pattern) => pattern.test(item))) boilerplate.push(item);
    else material.push(item);
  }
  return { material, boilerplate };
}
