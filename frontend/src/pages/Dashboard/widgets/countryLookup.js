/**
 * ISO 3166-1 alpha-2 → numeric code mapping.
 * Used to match ip_country values against world-atlas topojson IDs.
 */
export const ALPHA2_TO_NUMERIC = {
  AF: "004", AL: "008", DZ: "012", AS: "016", AD: "020", AO: "024",
  AG: "028", AR: "032", AM: "051", AU: "036", AT: "040", AZ: "031",
  BS: "044", BH: "048", BD: "050", BB: "052", BY: "112", BE: "056",
  BZ: "084", BJ: "204", BT: "064", BO: "068", BA: "070", BW: "072",
  BR: "076", BN: "096", BG: "100", BF: "854", BI: "108",
  CV: "132", KH: "116", CM: "120", CA: "124", CF: "140", TD: "148",
  CL: "152", CN: "156", CO: "170", KM: "174", CG: "178", CD: "180",
  CR: "188", CI: "384", HR: "191", CU: "192", CY: "196", CZ: "203",
  DK: "208", DJ: "262", DM: "212", DO: "214",
  EC: "218", EG: "818", SV: "222", GQ: "226", ER: "232", EE: "233",
  SZ: "748", ET: "231",
  FJ: "242", FI: "246", FR: "250",
  GA: "266", GM: "270", GE: "268", DE: "276", GH: "288", GR: "300",
  GD: "308", GT: "320", GN: "324", GW: "624", GY: "328",
  HT: "332", HN: "340", HK: "344", HU: "348",
  IS: "352", IN: "356", ID: "360", IR: "364", IQ: "368", IE: "372",
  IL: "376", IT: "380",
  JM: "388", JP: "392", JO: "400",
  KZ: "398", KE: "404", KI: "296", KP: "408", KR: "410", KW: "414",
  KG: "417",
  LA: "418", LV: "428", LB: "422", LS: "426", LR: "430", LY: "434",
  LI: "438", LT: "440", LU: "442",
  MO: "446", MG: "450", MW: "454", MY: "458", MV: "462", ML: "466",
  MT: "470", MH: "584", MR: "478", MU: "480", MX: "484", FM: "583",
  MD: "498", MC: "492", MN: "496", ME: "499", MA: "504", MZ: "508",
  MM: "104",
  NA: "516", NR: "520", NP: "524", NL: "528", NZ: "554", NI: "558",
  NE: "562", NG: "566", MK: "807", NO: "578",
  OM: "512",
  PK: "586", PW: "585", PS: "275", PA: "591", PG: "598", PY: "600",
  PE: "604", PH: "608", PL: "616", PT: "620", PR: "630",
  QA: "634",
  RO: "642", RU: "643", RW: "646",
  KN: "659", LC: "662", VC: "670", WS: "882", SM: "674", ST: "678",
  SA: "682", SN: "686", RS: "688", SC: "690", SL: "694", SG: "702",
  SK: "703", SI: "705", SB: "090", SO: "706", ZA: "710", SS: "728",
  ES: "724", LK: "144", SD: "729", SR: "740", SE: "752", CH: "756",
  SY: "760",
  TW: "158", TJ: "762", TZ: "834", TH: "764", TL: "626", TG: "768",
  TO: "776", TT: "780", TN: "788", TR: "792", TM: "795",
  UG: "800", UA: "804", AE: "784", GB: "826", US: "840", UY: "858",
  UZ: "860",
  VU: "548", VE: "862", VN: "704",
  YE: "887",
  ZM: "894", ZW: "716",
};

/**
 * Country centroid coordinates [longitude, latitude] used to center the map.
 */
export const COUNTRY_CENTROIDS = {
  // Europe
  FR: [2.2, 46.8],   DE: [10.4, 51.2],  GB: [-1.5, 54.0],  IT: [12.6, 42.8],
  ES: [-3.7, 40.4],  NL: [5.3, 52.1],   BE: [4.5, 50.5],   CH: [8.2, 46.8],
  AT: [14.5, 47.5],  PL: [19.4, 52.1],  SE: [17.9, 62.0],  NO: [8.5, 61.0],
  DK: [10.0, 56.0],  FI: [25.7, 61.9],  PT: [-8.2, 39.4],  GR: [21.8, 39.1],
  CZ: [15.5, 49.8],  HU: [19.5, 47.2],  RO: [25.0, 45.9],  UA: [32.0, 49.0],
  RU: [60.0, 60.0],  TR: [35.2, 39.0],  RS: [21.0, 44.0],  SK: [19.7, 48.7],
  HR: [15.2, 45.1],  BG: [25.5, 42.7],  LT: [23.9, 55.9],  LV: [24.6, 56.9],
  EE: [24.7, 58.6],  BY: [27.9, 53.7],  MD: [28.4, 47.4],
  // Americas
  US: [-95.7, 37.1], CA: [-96.8, 56.1], MX: [-102.5, 24.0], BR: [-51.9, -14.2],
  AR: [-63.6, -38.4], CL: [-71.5, -35.7], CO: [-74.3, 4.6], PE: [-75.0, -9.2],
  // Asia & Middle East
  CN: [104.2, 35.9], JP: [138.3, 36.2], IN: [78.9, 20.6],  KR: [127.8, 35.9],
  SG: [103.8, 1.4],  AE: [53.8, 23.4],  SA: [45.1, 24.7],  IL: [34.8, 31.4],
  IQ: [44.4, 33.2],  IR: [53.7, 32.4],  TH: [100.9, 15.9], VN: [106.3, 16.6],
  MY: [109.7, 4.2],  ID: [113.9, -0.8], PK: [69.3, 30.4],  BD: [90.4, 23.7],
  PH: [121.8, 12.9], TW: [120.9, 23.7], HK: [114.1, 22.4],
  // Africa
  EG: [30.8, 26.8],  ZA: [25.1, -29.0], NG: [8.7, 9.1],   ET: [40.5, 9.1],
  KE: [37.9, -0.0],  TN: [9.6, 33.9],   MA: [-7.1, 31.8],  DZ: [1.7, 28.0],
  // Oceania
  AU: [133.8, -25.7], NZ: [172.5, -41.5],
  // World default
  WORLD: [0, 20],
};

/**
 * Zoom level (1-5) → react-simple-maps projection scale.
 */
export const ZOOM_TO_SCALE = {
  1: 130,   // world view
  2: 280,   // continental
  3: 600,   // regional (default for France)
  4: 1000,  // country-level
  5: 1600,  // detail
};

/**
 * Ordered list of countries for the map center selector in WidgetWizard.
 */
export const MAP_CENTER_OPTIONS = [
  { group: "World",         options: [{ code: "WORLD", name: "World (default view)" }] },
  { group: "Europe",        options: [
    { code: "FR", name: "France" }, { code: "DE", name: "Germany" }, { code: "GB", name: "United Kingdom" },
    { code: "IT", name: "Italy" },  { code: "ES", name: "Spain" },   { code: "NL", name: "Netherlands" },
    { code: "BE", name: "Belgium" },{ code: "CH", name: "Switzerland" }, { code: "AT", name: "Austria" },
    { code: "PL", name: "Poland" }, { code: "SE", name: "Sweden" },  { code: "NO", name: "Norway" },
    { code: "DK", name: "Denmark" },{ code: "FI", name: "Finland" }, { code: "PT", name: "Portugal" },
    { code: "GR", name: "Greece" }, { code: "CZ", name: "Czechia" }, { code: "HU", name: "Hungary" },
    { code: "RO", name: "Romania" },{ code: "UA", name: "Ukraine" }, { code: "RU", name: "Russia" },
    { code: "TR", name: "Turkey" },
  ]},
  { group: "Americas",      options: [
    { code: "US", name: "United States" }, { code: "CA", name: "Canada" },
    { code: "MX", name: "Mexico" },        { code: "BR", name: "Brazil" },
    { code: "AR", name: "Argentina" },
  ]},
  { group: "Asia & Middle East", options: [
    { code: "CN", name: "China" },   { code: "JP", name: "Japan" },  { code: "IN", name: "India" },
    { code: "KR", name: "South Korea" }, { code: "SG", name: "Singapore" },
    { code: "AE", name: "UAE" },     { code: "SA", name: "Saudi Arabia" }, { code: "IL", name: "Israel" },
    { code: "TH", name: "Thailand" },{ code: "ID", name: "Indonesia" },
  ]},
  { group: "Africa",        options: [
    { code: "EG", name: "Egypt" }, { code: "ZA", name: "South Africa" }, { code: "NG", name: "Nigeria" },
    { code: "MA", name: "Morocco" },
  ]},
  { group: "Oceania",       options: [
    { code: "AU", name: "Australia" }, { code: "NZ", name: "New Zealand" },
  ]},
];
