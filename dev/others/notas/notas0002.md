O 028a está implementado e passou na suíte (1538 testes nas três versões), no lint e no type-check. A bateria Oracle está rodando, e o commit sai quando ela terminar.

**O que o 028a entrega:**
- **Papel pelo próprio arquivo:** um config com `[web]` e sem `[agent]` é o web, e não precisa mais de `exec_users`, `exec_work_dir` nem `purge_user`. Um config com `[agent]` e sem `[web]` é o agente. O formato único antigo continua aceito.
- **`[app] name = agente0001`:** com ele, as pastas saem sozinhas: `var/agente0001/logs`, `work`, `output`, `input` e `script_work`, mais `var/exec` e `scripts_ambiente/`. O `agent_id` é o próprio nome. Escrever uma chave vazia, como `output_dir =`, desliga a função.
- **Subida pelo nome:** `bin/sss-web.sh web0001`, `bin/sss-scheduler.sh agente0001`, `bin/sss-stop.sh agente0001` e `python3 scripts/prepare_dirs.py agente0001`. O `--config` continua valendo.
- **`scripts_ambiente/`:** aceita como pasta de scripts em DEV, HML e PROD.
- **Exemplos prontos:** `instance/exemplos/web0001/` e `instance/exemplos/agente0001/`, com `config.ini.example` e `secrets.cfg.example`. O config mínimo do web tem cerca de 10 linhas, e o do agente, cerca de 15.

**Na prática, a configuração de um agente novo fica:**
```bash
mkdir instance/agente0002
cp instance/exemplos/agente0001/config.ini.example instance/agente0002/config.ini   # ajustar name, ambiente, usuário
cp instance/exemplos/agente0001/secrets.cfg.example instance/agente0002/secrets.cfg  # senhas, chmod 0600
python3 scripts/prepare_dirs.py agente0002 --service-user <conta>                    # como root
bin/sss-scheduler.sh agente0002
```

**Próximos passos:**

| Passo | Conteúdo |
|---|---|
| 028b | `bin/sss-update.sh` e o empacotador sem os dados locais |
| 028c | Mudança do seu DEV para a estrutura nova (antes de mover, mostro o que vai para onde), documentação completa e homologação |
| 028d | Revisão independente e encerramento |

Te aviso quando a bateria Oracle terminar e o commit do 028a estiver feito.