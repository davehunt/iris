const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

class Element {
    constructor(tag = "div") {
        this.tag = tag;
        this.children = [];
        this.attributes = {};
        this.style = {};
        this.listeners = {};
        this.textContent = "";
    }
    setAttribute(name, value) { this.attributes[name] = value; }
    appendChild(child) { this.children.push(child); return child; }
    addEventListener(event, listener) { this.listeners[event] = listener; }
    click() { this.listeners.click(); }
    querySelector(selector) { return this.children.find(child => child.tag === selector); }
    set innerText(value) { this.children = []; this.textContent = value; }
    querySelectorAll(selector) {
        const matches = [];
        for (const child of this.children) {
            if (selector === ".pixel" && child.attributes.class === "pixel")
                matches.push(child);
            matches.push(...child.querySelectorAll(selector));
        }
        return matches;
    }
}

const setup = () => {
    let now = 0;
    let timerId = 0;
    const timers = new Map();
    const published = [];
    const events = {};
    const devices = {};
    for (const device of ["loki", "yuzu"]) {
        devices[device] = {
            presets: new Element(),
            live: Array.from({ length: 8 }, () => new Element()),
            custom: Array.from({ length: 8 }, () => {
                const colour = { value: "#14283c" };
                const brightness = { value: "1" };
                return { querySelector: selector => selector.includes("color") ? colour : brightness };
            }),
        };
    }
    const context = {
        window: { addEventListener: (event, action) => { events[event] = action; } },
        console: { log() {} },
        config: {
            pubnub: { userId: "web" },
            devices: [{ id: "loki" }, { id: "yuzu" }],
        },
        document: {
            createElement: tag => new Element(tag),
            createTextNode: text => { const element = new Element("text"); element.textContent = text; return element; },
            querySelector: selector => devices[selector.split(" ")[0].slice(1)].presets,
            querySelectorAll: selector => selector.includes(".custom")
                ? devices[selector.split(" ")[0].slice(1)].custom : [],
            getElementById: device => ({
                querySelectorAll: selector => selector.includes(".custom") ? devices[device].custom : devices[device].live,
            }),
        },
        bootstrap: { Tooltip: class {} },
        performance: { now: () => now },
        setTimeout: action => { timers.set(++timerId, action); return timerId; },
        clearTimeout: id => timers.delete(id),
    };
    vm.createContext(context);
    for (const file of ["effects.js", "main.js"])
        vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "src", file), "utf8"), context);
    context.published = published;
    const run = expression => vm.runInContext(expression, context);
    run("pubnub = { publish: async m => published.push(m) };");
    const advance = seconds => {
        now += seconds * 1000;
        const pending = [...timers.values()];
        timers.clear();
        pending.forEach(action => action());
    };
    const rows = device => devices[device].presets.children.filter(row => row.attributes.class.includes("special-preset"));
    const buttons = row => row.children[0].children.find(child => child.attributes.class === "btn-group").children;
    const colours = row => row.querySelectorAll(".pixel").map(pixel => pixel.style.backgroundColor);
    return { run, devices, timers, published, events, advance, rows, buttons, colours };
};

test("special list is available offline, unique on refresh, and preserves saved schema", () => {
    const app = setup();
    app.run("setLocalPresets('loki', []);");
    assert.deepEqual(app.rows("loki").map(row => row.children[0].children[0].textContent.trim()),
        ["🌈", "💝", "🎄", "🪔"]);
    assert.equal(app.published.length, 0);
    app.run(`setLocalPresets('loki', [
        { name: 'Rainbow', pixels: Array.from({length:8}, () => [20,40,60,0.1]), default:false }
    ]);`);
    assert.equal(app.rows("loki").length, 4);
    assert.equal(app.devices.loki.presets.children.length, 5);
    assert.equal(app.run("window.localPresets.loki.length"), 1);
    assert.equal(app.run("'id' in window.localPresets.loki[0]"), false);
    const savedButtons = app.devices.loki.presets.children[0].children[0].children
        .find(child => child.attributes.class === "btn-group").children;
    assert.equal(savedButtons.length, 5);
    app.run("loadPreset('loki', 'Rainbow'); setRemotePixels('loki');");
    assert.deepEqual(Array.from(app.published[0].message.pixels, p => Array.from(p)),
        Array.from({ length: 8 }, () => [20, 40, 60, 0.1]));
});

test("every preview starts/stops explicitly with no PubNub or pixel-editor writes", () => {
    const app = setup();
    app.run("setLocalPresets('loki', []);");
    const custom = app.run("JSON.stringify(getLocalPixels('loki'))");
    for (const row of app.rows("loki")) {
        const preview = app.buttons(row)[0];
        const idle = app.colours(row);
        preview.click();
        assert.equal(preview.attributes["aria-label"], "Stop preview");
        assert.equal(preview.querySelector("i").attributes.class, "bi bi-stop-fill");
        assert.equal(preview.attributes["aria-pressed"], "true");
        app.advance(1.1);
        assert.notDeepEqual(app.colours(row), idle);
        preview.click();
        assert.equal(app.timers.size, 0);
        assert.equal(preview.attributes["aria-pressed"], "false");
    }
    assert.equal(app.published.length, 0);
    assert.equal(app.run("JSON.stringify(getLocalPixels('loki'))"), custom);
    assert.ok(app.devices.loki.live.every(pixel => Object.keys(pixel.style).length === 0));
});

test("preview replacement, remote status isolation, refresh and pagehide", () => {
    const app = setup();
    app.run("setLocalPresets('loki', []); setLocalPresets('yuzu', []);");
    const [rainbow, valentines] = app.rows("loki");
    app.buttons(rainbow)[0].click();
    app.buttons(valentines)[0].click();
    assert.equal(app.buttons(rainbow)[0].attributes["aria-label"], "Preview");
    assert.equal(app.timers.size, 1);
    app.buttons(app.rows("yuzu")[0])[0].click();
    assert.equal(app.timers.size, 2);
    app.run("setLocalPixels('loki', Array.from({length:8}, () => [255,0,0,0.1]));");
    assert.equal(app.timers.size, 2);
    app.run("setLocalPresets('loki', []);");
    assert.equal(app.timers.size, 1);
    app.events.pagehide();
    assert.equal(app.timers.size, 0);
    assert.equal(app.published.length, 0);
});

test("all effects finish at device duration; only Diwali stays lit", () => {
    const app = setup();
    app.run("setLocalPresets('loki', []);");
    const durations = [30, 10, 10, 60];
    app.rows("loki").forEach((row, i) => {
        app.buttons(row)[0].click();
        app.advance(durations[i] - 0.01);
        assert.equal(app.timers.size, 1);
        app.advance(0.01);
        assert.equal(app.timers.size, 0);
        assert.equal(app.buttons(row)[0].attributes["aria-label"], "Preview");
        assert.equal(row.children[1].textContent, "Preview finished. Browser only.");
        assert.equal(row.children[1].attributes.class, "visually-hidden");
        assert.equal(app.colours(row).every(colour => colour === "transparent"), i !== 3);
    });
    assert.equal(app.published.length, 0);
});

test("Apply and Send to partner dispatch effect IDs, not preview frames", () => {
    const app = setup();
    app.run("setLocalPresets('loki', []);");
    const ids = ["rainbow", "valentines", "xmas", "diwali"];
    app.rows("loki").forEach((row, i) => {
        const [preview, apply, send] = app.buttons(row);
        preview.click();
        apply.click();
        assert.equal(app.timers.size, 0);
        preview.click();
        send.click();
        assert.equal(app.timers.size, 0);
        for (const [offset, device] of [[0, "loki"], [1, "yuzu"]]) {
            const message = app.published[i * 2 + offset];
            assert.equal(message.channel, device + "_control");
            assert.deepEqual({ ...message.message }, { command: "pressButton", button: ids[i], from: "web" });
        }
    });
});

test("static load, power off, custom send and seasonal commands interrupt previews", () => {
    const app = setup();
    app.run(`setLocalPresets('loki', [{name:'saved', pixels:Array.from({length:8}, () => [1,2,3,0.1])}]);
        window.localPixels.loki = Array.from({length:8}, () => [4,5,6,0.2]);`);
    for (const command of [
        "loadPreset('loki', 'saved')", "loadLocalPixels('loki')",
        "clearRemotePixels('loki')", "setRemotePixels('loki')", "lightDiyas('loki')",
    ]) {
        app.buttons(app.rows("loki")[0])[0].click();
        app.run(command);
        assert.equal(app.timers.size, 0);
    }
    assert.deepEqual(app.published.map(m => m.message.command), ["clearPixels", "setPixels", "pressButton"]);
});

test("eight-pixel marquee timing/brightness and rainbow spacing match hardware", () => {
    const app = setup();
    assert.equal(app.run("SPECIAL_PRESETS[1].create()(0).filter(p => p[3] > 0).length"), 1);
    assert.equal(app.run("SPECIAL_PRESETS[1].create()(0.7).filter(p => p[3] > 0).length"), 8);
    assert.equal(app.run("JSON.stringify(SPECIAL_PRESETS[1].create()(0.7).map(p => p[3]))"),
        JSON.stringify([0.1, 0.1, 0.5, 0.5, 0.9, 0.9, 0.5, 0.5]));
    assert.equal(app.run("JSON.stringify(SPECIAL_PRESETS[2].create()(0.1).slice(-2))"),
        JSON.stringify([[255, 0, 0, 0.1], [255, 255, 255, 0.1]]));
    assert.equal(app.run("JSON.stringify(rainbowFrame(0).slice(0,3))"),
        JSON.stringify([[255, 0, 0, 0.1], [255, 95, 0, 0.1], [255, 191, 0, 0.1]]));
    for (const id of ["rainbow", "valentines", "xmas", "diwali"]) {
        assert.equal(app.run(`SPECIAL_PRESETS.find(e => e.id === '${id}').create()(5).length`), 8);
    }
});

test("shared live, static and animated rendering represents brightness exactly once", () => {
    const app = setup();
    const pixels = [[200, 100, 50, 0], [200, 100, 50, 0.5], [200, 100, 50, 1],
        ...Array.from({ length: 5 }, () => [200, 100, 50, 0.1])];
    app.run(`setLocalPixels('loki', ${JSON.stringify(pixels)});
        setLocalPresets('loki', [{name:'levels', pixels:${JSON.stringify(pixels)}}]);`);
    const expected = ["transparent", `rgba(200, 100, 50, ${0.65 + 0.35 * Math.sqrt(0.5)})`,
        "rgba(200, 100, 50, 1)", ...Array(5).fill(`rgba(200, 100, 50, ${0.65 + 0.35 * Math.sqrt(0.1)})`)];
    assert.deepEqual(app.devices.loki.live.map(p => p.style.backgroundColor), expected);
    const staticRow = app.devices.loki.presets.children[0];
    assert.deepEqual(app.colours(staticRow), expected);
    assert.deepEqual(staticRow.querySelectorAll(".pixel").map(p => p.style.boxShadow),
        app.devices.loki.live.map(p => p.style.boxShadow));
    app.run("loadLocalPixels('loki'); setRemotePixels('loki');");
    assert.deepEqual(Array.from(app.published[0].message.pixels, p => Array.from(p)), pixels);
    assert.equal(app.run("JSON.stringify(window.localPixels.loki)"), JSON.stringify(pixels));
    const valentines = app.rows("loki")[1];
    app.buttons(valentines)[0].click();
    app.advance(0.7);
    assert.deepEqual(app.colours(valentines),
        [0.1, 0.1, 0.5, 0.5, 0.9, 0.9, 0.5, 0.5]
            .map(brightness => `rgba(247, 0, 162, ${0.65 + 0.35 * Math.sqrt(brightness)})`));
    const animationShadows = valentines.querySelectorAll(".pixel").map(p => p.style.boxShadow);
    assert.equal(animationShadows[0], animationShadows[1]);
    assert.notEqual(animationShadows[0], animationShadows[2]);
    assert.notEqual(animationShadows[2], animationShadows[4]);
    assert.deepEqual(app.devices.loki.live.map(p => p.style.backgroundColor), expected);
    assert.equal(app.published.length, 1);
});

test("off LEDs are transparent; low-brightness colours remain visible without data changes", () => {
    const app = setup();
    app.run("setLocalPixels('loki', [[255,100,0,0],[0,0,0,1],...Array.from({length:6},()=>[255,255,255,0.1])]);");
    assert.deepEqual(app.devices.loki.live.slice(0, 2).map(p => p.style.backgroundColor),
        ["transparent", "transparent"]);
    assert.equal(app.devices.loki.live[2].style.backgroundColor,
        `rgba(255, 255, 255, ${0.65 + 0.35 * Math.sqrt(0.1)})`);
    assert.equal(app.devices.loki.live[0].style.boxShadow,
        "inset 0 0 0 1px rgba(0, 0, 0, 0.12)");
    assert.equal(app.devices.loki.live[2].style.boxShadow,
        "inset 0 0 0 1px rgba(0, 0, 0, 0.12)");
    app.run("setLocalPixels('loki', Array.from({length:8},()=>[0,0,0,0]));");
    assert.ok(app.devices.loki.live.every(p => p.style.boxShadow === "inset 0 0 0 1px rgba(0, 0, 0, 0.12)"));
});

test("brightness up to 0.1 has crisp edges, with glow only above that threshold", () => {
    const app = setup();
    app.run("setLocalPixels('loki', [0,0.05,0.1,0.101,0.25,0.5,0.75,1].map(b=>[255,100,30,b]));");
    const outline = "inset 0 0 0 1px rgba(0, 0, 0, 0.12)";
    assert.ok(app.devices.loki.live.slice(0,3).every(p=>p.style.boxShadow === outline));
    assert.ok(app.devices.loki.live.slice(3).every(p=>p.style.boxShadow !== outline));
    assert.notEqual(app.devices.loki.live[2].style.backgroundColor, "transparent");
});

test("emoji-only labels keep names on hover and do not rename saved presets", () => {
    const app = setup();
    assert.equal(app.run("createPresetLabel('🩷').textContent"), "🩷");
    assert.equal(app.run("createPresetLabel('🩷').attributes.title"), "Love");
    assert.equal(app.run("createPresetLabel('🎉').attributes.title"), "Party");
    assert.equal(app.run("createPresetLabel('Evening').textContent"), "🔖");
    assert.equal(app.run("createPresetLabel('Evening').attributes.title"), "Evening");
    assert.equal(app.run("createPresetLabel('🌙 Evening').textContent"), "🌙");
    app.run("setLocalPresets('loki', [{name:'Evening', pixels:Array.from({length:8}, () => [1,2,3,0.1])}]);");
    assert.equal(app.run("window.localPresets.loki[0].name"), "Evening");
    for (const row of app.rows("loki")) {
        const buttons = app.buttons(row);
        assert.deepEqual(buttons.map(b => b.attributes["aria-label"]),
            ["Preview", "Apply to device", "Send to partner"]);
        assert.deepEqual(buttons.map(b => b.querySelector("i").attributes.class),
            ["bi bi-play-fill", "bi bi-lightbulb", "bi bi-send"]);
        assert.ok(buttons.every(b => b.attributes.title && b.attributes["data-bs-toggle"] === "tooltip"));
        buttons[0].click();
        buttons[0].click();
        assert.equal(buttons[0].querySelector("i").attributes.class, "bi bi-play-fill");
    }
});

test("static load and apply use distinct icons; apply sends original pixels without editing", () => {
    const app = setup();
    app.run("setLocalPresets('loki', [{name:'saved', pixels:Array.from({length:8},()=>[100,50,25,0.5]), default:true}]);");
    const row = app.devices.loki.presets.children[0];
    const buttons = row.children[0].children.find(c=>c.attributes.class === "btn-group").children;
    assert.equal(buttons[0].querySelector("i").attributes.class, "bi bi-pencil-square");
    assert.equal(buttons[1].querySelector("i").attributes.class, "bi bi-lightbulb");
    assert.equal(buttons[1].attributes["aria-label"], "Apply to device");
    const editor = app.run("JSON.stringify(getLocalPixels('loki'))");
    app.buttons(app.rows("loki")[0])[0].click();
    buttons[1].click();
    assert.equal(app.timers.size, 0);
    assert.equal(app.published.length, 1);
    assert.equal(app.published[0].channel, "loki_control");
    assert.equal(app.published[0].message.command, "setPixels");
    assert.deepEqual(Array.from(app.published[0].message.pixels,p=>Array.from(p)),
        Array.from({length:8},()=>[100,50,25,0.5]));
    assert.equal(app.run("JSON.stringify(getLocalPixels('loki'))"), editor);
});

test("defaults come from device status rather than an offline browser catalogue", () => {
    const app = setup();
    app.run("setLocalPresets('loki', []);");
    assert.equal(app.devices.loki.presets.children.length, 4);
    assert.equal(app.run("typeof DEFAULT_PRESETS"), "undefined");
    app.run("setLocalPresets('loki', [{name:'🩷',pixels:Array.from({length:8},()=>[247,0,162,0.1]),default:true}]);");
    assert.equal(app.devices.loki.presets.children.length, 5);
    const label = app.devices.loki.presets.children[0].children[0].children[0];
    assert.equal(label.textContent, "🩷");
    assert.equal(label.attributes.title, "Love");
    app.run("loadPreset('loki', '🩷'); setRemotePixels('loki');");
    assert.equal(app.published[0].message.pixels[0][0], 247);
});
