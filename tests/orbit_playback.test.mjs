// Exercise the shipped player with a deterministic clock and no graphics device.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import vm from "node:vm";

test("a delayed orbit window resumes playback only if the clock is still waiting", () => {
    const template = readFileSync(new URL("../src/viz/orbit_scene.html", import.meta.url), "utf8");
    const script = template.split("<script>")[1].split("</script>")[0];
    const frames = [0, 60, 120].map(time => ({time, positions: [[7000, 0, 0]], impact: false}));
    const packet = {frames, labels: ["Satellite"], earthRadiusKm: 6378, satelliteCount: 1, continuous: true};
    const elements = new Map();
    const graphics = new Proxy({}, {
        get: (_, key) => key === "createRadialGradient" ? () => ({addColorStop() {}}) : () => {},
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
    function deliver(sequence, lastTime, endTime, impact = false) {
        onMessage({source: parent, data: {
            type: "orbit-block",
            packet: {sequence, frames: [{...frames[0], time: lastTime}, {...frames[0], time: endTime, impact}]},
        }});
    }
    vm.runInContext(script.replace("__ENCOUNTER_DATA__", JSON.stringify(packet)), context);

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
