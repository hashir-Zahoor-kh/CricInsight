/**
 * Country name → flag emoji map.
 *
 * Generates regional-indicator-symbol pairs from ISO 3166 alpha-2
 * codes. Cricket-relevant nations are mapped explicitly; for anything
 * else the helper falls back to a cricket-bat glyph rather than a
 * blank cell so the dropdown row never looks broken.
 *
 * West Indies and England get special treatment:
 *   - West Indies isn't a single country; cricsheet uses "West Indies"
 *     for the regional team, so we use the cricket-bat glyph instead
 *     of picking one Caribbean flag.
 *   - England plays as a separate cricket nation from the UK; use the
 *     St George's cross sub-region flag rather than the Union Jack.
 */

const A = 0x1f1e6; // unicode regional indicator A

function flagFromCode(code2: string): string {
  // Two regional-indicator code points → flag emoji.
  if (code2.length !== 2) return "🏏";
  const upper = code2.toUpperCase();
  return String.fromCodePoint(
    A + (upper.charCodeAt(0) - 65),
    A + (upper.charCodeAt(1) - 65),
  );
}

const COUNTRY_TO_ISO: Record<string, string> = {
  Pakistan: "PK",
  India: "IN",
  Australia: "AU",
  "South Africa": "ZA",
  "New Zealand": "NZ",
  Bangladesh: "BD",
  "Sri Lanka": "LK",
  Afghanistan: "AF",
  Zimbabwe: "ZW",
  Ireland: "IE",
  Nepal: "NP",
  "United Arab Emirates": "AE",
  "United States of America": "US",
  USA: "US",
  Scotland: "GB-SCT",
  Netherlands: "NL",
  Oman: "OM",
  "Hong Kong": "HK",
  Namibia: "NA",
  Canada: "CA",
  "Papua New Guinea": "PG",
  Bermuda: "BM",
  "Cayman Islands": "KY",
  Jersey: "JE",
  Guernsey: "GG",
  Malaysia: "MY",
  Singapore: "SG",
  Thailand: "TH",
  Kuwait: "KW",
  Qatar: "QA",
  Bahrain: "BH",
  "Saudi Arabia": "SA",
  Bhutan: "BT",
  Maldives: "MV",
  Myanmar: "MM",
  Indonesia: "ID",
  Philippines: "PH",
  Japan: "JP",
  China: "CN",
  "South Korea": "KR",
  Germany: "DE",
  France: "FR",
  Italy: "IT",
  Spain: "ES",
  Portugal: "PT",
  Belgium: "BE",
  Denmark: "DK",
  Sweden: "SE",
  Norway: "NO",
  Finland: "FI",
  Austria: "AT",
  Switzerland: "CH",
  Czechia: "CZ",
  Romania: "RO",
  Bulgaria: "BG",
  Greece: "GR",
  Turkey: "TR",
  Israel: "IL",
  Kenya: "KE",
  Uganda: "UG",
  Tanzania: "TZ",
  Rwanda: "RW",
  Nigeria: "NG",
  Ghana: "GH",
  Botswana: "BW",
  Eswatini: "SZ",
  Lesotho: "LS",
  Malawi: "MW",
  Mozambique: "MZ",
  Cyprus: "CY",
  Mexico: "MX",
  Argentina: "AR",
  Brazil: "BR",
  Chile: "CL",
};

const SPECIAL: Record<string, string> = {
  // Cricsheet uses "West Indies" for the multi-country Caribbean team.
  // Picking one Jamaican / Bajan / Trinidadian flag would mislead, so
  // use the cricket-bat glyph as a clear "regional" marker.
  "West Indies": "🏏",
  // England plays separately from the UK in cricket — use the St
  // George's cross sub-region tag flag, with Union Jack as a
  // browser fallback (some terminals don't render the tag flag).
  England: "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
};

export function flagFor(country: string | null | undefined): string {
  if (!country) return "🏏";
  if (country in SPECIAL) return SPECIAL[country];
  const iso = COUNTRY_TO_ISO[country];
  if (!iso) return "🏏";
  // GB-* sub-region tags use the same regional indicator construction
  // for the country prefix; for anything but the special cases above
  // we drop down to the country letters.
  if (iso.includes("-")) return SPECIAL[country] ?? "🏏";
  return flagFromCode(iso);
}
