# Do Lutz 0.5 para o 1.0

O 1.0 é uma reescrita com outro objetivo: a tabela de extração validada de uma revisão sistemática. **Não há migração de projetos 0.5.x.** O 1.0 reconhece uma pasta 0.5 (`articles/` + `.lutz/vector_store`) e recusa abri-la com uma mensagem; um `lutz.db` de esquema desconhecido também é recusado.

Para continuar usando a 0.5:

```bash
pip install "lutz-research<1"
```

## O que mudou

| 0.5 | 1.0 |
|---|---|
| `lutz init` + `.env` com `LLM_PROVIDER`, `LLM_MODEL` | `lutz init` + `.env` só com chaves e URLs; modelos por papel (E1, E2, E3, V, J) no `lutz.yaml` |
| `lutz load --f PASTA` | `lutz load PASTA` (`--f` ainda é aceito) |
| `lutz vectorize` (LanceDB, embeddings) | Removido. `lutz load` já guarda o texto visível por página e as unidades; os extratores leem o texto completo |
| Scan de segurança em 6 camadas, quarentena, auditoria HMAC | Removidos. A ingestão descarta texto oculto e o relatório lista artigos afetados |
| `lutz analysis --p prompt.md` | Removido. Use um codebook e `lutz extract` |
| `lutz citations`, `lutz rank`, `lutz dedup`, `lutz query`, `lutz agent`, chat | Removidos |
| Categorias de veredito, roadmap de leitura | Removidos. Elegibilidade pode ser um campo categórico com `papel: triagem` |
| Modal de configurações gravando no `.env` | Mantido: a aba de chaves grava no `.env` com lista branca e mostra a origem de cada valor; a aba de consumo lê o registro de chamadas |
| Instalador Windows (PyInstaller) e PyPI | Mantidos |

## O que fazer com um projeto 0.5

1. Crie um projeto novo: `lutz init minha-revisao`.
2. Importe os PDFs da pasta `articles/` antiga: `lutz load ../projeto-antigo/articles`.
3. Reescreva o prompt da análise antiga como um codebook (`lutz codebook new` ajuda).
