const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '../src/api/templates/chat.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function browser(saved = '[]', intent = { decision: 'chat' }, resolution = { decision: 'cancel' }) {
    const elements = new Map();
    const writes = [];
    const requests = [];
    const routed = [];
    const resolved = [];
    const downloads = [];
    const memories = [];
    const knowledgeActions = [];
    let knowledgeItems = [{ id: '3.0123456789abcdef', text: 'Meu jogo usa Godot', date: '2026-10-18',
        source: 'conhecimentos/aprendizados_gerais.md' }];
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
        window: { matchMedia: () => ({ matches: false }), confirm: () => true },
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
                return { ok: true, json: async () => ({ saved: true, path: 'identidade/preferencias.md' }) };
            }
            if (url === '/memory/knowledge' && !options?.body) {
                return { ok: true, json: async () => ({ items: knowledgeItems }) };
            }
            if (url === '/memory/search') {
                const query = JSON.parse(options.body).query.toLowerCase();
                return { ok: true, json: async () => ({
                    items: knowledgeItems.filter(x => x.text.toLowerCase().includes(query))
                        .map(x => ({ content: x.text, source: x.source, line: 3 })),
                }) };
            }
            if (url === '/memory/knowledge/edit') {
                const body = JSON.parse(options.body);
                knowledgeActions.push({ type: 'edit', ...body });
                knowledgeItems = knowledgeItems.map(x => x.id === body.id
                    ? { ...x, text: body.text, id: '3.abcdefabcdefabcd' } : x);
                return { ok: true, json: async () => ({ action: 'edit' }) };
            }
            if (url === '/memory/knowledge/delete') {
                const body = JSON.parse(options.body);
                knowledgeActions.push({ type: 'delete', ...body });
                knowledgeItems = knowledgeItems.filter(x => x.id !== body.id);
                return { ok: true, json: async () => ({ action: 'delete' }) };
            }
            if (url === '/agent/resolve') {
                resolved.push(JSON.parse(options.body));
                return { ok: true, json: async () => resolution };
            }
            if (url === '/agent/route') {
                routed.push(JSON.parse(options.body));
                return { ok: true, json: async () => intent };
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
    return { context, elements, writes, requests, routed, resolved, memories, knowledgeActions,
        downloads, getBlob: () => blob };
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



test('falha ao salvar permanece visível depois do health check', async () => {
    const ui = browser();
    ui.context.localStorage.setItem = () => { throw new Error('QuotaExceeded'); };
    ui.context.createConversation('oi');
    await ui.context.refreshHealth();
    assert.match(ui.elements.get('storageStatus').textContent, /QuotaExceeded/);
    assert.equal(ui.elements.get('modelName').textContent, 'test-model');
});

test('sem intenção de memória segue para o chat incluindo o histórico', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'Explica variáveis em Python';
    await ui.context.sendMsg();
    assert.equal(ui.routed.length, 1);
    assert.equal(ui.requests.length, 1);
    assert.equal(ui.memories.length, 0);
});

test('pergunta de memória aparece na conversa, sem modal nem botões', async () => {
    const ui = browser('[]', {
        decision: 'ask', target: 'project', text: 'Criar um jogo de corrida',
        question: 'Quer que eu registre essa ideia? Onde?',
    });
    ui.elements.get('userInput').value = 'Tive uma ideia: criar um jogo de corrida';
    await ui.context.sendMsg();
    const conv = ui.context.getActiveConv();
    assert.equal(ui.requests.length, 0);
    assert.equal(ui.memories.length, 0);
    assert.equal(conv.messages.length, 2);
    assert.equal(conv.pendingMemory.text, 'Criar um jogo de corrida');
    assert.match(conv.messages.at(-1).content, /Onde/);
    assert.equal(ui.elements.has('memoryPanel'), false);
});

test('resposta natural à pergunta salva na pasta indicada pelo usuário', async () => {
    const ui = browser('[]', {
        decision: 'ask', target: 'none', text: 'Ideia de criar uma ferramenta de sprites',
        question: 'Quer guardar essa ideia? Em qual pasta?',
    }, {
        decision: 'save', target: 'tool', note_kind: 'none',
        memory: { path: 'ferramentas/ideias.md' },
    });
    ui.elements.get('userInput').value = 'Pensei em criar uma ferramenta para sprites';
    await ui.context.sendMsg();
    ui.elements.get('userInput').value = 'Sim, anota na pasta de ferramentas';
    await ui.context.sendMsg();
    const conv = ui.context.getActiveConv();
    assert.equal(ui.resolved.length, 1);
    assert.equal(ui.resolved[0].original, 'Ideia de criar uma ferramenta de sprites');
    assert.equal(ui.requests.length, 0);
    assert.equal(conv.pendingMemory, undefined);
    assert.equal(conv.messages.length, 4);
    assert.match(conv.messages.at(-1).content, /ferramentas\/ideias.md/);
});

test('resposta negativa cancela memória sem modificar nada', async () => {
    const ui = browser('[]', {
        decision: 'ask', target: 'project', text: 'Jogo de corrida',
        question: 'Quer registrar isso?',
    }, { decision: 'cancel' });
    ui.elements.get('userInput').value = 'Talvez criar um jogo de corrida';
    await ui.context.sendMsg();
    ui.elements.get('userInput').value = 'Não precisa, deixa';
    await ui.context.sendMsg();
    assert.equal(ui.context.getActiveConv().pendingMemory, undefined);
    assert.equal(ui.memories.length, 0);
    assert.match(ui.context.getActiveConv().messages.at(-1).content, /não registrei/);
});

test('nova dúvida mantém contexto pendente até esclarecer destino', async () => {
    const ui = browser('[]', {
        decision: 'ask', target: 'project', text: 'Sistema de batalha',
        question: 'Onde devo guardar?',
    }, { decision: 'ask', target: 'none', question: 'Em projetos ou conhecimentos?' });
    ui.elements.get('userInput').value = 'Pensei em um sistema de batalha';
    await ui.context.sendMsg();
    ui.elements.get('userInput').value = 'Não sei ainda';
    await ui.context.sendMsg();
    const conv = ui.context.getActiveConv();
    assert.equal(conv.pendingMemory.text, 'Sistema de batalha');
    assert.match(conv.messages.at(-1).content, /projetos ou conhecimentos/);
});

test('decisão clara confirmada pelo backend registra sem perguntar nem inventar', async () => {
    const ui = browser('[]', {
        decision: 'save', target: 'preference', text: 'Prefiro respostas objetivas',
        memory: { path: 'identidade/preferencias.md' },
    });
    ui.elements.get('userInput').value = 'Prefiro respostas objetivas, guarda isso';
    await ui.context.sendMsg();
    assert.equal(ui.memories.length, 0);
    assert.equal(ui.requests.length, 0);
    assert.match(ui.context.getActiveConv().messages.at(-1).content, /Registrei no cérebro/);
});

test('conversa natural seleciona projeto sem modal e envia contexto no próximo turno', async () => {
    const ui = browser('[]', {
        decision: 'select_project', target: 'project', text: 'Cidade Noturna',
        selected_project: { name: 'Cidade Noturna', slug: 'cidade-noturna' },
    });
    ui.elements.get('userInput').value = 'Vamos continuar no projeto Cidade Noturna';
    await ui.context.sendMsg();
    assert.equal(ui.context.getActiveConv().project, 'cidade-noturna');
    assert.equal(ui.requests.length, 0);
    assert.match(ui.context.getActiveConv().messages.at(-1).content, /Cidade Noturna/);
    ui.elements.get('userInput').value = 'Qual é nosso próximo passo?';
    await ui.context.sendMsg();
    assert.equal(ui.routed[1].project, 'cidade-noturna');
});

test('criação de projeto é ação real com confirmação do caminho criado', async () => {
    const ui = browser('[]', {
        decision: 'create_project', target: 'project', text: 'Cidade Noturna',
        project: { name: 'Cidade Noturna', path: 'projetos/cidade-noturna' },
    });
    ui.elements.get('userInput').value = 'Vamos criar um projeto novo chamado Cidade Noturna';
    await ui.context.sendMsg();
    assert.equal(ui.requests.length, 0);
    assert.match(ui.context.getActiveConv().messages.at(-1).content, /Criei o projeto Cidade Noturna/);
    assert.match(ui.context.getActiveConv().messages.at(-1).content, /projetos\/cidade-noturna/);
});

test('conversa não muda enquanto classificação ou geração está em curso', async () => {
    const ui = browser();
    let finish;
    const old = ui.context.fetch;
    ui.context.fetch = (url, opts) => {
        if (url === '/chat/stream') return new Promise(resolve => { finish = resolve; });
        return old(url, opts);
    };
    ui.elements.get('userInput').value = 'oi';
    const pending = ui.context.sendMsg();
    await new Promise(resolve => setImmediate(resolve));
    const conv = ui.context.getActiveConv();
    ui.context.newChat();
    assert.equal(ui.context.getActiveConv(), conv);
    finish({ ok: false, json: async () => ({ detail: 'Serviço indisponível' }) });
    await pending;
    assert.equal(conv.messages.length, 1);
});


test('painel de conhecimentos permite consultar, pesquisar, editar e excluir', async () => {
    const ui = browser();
    await ui.context.openBrain();
    assert.equal(ui.elements.get('brainPanel').hidden, false);
    assert.equal(ui.elements.get('brainList').children.length, 1);
    ui.elements.get('brainSearchInput').value = 'Godot';
    await ui.context.searchBrain();
    assert.equal(ui.elements.get('brainList').children.length, 1);
    ui.elements.get('brainSearchInput').value = 'Rust';
    await ui.context.searchBrain();
    assert.match(ui.elements.get('brainList').children[0].textContent, /Nenhum conhecimento/);
    await ui.context.loadBrain();
    ui.context.editBrainItem('3.0123456789abcdef');
    assert.equal(ui.elements.get('brainEditText').value, 'Meu jogo usa Godot');
    ui.elements.get('brainEditText').value = 'Meu jogo usa Unity';
    await ui.context.saveBrainEdit();
    assert.equal(ui.knowledgeActions[0].type, 'edit');
    assert.equal(ui.knowledgeActions[0].text, 'Meu jogo usa Unity');
    await ui.context.deleteBrainItem('3.abcdefabcdefabcd');
    assert.equal(ui.knowledgeActions[1].type, 'delete');
    assert.equal(ui.elements.get('brainList').children.length, 1);
    assert.match(ui.elements.get('brainList').children[0].textContent, /Nenhum conhecimento/);
    ui.context.closeBrain();
    assert.equal(ui.elements.get('brainPanel').hidden, true);
});
