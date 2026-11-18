# Referência da CLI

Todos os comandos aceitam `--projeto PASTA` (padrão: a pasta atual ou uma acima com `lutz.yaml`) e `-h/--help`. Comandos que gravam no projeto pegam o bloqueio de escrita; se outro processo estiver gravando, o comando para com uma mensagem clara.

## Projeto e biblioteca

| Comando | Faz |
|---|---|
| `lutz init [PASTA] [--nome] [--pergunta] [--tipo]` | Cria o projeto (`lutz.yaml`, `.env`, `lutz.db`, pastas) |
| `lutz project new NOME` / `lutz project show` | Atalhos da spec |
| `lutz status` | Artigos, codebook, execuções, piloto e custo |
| `lutz load CAMINHOS...` | Importa PDFs (arquivos ou pastas) |
| `lutz library [--status pronto\|sem_texto\|erro]` | Lista artigos com páginas, layout, seções, tabelas e texto oculto |

## Codebook

| Comando | Faz |
|---|---|
| `lutz codebook new [--modelo AREA] [--sem-llm]` | Assistente: entrevista, modelo de partida, sugestões, revisão campo a campo, lint |
| `lutz codebook import ARQUIVO [--nota]` | Importa YAML como rascunho |
| `lutz codebook check [ARQUIVO] [--semantico]` | Lint determinístico (e semântico por LLM) |
| `lutz codebook test --campo A,B [--n 3] [--artigos ...]` | Teste rápido com E1 (não conta como piloto) |
| `lutz codebook freeze [--versao N]` | Congela a versão |
| `lutz codebook show / history / diff V1 V2 / export [-o]` | Consulta e exportação |

## Extração (Modo Autônomo)

| Comando | Faz |
|---|---|
| `lutz extract [--campos] [--artigos] [--codebook N] [--sim]` | Planeja, estima o custo, confirma e roda |
| `lutz extract --estimar` | Só planeja e estima |
| `lutz extract --piloto ajuste\|validacao [--forcar]` | Roda no conjunto do piloto atual |
| `lutz extract --retomar ID` | Continua uma execução pausada ou interrompida |
| `lutz extract list / status ID / pause ID` | Acompanhamento |
| `lutz extract recompute ID [--limiares-atuais]` | Recalcula níveis e métricas sem chamar modelos |
| `lutz results [--execucao] [--formato largo\|longo] [-o] [--sep]` | Exporta a tabela com nível e evidência |

## Revisão

| Comando | Faz |
|---|---|
| `lutz adjudicate queue / export / import ARQUIVO` | Fila e planilha de adjudicação |
| `lutz adjudicate decide CELULA (--valor V \| --nao-reportado \| --aceitar) [--justificativa]` | Decide uma célula |
| `lutz audit sample [--n \| --fracao]` | Sorteia células Alta e gera a planilha |
| `lutz audit import ARQUIVO / status` | Registra e mostra o acerto com IC de Wilson |

## Piloto (Modo Calibrado)

| Comando | Faz |
|---|---|
| `lutz pilot plan [--n 30] [--ajuste 10] [--reserva] [--estratos ano\|revista] [--avaliadores A,B]` | Mostra o tamanho × IC e pré-registra o plano |
| `lutz pilot sample [--n --ajuste --seed]` | Sorteia e gera as planilhas cegas em `exports/piloto/` |
| `lutz pilot import ARQUIVO --avaliador A` | Importa uma planilha (nada é gravado se houver erro) |
| `lutz pilot consensus [--importar ARQUIVO]` | Gera ou importa o consenso entre dois avaliadores |
| `lutz pilot compare [--conjunto validacao\|ajuste]` | κ / κw / ICC por campo, decisão e calibração |
| `lutz pilot status` | Etapas, cobertura, rodadas e decisões |

## Relatório e integração

| Comando | Faz |
|---|---|
| `lutz report [--execucao] [--idioma pt,en] [--formato md,pdf]` | Relatório de confiabilidade e anexos A, B, C |
| `lutz bundle export [-o] [--com-pdfs]` | Zip do projeto com manifesto (sem `.env`) |
| `lutz web [--porta 8000]` | Interface web em `127.0.0.1` |
| `lutz mcp [--projeto]` | Servidor MCP (stdio, somente leitura) |
| `lutz usage [--execucao]` | Tokens e custo por papel e modelo |
| `lutz config show / set CHAVE VALOR / unset CHAVE` | `.env` e resumo do `lutz.yaml` |
| `lutz doctor [--chamar]` | Diagnóstico do projeto |
