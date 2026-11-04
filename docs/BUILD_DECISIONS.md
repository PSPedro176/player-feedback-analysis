# Como eu construí — decisões, trade-offs e o papel da IA

> Relato em primeira pessoa (Pedro Perdomo, Solutions Architect) de como este projeto foi construído
> e por quê. Os números citados vêm da execução real de 2026-11-04 — ver [`docs/evidence/`](evidence/).

## 1. O problema que eu queria resolver

O caso nasceu de um cliente real: um estúdio mobile que lê reviews da Play Store manualmente, em
vários idiomas, e só entende um *review bomb* dias depois — quando a nota da loja já caiu e a
conversão da página da loja (e o custo de aquisição) já pioraram. O objetivo não era "fazer análise
de sentimento", e sim **encurtar o tempo entre o jogador reclamar e o time agir**, com dado
governado que Marketing, LiveOps e Suporte consigam consultar sozinhos.

## 2. Como a IA multiplicou meu esforço (workflow de construção)

| Ferramenta | Onde usei | Por quê |
|---|---|---|
| **Omnigent** (orquestração multi-agente) | A maior parte da construção: pipeline, jobs, App, Genie space, deploy e evidências | Eu atuei como tech lead: decompunha o trabalho em tarefas com contrato de aceite, um agente de código implementava cada uma em seu próprio branch/worktree e **um agente de outro fornecedor revisava o diff** antes de eu aceitar. Isso pegou bugs reais antes do deploy (DDL proibido em streaming table, colisão de nomes com um deploy antigo, job referenciando o próprio ID) e permitiu trabalhar em frentes paralelas (dados × Genie/App). |
| **Isaac** | Refinos pontuais | Ajustes finos de código e texto depois que a estrutura estava pronta. |
| **Genie Code** | Apenas o Dashboard AI/BI | Montar as visualizações do dashboard a partir das tabelas do Unity Catalog. |

O que a IA **não** decidiu por mim: o escopo, o desenho de dados, o que conta como "pronto" e a
conferência final. Toda resposta do Genie usada como evidência foi conferida contra SQL escrito à mão
(10/10 consultas corretas — ver [`genie_conversations.md`](evidence/genie_conversations.md)).

## 3. Decisões técnicas e por quê

### Modelo: Llama 3.3 70B via `ai_query`
- **Por quê:** é uma tarefa de classificação em lote (7 rótulos booleanos + resumo semanal), não de
  raciocínio longo. O 70B entrega JSON estrito de forma confiável, com custo e latência adequados para
  milhares de reviews: **9.014 reviews classificadas em ~7 min de pipeline, 0 erros** em 9.017 chamadas.
- **Trade-off:** modelos maiores (Claude/GPT, disponíveis no workspace) dariam resumos mais ricos,
  mas a um custo por review muito maior. O modelo é uma **variável do bundle** (`ai_model`), então
  trocar é uma linha — sem reescrever pipeline.

### Prompt de classificação: 7 dimensões, JSON estrito
- Dimensões: `bug_report`, `pricing`, `game_balance`, `opinion`, `community`, `toxicity`, `visuals`.
- `responseFormat` com schema JSON estrito: **nada de texto livre para parsear**; cada review vira
  colunas booleanas consultáveis.
- Sentimento separado com `ai_analyze_sentiment` (função nativa, sem prompt para manter).
- Aprendizado no teste do Genie: `opinion` é genérico demais (aparece em quase toda review), então o
  Genie foi instruído a excluí-lo de rankings de temas.

### Prompt do relatório semanal: "não invente"
- Amostra de até 700 reviews por jogo, relatório em PT-BR, com período e volume explícitos e a seção
  "Principais tópicos da semana".
- Instrução explícita de **não inventar e não recomendar** — o relatório descreve o que os jogadores
  disseram; a decisão é do time.
- A **nota (verde/amarelo/vermelho) é determinística**, calculada por regra sobre as taxas de bug,
  toxicidade e negativos — não pelo LLM. Assim a nota é reprodutível e auditável.

### Guardrails e auditoria da IA
- `ai_query(..., failOnError => false)`: uma falha do endpoint não derruba o pipeline; o erro vira
  dado.
- Toda chamada fica em `ai_inference_log` (modelo, versão do prompt, resposta bruta, erro, horário) —
  governado no Unity Catalog e consultável pelo próprio Genie ("qual a taxa de erro das chamadas de IA?").
- Um relatório que falhou **não sobrescreve** um relatório bom anterior.
- *Expectations* do Lakeflow (id/texto não nulos, nota 1–5, sentimento válido): 4/4 passaram em
  9.014/9.014 linhas.

### Lakebase + CDF para o cadastro de jogos
- **Por quê:** o cadastro é transacional (o usuário adiciona um jogo no App e espera ver na hora) —
  Postgres é o lugar certo. O CDF do Lakebase replica as mudanças para o Unity Catalog
  (`lb_games_history` → `games_current`), que é a fonte de verdade dos jobs.
- **Trade-off:** mais uma peça de infraestrutura vs. gravar direto numa tabela Delta pelo App. Escolhi
  Lakebase porque separa a escrita operacional do analítico e mantém o histórico governado.

### Genie space dedicado (e não só o Genie embutido no dashboard)
- Na primeira versão, o App apenas embutia um Dashboard AI/BI — o Genie que aparecia era o padrão do
  dashboard, não um agente configurado. Corrigi isso: agora há um **Genie space dedicado**, versionado
  no repositório (`src/genie/`), com instruções PT/EN, glossário do domínio, 10 perguntas de exemplo,
  6 consultas SQL confiáveis e uma view feita para ele (`weekly_game_summary`).
- O App tem uma aba **"Pergunte ao Genie"** que usa a Genie Conversation API (resposta, SQL gerado,
  tabela de resultado, perguntas de seguimento).
- **Trade-off:** o space é criado por um job (`pf_febar_genie_setup`) e não como recurso nativo do
  bundle, porque a API exige que as tabelas já existam — e elas só existem depois do primeiro pipeline.
- Itereei as instruções 3 vezes a partir de testes reais (excluir `opinion` de rankings, arredondar
  notas, avisar volume baixo, **nunca expor nome de autor nem id de review**).

## 4. Limites honestos

- Fonte única (Play Store); sem id de usuário, então não meço churn real — meço sinais (sentimento,
  bugs, toxicidade) que antecedem churn.
- Na execução de demonstração limitei a 1.000 reviews por jogo/idioma por custo; o Free Fire ficou com
  pouco histórico (o Genie avisa quando o volume é < 300 reviews).
- A qualidade do classificador foi verificada por amostragem, ainda não contra um conjunto rotulado à
  mão com precisão/recall.
- Em uma das 10 perguntas, o SQL do Genie estava certo mas o texto da resposta contou errado por
  jogo/idioma — documentado em `genie_conversations.md`.

## 5. Próximos passos

- Conjunto rotulado (~200 reviews) para medir precisão/recall por dimensão e comparar modelos.
- Alertas automáticos quando a taxa de negativos de um jogo dobrar em 24h (review bomb).
- Mais fontes (App Store, Discord, tickets de suporte).
