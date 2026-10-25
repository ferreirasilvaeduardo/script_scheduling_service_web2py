# CR-024: Owner e prefixo no nome dos arquivos SQL gerados

| Campo | Valor |
|---|---|
| Status | **Encerrado** (2026-10-25). Pedido e plano aprovados pelo responsável pelo produto em 2026-10-25 |
| Origem | Gerar os SQL de mais de um esquema na mesma pasta sem que um sobrescreva o outro |
| Afeta | `ddl_builder.sql_file_name`, `scripts/generate_sql.py` e `init_db --generate-sql`; `docs/sql/`; README §11; DEPLOYMENT §5, §20; DEV_ENVIRONMENT; UTILITY_SCRIPTS; testes |

## Decisões

| # | Decisão |
|---|---|
| D1 | Nome `<base>_<owner>_<prefixo>.sql`, com o owner em minúsculas e o prefixo sem o `_` final: owner `OPENRISOW` e prefixo `tbsss_` geram `01_deploy_sss_openrisow_tbsss.sql`, `02_rollback_sss_openrisow_tbsss.sql`, `99_validate_deploy_openrisow_tbsss.sql` e, com `--grants-to`, `03_grants_sss_openrisow_tbsss.sql` |
| D2 | Um só lugar monta o nome (`ddl_builder.sql_file_name`), usado pela gravação e pelo cabeçalho do deploy, que cita o rollback do mesmo esquema. Owner e prefixo já são identificadores validados pelo `sql_ident`, então o nome só tem letras, números e `_` |
| D3 | Gerar de novo para o mesmo owner e prefixo sobrescreve; esquemas diferentes ficam lado a lado. Os arquivos de `docs/sql/` foram renomeados com `git mv` (os do DEV: `openrisow`, `tbsss_`) |
| D4 | Menções históricas ao nome antigo (ex.: o rollback "gerado pela versão anterior" no CR-016a, DEPLOYMENT §18, e a mensagem do `init_db` sobre o esquema anterior ao CR-016a) ficam como estão |
