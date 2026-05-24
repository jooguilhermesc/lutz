# Tier Classifier — Referência

Este arquivo documenta a lógica de classificação de tiers usada pelo TierClassifier determinístico.
Não é usado como system prompt real — o TierClassifier é baseado em regras (lutz/agent/model_router.py).

## Tiers de complexidade

| Tier | Complexidade | Tools |
|------|-------------|-------|
| L0 | Trivial | inspect_corpus, get_section_breakdown, get_article_chunks |
| L1 | Simples | search_corpus, query_analytics |
| L2 | Moderada | analyze_corpus (< 30 artigos, sem critério), extract_citations (≤ 15 artigos) |
| L3 | Complexa | analyze_corpus (> 30 artigos ou com critério), extract_citations (> 15 artigos), generate_roadmap |
