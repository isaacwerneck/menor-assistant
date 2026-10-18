"""Especificações de ferramentas pedidas pelo usuário, separadas das ideias soltas."""
import hashlib

from src.memory.store import BrainStore, _write_lock


def plan_tool(request, store=None):
    """Cria uma proposta rastreável, sem alegar que instalou código executável."""
    store = store or BrainStore()
    description = store._memory_text(request)
    digest = hashlib.sha256(description.casefold().encode("utf-8")).hexdigest()[:12]
    relative = f"ferramentas/propostas/solicitacao-{digest}.md"
    document = (
        "# Ferramenta solicitada\n\n"
        "Estado: aguardando definição técnica e implementação em branch isolada.\n\n"
        "## Pedido original\n\n"
        + description + "\n\n"
        "## Plano inicial\n\n"
        "- [ ] Confirmar objetivo, entradas, saídas e critérios de aceite\n"
        "- [ ] Verificar se existe motor/modelo compatível e recursos necessários\n"
        "- [ ] Criar adaptador executável em src/tools/ numa branch de desenvolvimento\n"
        "- [ ] Escrever testes, checar recursos e validar permissões\n"
        "- [ ] Abrir Pull Request e aguardar revisão antes do deploy\n\n"
        "Esta especificação NÃO significa que a ferramenta está instalada.\n"
    )
    with _write_lock:
        store.initialize()
        current = store.read_note(relative)
        if not current:
            store.write_note(relative, document)
    return {"status": "planned", "path": relative, "request": description, "implemented": False}
