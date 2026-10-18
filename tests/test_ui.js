const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '../src/api/templates/chat.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function browser(saved = '[]') {
    const elements = new Map();
    const writes = [];
    const requests = [];
    const downloads = [];
    const memories = [];
    let blob;
    function element() {
        return {
            textContent: '', innerHTML: '', value: '', style: {}, children: [],
            classList: { toggle() {}, remove() {}, add() {} },
            appendChild(child) { this.children.push(child); },
            replaceChildren() { this.children = []; },
            focus() {},
            click() { downloads.push(this.download); },
        };
    }
    for (const [, id] of html.matchAll(/\bid="([^"]+)"/g)) elements.set(id, element());
    const context = vm.createContext({
        document: {
            getElementById(id) {
                if (!elements.has(id)) elements.set(id, element());
                return elements.get(id);
            },
            createElement: element,
        },
        window: { matchMedia: () => ({ matches: false }) },
        localStorage: {
            getItem: () => saved,
            setItem: (key, value) => writes.push(JSON.parse(value)),
        },
        setInterval() {}, TextDecoder, Blob, console,
        URL: { createObjectURL(value) { blob = value; return 'blob:test'; }, revokeObjectURL() {} },
        fetch: async (url, options) => {
            if (url === '/auth/status') {
                return { ok: true, json: async () => ({ configured: true, authenticated: true }) };
            }
            if (url === '/memory/remember') {
                memories.push(JSON.parse(options.body));
                return { ok: true, json: async () => ({ saved: true }) };
            }
            if (url === '/health') {
                return { ok: true, json: async () => ({ default_model: 'test-model', ollama_status: 'online' }) };
            }
            requests.push(JSON.parse(options.body));
            const data = new TextEncoder().encode('Olá 👋');
            const chunks = [data.slice(0, 3), data.slice(3, 7), data.slice(7)];
            return { ok: true, body: { getReader: () => ({
                read: async () => chunks.length ? { value: chunks.shift(), done: false } : { done: true },
            }) } };
        },
    });
    vm.runInContext(script, context);
    return { context, elements, writes, requests, memories, downloads, getBlob: () => blob };
}

test('histórico mantém ordem, converte bot e respeita orçamento de contexto', () => {
    const { context } = browser();
    const messages = Array.from({ length: 30 }, (_, i) =>
        ({ role: i % 2 ? 'bot' : 'user', content: String(i) }));
    const history = context.buildHistory(messages, 'agora');
    assert.equal(history.length, 20);
    assert.equal(history[0].content, '10');
    assert.equal(history.at(-1).role, 'assistant');
    const large = context.buildHistory(messages.map(m => ({ ...m, content: 'x'.repeat(9000) })), 'oi');
    assert.equal(large.length, 3);
    assert.ok(large.every(m => m.content.length === 8000));
});

test('JSON inválido e IDs perigosos são preservados sem sobrescrever o armazenamento', async () => {
    for (const saved of ['{broken', '{"unexpected":true}',
        '[{"id":"x\\u0027);alert(1)","title":"bad","messages":[]}]']) {
        const ui = browser(saved);
        ui.context.createConversation('nova');
        await ui.context.refreshHealth();
        assert.equal(ui.writes.length, 0);
        assert.equal(ui.elements.get('storageStatus').hidden, false);
        assert.match(ui.elements.get('storageStatus').textContent, /preservadas/);
    }
});

test('enviar inclui histórico, decodifica UTF-8 e exporta Markdown', async () => {
    const ui = browser();
    ui.context.createConversation('Meu nome é Isaac');
    const conv = ui.context.getActiveConv();
    conv.messages.push({ role: 'user', content: 'Meu nome é Isaac' });
    conv.messages.push({ role: 'bot', content: 'Olá, Isaac' });
    ui.elements.get('userInput').value = 'Qual meu nome?';
    await ui.context.sendMsg();
    assert.equal(ui.requests[0].history.length, 2);
    assert.equal(ui.requests[0].history[1].role, 'assistant');
    assert.equal(conv.messages.at(-1).content, 'Olá 👋');
    assert.equal(ui.elements.get('sendBtn').disabled, false);
    ui.context.exportChat();
    assert.match(await ui.getBlob().text(), /## Você\n\nMeu nome é Isaac/);
    assert.match(ui.downloads[0], /^menor-[a-z0-9]+\.md$/);
    ui.context.newChat();
    ui.elements.get('userInput').value = 'Outra conversa';
    await ui.context.sendMsg();
    assert.equal(ui.elements.get('messagesContainer').children.length, 2);
});

test('falha no stream aparece na interface e não vira resposta no histórico', async () => {
    const ui = browser();
    ui.context.fetch = async () => ({
        ok: true, body: { getReader: () => ({ read: async () => { throw new Error('interrompido'); } }) },
    });
    ui.elements.get('userInput').value = 'oi';
    await ui.context.sendMsg();
    assert.equal(ui.context.getActiveConv().messages.length, 1);
    const rows = ui.elements.get('messagesContainer').children;
    assert.match(rows.at(-1).children[0].textContent, /interrompido/);
    assert.equal(ui.elements.get('sendBtn').disabled, false);
});

test('conversa não pode mudar enquanto há uma resposta em andamento', async () => {
    const ui = browser();
    let finish;
    ui.context.fetch = () => new Promise(resolve => { finish = resolve; });
    ui.elements.get('userInput').value = 'oi';
    const pending = ui.context.sendMsg();
    const original = ui.context.getActiveConv();
    ui.context.newChat();
    ui.context.openConv('outra');
    ui.context.deleteConv(original.id, { stopPropagation() {} });
    assert.equal(ui.context.getActiveConv(), original);
    finish({ ok: false, json: async () => ({ detail: 'Serviço indisponível' }) });
    await pending;
    assert.equal(ui.context.getActiveConv().messages.length, 1);
});

test('falha ao salvar permanece visível depois do health check', async () => {
    const ui = browser();
    ui.context.localStorage.setItem = () => { throw new Error('QuotaExceeded'); };
    ui.context.createConversation('oi');
    await ui.context.refreshHealth();
    assert.match(ui.elements.get('storageStatus').textContent, /QuotaExceeded/);
    assert.equal(ui.elements.get('modelName').textContent, 'test-model');
});

test('lembre disso exige confirmação e grava no cérebro sem chamar Ollama', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'Menor, lembre disso: Prefiro respostas objetivas';
    await ui.context.sendMsg();
    assert.equal(ui.requests.length, 0);
    assert.equal(ui.memories.length, 0);
    assert.equal(ui.elements.get('memoryPanel').hidden, false);
    assert.equal(ui.elements.get('memoryText').textContent, 'Prefiro respostas objetivas');
    await ui.context.confirmMemory('preference');
    assert.equal(ui.memories.length, 1);
    assert.equal(ui.memories[0].kind, 'preference');
    assert.equal(ui.memories[0].text, 'Prefiro respostas objetivas');
    assert.equal(ui.elements.get('memoryPanel').hidden, true);
    assert.equal(ui.context.getActiveConv().messages.length, 2);
    assert.match(ui.context.getActiveConv().messages[1].content, /Preferência salva/);
});

test('cancelar memória não a salva e aprendizado permanece separado de preferência', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'lembre disso: Meu jogo usa Godot';
    await ui.context.sendMsg();
    ui.context.cancelMemory();
    assert.equal(ui.memories.length, 0);
    ui.elements.get('userInput').value = 'lembre disso: Meu jogo usa Godot';
    await ui.context.sendMsg();
    await ui.context.confirmMemory('knowledge');
    assert.equal(ui.memories[0].kind, 'knowledge');
    assert.match(ui.context.getActiveConv().messages[1].content, /Conhecimento anotado/);
});
