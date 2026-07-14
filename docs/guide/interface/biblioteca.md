# Aba Biblioteca

A aba **Biblioteca** é o ponto de entrada para gerenciar e indexar os artigos do projeto.

![Aba Biblioteca](/screenshots/biblioteca.png)

---

## Lista de artigos

A tabela exibe todos os arquivos PDF em `articles/`:

| Coluna | Descrição |
|---|---|
| **Arquivo** | Nome do PDF |
| **Tamanho** | Tamanho em KB ou MB |
| **Status** | `Pendente` (não vetorizado) · `Vetorizado` · `Erro` |
| **Chunks** | Número de chunks gerados na vetorização |

Use a **barra de busca** para filtrar artigos por nome.

---

## Ações

### Carregar PDFs

Clique em **Carregar PDFs** para selecionar arquivos locais. Os arquivos são copiados para `articles/` e aparecem na lista com status `Pendente`.

Alternativamente, use o CLI:

```bash
lutz load --f /caminho/para/pasta
```

### Vetorizar

O botão **Vetorizar (N)** inicia a indexação de todos os artigos pendentes:

1. Verificação de segurança (6 camadas)
2. Extração de texto por seção
3. Geração de embeddings
4. Persistência no LanceDB (`.lutz/vector_store/`)

::: tip
Acompanhe o progresso pelo log no terminal onde `lutz web` está rodando.
:::

### Renomear

O botão **✦ Renomear** usa o LLM para gerar nomes descritivos a partir do conteúdo dos PDFs, substituindo nomes genéricos como `10_1002_eap_2893.pdf`.

### Remover

- **×** na linha: remove o artigo individualmente
- **Remover todos**: limpa toda a biblioteca

::: warning
A remoção exclui o PDF de `articles/` e seus chunks do vector store. Essa ação não pode ser desfeita pela interface.
:::

---

## Anexar contexto

O botão **Anexar arquivo** (abaixo do painel lateral) permite adicionar documentos de contexto ao projeto — aceita PDF, DOCX, XLSX e PPTX. Esses arquivos são usados como contexto adicional nas análises, fora dos artigos vetorizados.

---

## Status do pipeline

O bloco **PIPELINE** no painel lateral reflete o estado atual:

```
✓ Biblioteca     → N PDFs carregados
✓ Vetorizado     → N artigos prontos
✓ Análise        → Concluída · N para incluir
```
