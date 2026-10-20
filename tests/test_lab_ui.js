"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const page = fs.readFileSync(path.join(__dirname, "../src/api/templates/remote_lab.html"), "utf8");
const match = page.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(match, "Menor Lab should include its inline script");
const source = match[1];

test("Menor Lab: inline JavaScript is valid (including push handler)", () => {
    assert.doesNotThrow(() => new vm.Script(source, { filename: "remote_lab.html" }));
});

test("Menor Lab: loads saved reports and offers explicit manual GitHub push", async () => {
    const elements = new Map();
    const requests = [];
    const report = {
        run_id: "20261020T005944Z-c232a9e6",
        total: 5, automatic_passes: 2, ungraded: 3,
    };
    function element() {
        return {
            textContent: "", value: "", style: {}, children: [], disabled: false,
            listeners: {},
            append(child) { this.children.push(child); },
            replaceChildren() { this.children = []; },
            setAttribute() {},
            addEventListener(name, callback) { this.listeners[name] = callback; },
        };
    }
    for (const [, id] of page.matchAll(/\bid="([^"]+)"/g)) elements.set(id, element());
    const context = vm.createContext({
        document: {
            getElementById(id) { return elements.get(id); },
            createElement() { return element(); },
        },
        confirm: () => true,
        setTimeout() {},
        fetch: async (url, opts) => {
            requests.push({ url, opts });
            if (url === "/lab/batches") {
                return { ok: true, json: async () => ({ items: [
                    { id: "diagnostico-inicial", title: "Diagnóstico inicial", cases: 5 },
                ] }) };
            }
            if (url === "/lab/reports") {
                return { ok: true, json: async () => ({ items: [report] }) };
            }
            if (url === "/lab/reports/" + report.run_id + "/publish") {
                return { ok: true, json: async () => ({
                    url: "https://github.com/example/private-repo/blob/lab-reports/report.json",
                }) };
            }
            throw new Error("Unexpected endpoint: " + url);
        },
    });
    vm.runInContext(source, context);
    // Let the initial batchRefresh Promise.all and JSON reads resolve.
    await new Promise(resolve => setImmediate(resolve));
    const list = elements.get("batchReports");
    assert.equal(list.children.length, 1);
    const paragraph = list.children[0];
    assert.equal(paragraph.children.length, 2);
    const [download, push] = paragraph.children;
    assert.match(download.href, /\/lab\/reports\/.+\/download/);
    assert.equal(push.textContent, "Enviar ao GitHub");
    assert.equal(requests.filter(x => x.url.endsWith("/publish")).length, 0);
    await push.listeners.click();
    assert.equal(requests.filter(x => x.url.endsWith("/publish")).length, 1);
    assert.equal(requests.at(-1).opts.method, "POST");
    assert.equal(requests.at(-1).opts.credentials, "same-origin");
    assert.equal(push.textContent, "Enviado");
    assert.match(elements.get("batchStatus").textContent, /Relatório publicado/);
});
