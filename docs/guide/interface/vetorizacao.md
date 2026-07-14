# Biblioteca (Vetorização)

::: warning Página removida na v0.5.0
A página `/vectorize` foi removida. O gerenciamento de artigos e a vetorização agora estão integrados à **[aba Biblioteca](./biblioteca.md)** da interface principal.
:::

---

## Aba Artigos

Lista todos os arquivos `.pdf` presentes em `articles/`. Para cada arquivo, exibe nome e tamanho.

### Upload de PDFs

Clique em **+ Adicionar PDFs** para selecionar múltiplos arquivos de uma vez. O Lutz:

1. Valida que cada arquivo é um PDF legítimo (verifica assinatura binária).
2. Sanitiza o nome do arquivo para evitar caracteres inválidos.
3. Salva o arquivo em `articles/`.

Você também pode renomear arquivos com a sugestão de nome inteligente (**Sugerir nomes**), que lê o conteúdo do PDF e propõe um nome limpo sem precisar vetorizar.

::: tip
Você também pode copiar os arquivos manualmente para a pasta `articles/` do seu projeto usando `lutz load`.
:::

---

## Aba Processar

### Parâmetros de vetorização

| Parâmetro | Descrição | Padrão |
|---|---|---|
| **Tamanho do chunk** | Número de palavras por fragmento | `512` |
| **Sobreposição** | Palavras compartilhadas entre chunks consecutivos | `64` |
| **Ignorar segurança** | Pula verificações de segurança (não recomendado) | desativado |
| **Análise por seções** | Detecta e rotula seções (abstract, metodologia…) | desativado |
| **Modo quarentena** | Processa arquivos de `articles/_quarantine/` | desativado |

### Como funcionam os chunks e embeddings

O **chunk** é a unidade fundamental de indexação. Quando um PDF é processado:

1. O texto é extraído e dividido em janelas deslizantes de *N* palavras.
2. Cada chunk é convertido em um vetor de embedding pelo modelo configurado no `.env`.
3. Os vetores são armazenados no banco LanceDB em `.lutz/vector_store/`.

```
Artigo PDF (texto completo)
    ↓ pdfplumber / pypdf
Texto bruto
    ↓ divisão por palavras com sobreposição
[chunk 1][chunk 2][chunk 3]...
    ↓ modelo de embedding
[[0.12, -0.34, 0.78, ...], ...]
    ↓ LanceDB
Banco vetorial indexado
```

A sobreposição entre chunks preserva o contexto nas fronteiras — uma frase que cai no final de um chunk aparece também no início do próximo.

### Análise por seções

Quando ativada, o Lutz detecta as seções do artigo antes de chunkar:

- Seções reconhecidas: `abstract`, `introduction`, `background`, `methodology`, `results`, `discussion`, `conclusion`, `references`, `acknowledgements`, `appendix`
- Cada chunk recebe o rótulo da sua seção
- Permite filtrar análises por seção (ex: analisar apenas abstracts)

### Fases do processo

O progresso é exibido em tempo real com indicadores de fase:

1. **Verificação de segurança** — detecta JavaScript, XFA, ações automáticas e padrões de prompt injection em cada PDF
2. **Extração de texto** — extrai o conteúdo textual e divide em chunks
3. **Embedding e indexação** — gera os vetores e persiste no banco

PDFs suspeitos são movidos automaticamente para `articles/_quarantine/` e podem ser revisados manualmente antes de serem processados com `--quarantine`.

---

## Equivalente no CLI

```bash
# Vetorização padrão
lutz vectorize

# Com seções e parâmetros customizados
lutz vectorize --section-parse --chunk-size 256 --chunk-overlap 32

# Modo quarentena
lutz vectorize --quarantine
```
