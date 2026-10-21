"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const lab = fs.readFileSync(path.join(__dirname, "../src/api/templates/remote_lab.html"), "utf8");
const chat = fs.readFileSync(path.join(__dirname, "../src/api/templates/chat.html"), "utf8");
const source = lab.match(/<script>([\s\S]*?)<\/script>/)?.[1];

const SUITES = [{"id":"planejamento-supervisionado","title":"Planejamento supervisionado","description":"Planos completos","cases":12,"run_count":0,"status":"pending","recommended_order":1,"recommended_label":"Planos e ferramentas","last_report":null},{"id":"programacao-debug","title":"Programação","description":"Bugs e revisões","cases":12,"run_count":0,"status":"pending","recommended_order":2,"recommended_label":"Programação e correção","last_report":null},{"id":"matematica-validacao-v2","title":"Aritmética v2","description":"Valores numéricos","cases":12,"run_count":1,"status":"completed","recommended_order":3,"recommended_label":"Matemática: valor e formato","last_report":{"run_id":"20261020T005944Z-c232a9e6","total":12,"automatic_passes":5,"automatic_failures":2,"ungraded":5}},{"id":"regressoes-planejamento-v3","title":"Segurança dos planos","description":"Restrições do usuário","cases":24,"run_count":0,"status":"pending","recommended_order":4,"recommended_label":"Segurança dos planos","last_report":null},{"id":"conversacao-robustez","title":"Conversa informal","description":"Coerência de conversa","cases":12,"run_count":2,"status":"completed","recommended_order":null,"recommended_label":null,"last_report":{"run_id":"20261020T131632Z-d0a1d5d8","total":12,"automatic_passes":6,"automatic_failures":2,"ungraded":4}}];
const REPORT = {
    suite_id: "matematica-validacao-v2", run_id: "20261020T005944Z-c232a9e6",
    total: 12, automatic_passes: 5, automatic_failures: 2, ungraded: 5,
};

function makeElement(tag = "") {
    return {
        tag, textContent: "", value: "", style: {}, children: [], disabled: false,
        hidden: false, checked: false, attrs: {}, listeners: {}, className: "",
        append(...items) { this.children.push(...items); },
        replaceChildren(...items) { this.children = [...items]; },
        setAttribute(name, value) { this.attrs[name] = value; },
        addEventListener(name, callback) { this.listeners[name] = callback; },
    };
}
function browser(overrides = {}) {
    const elements = new Map();
    for (const [, id] of lab.matchAll(/\bid="([^"]+)"/g))
        elements.set(id, makeElement(id));
    const requests = [];
    const confirmations = [];
    const app = {
        suites: (overrides.suites || SUITES).map(item => ({...item})),
        reports: overrides.reports || [REPORT],
        syncedStatuses: overrides.syncedStatuses || {},
        status: overrides.status || {status:"idle"},
        compare: overrides.compare || {},
        denied: overrides.denied || false,
        timeouts: [],
    };
    const context = vm.createContext({
        document: {
            getElementById(id) { return elements.get(id); },
            createElement(tag) { return makeElement(tag); },
        },
        confirm(message) { confirmations.push(message); return !app.denied; },
        setTimeout(callback, ms) { const ref = {callback, ms}; app.timeouts.push(ref); return ref; },
        clearTimeout(ref) {
            const pos = app.timeouts.indexOf(ref);
            if (pos >= 0) app.timeouts.splice(pos, 1);
        },
        FormData: class { append() {} },
        fetch: async (url, opts) => {
            requests.push({url, opts});
            if (url === "/models")
                return {ok:!overrides.modelsFailed, json:async () => ({models:overrides.models || [
                    {name:"control:7b"}, {name:"candidate:14b"},
                ]})};
            if (url === "/lab/compare")
                return {ok:true, json:async () => app.compare};
            if (url === "/lab/batches")
                return {ok:true, json:async () => ({items:app.suites})};
            if (url === "/lab/reports")
                return {ok:true, json:async () => ({items:app.reports})};
            if (url === "/lab/reports/sync") {
                const counts = {not_sent:0, sent:0, conflict:0, invalid:0};
                for (const state of Object.values(app.syncedStatuses))
                    if (Object.hasOwn(counts, state)) counts[state] += 1;
                return {ok:true, json:async () => ({available:true,
                    items:app.syncedStatuses, counts})};
            }
            if (url === "/lab/reports/publish-batch")
                return {ok:true, json:async () => ({status:"running", total:1})};
            if (url === "/lab/reports/publish-batch/status")
                return {ok:true, json:async () => ({status:"completed", total:1, done:1, errors:[]})};
            if (url === "/lab/batches/status")
                return {ok:true, json:async () => app.status};
            if (url === "/lab/batches/queue") {
                const ids = JSON.parse(opts.body).suite_ids;
                app.status = {
                    status:"running", suite_id:ids[0], done:0,
                    total:app.suites.find(s => s.id === ids[0]).cases,
                    queue_index:1, queue_total:ids.length,
                    overall_done:0, overall_total:ids.reduce(
                        (sum,id) => sum + app.suites.find(s => s.id === id).cases, 0),
                    queue_finished:[], queue_failures:[],
                };
                return {ok:true, json:async () => ({suite_ids:ids})};
            }
            if (url.endsWith("/publish"))
                return {ok:true, json:async () => ({url:"https://github.com/example/report"})};
            if (url === "/lab/batches/import")
                return {ok:true, json:async () => ({id:"imported-batch"})};
            throw new Error("Unexpected endpoint: " + url);
        },
    });
    vm.runInContext(source, context);
    const ready = () => new Promise(resolve => setImmediate(resolve));
    const list = () => elements.get("suiteList").children;
    const idText = node => node.children[0].children[1].children[2].textContent.replace(/^ID: /, "");
    const cards = () => list().map(node => ({node, id:idText(node), checkbox:node.children[0].children[0]}));
    const click = (id) => elements.get(id).listeners.click();
    const input = (id, value) => {
        elements.get(id).value = value;
        elements.get(id).listeners.input();
    };
    return {elements, requests, confirmations, app, ready, list, cards, click, input, context};
}

test("Lab: script parses and chat has desktop and mobile navigation to the lab", () => {
    assert.ok(source);
    assert.doesNotThrow(() => new vm.Script(source, {filename:"remote_lab.html"}));
    assert.equal((chat.match(/href="\/lab\/view"/g) || []).length, 3);
    assert.match(chat, /Laboratório · Testes/);
    assert.match(chat, /Lab · Testes/);
});

test("Lab: installed model applies to direct, planner and queue without changing defaults", async () => {
    const ui = browser();
    await ui.ready();
    assert.equal(ui.requests.filter(item => item.opts?.method === "POST").length, 0);
    assert.deepEqual(ui.elements.get("evaluationModel").children.map(item => item.value),
        ["", "control:7b", "candidate:14b"]);
    ui.elements.get("evaluationModel").value = "candidate:14b";
    ui.elements.get("question").value = "Uma pergunta pública";
    await ui.click("runDirect");
    await ui.click("runPlanner");
    for (const call of ui.requests.filter(item => item.url === "/lab/compare"))
        assert.equal(JSON.parse(call.opts.body).model, "candidate:14b");
    await ui.click("selectRecommended");
    await ui.click("batchRun");
    assert.equal(JSON.parse(ui.requests.find(item => item.url === "/lab/batches/queue").opts.body).model,
        "candidate:14b");
    assert.match(ui.confirmations[0], /candidate:14b/);
});

test("Lab: missing model list keeps default and never starts inference", async () => {
    const ui = browser({modelsFailed:true});
    await ui.ready();
    assert.match(ui.elements.get("modelStatus").textContent, /Não consegui/);
    assert.equal(ui.elements.get("evaluationModel").value, "");
    assert.equal(ui.requests.filter(item => item.opts?.method === "POST").length, 0);
});

test("Lab: shows reliable totals, done and pending from saved reports", async () => {
    const ui = browser();
    await ui.ready();
    assert.equal(ui.elements.get("suiteTotal").textContent, "5");
    assert.equal(ui.elements.get("suiteDone").textContent, "2");
    assert.equal(ui.elements.get("suitePending").textContent, "3");
    assert.equal(ui.cards().length, 3);
    assert.ok(ui.cards().every(item => /Pendente/.test(
        item.node.children[1].children[0].children[0].textContent)));
    const item = ui.cards()[0];
    assert.match(item.node.children[0].children[1].children[2].textContent, /ID: /);
    assert.equal(ui.elements.get("batchRun").disabled, true);
});

test("Lab: filters completed, recommended, all and searches IDs without losing selection", async () => {
    const ui = browser();
    await ui.ready();
    await ui.click("filterDone");
    assert.equal(ui.cards().length, 2);
    assert.ok(ui.cards().every(item => item.checkbox.checked === false));
    await ui.click("filterRecommended");
    assert.equal(ui.cards().length, 4);
    const desired = ui.cards().find(item => item.id === "matematica-validacao-v2");
    desired.checkbox.checked = true; desired.checkbox.listeners.change();
    ui.input("suiteSearch", "programacao");
    assert.equal(ui.cards().length, 1);
    ui.input("suiteSearch", "");
    const retained = ui.cards().find(item => item.id === "matematica-validacao-v2");
    assert.equal(retained.checkbox.checked, true);
    assert.match(ui.elements.get("selectionCount").textContent, /1 bateria/);
    assert.equal(ui.elements.get("filterRecommended").attrs["aria-pressed"], "true");
    await ui.click("filterAll");
    assert.equal(ui.cards().length, 5);
});

test("Lab: one click queues multiple checked suites in recommended order", async () => {
    const ui = browser();
    await ui.ready();
    await ui.click("selectRecommended");
    assert.match(ui.elements.get("selectionCount").textContent, /4 bateria/);
    assert.match(ui.elements.get("selectionCount").textContent, /60 caso/);
    await ui.click("batchRun");
    const posts = ui.requests.filter(x => x.url === "/lab/batches/queue");
    assert.equal(posts.length, 1);
    const payload = JSON.parse(posts[0].opts.body);
    assert.deepEqual(payload.suite_ids, [
        "planejamento-supervisionado", "programacao-debug",
        "matematica-validacao-v2", "regressoes-planejamento-v3",
    ]);
    assert.equal(posts[0].opts.credentials, "same-origin");
    assert.equal(posts[0].opts.method, "POST");
    assert.match(ui.confirmations[0], /60 perguntas/);
    assert.equal(ui.elements.get("batchRun").disabled, true);
    assert.equal(ui.elements.get("queuePanel").hidden, false);
    assert.match(ui.elements.get("queueTitle").textContent, /1 de 4/);
});

test("Lab: queue state survives page reopening while service is active", async () => {
    const ui = browser({status: {
        status:"running", suite_id:"programacao-debug",
        queue_index:2, queue_total:4, overall_done:16, overall_total:60,
        queue_finished: [{suite_id:"planejamento-supervisionado", status:"completed"}],
    }});
    await ui.ready();
    assert.equal(ui.elements.get("queuePanel").hidden, false);
    assert.match(ui.elements.get("queueTitle").textContent, /2 de 4/);
    assert.match(ui.elements.get("queueCurrent").textContent, /Programação/);
    assert.equal(ui.elements.get("queueProgress").value, 16);
    assert.equal(ui.elements.get("queueProgress").max, 60);
    assert.equal(ui.elements.get("batchRun").disabled, true);
});

test("Lab: groups history instead of listing every report, with manual publish", async () => {
    const ui = browser({reports:[
        REPORT, {...REPORT, run_id:"20261020T131632Z-d0a1d5d8"},
        {...REPORT, suite_id:"conversacao-robustez", run_id:"20261020T131502Z-b58ba2c6"},
    ]});
    await ui.ready();
    assert.equal(ui.elements.get("reportsHistory").tag, "reportsHistory");
    assert.match(ui.elements.get("historySummary").textContent, /3/);
    const groups = ui.elements.get("batchReports").children;
    assert.equal(groups.length, 2);
    assert.match(groups[0].children[0].textContent, /2 execução/);
    assert.equal(ui.requests.filter(x => x.url.endsWith("/publish")).length, 0);
    const record = groups[0].children[1];
    assert.match(record.children[0].textContent, /00:59 UTC/);
    const actions = record.children[1].children;
    assert.match(actions[0].href, /download/);
    await actions[1].listeners.click();
    assert.equal(ui.requests.filter(x => x.url.endsWith("/publish")).length, 1);
    assert.equal(actions[1].textContent, "Enviado");
});

test("Lab: manual comparison continues reporting bounded diagnostic metadata", async () => {
    const ui = browser({compare:{
        reply:"Não consegui validar", status:"no_valid_decision", elapsed_seconds:29,
        diagnostics:{outcome:"invalid_decision", output_limited:true,
                     raw_error:"PRIVATE", validation_issue:"goal"},
        performance:{eval_count:480, generation_tokens_per_second:7.23},
        reply_truncated:true,
    }});
    await ui.ready();
    ui.elements.get("question").value = "Planeje um exemplo";
    await ui.click("runPlanner");
    const meta = ui.elements.get("plannerMeta").textContent;
    for (const expected of [
        "Contrato rejeitado", "Objetivo ausente ou inválido",
        "Limite de geração atingido", "Trecho exibido limitado",
        "480 tokens gerados", "7.23 tokens/s",
    ]) assert.ok(meta.includes(expected));
    assert.doesNotMatch(meta, /PRIVATE/);
    assert.equal(ui.elements.get("runPlanner").disabled, false);
});

test("Lab: stale or private diagnostics never appear in the UI", async () => {
    const ui = browser({compare:{
        reply:"Resposta antiga", status:"answered", elapsed_seconds:2,
        diagnostics:{outcome:"PRIVATE", validation_issue:"PRIVATE"},
        performance:{eval_count:"PRIVATE", generation_tokens_per_second:Infinity},
    }});
    await ui.ready();
    ui.elements.get("question").value = "Explique um exemplo";
    await ui.click("runDirect");
    assert.equal(ui.elements.get("directResult").textContent, "Resposta antiga");
    assert.doesNotMatch(ui.elements.get("directMeta").textContent, /PRIVATE|Infinity/);
});

test("Lab: declining queue confirmation starts nothing", async () => {
    const ui = browser({denied:true});
    await ui.ready();
    await ui.click("selectRecommended");
    await ui.click("batchRun");
    assert.equal(ui.requests.filter(x => x.url === "/lab/batches/queue").length, 0);
});


test("Lab: manual direct comparison allows selecting improved profile without changing historical default", async () => {
    const ui = browser({compare:{
        reply:"Não.", status:"answered", elapsed_seconds:1.4, profile:"assistant",
        output_budget_tokens:56, performance:{eval_count:3, generation_tokens_per_second:10},
    }});
    await ui.ready();
    ui.elements.get("question").value = "Só SIM ou NÃO.";
    ui.elements.get("directProfile").value = "assistant";
    await ui.click("runDirect");
    const calls = ui.requests.filter(x => x.url === "/lab/compare");
    assert.equal(calls.length, 1);
    assert.equal(JSON.parse(calls[0].opts.body).profile, "assistant");
    assert.match(ui.elements.get("directMeta").textContent, /Perfil: assistant/);
    assert.match(ui.elements.get("directMeta").textContent, /56 tokens/);
    ui.elements.get("directProfile").value = "";
    await ui.click("runDirect");
    assert.equal(JSON.parse(ui.requests.at(-1).opts.body).profile, "baseline");
});

test("E7: laboratório preserva resultados, seleção e atalhos de navegação", () => {
    for (const id of ["teste-avulso", "suiteList", "selectionCount",
        "batchRun", "suiteSearch", "runDirect", "runPlanner", "reportsHistory"])
        assert.match(lab, new RegExp('id="' + id + '"'));
    assert.match(lab, /class="compare-results"/);
    assert.match(lab, /class="lab-jump-nav"/);
    assert.match(lab, /class="batch-action-bar"/);
    assert.match(lab, /aria-label="Seções do laboratório"/);
});

test("E7: painel de teste avulso fecha semanticamente antes dos dois resultados", () => {
    assert.match(lab, /id="teste-avulso"[\s\S]*id="status"[\s\S]*<\/section>\s*<div class="compare-results"/);
});

test("E8: seleção em um toque marca só as oito suítes, não os testes antigos", async () => {
    const e8 = [
        "e8-conversa-natural", "e8-contexto-sequencia", "e8-aprovacao-dialogo",
        "e8-codigo-escopo", "e8-honestidade-execucao", "e8-falhas-recuperacao",
        "e8-seguranca-privacidade", "e8-raciocinio-qualidade",
    ];
    const entries = SUITES.concat(e8.map(id => ({id, title:id, description:"E8",
        cases:16, run_count:0, status:"pending", last_report:null})));
    const ui = browser({suites:entries, reports:[]});
    await ui.ready();
    await ui.click("selectRecommended");
    ui.input("suiteSearch", "algum termo");
    await ui.click("selectE8");
    assert.equal(ui.elements.get("suiteSearch").value, "");
    assert.equal(ui.elements.get("filterAll").attrs["aria-pressed"], "true");
    assert.match(ui.elements.get("selectionCount").textContent, /8 bateria/);
    assert.match(ui.elements.get("selectionCount").textContent, /128 caso/);
    assert.match(ui.elements.get("batchStatus").textContent, /modelo/);
    await ui.click("batchRun");
    const calls = ui.requests.filter(x => x.url === "/lab/batches/queue");
    assert.equal(calls.length, 1);
    const ids = JSON.parse(calls[0].opts.body).suite_ids;
    assert.deepEqual([...ids].sort(), [...e8].sort());
    assert.match(ui.confirmations[0], /128 perguntas/);
    assert.equal(ui.elements.get("queuePanel").hidden, false);
});

test("E8: seletor não inicia teste sozinho, sem deployment e durante fila ativa", async () => {
    const ui = browser({suites:SUITES, reports:[]});
    await ui.ready();
    await ui.click("selectE8");
    assert.match(ui.elements.get("batchStatus").textContent, /não estão instaladas/);
    assert.equal(ui.elements.get("batchRun").disabled, true);
    assert.equal(ui.requests.filter(x => x.url === "/lab/batches/queue").length, 0);
    ui.app.status = {status:"running", queue_total:2, queue_index:1,
        suite_id:"programacao-debug", overall_total:24, overall_done:3};
    await ui.click("batchRefresh");
    await ui.click("selectE8");
    assert.equal(ui.requests.filter(x => x.url === "/lab/batches/queue").length, 0);
});

test("Lab: user chooses two installed models at queue execution, independently", async () => {
    const ui = browser();
    await ui.ready();
    const labels = ui.elements.get("batchModelChoices").children;
    assert.equal(labels.length, 2);
    const a = labels[0].children[0], b = labels[1].children[0];
    a.checked = true; a.listeners.change();
    b.checked = true; b.listeners.change();
    await ui.click("selectRecommended");
    assert.match(ui.elements.get("selectionCount").textContent, /120 caso/);
    await ui.click("batchRun");
    const payload = JSON.parse(ui.requests.find(x => x.url === "/lab/batches/queue").opts.body);
    assert.deepEqual(payload.models, ["control:7b", "candidate:14b"]);
    assert.equal(payload.suite_ids.length, 4);
    assert.match(ui.confirmations[0], /control:7b.*candidate:14b/);
});

test("Lab: history is paged and only verified missing reports can be sent in bulk", async () => {
    const reports = Array.from({length:18}, (_, i) => ({
        ...REPORT, run_id:"20261021T" + String(i).padStart(6,"0") + "Z-" +
            i.toString(16).padStart(8,"0"),
    }));
    const syncedStatuses = Object.fromEntries(reports.map((r,i) =>
        [r.run_id, i === 0 ? "not_sent" : "sent"]));
    const ui = browser({reports, syncedStatuses});
    await ui.ready();
    assert.equal(ui.elements.get("batchReports").children[0].children.length, 16);
    assert.equal(ui.elements.get("moreReports").hidden, false);
    await ui.click("syncReports");
    assert.match(ui.elements.get("reportSyncStatus").textContent, /1 não enviados/);
    await ui.click("selectNotSent");
    assert.match(ui.elements.get("reportSelection").textContent, /1 relatório/);
    await ui.click("publishSelected");
    const requests = ui.requests.filter(x => x.url === "/lab/reports/publish-batch");
    assert.equal(requests.length, 1);
    assert.deepEqual(JSON.parse(requests[0].opts.body).run_ids, [reports[0].run_id]);
    assert.match(ui.confirmations[0], /COMPLETOS/);
});

test("Lab: without GitHub verification nothing enters unsent bulk queue", async () => {
    const ui = browser();
    await ui.ready();
    await ui.click("selectNotSent");
    assert.match(ui.elements.get("reportSyncStatus").textContent, /Primeiro verifique/);
    assert.equal(ui.elements.get("publishSelected").disabled, true);
    assert.equal(ui.requests.filter(x => x.url === "/lab/reports/publish-batch").length, 0);
});
