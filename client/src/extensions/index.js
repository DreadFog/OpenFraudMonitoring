/**
 * Extension registry — import and list all OFM extensions here.
 *
 * To add a new extension:
 *   1. Create a file in extensions/ exporting { name, collect?, init?, drain? }
 *   2. Import it here and add it to the array
 *
 * Extension interface:
 *   name           – unique string identifier
 *   init()         – (optional) called once at startup (e.g. attach event listeners)
 *   collect()      – (optional) async, called once during fingerprint collection
 *   drain()        – (optional) called every heartbeat, returns accumulated data
 */

import behavior from "./behavior.js";
import ip from "./ip.js";

const extensions = [
  behavior,
  ip,
];

export default extensions;
