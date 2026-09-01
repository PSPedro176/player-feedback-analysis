# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Equipes internas da Databricks que demonstram e adaptam soluções para clientes, e profissionais de estúdios de jogos mobile que precisam acompanhar feedback de jogadores.

## Product Purpose

Player Feedback Analysis é uma solução reutilizável para clientes Databricks que desenvolvem jogos mobile. Ela coleta avaliações públicas da Google Play, enriquece os comentários com recursos de IA, produz relatórios semanais e reúne análise operacional e exploratória em um Databricks App. O sucesso é permitir que uma equipe cadastre seus próprios jogos, execute a coleta e encontre rapidamente sinais acionáveis no feedback dos jogadores.

## Positioning

Um acelerador de solução Databricks completo e adaptável que conecta cadastro operacional, ingestão, enriquecimento com AI Functions, relatórios gerados por IA e exploração via AI/BI + Genie em um único fluxo implantável por bundle.

## Operating Context

A solução é apresentada em demonstrações para clientes, publicada em repositórios oficiais de soluções e adaptada por equipes técnicas para estúdios de jogos mobile. Os usuários alternam entre relatórios por jogo, exploração no dashboard AI/BI e gestão dos jogos monitorados.

## Capabilities and Constraints

- Cadastra e remove jogos da Google Play pela própria interface.
- Dispara a coleta e acompanha a execução do job.
- Exibe indicadores agregados, sentimento, avaliações recentes e relatórios semanais por jogo.
- Incorpora um dashboard Databricks AI/BI com Genie.
- Usa FastAPI, React, Vite, Lakebase, Unity Catalog, AI Functions e Declarative Automation Bundles.
- Deve permanecer reutilizável por diferentes clientes, sem referências visuais ou funcionais específicas da Wildlife.
- Preserva o nome do produto, o conteúdo atual, os fluxos e a funcionalidade existente.

## Brand Commitments

A interface deve adotar uma identidade visual coerente com produtos e soluções oficiais da Databricks. A marca Wildlife não deve aparecer nem orientar a linguagem visual. O tom deve ser profissional, claro, técnico e apropriado tanto para clientes quanto para equipes internas.

## Evidence on Hand

- Arquitetura e instruções de implantação documentadas em `README.md`.
- Implementação funcional em `app/` e recursos de implantação em `resources/`.
- Não há depoimentos, benchmarks ou alegações comerciais aprovadas; futuras superfícies não devem inventá-los.

## Product Principles

- Tornar sinais de feedback acionáveis rapidamente.
- Explicar a origem e o estado dos dados com clareza.
- Demonstrar recursos Databricks por meio do fluxo real da solução.
- Permanecer adaptável a diferentes portfólios de jogos e clientes.
- Priorizar confiança, legibilidade e operação eficiente.

## Accessibility & Inclusion

A experiência deve funcionar com teclado, respeitar redução de movimento, manter contraste adequado e não depender apenas de cor para comunicar estado.
