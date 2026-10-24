const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

async function setup(captureFormValues, buildFlags = {}) {
  const listeners = new Map();
  const sent = [];
  const hooks = [];
  const logs = [];
  const context = vm.createContext({
    ...buildFlags,
    Date,
    location: { href: "https://shop.test/login" },
    document: { addEventListener: (name, listener) => listeners.set(name, listener) },
    window: {
      addEventListener() {},
      __OFM__: { onBehavioralEvent: payload => hooks.push(payload) },
    },
    console: { debug: (...args) => logs.push(args) },
  });
  const config = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, "../src/config.js"), "utf8"), { context },
  );
  const sender = new vm.SyntheticModule(["send"], function () {
    this.setExport("send", (endpoint, payload) => sent.push({ endpoint, payload }));
  }, { context });
  const behavior = new vm.SourceTextModule(
    fs.readFileSync(path.join(__dirname, "../src/extensions/behavior.js"), "utf8"), { context },
  );
  await config.link(() => {});
  await sender.link(() => {});
  await behavior.link(specifier => specifier === "../config.js" ? config : sender);
  await behavior.evaluate();
  if (captureFormValues !== undefined) config.namespace.CFG.captureFormValues = captureFormValues;
  behavior.namespace.default.setVisitId("visit-one");
  behavior.namespace.default.init();
  return { listeners, sent, hooks, logs, config: config.namespace.CFG };
}

test("both capture settings use injected build flags and default to false", async () => {
  const defaults = await setup();
  assert.equal(defaults.config.captureFormValues, false);
  assert.equal(defaults.config.captureClipboard, false);
  for (const enabled of [false, true]) {
    const { config } = await setup(undefined, {
      __OFM_CAPTURE_FORM_VALUES__: enabled,
      __OFM_CAPTURE_CLIPBOARD__: enabled,
    });
    assert.equal(config.captureFormValues, enabled);
    assert.equal(config.captureClipboard, enabled);
  }
});

function submit(listeners, elements) {
  listeners.get("submit")({
    target: {
      action: "https://shop.test/login", method: "post",
      querySelectorAll: () => elements,
    },
  });
}

for (const setting of [undefined, false]) {
  test(`form capture ${setting === undefined ? "defaults to disabled" : "disabled"} never reads values`, async () => {
    const { listeners, sent, hooks, logs, config } = await setup(setting);
    assert.equal(config.captureFormValues, false);
    const elements = [
      { name: "email", type: "email" },
      { name: "password", type: "password" },
      { name: "csrf", type: "hidden" },
      { id: "message", type: "textarea" },
      { name: "country", type: "select-one" },
      { name: "", id: "", type: "text" },
    ];
    for (const element of elements) {
      Object.defineProperty(element, "value", {
        get() { assert.fail("Disabled capture must not read field values"); },
      });
    }
    submit(listeners, elements);
    assert.equal(sent.length, 1);
    assert.equal(sent[0].endpoint, "/api/behavioral_event");
    const payload = JSON.parse(JSON.stringify(sent[0].payload));
    assert.deepEqual(payload.data, {
      action: "https://shop.test/login", method: "post",
      fieldNames: ["email", "password", "csrf", "message", "country"],
    });
    assert.equal(payload.event_type, "form_submit");
    assert.equal(payload.visit_id, "visit-one");
    assert.equal(hooks[0], sent[0].payload);
    assert.deepEqual(logs, []);
  });
}

test("explicit opt-in transmits values without logging the payload", async () => {
  const { listeners, sent, logs } = await setup(true);
  const elements = [
    { name: "email", type: "email", value: "test@example.test" },
    { name: "password", type: "password", value: "test-only-secret" },
    { name: "", id: "", get value() { assert.fail("Unnamed fields are not collected"); } },
  ];
  submit(listeners, elements);
  const data = JSON.parse(JSON.stringify(sent[0].payload.data));
  assert.deepEqual(data.fields, elements.slice(0, 2));
  assert.deepEqual(data.fieldNames, ["email", "password"]);
  assert.deepEqual(logs, []);
});
