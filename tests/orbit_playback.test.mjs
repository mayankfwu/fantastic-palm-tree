// Exercise the shipped player with a deterministic clock and no graphics device.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import vm from "node:vm";

/** Mount the scene with positions in km and a controllable clock in milliseconds. */
function mountPlayer(packet) {
    const template = readFileSync(new URL("../src/viz/orbit_scene.html", import.meta.url), "utf8");
    const script = template.split("<script>")[1].split("</script>")[0];
    const elements = new Map();
    let lineCount = 0;
    const graphics = new Proxy({}, {
        get: (_, key) => {
            if (key === "createRadialGradient") return () => ({addColorStop() {}});
            if (key === "lineTo") return () => { lineCount++; };
            return () => {};
        },
    });
    function element(id) {
        if (!elements.has(id)) {
            elements.set(id, {
                value: "", style: {}, classList: {add() {}}, add() {},
                getContext: () => graphics, clientWidth: 300, clientHeight: 300,
            });
        }
        return elements.get(id);
    }
    for (const [tag, id] of template.matchAll(/<input\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
        element(id).checked = /\schecked\b/.test(tag);
    }
    let now = 0;
    let nextId = 0;
    let onMessage;
    const animations = new Map();
    const parent = {postMessage() {}};
    const context = vm.createContext({
        document: {getElementById: element, querySelector: element},
        Option: class {}, ResizeObserver: class { observe() {} }, devicePixelRatio: 1,
        parent, window: {addEventListener: (_, callback) => { onMessage = callback; }},
        performance: {now: () => now},
        requestAnimationFrame(callback) {
            animations.set(++nextId, callback);
            return nextId;
        },
        cancelAnimationFrame: id => animations.delete(id),
    });
    function advance(ms) {
        now += ms;
        const callbacks = [...animations.values()];
        animations.clear();
        callbacks.forEach(callback => callback(now));
    }
    function deliver(sequence, lastTime, endTime, impact = false, maneuverPasses = []) {
        const initial = packet.frames[0];
        onMessage({source: parent, data: {
            type: "orbit-block",
            packet: {sequence, maneuverPasses, frames: [{...initial, time: lastTime}, {...initial, time: endTime, impact}]},
        }});
    }
    vm.runInContext(script.replace("__ENCOUNTER_DATA__", JSON.stringify(packet)), context);
    return {advance, animations, deliver, element, drawnLines: () => lineCount};
}

test("orbit playback starts with short debris trails and slows automatically at an encounter", () => {
    const frames = [0, 15, 30, 45].map(time => ({time, positions: [[8000, 0, 0], [8100, time, 0]]}));
    const {advance, element, drawnLines} = mountPlayer({
        frames, labels: ["Satellite", "Debris"], earthRadiusKm: 6378, satelliteCount: 1,
        encounterTimes: [0], clockStepS: 10, frameIntervalMs: 1000,
    });
    const orbits = element("debris-orbits");
    assert.equal(orbits.checked, false);
    const before = drawnLines();
    orbits.onchange();
    const shortTrail = drawnLines() - before;
    orbits.checked = true;
    const beforeFullOrbit = drawnLines();
    orbits.onchange();
    assert.ok(drawnLines() - beforeFullOrbit > shortTrail);

    const slow = element("slow-near");
    assert.equal(slow.checked, true);
    advance(1000);
    assert.equal(element("time").textContent, "Slow motion · 4.00 s");
    slow.checked = false;
    slow.onchange();
    advance(1000);
    assert.equal(element("time").textContent, "14.00 s");
});

test("a delayed orbit window resumes playback only if the clock is still waiting", () => {
    const frames = [0, 60, 120].map(time => ({time, positions: [[7000, 0, 0]], impact: false}));
    const {advance, animations, deliver, element} = mountPlayer({
        frames, labels: ["Satellite"], earthRadiusKm: 6378, satelliteCount: 1, continuous: true,
    });
    advance(1000);
    assert.equal(animations.size, 0);
    element("pause").onclick();
    element("timeline").value = "0";
    element("timeline").oninput();
    element("play").onclick();
    deliver(1, 120, 240);
    assert.equal(animations.size, 1, "a late response must not start a second clock");
    element("pause").onclick();
    assert.equal(animations.size, 0);

    element("play").onclick();
    advance(1000);
    assert.equal(animations.size, 0);
    deliver(2, 240, 360, true);
    assert.equal(animations.size, 1, "a player waiting at the boundary must resume");
    advance(1000);
    assert.equal(animations.size, 0);
    assert.match(element("time").textContent, /Contact snapshot.*360\.00 s/);
});

test("initial and streamed passes use the refined miss distance for the required clearance", () => {
    const frames = [0, 5, 10].map(time => ({time, positions: [[7000, 0, 0], [7005, 0, 0]], impact: false}));
    const pass = {time: 0, primary: 0, debris: 1, missKm: 4.99999, dvMps: 10};
    const {element, deliver} = mountPlayer({
        frames, labels: ["Satellite", "Debris"], earthRadiusKm: 6378, satelliteCount: 1, continuous: true,
        safeMissKm: 5, maneuverPasses: [pass],
    });
    assert.equal(element("encounter-panel").hidden, false);
    assert.equal(element("avoidance-panel").hidden, false);
    assert.match(element("encounter-distance").textContent, /Too close · Minimum < 5 km · Target 5 km/);
    assert.match(element("avoidance-distance").textContent, /Δv \+10 m\/s/);

    deliver(1, 10, 11, false, [{...pass, time: 11, missKm: 5.0, dvMps: -2}]);
    element("timeline").value = "3";
    element("timeline").oninput();
    assert.match(element("encounter-distance").textContent, /Clearance met · Minimum 5.000 km · Target 5 km/);
    assert.match(element("avoidance-distance").textContent, /Δv -2 m\/s/);
    assert.doesNotMatch(element("time").textContent, /Contact/);

    const alternate = mountPlayer({
        frames, labels: ["Satellite", "Debris"], earthRadiusKm: 6378, satelliteCount: 1,
        safeMissKm: 6, maneuverPasses: [{...pass, missKm: 5.5}],
    });
    assert.match(alternate.element("encounter-distance").textContent, /Too close · Minimum 5.500 km · Target 6 km/);
});
