# CR-032: Revisão de toda a parametrização dos configs

| Campo | Valor |
|---|---|
| Status | **Registrada** em 2026-10-27, pendente (depois do CR-031) |
| Origem | Pedido do responsável pelo produto: verificar toda a parametrização dos `config.ini` e `secrets.cfg`, inclusive as chaves não obrigatórias e as que têm padrão, para ver o que pode ser simplificado ou até retirado |
| Objetivo | Config funcional e prático, sem abrir mão da funcionalidade |
| Restrições | Python 3.6.0 a 3.13; sem dependência nova; o ambiente real tem um usuário de banco e um usuário do sistema operacional, só DEV e PROD, `sss_env = DEV` nos dois (CR-028 D12, CR-030) |

## 1. Escopo

Cada chave de `sss_config.SCHEMA` (`[app]`, `[oracle]`, `[secrets]`, `[agent]`, `[logging]`, `[web]`) e cada seção do `secrets.cfg`, inclusive as que só existem para cenários que o ambiente real não usa (usuários de execução, helper, `sudo`, contas por papel, modo do driver, pool, monitor separado).

Para cada chave, registrar numa tabela:

* quem a lê no código e o que acontece com o valor padrão;
* se alguém já precisou mudá-la (DEV, homologações, ensaios);
* proposta: **manter**, **manter com outro padrão**, **juntar com outra**, **tornar fixa no código** ou **retirar** (com o tratamento das linhas antigas: ignorar com aviso, como no CR-026 e no CR-030);
* risco de cada proposta para a funcionalidade.

## 2. Forma de trabalho

1. Levantamento completo (tabela acima), sem mudar código.
2. Decisões apresentadas uma por vez, com opções A/B e recomendação.
3. Plano com os passos aprovados; implementação, testes, documentação (README §12.1, DEPLOYMENT, AGENTS) e relatório §9 por passo.
