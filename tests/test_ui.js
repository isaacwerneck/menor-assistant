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
    const imageCalls = [];
    const agentCalls = [];
    const repairCalls = [];
    const missionCalls = [];
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
        FormData: class { constructor() { this.values = {}; } append(k, v) { this.values[k] = v; } },
        URL: { createObjectURL(value) { blob = value; return 'blob:test'; }, revokeObjectURL() {} },
        fetch: async (url, options) => {
            if (url === '/agent/run') {
                agentCalls.push(JSON.parse(options.body));
                return { ok: true, json: async () => ({ handled: false }) };
            }
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
            if (url === '/images/intent') {
                const body = JSON.parse(options.body);
                imageCalls.push({ type: 'intent', body });
                const text = body.message.toLowerCase();
                if (text.includes('imagem') && text.includes('crie') && !text.includes(' de ')) {
                    return { ok: true, json: async () => ({
                        decision: 'image_ask', kind: 'generate',
                        question: 'Que imagem você quer? Me descreve a cena e o estilo.',
                    }) };
                }
                if (text.includes('cria uma imagem de') || text.includes('gerar uma imagem de')) {
                    return { ok: true, json: async () => ({
                        decision: 'image_generate', prompt: body.message,
                    }) };
                }
                if (text.includes('edita essa foto')) {
                    return { ok: true, json: async () => ({
                        decision: body.has_attachment ? 'image_edit' : 'image_ask',
                        kind: 'edit', prompt: body.message,
                        question: 'Anexa a foto.',
                    }) };
                }
                return { ok: true, json: async () => ({ decision: 'chat' }) };
            }
            if (/^\/images\/files\/[a-f0-9]{32}$/.test(url)) {
                return { ok: true, blob: async () => new Blob(['PNG mock'], { type: 'image/png' }) };
            }
            if (url === '/images/generate') {
                imageCalls.push({ type: 'generate', body: JSON.parse(options.body) });
                return { ok: true, json: async () => ({
                    status: 'completed', url: '/images/files/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                }) };
            }
            if (url === '/images/edit') {
                imageCalls.push({ type: 'edit', body: options.body });
                return { ok: true, json: async () => ({
                    status: 'completed', url: '/images/files/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                }) };
            }
            if (url === '/agent/improve') {
                repairCalls.push(JSON.parse(options.body));
                return { ok: true, json: async () => ({
                    status: 'pr_created', url: 'https://github.com/example/pull/10',
                }) };
            }
            if (url === '/agent/missions') {
                missionCalls.push({ type: 'begin', data: JSON.parse(options.body) });
                return { ok: true, json: async () => ({
                    id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    status: 'gathering', question: 'Como você quer essa ferramenta?',
                }) };
            }
            if (url === '/agent/missions/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/requirements') {
                missionCalls.push({ type: 'requirements', data: JSON.parse(options.body) });
                return { ok: true, json: async () => ({
                    status: 'awaiting_approval',
                    plan: {
                        steps: ['Preparar o modelo local e validar entradas de texto'],
                        acceptance: ['Imagem PNG testada com verificação de arquivo'],
                        limitations: ['Pode ser lento na CPU'],
                    },
                    question: 'Posso instalar o modelo local?',
                }) };
            }
            if (url === '/agent/missions/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/question') {
                missionCalls.push({ type: 'question', data: JSON.parse(options.body) });
                return { ok: true, json: async () => ({
                    reply: 'A geração calcula etapas na CPU. Não há benchmark ainda. A aprovação continua pendente.',
                }) };
            }
            if (url === '/agent/missions/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/approve') {
                missionCalls.push({ type: 'approve', data: JSON.parse(options.body) });
                return { ok: true, json: async () => ({
                    status: 'queued', question: 'Aprovado. Aguardando o worker.',
                }) };
            }
            if (url === '/agent/missions/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa') {
                return { ok: true, json: async () => ({ status: 'ready' }) };
            }
            if (url === '/agent/skills') {
                return { ok: true, json: async () => ({ items: [
                    { capability: 'images.generate', ready: true,
                        mission_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' },
                ] }) };
            }
            if (url === '/agent/route') {
                routed.push(JSON.parse(options.body));
                return { ok: true, json: async () => intent };
            }
            if (url === '/health') {
                return { ok: true, json: async () => ({ default_model: 'test-model', ollama_status: 'online', api_contract: 1 }) };
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
    return { context, elements, writes, requests, routed, resolved, memories, knowledgeActions, imageCalls, agentCalls, repairCalls, missionCalls,
        downloads, getBlob: () => blob };
}

test('núcleo do servidor assume tarefa e mostra recibo sem chamar roteadores antigos', async () => {
    const ui = browser();
    ui.context.fetch = async () => ({ ok: true, json: async () => ({
        handled: true, reply: 'Consulta concluída.', events: [{ tool: 'projects.list', status: 'executed' }],
    }) });
    ui.elements.get('userInput').value = 'Liste meus projetos';
    await ui.context.sendMsg();
    assert.match(ui.context.getActiveConv().messages.at(-1).content, /projects.list/);
    assert.equal(ui.routed.length, 0);
    assert.equal(ui.requests.length, 0);
});

test('novo pedido de ferramenta interrompe memória pendente sem salvar a ideia', async () => {
    const ui = browser();
    ui.context.createConversation('pixel art');
    const conv = ui.context.getActiveConv();
    conv.pendingMemory = { text: 'Criar pixel art', target: 'tool', question: 'Em qual pasta?' };
    ui.context.fetch = async url => {
        assert.equal(url, '/agent/run');
        return { ok: true, json: async () => ({ handled: true, phase: 'mission', reply: 'Como deve funcionar?' }) };
    };
    ui.elements.get('userInput').value = 'quero que vc crie uma ferramenta de criar pixel art!';
    await ui.context.sendMsg();
    assert.equal(conv.pendingMemory, undefined);
    assert.equal(ui.resolved.length, 0);
    assert.equal(ui.routed.length, 0);
    assert.equal(ui.memories.length, 0);
    assert.match(conv.messages.at(-1).content, /Como deve funcionar/);
});

test('API antiga informa incompatibilidade sem inventar resposta textual', async () => {
    const ui = browser();
    ui.context.fetch = async () => ({ status: 404, ok: false });
    ui.elements.get('userInput').value = 'conseguimos fazer uma imagem?';
    await ui.context.sendMsg();
    const rows = ui.elements.get('messagesContainer').children;
    assert.match(rows.at(-1).children[0].textContent, /deploy e reinício/);
    assert.equal(ui.context.getActiveConv().messages.length, 1);
    assert.equal(ui.requests.length, 0);
});

test('retry de rede conserva o mesmo identificador e conteúdo do turno', async () => {
    const ui = browser();
    const sent = [];
    ui.context.fetch = async (url, options) => {
        sent.push(JSON.parse(options.body));
        if (sent.length === 1) throw new Error('conexão perdida');
        return { ok: true, json: async () => ({ handled: true, reply: 'Resultado recuperado.' }) };
    };
    ui.elements.get('userInput').value = 'Liste meus projetos';
    await ui.context.sendMsg();
    ui.elements.get('userInput').value = 'Liste meus projetos';
    await ui.context.sendMsg();
    assert.equal(sent[0].turn_id, sent[1].turn_id);
    assert.deepEqual(sent[0], sent[1]);
});

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
    ui.context.fetch = async url => url === '/agent/run'
        ? { ok: true, json: async () => ({ handled: false }) }
        : { ok: true, body: { getReader: () => ({ read: async () => { throw new Error('interrompido'); } }) } };
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


test('pedido de imagem sem cena inicia conversa e aceita detalhe posterior', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'quero q vc crie uma imagem pra mim';
    await ui.context.sendMsg();
    const conv = ui.context.getActiveConv();
    assert.equal(conv.pendingImage.kind, 'generate');
    assert.match(conv.messages.at(-1).content, /Que imagem você quer/);
    assert.equal(ui.requests.length, 0);
    ui.elements.get('userInput').value = 'um gato cinza no parque, realista e vertical';
    await ui.context.sendMsg();
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 1);
    assert.equal(conv.pendingImage, undefined);
    assert.equal(conv.messages.at(-1).image, '/images/files/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
});

test('pedido de imagem completo gera resultado sem passar pelo chat textual', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'cria uma imagem de uma moto preta numa rua chuvosa';
    await ui.context.sendMsg();
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 1);
    assert.equal(ui.routed.length, 0);
    assert.match(ui.context.getActiveConv().messages.at(-1).content, /Imagem gerada/);
});

test('editar foto usa anexo discreto e não envia arquivo ao Ollama textual', async () => {
    const ui = browser();
    const file = { name: 'foto.png', size: 1024 };
    const input = ui.elements.get('imageAttachment');
    input.files = [file];
    ui.context.imageSelected(input);
    ui.elements.get('userInput').value = 'edita essa foto e troca o fundo por azul';
    await ui.context.sendMsg();
    assert.equal(ui.imageCalls.filter(x => x.type === 'edit').length, 1);
    assert.equal(ui.routed.length, 0);
    assert.equal(ui.context.getActiveConv().messages.at(-1).image,
        '/images/files/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
    assert.equal(ui.elements.get('imageAttachmentName').hidden, true);
});

test('estado de imagem persiste na conversa e pode ser cancelado', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'quero q vc crie uma imagem pra mim';
    await ui.context.sendMsg();
    ui.elements.get('userInput').value = 'cancela';
    await ui.context.sendMsg();
    assert.equal(ui.context.getActiveConv().pendingImage, undefined);
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 0);
    assert.match(ui.context.getActiveConv().messages.at(-1).content, /cancelei/);
});


test('pedido de corrigir bug em linguagem natural não pula o agente para autoedição', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'Menor, corrige esse bug no código do roteador';
    await ui.context.sendMsg();
    assert.equal(ui.repairCalls.length, 0);
    assert.equal(ui.agentCalls.length, 1);
    assert.equal(ui.requests.length, 1);
});

test('pedido de planejar melhoria não inicia autoedição sem autorização', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'quero organizar meu projeto menor assistant. ' +
        'crie um objetivo para melhorar a interface, divida em 3 etapas e me mostre o plano ' +
        'antes de executar qualquer ação';
    await ui.context.sendMsg();
    assert.equal(ui.repairCalls.length, 0);
    assert.equal(ui.agentCalls.length, 1);
    assert.equal(ui.requests.length, 1);
});

test('comando /corrigir explícito continua limitado por autorização do servidor', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = '/corrigir bug no código do roteador';
    await ui.context.sendMsg();
    assert.equal(ui.repairCalls.length, 1);
    assert.equal(ui.repairCalls[0].dry_run, false);
    assert.match(ui.context.getActiveConv().messages.at(-1).content, /Precisa de revisão/);
});

test('pergunta sobre como corrigir um bug continua como conversa normal', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'como corrigir um bug no código?';
    await ui.context.sendMsg();
    assert.equal(ui.repairCalls.length, 0);
    assert.equal(ui.requests.length, 1);
});


test('missão conversacional exibe plano, pede consentimento e registra aprovação', async () => {
    const ui = browser('[]', {
        decision: 'plan_tool',
        mission: { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'gathering',
            question: 'Como você quer essa ferramenta?' },
    });
    ui.elements.get('userInput').value = 'vamos criar uma ferramenta nova de imagens';
    await ui.context.sendMsg();
    const conv = ui.context.getActiveConv();
    assert.equal(conv.activeMission.status, 'gathering');
    ui.elements.get('userInput').value = 'Recebe texto e gera capa quadrada no meu servidor';
    await ui.context.sendMsg();
    assert.equal(ui.missionCalls[0].type, 'requirements');
    assert.equal(conv.activeMission.status, 'awaiting_approval');
    assert.match(conv.messages.at(-1).content, /Para considerar pronto/);
    assert.match(conv.messages.at(-1).content, /Posso instalar/);
    ui.elements.get('userInput').value = 'pode';
    await ui.context.sendMsg();
    assert.equal(ui.missionCalls[1].type, 'approve');
    assert.equal(ui.missionCalls[1].data.approved, true);
    assert.equal(conv.activeMission.status, 'queued');
    ui.elements.get('userInput').value = 'status';
    await ui.context.sendMsg();
    assert.match(conv.messages.at(-1).content, /está disponível/);
    assert.equal(ui.requests.length, 0);
});

test('missão antiga responde dúvidas e mantém aprovação pendente', async () => {
    const ui = browser();
    ui.context.createConversation('pixel art');
    const conv = ui.context.getActiveConv();
    conv.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'awaiting_approval' };
    for (const question of ['como assim cpu pode ser lenta?', 'quero q vc me explique melhor do modelo']) {
        ui.elements.get('userInput').value = question;
        await ui.context.sendMsg();
        assert.match(conv.messages.at(-1).content, /CPU/);
        assert.equal(conv.activeMission.status, 'awaiting_approval');
    }
    assert.equal(ui.missionCalls.filter(item => item.type === 'question').length, 2);
    assert.equal(ui.missionCalls.filter(item => item.type === 'approve').length, 0);
    assert.equal(ui.requests.length, 0);
});

test('missão não instala nada após recusa do usuário', async () => {
    const ui = browser('[]', {
        decision: 'plan_tool',
        mission: { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'gathering',
            question: 'Como você quer essa ferramenta?' },
    });
    ui.elements.get('userInput').value = 'vamos criar uma ferramenta nova de imagens';
    await ui.context.sendMsg();
    ui.elements.get('userInput').value = 'Aceita uma descrição e gera fotos locais';
    await ui.context.sendMsg();
    ui.elements.get('userInput').value = 'não';
    await ui.context.sendMsg();
    assert.equal(ui.missionCalls.at(-1).data.approved, false);
});

test('prints: que aprovação é pergunta, eu aprovo registra aceite e não volta a pedir', async () => {
    const ui = browser();
    ui.context.createConversation('pixel art');
    const conv = ui.context.getActiveConv();
    conv.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'awaiting_approval' };
    ui.elements.get('userInput').value = 'que aprovação?';
    await ui.context.sendMsg();
    assert.match(conv.messages.at(-1).content, /baixar o modelo/);
    assert.equal(ui.missionCalls.filter(item => item.type === 'approve').length, 0);
    ui.elements.get('userInput').value = 'eu aprovo';
    await ui.context.sendMsg();
    assert.equal(ui.missionCalls.filter(item => item.type === 'approve').length, 1);
    assert.equal(ui.missionCalls.at(-1).data.approved, true);
    assert.equal(conv.activeMission.status, 'queued');
    assert.match(conv.messages.at(-1).content, /Aprovado/);
});

test('prints: ordem direta para baixar o modelo autoriza plano pendente', async () => {
    const ui = browser();
    ui.context.createConversation('pixel art');
    const conv = ui.context.getActiveConv();
    conv.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'awaiting_approval' };
    ui.elements.get('userInput').value =
        'mete marcha, planeja a implementação, baixa o modelo, constrói todo o fluxo e vai me avisando';
    await ui.context.sendMsg();
    assert.equal(ui.missionCalls.filter(item => item.type === 'approve').length, 1);
    assert.equal(conv.activeMission.status, 'queued');
});

test('pergunta apos autorizacao consulta missao e nao promete nada via Qwen', async () => {
    const ui = browser();
    ui.context.createConversation('pixel art');
    const conv = ui.context.getActiveConv();
    conv.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'queued' };
    ui.elements.get('userInput').value = 'conseguimos fazer cara?';
    await ui.context.sendMsg();
    assert.equal(ui.requests.length, 0);
    assert.equal(ui.routed.length, 0);
    assert.match(conv.messages.at(-1).content, /subagente local/);
});

test('recibo de imagem permanece no histórico e nunca equivale a qualidade aprovada', () => {
    const ui = browser();
    const conv = ui.context.createConversation('imagem criada');
    conv.messages.push({
        role: 'bot', content: 'Imagem gerada.', image: '/images/files/' + 'a'.repeat(32),
        artifact: {
            kind: 'image', prompt: 'mago 32x32 com capa roxa',
            actual_size: [32, 32], file_verified: true, content_verified: false,
        },
    });
    const history = ui.context.buildHistory(conv.messages, 'o que acabou de gerar?');
    assert.match(history.at(-1).content, /mago 32x32/);
    assert.match(history.at(-1).content, /NÃO verificado/);
});

test('conversa permite recuperar interrupção com sim, sem repetir a ação', async () => {
    const ui = browser();
    const calls = [];
    ui.context.fetch = async (url, options) => {
        calls.push(url);
        if (url === '/agent/run') return {
            ok: false, status: 409,
            json: async () => ({ detail: 'Este turno foi interrompido; não vou repetir efeitos.' }),
        };
        if (url.endsWith('/recover')) return {
            ok: true, status: 200,
            json: async () => ({ recovered: true, interrupted_turns: 1 }),
        };
        throw new Error('unexpected recovery URL');
    };
    ui.elements.get('userInput').value = 'continue aquela ferramenta';
    await ui.context.sendMsg();
    const conv = ui.context.getActiveConv();
    assert.equal(conv.pendingRunRecovery, true);
    assert.match(conv.messages.at(-1).content, /resultado pode ser incerto/);
    ui.elements.get('userInput').value = 'sim';
    await ui.context.sendMsg();
    assert.equal(conv.pendingRunRecovery, undefined);
    assert.equal(conv.pendingAgentRequest, undefined);
    assert.match(conv.messages.at(-1).content, /não repetirei|sem repetir|não vou repetir|resultado/i);
    assert.equal(calls.filter(url => url === '/agent/run').length, 1);
    assert.equal(calls.filter(url => url.endsWith('/recover')).length, 1);
});

test('recusa da recuperação mantém tarefa travada sem invocar endpoint', async () => {
    const ui = browser();
    const conv = ui.context.createConversation('tarefa travada');
    conv.pendingRunRecovery = true;
    const calls = [];
    ui.context.fetch = async (url) => { calls.push(url); throw new Error('no calls expected'); };
    ui.elements.get('userInput').value = 'não';
    await ui.context.sendMsg();
    assert.deepEqual(calls, []);
    assert.equal(conv.pendingRunRecovery, undefined);
    assert.match(conv.messages.at(-1).content, /não liberei/i);
});


test('Chat D: pedido coloquial de img vai direto ao gerador, sem aprovação redundante', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'opa vc pode gerar uma img de um cachorro pra mim?';
    await ui.context.sendMsg();
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 1);
    assert.equal(ui.agentCalls.length, 0);
    assert.equal(ui.routed.length, 0);
    assert.equal(ui.context.getActiveConv().messages.at(-1).image,
        '/images/files/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
});

test('Chat D: cadê a imagem reexibe a última imagem, sem alucinar incapacidade', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'cria uma imagem de um cachorro na grama';
    await ui.context.sendMsg();
    ui.elements.get('userInput').value = 'cadê a imagem que vc gerou? me manda';
    await ui.context.sendMsg();
    const answer = ui.context.getActiveConv().messages.at(-1);
    assert.equal(answer.image, '/images/files/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
    assert.match(answer.content, /última imagem salva/);
    assert.equal(ui.agentCalls.length, 0);
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 1);
});

test('Chat D: refinamento coloquial edita o resultado existente sem pedir upload', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'cria uma imagem de um cachorro na grama';
    await ui.context.sendMsg();
    ui.elements.get('userInput').value =
        'o cachorro possui 3 patas, consegue arrumar pra ficar só 2? tem que ser adulto e cinza com preto';
    await ui.context.sendMsg();
    const edited = ui.imageCalls.filter(x => x.type === 'edit');
    assert.equal(edited.length, 1);
    assert.match(edited[0].body.values.prompt, /cachorro possui 3 patas/);
    assert.equal(edited[0].body.values.file.size > 0, true);
    assert.equal(ui.agentCalls.length, 0);
    assert.equal(ui.context.getActiveConv().messages.at(-1).image,
        '/images/files/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb');
});

test('Chat D: criação de ferramenta de imagens continua sob autoridade do agente', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'quero criar uma ferramenta para gerar imagens';
    await ui.context.sendMsg();
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 0);
    assert.equal(ui.agentCalls.length, 1);
});

test('Chat D: aprovações de ação sensível não são confundidas com refinamento de imagem', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'cria uma imagem de um cachorro na grama';
    await ui.context.sendMsg();
    ui.elements.get('userInput').value = 'eu aprovo';
    await ui.context.sendMsg();
    assert.equal(ui.agentCalls.length, 1);
    assert.equal(ui.imageCalls.filter(x => x.type === 'edit').length, 0);
});


test('Chat D: pedido para corrigir bug de software não edita imagem recém-gerada', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'cria uma imagem de um cachorro na grama';
    await ui.context.sendMsg();
    ui.elements.get('userInput').value = 'corrige esse bug no código do aplicativo';
    await ui.context.sendMsg();
    assert.equal(ui.imageCalls.filter(x => x.type === 'edit').length, 0);
    assert.equal(ui.agentCalls.length, 1);
});

test('D01: sim sem aprovação pendente não autoriza missão nem memória', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'sim';
    await ui.context.sendMsg();
    assert.equal(ui.missionCalls.filter(x => x.type === 'approve').length, 0);
    assert.equal(ui.memories.length, 0);
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate' || x.type === 'edit').length, 0);
});

test('D02: pedido de explicação não aprova plano sensível', async () => {
    const ui = browser();
    ui.context.createConversation('ferramenta');
    const conv = ui.context.getActiveConv();
    conv.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'awaiting_approval' };
    ui.elements.get('userInput').value = 'que aprovação?';
    await ui.context.sendMsg();
    assert.equal(conv.activeMission.status, 'awaiting_approval');
    assert.equal(ui.missionCalls.filter(x => x.type === 'approve').length, 0);
    assert.equal(ui.requests.length, 0);
});

test('D11: missão enfileirada não é apresentada como executada antes de consulta', async () => {
    const ui = browser();
    ui.context.createConversation('ferramenta');
    const conv = ui.context.getActiveConv();
    conv.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'queued' };
    ui.elements.get('userInput').value = 'já terminou?';
    await ui.context.sendMsg();
    assert.equal(ui.missionCalls.filter(x => x.type === 'approve').length, 0);
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 0);
    assert.equal(ui.requests.length, 0);
});

test('D04: recusa de plano sensível não executa e mantém histórico da conversa', async () => {
    const ui = browser();
    ui.context.createConversation('ferramenta');
    const conv = ui.context.getActiveConv();
    conv.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'awaiting_approval' };
    const previous = { role: 'user', content: 'Quero criar uma ferramenta de imagens' };
    conv.messages.push(previous);
    ui.elements.get('userInput').value = 'não';
    await ui.context.sendMsg();
    assert.equal(ui.missionCalls.filter(x => x.type === 'approve').length, 1);
    assert.equal(ui.missionCalls.at(-1).data.approved, false);
    assert.equal(conv.messages[0].content, previous.content);
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate' || x.type === 'edit').length, 0);
});

test('D06: reexibir imagem preserva URL original e não gera outro artefato', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'cria uma imagem de um cachorro na grama';
    await ui.context.sendMsg();
    const original = ui.context.getActiveConv().messages.at(-1).image;
    ui.elements.get('userInput').value = 'cadê a imagem que vc gerou? me manda';
    await ui.context.sendMsg();
    assert.equal(ui.context.getActiveConv().messages.at(-1).image, original);
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 1);
    assert.equal(ui.imageCalls.filter(x => x.type === 'edit').length, 0);
});

test('D08: trocar de imagem para correção de software não envia edição visual', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'cria uma imagem de um cachorro na grama';
    await ui.context.sendMsg();
    ui.elements.get('userInput').value = 'corrige esse bug no código do aplicativo';
    await ui.context.sendMsg();
    assert.equal(ui.imageCalls.filter(x => x.type === 'edit').length, 0);
    assert.equal(ui.agentCalls.length, 1);
});

test('trocar de conversa durante geração permite navegar e não contamina histórico', async () => {
    const ui = browser();
    let release;
    const paused = new Promise(resolve => { release = resolve; });
    ui.context.createConversation('Conversa antiga');
    const old = ui.context.getActiveConv();
    const other = ui.context.createConversation('Conversa nova');
    ui.context.openConv(old.id);
    ui.context.fetch = async url => {
        if (url === '/agent/run') {
            await paused;
            return { ok: true, status: 200, json: async () =>
                ({ handled: true, reply: 'Retorno antigo' }) };
        }
        throw new Error('Requisição inesperada: ' + url);
    };
    ui.elements.get('userInput').value = 'Me explique a arquitetura';
    const inProgress = ui.context.sendMsg();
    assert.equal(ui.elements.get('cancelBtn').hidden, false);
    ui.context.openConv(other.id);
    assert.equal(ui.context.getActiveConv().id, other.id);
    assert.equal(ui.elements.get('cancelBtn').hidden, true);
    release();
    await inProgress;
    assert.equal(old.messages.at(-1).role, 'bot');
    assert.match(old.messages.at(-1).content, /interrompida/i);
    assert.equal(old.messages.some(msg => msg.content === 'Retorno antigo'), false);
    assert.equal(other.messages.length, 0);
});

test('nova conversa cancela visualmente pedido pendente sem conceder execução', async () => {
    const ui = browser();
    let release;
    const paused = new Promise(resolve => { release = resolve; });
    ui.context.fetch = async url => {
        if (url === '/agent/run') {
            await paused;
            return { ok: true, status: 200, json: async () =>
                ({ handled: false }) };
        }
        throw new Error('Requisição inesperada');
    };
    ui.elements.get('userInput').value = 'Me ajude a planejar um projeto';
    const inProgress = ui.context.sendMsg();
    const previous = ui.context.getActiveConv();
    ui.context.newChat();
    assert.equal(ui.context.getActiveConv(), undefined);
    assert.equal(ui.elements.get('sendBtn').disabled, false);
    release();
    await inProgress;
    assert.match(previous.messages.at(-1).content, /servidor pode continuar/i);
    assert.equal(ui.context.getActiveConv(), undefined);
});

test('D14: nova conversa mantém histórico e imagem da conversa anterior', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'cria uma imagem de um cachorro na grama';
    await ui.context.sendMsg();
    const first = ui.context.getActiveConv();
    const original = first.messages.at(-1).image;
    ui.context.newChat();
    ui.elements.get('userInput').value = 'Explica uma função Python';
    await ui.context.sendMsg();
    const second = ui.context.getActiveConv();
    assert.notEqual(second.id, first.id);
    assert.equal(first.messages.at(-1).image, original);
    assert.equal(second.messages.some(m => m.image === original), false);
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 1);
});

test('D14: voltar à conversa anterior restaura mensagens e artefatos sem execução', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'cria uma imagem de um cachorro na grama';
    await ui.context.sendMsg();
    const first = ui.context.getActiveConv();
    const image = first.messages.at(-1).image;
    ui.context.newChat();
    ui.elements.get('userInput').value = 'Explica uma função Python';
    await ui.context.sendMsg();
    ui.context.openConv(first.id);
    assert.equal(ui.context.getActiveConv().id, first.id);
    assert.equal(ui.context.getActiveConv().messages.at(-1).image, image);
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 1);
});

test('D14: nova conversa não herda aprovação sensível pendente de outra', async () => {
    const ui = browser();
    const first = ui.context.createConversation('ferramenta');
    first.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'awaiting_approval' };
    ui.context.newChat();
    ui.elements.get('userInput').value = 'sim';
    await ui.context.sendMsg();
    assert.notEqual(ui.context.getActiveConv().id, first.id);
    assert.equal(ui.missionCalls.filter(x => x.type === 'approve').length, 0);
    assert.equal(first.activeMission.status, 'awaiting_approval');
});

test('D14: nova conversa não herda esclarecimento de imagem pendente', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'quero q vc crie uma imagem pra mim';
    await ui.context.sendMsg();
    const first = ui.context.getActiveConv();
    assert.equal(first.pendingImage.kind, 'generate');
    ui.context.newChat();
    ui.elements.get('userInput').value = 'Explica uma função Python';
    await ui.context.sendMsg();
    assert.equal(ui.context.getActiveConv().pendingImage, undefined);
    assert.equal(first.pendingImage.kind, 'generate');
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 0);
});

test('D10: recusa de recuperação não chama endpoint nem libera replay', async () => {
    const ui = browser();
    const conv = ui.context.createConversation('tarefa interrompida');
    conv.pendingRunRecovery = true;
    const calls = [];
    ui.context.fetch = async url => { calls.push(url); throw new Error('unexpected request'); };
    ui.elements.get('userInput').value = 'não';
    await ui.context.sendMsg();
    assert.equal(calls.length, 0);
    assert.equal(conv.pendingRunRecovery, undefined);
});

test('D12: recibo visual no histórico explicita ausência de revisão do conteúdo', () => {
    const ui = browser();
    const conv = ui.context.createConversation('capa');
    conv.messages.push({
        role: 'bot', content: 'Arquivo gerado.',
        image: '/images/files/' + 'a'.repeat(32),
        artifact: { kind: 'image', prompt: 'capa vermelha',
            actual_size: [512, 512], file_verified: true, content_verified: false },
    });
    const history = ui.context.buildHistory(conv.messages, 'ficou perfeito?');
    assert.match(history.at(-1).content, /conteúdo visual: NÃO verificado/);
    assert.match(history.at(-1).content, /capa vermelha/);
});

test('D14: troca de conversa durante requisição não redireciona resposta pendente', async () => {
    const ui = browser();
    let finish;
    const originalFetch = ui.context.fetch;
    ui.context.fetch = (url, options) => url === '/chat/stream'
        ? new Promise(resolve => { finish = resolve; }) : originalFetch(url, options);
    ui.elements.get('userInput').value = 'oi';
    const pending = ui.context.sendMsg();
    await new Promise(resolve => setImmediate(resolve));
    const first = ui.context.getActiveConv();
    ui.context.newChat();
    assert.equal(ui.context.getActiveConv().id, first.id);
    finish({ ok: false, json: async () => ({ detail: 'Serviço indisponível' }) });
    await pending;
    assert.equal(first.messages.length, 1);
    assert.equal(ui.context.getActiveConv().id, first.id);
});

test('D03: bora autoriza apenas a missão pendente da conversa ativa', async () => {
    const ui = browser();
    const other = ui.context.createConversation('missão antiga');
    other.activeMission = { id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', status: 'awaiting_approval' };
    ui.context.newChat();
    const current = ui.context.createConversation('missão atual');
    current.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'awaiting_approval' };
    ui.elements.get('userInput').value = 'bora';
    await ui.context.sendMsg();
    const approvals = ui.missionCalls.filter(x => x.type === 'approve');
    assert.equal(approvals.length, 1);
    assert.equal(approvals[0].data.approved, true);
    assert.equal(current.activeMission.status, 'queued');
    assert.equal(other.activeMission.status, 'awaiting_approval');
});

test('D03: pergunta com sim não deve autorizar missão sensível', async () => {
    const ui = browser();
    const conv = ui.context.createConversation('missão');
    conv.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'awaiting_approval' };
    ui.elements.get('userInput').value = 'sim, mas como funciona?';
    await ui.context.sendMsg();
    assert.equal(ui.missionCalls.filter(x => x.type === 'approve').length, 0);
    assert.equal(conv.activeMission.status, 'awaiting_approval');
});

test('D10: recuperação autorizada usa apenas sessão ativa e não repete agente', async () => {
    const ui = browser();
    const old = ui.context.createConversation('interrompida');
    old.pendingRunRecovery = true;
    ui.context.newChat();
    const current = ui.context.createConversation('outra tarefa');
    current.pendingRunRecovery = true;
    const paths = [];
    ui.context.fetch = async (url, options) => {
        paths.push({ url, body: options?.body });
        if (url.endsWith('/recover')) {
            return { ok: true, status: 200, json: async () => ({ recovered: true }) };
        }
        throw new Error('unexpected network request');
    };
    ui.elements.get('userInput').value = 'sim';
    await ui.context.sendMsg();
    assert.equal(paths.length, 1);
    assert.equal(paths[0].url, '/agent/runs/' + current.id + '/recover');
    assert.equal(JSON.parse(paths[0].body).confirmed, true);
    assert.equal(current.pendingRunRecovery, undefined);
    assert.equal(old.pendingRunRecovery, true);
});

test('D10: consulta de recuperação não autoriza endpoint sensível', async () => {
    const ui = browser();
    const conv = ui.context.createConversation('interrompida');
    conv.pendingRunRecovery = true;
    const calls = [];
    ui.context.fetch = async url => { calls.push(url); throw new Error('unexpected network request'); };
    ui.elements.get('userInput').value = 'como recupera essa tarefa?';
    await ui.context.sendMsg();
    assert.equal(calls.length, 0);
    assert.equal(conv.pendingRunRecovery, true);
});

test('D14: aprovação pendente permanece isolada após alternar e voltar', async () => {
    const ui = browser();
    const first = ui.context.createConversation('missão');
    first.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'awaiting_approval' };
    ui.context.newChat();
    ui.context.createConversation('conversa neutra');
    ui.context.openConv(first.id);
    assert.equal(ui.context.getActiveConv().id, first.id);
    assert.equal(first.activeMission.status, 'awaiting_approval');
    assert.equal(ui.missionCalls.filter(x => x.type === 'approve').length, 0);
});


test('Chat E: objetivos consultam estado real, sem percentuais fabricados', async () => {
    const ui = browser();
    const conv = ui.context.createConversation('Meu projeto <img src=x>');
    const calls = [];
    ui.context.fetch = async url => {
        calls.push(url);
        assert.equal(url, '/agent/runs/' + conv.id);
        return { ok: true, status: 200, json: async () => ({
            phase: 'goal', goal: 'Planejar aplicativo', steps: ['Pesquisar bibliotecas', 'Testar no servidor'],
            paused_goals: [{ id: 'teste', goal: 'Outro objetivo', status: 'paused', steps: ['Revisar ideia'] }],
        }) };
    };
    await ui.context.openObjectives();
    const list = ui.elements.get('objectivesList');
    assert.equal(calls.length, 1);
    assert.equal(list.children.length, 2);
    assert.equal(list.children[0].children[1].textContent, 'Planejar aplicativo');
    assert.equal(list.children[0].children[3].children[0].textContent, 'Pesquisar bibliotecas');
    assert.match(list.children[0].children[0].textContent, /execução não comprovada/i);
    assert.doesNotMatch(list.children[0].children[0].textContent, /%/);
    ui.context.setObjectiveFilter('paused');
    assert.equal(list.children.length, 1);
    assert.equal(list.children[0].children[1].textContent, 'Outro objetivo');
});

test('Chat E: indisponibilidade é exibida sem declarar objetivo concluído', async () => {
    const ui = browser();
    ui.context.createConversation('Conversa não disponível');
    ui.context.fetch = async () => { throw new Error('offline'); };
    await ui.context.openObjectives();
    const list = ui.elements.get('objectivesList');
    assert.equal(list.children.length, 1);
    assert.match(list.children[0].children[1].textContent, /não foi possível consultar/i);
    assert.match(list.children[0].children[0].textContent, /indisponível/i);
});

test('Chat E: consulta de objetivos nunca invoca execução ou recuperação', async () => {
    const ui = browser();
    ui.context.createConversation('Objetivo real');
    const calls = [];
    ui.context.fetch = async (url, options) => {
        calls.push({ url, options });
        return { ok: true, status: 200, json: async () => ({ phase: 'idle' }) };
    };
    await ui.context.openObjectives();
    assert.equal(calls.length, 1);
    assert.match(calls[0].url, /^\/agent\/runs\/[a-z0-9]+$/);
    assert.equal(calls[0].options.method, undefined);
    assert.equal(calls[0].options.credentials, 'same-origin');
    assert.match(ui.elements.get('objectivesList').textContent, /nenhum objetivo registrado/i);
});

test('Chat E: painel completo preserva metas pausadas de sessões ociosas', async () => {
    const javascript = fs.readFileSync(path.join(__dirname,
        '../src/api/workspace_assets/assets.js'), 'utf8');
    const elements = new Map();
    function element(tag = 'div') {
        return {
            tag, textContent: '', className: '', children: [], disabled: false, value: 'all',
            append(...items) { this.children.push(...items); },
            replaceChildren(...items) { this.children = [...items]; },
            get childNodes() { return this.children; },
            addEventListener() {},
        };
    }
    for (const name of ['goals', 'missions', 'status', 'refresh', 'mission-filter']) {
        elements.set(name, element());
    }
    const conv = { id: 'abcde12345', title: 'Conversa de testes' };
    const requests = [];
    const context = vm.createContext({
        document: {
            getElementById(id) { return elements.get(id); },
            createElement: element,
        },
        localStorage: { getItem() { return JSON.stringify([conv]); } },
        fetch: async (url, options) => {
            requests.push({ url, options });
            return { ok: true, status: 200, json: async () => url === '/agent/missions'
                ? { items: [] } : { phase: 'idle', paused_goals: [
                    { goal: 'Meta anteriormente pausada', steps: ['Revisar escopo'] },
                ] } };
        },
        Date, encodeURIComponent, console,
    });
    vm.runInContext(javascript, context);
    await context.refresh();
    const items = elements.get('goals').children;
    assert.equal(items.length, 1);
    assert.equal(items[0].children[0].textContent, 'Meta anteriormente pausada');
    assert.match(items[0].children[1].textContent, /paused/);
    assert.equal(items[0].children[3].children[0].textContent, 'Revisar escopo');
    assert.ok(requests.every(request => request.options.method === undefined));
    assert.ok(requests.every(request => request.options.credentials === 'same-origin'));
});

test('Chat E: refresh concorrente usa uma consulta e evita cartões duplicados', async () => {
    const javascript = fs.readFileSync(path.join(__dirname,
        '../src/api/workspace_assets/assets.js'), 'utf8');
    const elements = new Map();
    function element(tag = 'div') {
        return {
            tag, textContent: '', children: [], disabled: false, value: 'all',
            append(...items) { this.children.push(...items); },
            replaceChildren(...items) { this.children = [...items]; },
            get childNodes() { return this.children; },
            addEventListener() {},
        };
    }
    for (const name of ['goals', 'missions', 'status', 'refresh', 'mission-filter']) {
        elements.set(name, element());
    }
    let release;
    const pause = new Promise(resolve => { release = resolve; });
    const calls = [];
    const context = vm.createContext({
        document: {
            getElementById(id) { return elements.get(id); },
            createElement: element,
        },
        localStorage: { getItem() { return JSON.stringify([
            { id: 'abcde12345', title: 'Conversa' },
        ]); } },
        fetch: async (url, options) => {
            calls.push({ url, options });
            await pause;
            return { ok: true, status: 200, json: async () =>
                url === '/agent/missions' ? { items: [] } :
                    { phase: 'idle', paused_goals: [{ goal: 'Meta pausada' }] } };
        },
        Date, encodeURIComponent, console,
    });
    vm.runInContext(javascript, context); // primeira consulta automática
    const first = context.refresh();
    const second = context.refresh();
    assert.equal(first, second);
    assert.equal(elements.get('refresh').disabled, true);
    release();
    await first;
    assert.equal(calls.length, 2); // apenas um GET de missões e um da sessão
    assert.equal(elements.get('goals').children.length, 1);
    assert.equal(elements.get('refresh').disabled, false);

    // Uma falha parcial não pode ser apresentada como consulta bem-sucedida.
    context.fetch = async url => {
        if (url.includes('/agent/runs/')) throw new Error('offline');
        return { ok: true, status: 200, json: async () => ({ items: [] }) };
    };
    await context.refresh();
    assert.match(elements.get('status').textContent, /Consulta parcial/i);
    assert.match(elements.get('goals').children[0].textContent, /não foi possível consultar/i);
});

test('D01: confirmação solta não cria autorização nem execução supervisionada', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'eu aprovo';
    await ui.context.sendMsg();
    assert.equal(ui.missionCalls.length, 0);
    assert.equal(ui.repairCalls.length, 0);
    assert.equal(ui.memories.length, 0);
});

test('D02: pergunta de autorização conserva estado sem baixar ou enfileirar', async () => {
    const ui = browser();
    const conv = ui.context.createConversation('missão');
    conv.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'awaiting_approval' };
    ui.elements.get('userInput').value = 'que aprovação?';
    await ui.context.sendMsg();
    assert.equal(conv.activeMission.status, 'awaiting_approval');
    assert.equal(ui.missionCalls.filter(x => x.type === 'approve').length, 0);
    assert.match(conv.messages.at(-1).content, /não iniciei|ainda não iniciei/i);
});

test('D03: autorização explícita é idempotente após a missão entrar na fila', async () => {
    const ui = browser();
    const conv = ui.context.createConversation('missão');
    conv.activeMission = { id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', status: 'awaiting_approval' };
    ui.elements.get('userInput').value = 'eu aprovo';
    await ui.context.sendMsg();
    assert.equal(conv.activeMission.status, 'queued');
    ui.elements.get('userInput').value = 'eu aprovo';
    await ui.context.sendMsg();
    assert.equal(ui.missionCalls.filter(x => x.type === 'approve').length, 1);
});

test('D05: pedido de imagem incompleto não gera arquivo até receber detalhes', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'quero q vc crie uma imagem pra mim';
    await ui.context.sendMsg();
    const conv = ui.context.getActiveConv();
    assert.equal(conv.pendingImage.kind, 'generate');
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 0);
    assert.match(conv.messages.at(-1).content, /imagem|descrev|cena/i);
});

test('D06: imagem de outra conversa não é recuperada por confirmação genérica', async () => {
    const ui = browser();
    ui.elements.get('userInput').value = 'cria uma imagem de um cachorro na grama';
    await ui.context.sendMsg();
    const previous = ui.context.getActiveConv();
    ui.context.newChat();
    ui.elements.get('userInput').value = 'cadê a imagem que vc gerou? me manda';
    await ui.context.sendMsg();
    const current = ui.context.getActiveConv();
    assert.notEqual(current.id, previous.id);
    assert.equal(current.messages.some(x => x.image), false);
    assert.equal(ui.imageCalls.filter(x => x.type === 'generate').length, 1);
});

test('D09: histórico enviado ao agente contém apenas mensagens da conversa ativa', async () => {
    const ui = browser();
    const first = ui.context.createConversation('segredo da primeira conversa');
    first.messages.push({ role: 'user', content: 'contexto exclusivo da primeira conversa' });
    ui.context.newChat();
    const second = ui.context.createConversation('segunda conversa');
    second.messages.push({ role: 'user', content: 'contexto exclusivo da segunda conversa' });
    ui.elements.get('userInput').value = 'me ajude com esse assunto';
    await ui.context.sendMsg();
    assert.equal(ui.agentCalls.length, 1);
    const history = JSON.stringify(ui.agentCalls[0].history);
    assert.match(history, /contexto exclusivo da segunda conversa/);
    assert.doesNotMatch(history, /contexto exclusivo da primeira conversa/);
});

test('D10: falha 409 na recuperação não libera execução pendente', async () => {
    const ui = browser();
    const conv = ui.context.createConversation('interrompida');
    conv.pendingRunRecovery = true;
    const calls = [];
    ui.context.fetch = async url => {
        calls.push(url);
        return { ok: false, status: 409, json: async () => ({ detail: 'active' }) };
    };
    ui.elements.get('userInput').value = 'sim';
    await ui.context.sendMsg();
    assert.equal(calls.length, 1);
    assert.match(calls[0], /\/recover$/);
    assert.equal(conv.pendingRunRecovery, true);
    assert.match(conv.messages.at(-1).content, /operação ativa/i);
});

test('D12: recibo sem arquivo verificado não afirma integridade válida', () => {
    const ui = browser();
    const conv = ui.context.createConversation('imagem');
    conv.messages.push({ role: 'bot', content: 'Resultado parcial.',
        artifact: { kind: 'image', prompt: 'cartaz azul', actual_size: [256, 256],
            file_verified: false, content_verified: false } });
    const history = ui.context.buildHistory(conv.messages, 'posso publicar?');
    assert.match(history.at(-1).content, /integridade: não confirmada/);
    assert.match(history.at(-1).content, /conteúdo visual: NÃO verificado/);
});

test('D14: histórico de cada conversa mantém sua própria ordem cronológica', () => {
    const ui = browser();
    const first = ui.context.createConversation('primeira');
    first.messages.push({ role: 'user', content: 'primeiro A' }, { role: 'bot', content: 'segundo A' });
    ui.context.newChat();
    const second = ui.context.createConversation('segunda');
    second.messages.push({ role: 'user', content: 'primeiro B' }, { role: 'bot', content: 'segundo B' });
    const a = ui.context.buildHistory(first.messages, 'continua A');
    const b = ui.context.buildHistory(second.messages, 'continua B');
    assert.deepEqual(Array.from(a, x => x.content), ['primeiro A', 'segundo A']);
    assert.deepEqual(Array.from(b, x => x.content), ['primeiro B', 'segundo B']);
});
