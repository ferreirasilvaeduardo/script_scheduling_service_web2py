# -*- coding: utf-8 -*-
"""Gera o documento de evidencias da homologacao (DEV real) a partir do results.json do capture_evidence.js.

Uso (da pasta tools/, Python 3 com python-docx):
    SSS_EVIDENCE_DATE=AAAAMMDD [SSS_EVIDENCE_ROUND=n] python3 build_evidence_docx.py [pasta_evidencias] [saida.docx]
Rodadas conhecidas em RODADAS (20261022: CR-016; 20261023: CR-017; 20261023_r2: CR-018; 20261023_r3: CR-019
e CR-020; 20261024_r2: CR-021a-c; 20261024_r4: CR-021e; 20261024_r6: CR-021f). Padrao: a rodada de
20261023, ../evidence_<data>[_r<n>] -> ../../../docs/homologation/SSS_Homologation_Evidence_<AAAA-MM-DD>[_r<n>].docx
"""
import io
import json
import os
import re
import calendar
import struct
import sys
import time

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

AQUI = os.path.dirname(os.path.abspath(__file__))
HOMOLOG = os.path.dirname(AQUI)
APP = os.path.dirname(os.path.dirname(HOMOLOG))
RUN_DATE = os.environ.get("SSS_EVIDENCE_DATE", "20261023")
DATE_ISO = "%s-%s-%s" % (RUN_DATE[:4], RUN_DATE[4:6], RUN_DATE[6:])
DATE_BR = "%s/%s/%s" % (RUN_DATE[6:], RUN_DATE[4:6], RUN_DATE[:4])
ROUND = os.environ.get("SSS_EVIDENCE_ROUND", "")
RUN_TAG = RUN_DATE + ("_r" + ROUND if ROUND else "")
SUFFIX = "_r" + ROUND if ROUND else ""
STAMP = "HOMOLOG_" + RUN_DATE + ("R" + ROUND if ROUND else "")
EVID = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HOMOLOG, "evidence_" + RUN_TAG)
SAIDA = sys.argv[2] if len(sys.argv) > 2 else os.path.join(APP, "docs", "homologation",
                                                          "SSS_Homologation_Evidence_%s%s.docx" % (DATE_ISO, SUFFIX))
ROXO = RGBColor(0x4A, 0x0A, 0x64)
VERDE = RGBColor(0x1B, 0x6E, 0x3A)
VERMELHO = RGBColor(0xB0, 0x1C, 0x1C)
AMBAR = RGBColor(0x8A, 0x5A, 0x00)

ORDEM = ["CT-01", "CT-02", "CT-03", "MASSA", "CT-04", "CT-05", "CT-06", "CT-07", "CT-08", "CT-09", "CT-10",
         "CT-11", "CT-12", "CT-13", "CT-14", "CT-15", "CT-16", "CT-17", "CT-18", "CT-19", "CT-20", "CT-21",
         "CT-22", "CT-23", "CT-24", "CT-25", "CT-26", "CT-27", "CT-28", "CT-29", "CT-30", "ENCERRAMENTO"]

# Adaptacao de cada caso ao DEV real (o manual de 18/10 foi escrito sobre a massa simulada do FAKE).
ADAPTACAO = {
    "CT-01": u"Igual ao manual. A troca válida de senha do admin usou a senha escolhida pelo responsável pela "
             u"homologação; os demais usuários seguem com a senha inicial documentada (DEPLOYMENT.md §5.3).",
    "CT-03": u"HOMOLOGACAO → GFPREPROD; o perfil OPERATOR_HML do DEV tem CLONE6, CLONE7 e GFPREPROD.",
    "CT-04": u"carga_diaria → contar_linhas_arquivo; o histórico mostra as execuções reais do dia.",
    "CT-05": u"carga_diaria em PRODUCAO → gerar_hash_arquivo em CLONE2. Os 14 utilitários do seed são liberados "
             u"aos três perfis operacionais, então não há script fora do perfil para mostrar na etapa 1.",
    "CT-06": u"O ticket rodando é uma compactação real de 3 GB de texto (nível 9, cerca de 4 minutos).",
    "CT-07": u"Os tickets #11 e #30 do FAKE → ticket longo rodando e um ticket que deu erro de verdade "
             u"(arquivo inexistente, código de retorno 2). A exibição segura do log usa um caminho com "
             u"<script> e <b>, ecoado pelo próprio script.",
    "CT-08": u"O ticket esperando foi criado com Agendar para daqui a 2 horas (o agente real pega os imediatos em "
             u"segundos).",
    "CT-09": u"Ticket #19 do FAKE → ticket real do op.prod (gerar_hash_arquivo em CLONE2); o vínculo obrigatório "
             u"temporário foi o termo_busca, desfeito ao final.",
    "CT-11": u"HOMOLOG2 → ambiente %s_<hhmm>, desativado ao final; a confirmação de desativação "
             u"foi aberta no GFPREPROD e cancelada." % STAMP,
    "CT-12": u"CONSULTA → READ_ONLY; OPERADOR_HML → OPERATOR_HML; DESENV (inativo) → CLONE7; VER_AUDITORIA → "
             u"VIEW_AUDIT. A revisão foi cancelada (matriz inalterada).",
    "CT-13": u"carga_diaria → contar_linhas_arquivo; HOMOLOGACAO → GFPREPROD.",
    "CT-14": u"O usuário bloqueado foi produzido de verdade: 5 tentativas erradas do consulta, depois "
             u"desbloqueado pela tela. A redefinição válida do op.prod usou a própria senha inicial.",
    "CT-15": u"data_ref/documento_cliente → parâmetro sigiloso documento_cliente_hml criado pela tela "
             u"(regex ^[0-9]{11}$), sem vínculo com scripts.",
    "CT-16": u"carga_diaria → contar_linhas_arquivo; o caminho original foi restaurado no fim. Pela regra "
             u"atual (CR-011), o arquivo é conferido pelo agente na execução, não pelo nó web.",
    "CT-17": u"Regra nova %s_DIARIA_<hhmm>, diária com a primeira execução em poucos minutos; o "
             u"agente real criou o ticket no horário (CT-18)." % STAMP,
    "CT-18": u"A regra pausada do FAKE não existe no DEV; a agenda mostra a regra do CT-17.",
    "CT-19": u"Códigos atuais da auditoria: TICKET_CANCEL e AUDIT_EXPORT (antes TICKET_CANCELAR e AUD_EXPORTAR).",
    "CT-20": u"Um único agente real (srv-linux-local-01); os agentes agt-host01/02 eram simulados pelo FAKE.",
    "CT-21": u"Ticket fora do escopo do op.hml: um ticket real de CLONE2.",
    "CT-23": u"PRODUCAO → ambiente criado no CT-11; ticket #17 → ticket real do op.prod.",
    "CT-24": u"Responsável inativo e link simbólico seguem a regra atual (ver Observações).",
    "CT-25": u"SHA-256 retirado pelo CR-011; a matriz do OPERATOR_PROD voltou ao original no fim.",
}

# Ressalvas (o caso passou, com observacao relevante para o responsavel).
_RESSALVA_1022 = {
    "CT-05": u"Destaque de produção fixo no nome PRODUCAO (ticket_service.PRODUCTION_ENVIRONMENT): não aparece "
             u"para nenhum ambiente do DEV.",
    "CT-20": u"Estados Atrasado/Em risco/Offline e quadros de atenção não reproduzíveis com um único agente "
             u"saudável.",
    "CT-24": u"Cenário de responsável inativo não reproduzível no DEV sem mudar permissões (coberto pelos testes "
             u"automatizados).",
}

_DEFEITOS_1022 = [
    (u"Linha de situação ao vivo vazia em 4 telas",
     u"views/tickets/index.html, views/tickets/detail.html, views/audit/agents.html, views/admin_profiles/matrix.html",
     u"O template mostrava x-text=\"state\", mas os componentes Alpine expõem statusText. Desde o CR-016a não "
     u"apareciam: \"Atualizada às …\" da lista de tickets, \"Atualizado às …\" do painel de agentes, a situação do "
     u"visualizador de log (\"Acompanhando a execução\", \"Atualização pausada\") e a contagem de alterações "
     u"pendentes da matriz.",
     u"Corrigido; conferido no CT-06, CT-12 e CT-20."),
    (u"Duração típica \"cerca de menos de 1 minuto\"",
     u"modules/ticket_service.py (histórico do script)",
     u"O prefixo \"cerca de\" era somado ao texto \"menos de 1 minuto\".",
     u"Corrigido (abaixo de 1 minuto: \"menos de 1 minuto\"); teste novo em test_catalog_service."),
    (u"Caminho longo estoura a janela de confirmação do disparo",
     u"static/css/sss.css (.sss-summary-answers)",
     u"As respostas do resumo (caminhos de arquivo sem espaço) não quebravam linha e passavam da borda do modal.",
     u"Corrigido (quebra em qualquer ponto); conferido na figura de confirmação do CT-05."),
]

_OBSERVACOES_1022 = [
    u"Destaque de ambiente de produção: só o ambiente chamado PRODUCAO recebe o selo vermelho e a confirmação "
    u"\"AMBIENTE DE PRODUÇÃO\" (ticket_service.PRODUCTION_ENVIRONMENT). No DEV nenhum ambiente tem esse nome; "
    u"recomenda-se torná-lo configurável antes da implantação em produção.",
    u"Cancelamento no agente real: o log não ganha a linha \"processo encerrado por cancelamento (SIGTERM)\", "
    u"que só existia na simulação do FAKE; o motivo aparece no Detalhe técnico (CANCELLED / CANCEL_USER).",
    u"Scripts PYTHON3 rodam com -I e saída em buffer: o log de um script Python aparece quando o buffer descarrega "
    u"(no fim, ou nunca, se o processo for cancelado). Scripts SH/BASH escrevem na hora.",
    u"Sufixo do id da mensagem de erro dos campos: components/form_field.html usa \"-erro\" e os formulários próprios "
    u"(disparo, regra) usam \"-error\". Sem efeito para o usuário; resquício do CR-016, cuja tradução foi encerrada.",
]


# Rodada de 23/10/2026 (CR-017): o que mudou nas telas e a massa de um banco DEV recriado.
_ADAPTACAO_1023 = {
    "CT-02": u"Painel sem o cartão de disparo e sem o menu repetido (CR-017b): o disparo fica no item de menu "
             u"Rodar um script.",
    "CT-04": u"Rotinas disponíveis passou a se chamar Rodar um script (CR-017b), com o botão Agendar para quem tem "
             u"Regras de Agendamento (CR-017c).",
    "CT-05": u"carga_diaria em PRODUCAO → gerar_hash_arquivo em CLONE2. A escolha do script é feita nos cartões de "
             u"Rodar um script; o comando aparece só na confirmação (sem a pré-visualização separada, CR-017b). "
             u"Todos os ambientes do DEV estão marcados como produção no cadastro (CR-017a), então o alerta e o botão "
             u"vermelho aparecem.",
    "CT-26": u"Caso novo do CR-017: o perfil OPERATOR_HML perdeu VIEW_LOGS por alguns segundos (para mostrar o item "
             u"Tickets de quem só dispara) e o limpar_linhas_vazias ficou homologado em um ambiente e depois em "
             u"nenhum (disparo e regra direto ao formulário; quadro Quem pode rodar). Tudo foi desfeito no próprio "
             u"caso.",
}

_OBSERVACOES_1023 = [
    u"Banco do DEV recriado no CR-017a (rollback, implantação e validação dos scripts de docs/sql/): os "
    u"registros da rodada de 22/10 não existem mais, e a massa desta rodada foi criada do zero pelas telas.",
    u"Ambiente de produção agora é uma marcação do cadastro (tbsss_environments.is_production, CR-017a). O seed "
    u"marca os 5 ambientes do DEV como produção; por isso o alerta aparece em todo disparo.",
    u"Cancelamento no agente real: o log não ganha a linha \"processo encerrado por cancelamento (SIGTERM)\", "
    u"que só existia na simulação do FAKE; o motivo aparece no Detalhe técnico (CANCELLED / CANCEL_USER).",
    u"Scripts PYTHON3 rodam com -I e saída em buffer: o log de um script Python aparece quando o buffer descarrega "
    u"(no fim, ou nunca, se o processo for cancelado). Scripts SH/BASH escrevem na hora.",
    u"Três verificações da primeira passada (menu com Administração, alerta de produção e coluna Produção) "
    u"procuravam o texto como escrito, mas a tela o exibe em maiúsculas por CSS. O roteiro passou a comparar sem "
    u"diferenciar maiúsculas, e o CT-02, o CT-05 e o CT-11 foram executados de novo; por isso há um segundo "
    u"ambiente %s_<hhmm> (também inativo) e um segundo ticket do CT-05." % STAMP,
]

# Rodada 2 de 23/10/2026 (CR-018), no mesmo banco da rodada da manha (sem recriar).
_ADAPTACAO_1023R2 = dict(_ADAPTACAO_1023, **{
    "CT-01": u"O admin já usava a senha escolhida pelo responsável pela homologação (rodada da manhã no mesmo "
             u"banco); a troca válida repetiu essa senha. Os demais usuários seguem com a senha inicial "
             u"documentada (DEPLOYMENT.md §5.3).",
    "CT-03": u"HOMOLOGACAO → GFPREPROD. Os botões Rodar em… saíram (CR-018b): a tela mostra quantos scripts o "
             u"usuário pode rodar e leva aos cartões de Rodar um script. Funcionalidades com os nomes do menu.",
    "CT-06": u"Coluna Situação e motivo de erro em nome simples (CR-018b). Filtro por solicitante só para quem vê "
             u"logins; para o consulta, um login alheio na URL é ignorado (CR-018a).",
    "CT-07": u"Os tickets #11 e #30 do FAKE → ticket longo rodando e um ticket que deu erro de verdade. No ticket "
             u"encerrado o log termina com \"Log completo.\" (CR-018b).",
    "CT-11": u"HOMOLOG2 → ambiente %s_<hhmm>, desativado ao final. O GFPREPROD do seed foi editado (produção "
             u"desmarcada e remarcada), o que só funciona com o DSN sem porta aceito (CR-018g)." % STAMP,
    "CT-12": u"CONSULTA → READ_ONLY; OPERADOR_HML → OPERATOR_HML; DESENV (inativo) → CLONE7; VER_AUDITORIA → "
             u"VIEW_AUDIT. A revisão foi cancelada (matriz inalterada). Perfil novo %s_P<hhmm>: a inclusão abre a "
             u"matriz (CR-018b); desativado ao final." % STAMP,
    "CT-13": u"carga_diaria → contar_linhas_arquivo; HOMOLOGACAO → GFPREPROD. Motivos com o nome do cadastro "
             u"(\"tem Rodar Scripts\", CR-018b).",
    "CT-15": u"Parâmetro sigiloso documento_cliente_hml (já criado na rodada da manhã). O caminho_arquivo, usado "
             u"por script ativo, mostra o aviso no lugar do botão Desativar (CR-018b).",
    "CT-17": u"Regra nova %s_DIARIA_<hhmm>, diária com a primeira execução em poucos minutos; o agente real "
             u"criou o ticket no horário (CT-18). Filtro de ambiente em lista (CR-018b)." % STAMP,
    "CT-19": u"Ações e entidades com nomes simples na tela, com o código ao lado (CR-018b); o CSV continua com os "
             u"códigos.",
    "CT-27": u"Caso novo do CR-018: o OPERATOR_HML ficou sem Consultar Tickets por alguns segundos (cancelar só "
             u"quem enxerga); a regex do caminho_arquivo e o arquivo do contar_linhas_arquivo foram trocados para "
             u"mostrar os avisos e desfeitos no próprio caso; tempos de abertura registrados (CR-018c).",
})

_OBSERVACOES_1023R2 = [
    u"Segunda rodada do dia, no mesmo banco da rodada da manhã (sem recriar): os registros HOMOLOG_20261023_* "
    u"continuam lá, e os desta rodada têm a marca %s." % STAMP,
    u"Antes desta rodada o repositório foi movido para /portaloptrib/TESHUVA/SSS/DEV/web2py; os caminhos dos "
    u"arquivos de entrada nas telas já são os novos.",
    u"Uma primeira passada desta rodada foi descartada: o link /opt/automacoes/scripts/utilitarios ainda apontava "
    u"para o caminho antigo do repositório, e os tickets terminaram com erro (as verificações do CR-018 passaram). "
    u"Depois de refazer o link, a rodada foi executada do zero. Os registros daquela passada ficam no banco com a "
    u"mesma marca (tickets com erro, ambiente e perfil inativos, regra pausada).",
    u"Agente iniciado com o config padrão do DEV (CR-018d): os interpretadores estão no instance/config.ini local, "
    u"sem cópia separada.",
    u"Nomes das funcionalidades (Rodar Scripts, Consultar Tickets) aplicados ao banco do DEV pelo MERGE do "
    u"init_db (CR-018b), sem recriar.",
    u"Cancelamento no agente real: o log não ganha a linha \"processo encerrado por cancelamento (SIGTERM)\", "
    u"que só existia na simulação do FAKE; o motivo aparece no Detalhe técnico (CANCELLED / CANCEL_USER).",
    u"Scripts PYTHON3 rodam com -I e saída em buffer: o log de um script Python aparece quando o buffer descarrega "
    u"(no fim, ou nunca, se o processo for cancelado). Scripts SH/BASH escrevem na hora.",
]

# Rodada 3 de 23/10/2026 (CR-019 e CR-020), no banco do DEV recriado no CR-020b.
_ADAPTACAO_1023R3 = dict(_ADAPTACAO_1023R2, **{
    "CT-01": ADAPTACAO["CT-01"] + u" O banco foi recriado no CR-020b, então o admin voltou à senha inicial.",
    "CT-15": u"Parâmetro sigiloso documento_cliente_hml criado pela tela (banco recriado). O caminho_arquivo, "
             u"usado por script ativo, mostra o aviso no lugar do botão Desativar (CR-018b).",
    "CT-28": u"Caso novo do CR-020a. Nenhum script do seed grava na pasta de saída: o diagnóstico "
             u"dev/scripts/diagnostico/gerar_saida.sh foi cadastrado pela tela (diag_gerar_saida, só GFPREPROD), "
             u"rodado pelo admin e desativado no fim; o op.prod navegou e baixou como outra pessoa.",
    "CT-29": u"Caso novo do CR-020b a 020d, com o agente real: envio pela tela do op.hml para o GFPREPROD, entrega, "
             u"retrato, EXISTS, substituição com confirmação, subpasta recusada, 413 acima de 50 MiB e um ticket do "
             u"contar_linhas_arquivo que leu o arquivo enviado.",
    "CT-30": u"Caso novo do CR-019: o diagnóstico dev/scripts/diagnostico/pasta_trabalho.sh foi cadastrado pela tela "
             u"(diag_pasta_trabalho, só GFPREPROD), rodado e desativado no fim. O DEV tem [agent] script_work_dir ligado.",
})

_OBSERVACOES_1023R3 = [
    u"Terceira rodada do dia. O banco do DEV foi recriado no CR-020b (02 → 01 → 99): os registros das rodadas "
    u"anteriores não existem mais, e a massa desta rodada foi criada do zero pelas telas (marca %s)." % STAMP,
    u"Telas novas desde a rodada 2: Saídas (CR-020a, funcionalidade Baixar Saídas) e Entrada (CR-020d, Enviar "
    u"Arquivos), ambas concedidas no seed a ADMINISTRATOR, OPERATOR_PROD e OPERATOR_HML; o READ_ONLY recebe 403.",
    u"A entrada pela tela vai pelo banco: o agente grava o arquivo pelo helper put-input como o usuário de "
    u"execução e publica o retrato da pasta; o web nunca acessa o disco do agente.",
    u"O purge dos envios (CR-020e) não aparece nesta rodada: o purge.py não roda no DEV (purge_user vazio). A "
    u"etapa foi ensaiada no CR-020e contra o banco do DEV (conteúdos esvaziados e PURGE auditado).",
    u"Os dois scripts de diagnóstico (diag_gerar_saida e diag_pasta_trabalho) ficam cadastrados e inativos; Rodar "
    u"um script continua com os 14 utilitários do seed.",
    u"Cancelamento no agente real: o log não ganha a linha \"processo encerrado por cancelamento (SIGTERM)\", "
    u"que só existia na simulação do FAKE; o motivo aparece no Detalhe técnico (CANCELLED / CANCEL_USER).",
    u"Scripts PYTHON3 rodam com -I e saída em buffer: o log de um script Python aparece quando o buffer descarrega "
    u"(no fim, ou nunca, se o processo for cancelado). Scripts SH/BASH escrevem na hora.",
]

_AGENTE_PADRAO = (u"Agente iniciado com bin/sss-scheduler.sh e uma cópia do instance/config.ini do DEV com o mesmo "
                  u"agent_id (srv-linux-local-01), os mesmos ambientes e as mesmas pastas, acrescentando apenas "
                  u"interpreters = PYTHON3=/usr/bin/python3,BASH=/bin/bash,SH=/bin/sh (o padrão é vazio, e sem "
                  u"interpretadores o agente não pega tickets).")
_SENHAS_PADRAO = u"No CT-01 a senha do admin foi trocada pela tela para a senha escolhida pelo responsável pela homologação."

RODADAS = {
    "20261022": {"commit": u"07e424f (encerramento do CR-016) mais as correções desta homologação, no mesmo commit "
                           u"deste documento",
                 "adaptacao": {}, "ressalva": _RESSALVA_1022, "defeitos": _DEFEITOS_1022,
                 "observacoes": _OBSERVACOES_1022},
    "20261023": {"commit": u"dedf93a (CR-017 concluído: 017a a 017d) mais o roteiro ajustado, no mesmo commit "
                           u"deste documento",
                 "adaptacao": _ADAPTACAO_1023,
                 "ressalva": dict((k, v) for k, v in _RESSALVA_1022.items() if k != "CT-05"),
                 "defeitos": [], "observacoes": _OBSERVACOES_1023},
    "20261023_r2": {"commit": u"d4cf9a9 (CR-018: 018a a 018d, 018f e 018g) e a mudança de pasta (b7ac268, "
                              u"bc3f31b), mais o roteiro ajustado, no mesmo commit deste documento",
                    "adaptacao": _ADAPTACAO_1023R2,
                    "ressalva": dict((k, v) for k, v in _RESSALVA_1022.items() if k != "CT-05"),
                    "defeitos": [], "observacoes": _OBSERVACOES_1023R2,
                    "agente": u"Agente iniciado com bin/sss-scheduler.sh e o config padrão do DEV "
                              u"(instance/config.ini, agent_id srv-linux-local-01), que já traz os interpretadores "
                              u"PYTHON3, BASH e SH (CR-018d).",
                    "senhas": u"O admin já estava com a senha escolhida pelo responsável pela homologação (rodada da "
                              u"manhã); no CT-01 a troca válida repetiu essa senha.",
                    "registros": u" Nesta rodada também: o perfil %s_P<hhmm> (inativo) e, no CT-27, a permissão Consultar "
                                 u"Tickets do OPERATOR_HML, a regex do caminho_arquivo e o arquivo do "
                                 u"contar_linhas_arquivo, todos desfeitos no próprio caso." % STAMP},
}
RODADAS["20261023_r3"] = {
    "commit": u"97c8687 (CR-020 concluído; CR-019 em aa7bc1f) mais o roteiro com o CT-28 a CT-30, no mesmo commit "
              u"deste documento",
    "adaptacao": _ADAPTACAO_1023R3,
    "ressalva": dict((k, v) for k, v in _RESSALVA_1022.items() if k != "CT-05"),
    "defeitos": [], "observacoes": _OBSERVACOES_1023R3,
    "agente": RODADAS["20261023_r2"]["agente"],
    "registros": u" Nesta rodada também: o perfil %s_P<hhmm> (inativo), os scripts de diagnóstico diag_gerar_saida "
                 u"e diag_pasta_trabalho (inativos), os envios da tela de Entrada e a subpasta tela_r3 na pasta de "
                 u"entrada do contar_linhas_arquivo no GFPREPROD." % STAMP,
}
RODADAS["20261024_r2"] = {
    "commit": u"479f54b (CR-021a a 021c: sem Alpine.js e sem gluon.current em modules/; correção da parada antes do "
              u"claim no scheduler) mais o roteiro ajustado e o bin/start_local.sh corrigido, no mesmo commit deste "
              u"documento",
    "adaptacao": dict(_ADAPTACAO_1023R3, **{
        "CT-01": ADAPTACAO["CT-01"] + u" O banco não foi recriado desde a rodada 3 de 23/10: o admin já estava com a "
                                      u"senha escolhida (SSS_ADMIN_START=new).",
    }),
    "ressalva": dict((k, v) for k, v in _RESSALVA_1022.items() if k != "CT-05"),
    "defeitos": [
        (u"Roteiro sem o botão Criar ticket",
         u"dev/homologation/tools/capture_evidence.js",
         u"O roteiro clicava em button[data-summary-trigger], gancho do JavaScript antigo que saiu com o Alpine "
         u"(CR-021b2). Na rodada 1 deste dia o modal de disparo não abriu, nenhum ticket foi criado e 48 verificações "
         u"falharam em cascata (227 OK).",
         u"Corrigido: o roteiro usa o contrato novo ([data-component=\"ticketTrigger\"] [data-action=\"open\"]) e o "
         u"test_frontend_components confere que todo [data-*] dos seletores do roteiro existe no HTML ou no JS. "
         u"Rodada 2: 283 OK, 0 falha."),
        (u"Servidor local do DEV não subia",
         u"bin/start_local.sh",
         u"O diagnóstico antes de subir ainda lia current.sss_cfg, que deixou de existir no CR-021c.",
         u"Corrigido: lê app_context.require_config(); o test_app_context confere que nenhum código lê o contexto "
         u"antigo."),
    ],
    "observacoes": [
        u"Segunda rodada do dia. A primeira (evidence_20261024) parou no botão Criar ticket do roteiro (ver "
        u"Defeitos); esta rodada repetiu todos os casos com a marca %s." % STAMP,
        u"Telas sem Alpine.js desde o CR-021b: os componentes são JavaScript próprio (static/js/app/dom.js), sem "
        u"expressão no HTML. Os textos, as classes e o comportamento das telas não mudaram; os casos de matriz, "
        u"homologação, parâmetros, regra de agendamento, disparo, log, Entrada e listas passaram sem ajuste de "
        u"resultado esperado.",
        u"O agente desta rodada já tem a correção da parada (479f54b): com o .stop ou o sinal, não faz claim nem "
        u"desdobro na volta seguinte.",
        u"Cancelamento no agente real: o log não ganha a linha \"processo encerrado por cancelamento (SIGTERM)\", "
        u"que só existia na simulação do FAKE; o motivo aparece no Detalhe técnico (CANCELLED / CANCEL_USER).",
    ],
    "agente": u"Agente iniciado com scripts/run_scheduler.py (Python 3.6.15 com o driver Oracle, modo thick) e o "
              u"config padrão do DEV (instance/config.ini, agent_id srv-linux-local-01, interpretadores PYTHON3, BASH "
              u"e SH); servidor web pelo bin/start_local.sh na porta 18000.",
    "senhas": u"O admin já estava com a senha escolhida pelo responsável pela homologação (rodada 3 de 23/10); no "
              u"CT-01 a troca válida repetiu essa senha.",
    "registros": RODADAS["20261023_r3"]["registros"].replace("tela_r3", "tela_r2"),
}
RODADAS["20261024_r4"] = {
    "commit": u"ee3b3a8 (CR-021e1: aplicação no servidor web próprio, sem web2py em execução) mais o CR-021e2 "
              u"(launchers, start_local/stop_local e a correção da raiz do endereço), no mesmo commit deste documento",
    "adaptacao": RODADAS["20261024_r2"]["adaptacao"],
    "ressalva": RODADAS["20261024_r2"]["ressalva"],
    "defeitos": [
        (u"Endereço raiz com 404",
         u"modules/web/routing.py e modules/web/app.py",
         u"Na rodada 3 deste dia (evidence_20261024_r3), o primeiro passo do CT-01 falhou: o servidor novo devolvia "
         u"404 em / e em /script_scheduling_service/, onde o web2py levava ao login. A faixa do ambiente também não "
         u"apareceu, porque a página era a de erro (281 OK, 2 falhas, todas no CT-01).",
         u"Corrigido: / responde 303 para /script_scheduling_service/, e a raiz da aplicação é default/index, como "
         u"no web2py (D4); testes novos em test_web_routing e test_web_app. Rodada 4: 283 OK, 0 falha."),
    ],
    "observacoes": [
        u"Quarta rodada do dia, a primeira com o servidor web próprio (scripts/run_web.py, CR-021e): o web2py não "
        u"roda mais a aplicação. A rodada 3 parou no endereço raiz (ver Defeitos); esta repetiu todos os casos com "
        u"a marca %s." % STAMP,
        u"Telas, textos e comportamento iguais aos do web2py: antes desta rodada, o HTML de 37 páginas foi comparado "
        u"com o do web2py para admin, op.prod e consulta (111 de 111 iguais, a única diferença documentada é a "
        u"vitrine de DEV).",
        u"Servidor web subido e parado pelo bin/start_local.sh e bin/stop_local.sh, que agora usam o "
        u"bin/sss-web.sh com o run_web.py (parada por SIGTERM, esperando as requisições em andamento).",
        u"Cancelamento no agente real: o log não ganha a linha \"processo encerrado por cancelamento (SIGTERM)\", "
        u"que só existia na simulação do FAKE; o motivo aparece no Detalhe técnico (CANCELLED / CANCEL_USER).",
    ],
    "agente": u"Agente iniciado com bin/sss-scheduler.sh (Python 3.6.15 com o driver Oracle) e o config padrão do DEV "
              u"(instance/config.ini, agent_id srv-linux-local-01, interpretadores PYTHON3, BASH e SH); servidor web "
              u"próprio pelo bin/start_local.sh na porta 18000; agente parado pelo bin/sss-stop.sh.",
    "senhas": RODADAS["20261024_r2"]["senhas"],
    "servidor_web": u"servidor web próprio (scripts/run_web.py)",
    "registros": RODADAS["20261023_r3"]["registros"].replace("tela_r3", "tela_r4"),
}
RODADAS["20261024_r6"] = {
    "commit": u"2377a5c (CR-021f1 a 021f3: web2py fora do repositório e do pacote) mais o CR-021f4 (documentação e o "
              u"roteiro corrigido), no mesmo commit deste documento",
    "adaptacao": RODADAS["20261024_r2"]["adaptacao"],
    "ressalva": RODADAS["20261024_r2"]["ressalva"],
    "defeitos": [
        (u"Roteiro lia a situação do ticket na página inteira",
         u"dev/homologation/tools/capture_evidence.js",
         u"Na rodada 5 deste dia (evidence_20261024_r5), o filtro pela situação Rodando do CT-06 saiu vazio (282 OK, "
         u"1 falha). O roteiro esperava o ticket longo \"rodando\" procurando a palavra na página inteira do detalhe, "
         u"mas a barra de etapas sempre tem \"Rodando\": o ticket ainda estava na fila quando o filtro rodou (o "
         u"agente o pegou 10 s depois). Defeito antigo do roteiro, que passava porque o agente costumava pegar o "
         u"ticket antes.",
         u"Corrigido: a situação é lida só do selo do visualizador de log ([data-ref=\"badgeLabel\"]). Rodada 6: "
         u"283 OK, 0 falha."),
    ],
    "observacoes": [
        u"Rodada final do CR-021, com o repositório já sem web2py (sem gluon/, web2py.py, anyserver.py e "
        u"routes.py): servidor web próprio (scripts/run_web.py) subido pelo bin/start_local.sh, agente real e Oracle. "
        u"Marca %s." % STAMP,
        u"Antes desta rodada, o pacote sem web2py foi gerado de uma cópia limpa e ensaiado em DEV (CR-021f3): "
        u"subida pelo bin/sss-web.sh, raiz, login, estáticos, cabeçalhos de segurança, origem estranha e parada.",
        u"Cancelamento no agente real: o log não ganha a linha \"processo encerrado por cancelamento (SIGTERM)\", "
        u"que só existia na simulação do FAKE; o motivo aparece no Detalhe técnico (CANCELLED / CANCEL_USER).",
    ],
    "agente": RODADAS["20261024_r4"]["agente"],
    "senhas": RODADAS["20261024_r2"]["senhas"],
    "servidor_web": u"servidor web próprio (scripts/run_web.py), sem web2py no repositório",
    "registros": RODADAS["20261023_r3"]["registros"].replace("tela_r3", "tela_r6"),
}
RODADAS["20261025_r2"] = {
    "commit": u"289247c (CR-022a: aplicação na raiz do repositório, sem web2py/ nem applications/) mais a correção "
              u"do roteiro, no mesmo commit deste documento",
    "adaptacao": RODADAS["20261024_r2"]["adaptacao"],
    "ressalva": RODADAS["20261024_r2"]["ressalva"],
    "defeitos": [
        (u"Roteiro reaproveitava o cadastro dos scripts de diagnóstico com o caminho antigo",
         u"dev/homologation/tools/capture_evidence.js",
         u"Na rodada 1 deste dia (evidence_20261025), os tickets do diag_gerar_saida e do diag_pasta_trabalho "
         u"terminaram em PRECHECK_FAILED (NOT_FOUND), com 275 OK e 8 falhas no CT-26 e no CT-30. Os dois scripts "
         u"foram cadastrados por rodadas anteriores com o caminho da pasta antiga do repositório "
         u"(.../DEV/web2py/applications/...), e o roteiro reativava o cadastro sem conferir o arquivo.",
         u"Corrigido: ao reaproveitar o cadastro, o roteiro grava pela tela o caminho atual do arquivo. Rodada 2: "
         u"283 OK, 0 falha."),
    ],
    "observacoes": [
        u"Rodada do CR-022a, com a aplicação na raiz do repositório e a pasta em "
        u"/portaloptrib/TESHUVA/SSS/DEV/script_scheduling_service: servidor web subido pelo bin/start_local.sh, "
        u"agente pelo bin/sss-scheduler.sh, Oracle. Marca %s." % STAMP,
        u"Antes desta rodada, o link /opt/automacoes/scripts/utilitarios foi refeito para a pasta nova e o pacote "
        u"foi gerado de uma cópia limpa do commit 289247c (só bin/ de produção e as pastas da aplicação).",
        RODADAS["20261024_r6"]["observacoes"][2],
    ],
    "agente": RODADAS["20261024_r4"]["agente"],
    "senhas": RODADAS["20261024_r2"]["senhas"],
    "servidor_web": u"servidor web próprio (scripts/run_web.py), aplicação na raiz do repositório",
    "registros": RODADAS["20261023_r3"]["registros"].replace("tela_r3", "tela_r2"),
}
RODADAS["20261025_r3"] = {
    "commit": u"c8874e9 (CR-022b3: pacote src/sss com as camadas config e core) mais o CR-022b4 (camadas platform e "
              u"persistence em src/sss), no mesmo commit deste documento",
    "adaptacao": RODADAS["20261024_r2"]["adaptacao"],
    "ressalva": RODADAS["20261024_r2"]["ressalva"],
    "defeitos": [],
    "observacoes": [
        u"Rodada do CR-022b4, depois de mover para o pacote src/sss as camadas config, core, platform e "
        u"persistence (conexão Oracle, repositórios Oracle e FAKE, primitivas de sistema operacional e o helper). "
        u"Servidor web pelo bin/start_local.sh, agente pelo bin/sss-scheduler.sh, Oracle. Marca %s." % STAMP,
        u"Antes desta rodada: suíte nas versões 3.6.0, 3.6.8 e 3.13.2 e bateria contra o Oracle real nos três "
        u"drivers; pacote gerado de cópia limpa, sem o FAKE.",
        u"Na primeira passada o navegador de captura (Chrome do Puppeteer) caiu no meio do CT-13 (\"Navigating "
        u"frame was detached\") e os casos seguintes não rodaram (\"Connection closed\"); falha da ferramenta, "
        u"não da aplicação. A execução foi retomada do CT-13 ao encerramento sobre o mesmo state.json, e os "
        u"resultados abaixo são os da retomada.",
        RODADAS["20261024_r6"]["observacoes"][2],
    ],
    "agente": RODADAS["20261024_r4"]["agente"],
    "senhas": RODADAS["20261024_r2"]["senhas"],
    "servidor_web": u"servidor web próprio (scripts/run_web.py), código em src/sss (CR-022b)",
    "registros": RODADAS["20261023_r3"]["registros"],
}
RODADA = RODADAS[RUN_TAG]
ADAPTACAO.update(RODADA["adaptacao"])
RESSALVA = RODADA["ressalva"]
DEFEITOS = RODADA["defeitos"]
OBSERVACOES = RODADA["observacoes"]
# Servidor web da rodada: web2py ate o CR-021e1; depois, o servidor proprio (scripts/run_web.py).
SERVIDOR_WEB = RODADA.get("servidor_web", u"web2py")

def local(iso):
    """ISO em UTC (registro do roteiro) -> 'dd/mm/aaaa hh:mm:ss' no horario desta maquina (o mesmo das telas)."""
    utc = calendar.timegm(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S"))
    return time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(utc))


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def shade(cell, hex_color):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcpr.append(shd)


def set_col_widths(table, widths_cm):
    table.autofit = False
    for row in table.rows:
        for i, w in enumerate(widths_cm):
            row.cells[i].width = Cm(w)


def cell_text(cell, text, bold=False, color=None, size=9):
    cell.text = ""
    p = cell.paragraphs[0]
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color
    return p


def kv_table(doc, rows, widths=(4.2, 12.8)):
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    for k, v in rows:
        r = t.add_row().cells
        cell_text(r[0], k, bold=True)
        shade(r[0], "EFE7F3")
        cell_text(r[1], v)
    set_col_widths(t, widths)
    doc.add_paragraph()
    return t


def add_toc(doc):
    p = doc.add_paragraph()
    run = p.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), 'TOC \\o "1-2" \\h \\z \\u')
    run._r.append(fld)
    doc.add_paragraph(u"Se o sumário aparecer vazio, clique com o botão direito sobre ele e escolha "
                      u"\"Atualizar campo\".").runs[0].italic = True


def resultado_ct(ct_id, r):
    ok = all(c["ok"] for c in r["checks"])
    if not ok:
        return u"Não OK", VERMELHO
    if ct_id in RESSALVA:
        return u"OK com ressalva", AMBAR
    return u"OK", VERDE


def passos_manual():
    """Objetivo e usuarios de cada CT, do texto do manual (all_cts_steps.txt)."""
    txt = io.open(os.path.join(HOMOLOG, "all_cts_steps.txt"), encoding="utf-8").read()
    out = {}
    partes = re.split(r"^=== (CT-\d+\.?) ===$", txt, flags=re.M)
    for i in range(1, len(partes), 2):
        cid, corpo = partes[i], partes[i + 1]
        if cid.endswith("."):
            continue
        linhas = [l.strip() for l in corpo.splitlines() if l.strip()]
        obj = linhas[linhas.index("Objetivo") + 1] if "Objetivo" in linhas else ""
        usr = linhas[linhas.index(u"Usuário(s)") + 1] if u"Usuário(s)" in linhas else ""
        out[cid] = (obj, usr)
    return out


def main():
    res = json.load(io.open(os.path.join(EVID, "results.json"), encoding="utf-8"))
    state = json.load(io.open(os.path.join(EVID, "state.json"), encoding="utf-8"))
    manual = passos_manual()
    ids = [c for c in ORDEM if c in res]
    inicio = min(res[c]["started_at"] for c in ids)
    fim = max(res[c].get("finished_at", res[c]["started_at"]) for c in ids)
    total_chk = sum(len(res[c]["checks"]) for c in ids)
    total_ok = sum(1 for c in ids for k in res[c]["checks"] if k["ok"])
    total_fig = sum(len(res[c]["figures"]) for c in ids)

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    for m in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, m, Cm(2.0))
    st = doc.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10)
    for name in ("Heading 1", "Heading 2", "Heading 3", "Title"):
        doc.styles[name].font.color.rgb = ROXO

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = t.add_run(u"Script Scheduling Service (SSS)")
    r.font.size = Pt(14)
    r.font.color.rgb = ROXO
    doc.add_heading(u"Evidências de Homologação — DEV real (Oracle e agente)", 0)
    doc.add_paragraph(
        u"Execução real dos casos de teste do Manual de Homologação (UI Freeze, versão 2.5) sobre o ambiente DEV: "
        u"banco Oracle, servidor web na porta 18000 e o agente srv-linux-local-01 executando os scripts de verdade. "
        u"Cada caso foi executado no navegador por um roteiro automatizado, que conferiu na própria página o "
        u"resultado esperado e capturou as telas.")
    kv_table(doc, [
        (u"Data da execução", u"%s a %s (horário de Brasília, o mesmo das telas)" % (local(inicio), local(fim)[11:])),
        (u"Ambiente", u"DEV — %s (Python 3.6.15) em http://127.0.0.1:18000, banco Oracle 19c (driver thick)"
         % SERVIDOR_WEB),
        (u"Agente", u"srv-linux-local-01 (Linux), ambientes CLONE2, CLONE1, CLONE6, CLONE7 e GFPREPROD; "
                    u"interpretadores PYTHON3, BASH e SH"),
        (u"Base", u"Manual de Homologação — UI Freeze 2.5 (17/10/2026), adaptado aos dados do DEV"),
        (u"Commit de referência", RODADA["commit"]),
        (u"Execução", u"Roteiro dev/homologation/tools/capture_evidence.js (Chrome headless), %d verificações, "
                      u"%d figuras" % (total_chk, total_fig)),
        (u"Resultado geral", u"%d de %d verificações OK" % (total_ok, total_chk)),
        (u"Responsável pela homologação", u""),
    ])

    doc.add_heading(u"Sumário", 1)
    add_toc(doc)
    doc.add_page_break()

    # 1. Resumo
    doc.add_heading(u"1. Resumo da execução", 1)
    tb = doc.add_table(rows=1, cols=5)
    tb.style = "Table Grid"
    for i, h in enumerate((u"Caso", u"Título", u"Verificações", u"Figuras", u"Resultado")):
        cell_text(tb.rows[0].cells[i], h, bold=True)
        shade(tb.rows[0].cells[i], "4A0A64")
        tb.rows[0].cells[i].paragraphs[0].runs[0].font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    for c in ids:
        r = res[c]
        ok = sum(1 for k in r["checks"] if k["ok"])
        txt, cor = resultado_ct(c, r)
        row = tb.add_row().cells
        cell_text(row[0], c if c.startswith("CT") else u"—")
        cell_text(row[1], r["title"])
        cell_text(row[2], u"%d/%d" % (ok, len(r["checks"])))
        cell_text(row[3], str(len(r["figures"])))
        cell_text(row[4], txt, bold=True, color=cor)
    set_col_widths(tb, (1.6, 9.2, 2.2, 1.6, 2.4))
    doc.add_paragraph()

    # 2. Preparacao
    doc.add_heading(u"2. Preparação do ambiente", 1)
    doc.add_heading(u"2.1 Servidor web e agente", 2)
    for txt in (
            u"Servidor web do DEV iniciado com bin/start_local.sh 18000 (Python 3.6.15), ligado ao Oracle do DEV.",
            RODADA.get("agente", _AGENTE_PADRAO),
            u"Scripts do seed: o cadastro aponta para /opt/automacoes/scripts/utilitarios/, instalado nesta máquina "
            u"como link simbólico para dev/scripts/utilitarios/ do repositório (aceito pelo CR-011).",
            u"Arquivos de entrada reais nas pastas de entrada de cada ambiente e script (CR-014): clientes, notas e "
            u"extrato em texto e um lote de 3 GB de texto para a compactação longa."):
        doc.add_paragraph(txt, style="List Bullet")
    doc.add_heading(u"2.2 Usuários e senhas", 2)
    doc.add_paragraph(
        u"Usuários do seed do DEV: admin (ADMINISTRATOR), op.prod (OPERATOR_PROD), op.hml (OPERATOR_HML) e "
        u"consulta (READ_ONLY), com a senha inicial documentada no DEPLOYMENT.md §5.3. " +
        RODADA.get("senhas", _SENHAS_PADRAO) +
        u" Nenhuma senha aparece neste documento, nas telas capturadas ou no roteiro.")
    doc.add_heading(u"2.3 Massa criada pelas telas", 2)
    m = res.get("MASSA")
    if m:
        doc.add_paragraph(u"Antes do CT-04, cinco tickets reais foram criados pelo assistente de disparo e executados "
                          u"pelo agente:")
        for k in m["checks"]:
            if k["desc"].startswith(u"Ticket"):
                doc.add_paragraph(k["desc"] + (u" — " + k["detail"] if k.get("detail") else u""), style="List Bullet")
    doc.add_heading(u"2.4 Registros mantidos como evidência", 2)
    doc.add_paragraph(
        u"Os registros criados ficam no banco do DEV, identificados pela marca %s: tickets e "
        u"execuções, o ambiente %s_<hhmm> (inativo), o parâmetro sigiloso documento_cliente_hml, o "
        u"parâmetro ct24_valor_<hhmm> e as regras %s_DIARIA_<hhmm> (pausadas no encerramento). "
        % (STAMP, STAMP, STAMP) +
        u"Alterações de cadastro feitas para testar (caminho de script, vínculo de parâmetro, permissão "
        u"MANAGE_USERS do OPERATOR_PROD) foram desfeitas pela tela no próprio caso." + RODADA.get("registros", u"") +
        u" Tudo está na trilha de auditoria.")

    # 3. Defeitos e observacoes
    doc.add_heading(u"3. Defeitos encontrados e corrigidos", 1)
    td = doc.add_table(rows=1, cols=4)
    td.style = "Table Grid"
    for i, h in enumerate((u"Defeito", u"Onde", u"Causa", u"Situação")):
        cell_text(td.rows[0].cells[i], h, bold=True)
        shade(td.rows[0].cells[i], "EFE7F3")
    for d in DEFEITOS:
        row = td.add_row().cells
        for i, v in enumerate(d):
            cell_text(row[i], v)
    set_col_widths(td, (3.6, 4.0, 6.0, 3.4))
    doc.add_paragraph()
    doc.add_heading(u"4. Observações e diferenças em relação ao manual", 1)
    for o in OBSERVACOES:
        doc.add_paragraph(o, style="List Bullet")

    # 5. Casos
    doc.add_page_break()
    doc.add_heading(u"5. Casos de teste executados", 1)
    fig_n = 0
    for c in ids:
        r = res[c]
        doc.add_heading((u"%s — %s" % (c, r["title"])) if c.startswith("CT") else r["title"], 2)
        obj, usr = manual.get(c, (u"", u""))
        linhas = []
        if obj:
            linhas.append((u"Objetivo", obj))
        if usr:
            linhas.append((u"Usuário(s)", usr))
        if c in ADAPTACAO:
            linhas.append((u"Adaptação ao DEV", ADAPTACAO[c]))
        linhas.append((u"Executado em", local(r["started_at"])))
        if linhas:
            kv_table(doc, linhas)
        doc.add_heading(u"Verificações executadas", 3)
        tv = doc.add_table(rows=1, cols=4)
        tv.style = "Table Grid"
        for i, h in enumerate((u"#", u"Verificação (resultado esperado)", u"Obtido", u"Resultado")):
            cell_text(tv.rows[0].cells[i], h, bold=True)
            shade(tv.rows[0].cells[i], "EFE7F3")
        for n, k in enumerate(r["checks"], 1):
            row = tv.add_row().cells
            cell_text(row[0], str(n))
            cell_text(row[1], k["desc"])
            cell_text(row[2], k.get("detail", u""), size=8)
            cell_text(row[3], u"OK" if k["ok"] else u"Não OK", bold=True, color=VERDE if k["ok"] else VERMELHO)
        set_col_widths(tv, (0.8, 8.0, 6.2, 2.0))
        if r["notes"]:
            doc.add_heading(u"Observações", 3)
            for n in r["notes"]:
                doc.add_paragraph(n, style="List Bullet")
        if r["figures"]:
            doc.add_heading(u"Telas", 3)
        for f in r["figures"]:
            fig_n += 1
            path = os.path.join(EVID, f["file"])
            w, h = png_size(path)
            largura = 16.5
            altura = largura * h / float(w)
            if altura > 21.5:
                largura = 21.5 * w / float(h)
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(path, width=Cm(largura))
            cap = doc.add_paragraph()
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            rr = cap.add_run(u"Figura %d — %s" % (fig_n, f["caption"]))
            rr.italic = True
            rr.font.size = Pt(9)
            u = cap.add_run(u"  (%s)" % f["url"])
            u.font.size = Pt(8)
            u.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        doc.add_heading(u"Registro", 3)
        txt, cor = resultado_ct(c, r)
        reg = [(u"Resultado", txt)]
        if c in RESSALVA:
            reg.append((u"Ressalva", RESSALVA[c]))
        reg.append((u"Executado por", u"Roteiro automatizado capture_evidence.js, em %s" % DATE_BR))
        reg.append((u"Conferido por / data", u""))
        tr = kv_table(doc, reg)
        tr.rows[0].cells[1].paragraphs[0].runs[0].bold = True
        tr.rows[0].cells[1].paragraphs[0].runs[0].font.color.rgb = cor

    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    doc.save(SAIDA)
    resumo_md(res, ids, inicio, fim, total_ok, total_chk, fig_n)
    print("gerado:", SAIDA, "| casos:", len(ids), "| verificacoes:", total_ok, "/", total_chk, "| figuras:", fig_n)


def resumo_md(res, ids, inicio, fim, total_ok, total_chk, total_fig):
    """Resumo em Markdown ao lado do .docx (como o registro do UI Freeze de 18/10)."""
    nao_ok = [(c, k) for c in ids for k in res[c]["checks"] if not k["ok"]]
    linhas = [
        u"# Homologação no DEV real: Registro de Evidências", u"",
        u"**Data:** %s a %s (horário de Brasília)" % (local(inicio), local(fim)[11:]), u"",
        u"**Ambiente:** DEV, banco Oracle, %s em `127.0.0.1:18000`, agente `srv-linux-local-01`" % SERVIDOR_WEB,
        u"**Resultado geral:** %d de %d verificações OK; %d figuras." % (total_ok, total_chk, total_fig), u"",
        u"Documento completo, com as telas: `%s` (mesma pasta). "
        u"Gerado por `dev/homologation/tools/capture_evidence.js` e `build_evidence_docx.py`; o resultado bruto "
        u"de cada verificação está em `dev/homologation/evidence_%s/results.json`. Nenhuma senha foi "
        u"registrada." % (os.path.basename(SAIDA), RUN_TAG), u"",
        u"## Resultado por caso", u"",
        u"| Caso | Título | Verificações | Figuras | Resultado |", u"|---|---|---|---|---|",
    ]
    for c in ids:
        r = res[c]
        txt, _cor = resultado_ct(c, r)
        linhas.append(u"| %s | %s | %d/%d | %d | %s |" % (c if c.startswith("CT") else u"—", r["title"],
                      sum(1 for k in r["checks"] if k["ok"]), len(r["checks"]), len(r["figures"]), txt))
    linhas += [u"", u"## Defeitos encontrados e corrigidos", u""]
    for d in DEFEITOS:
        linhas.append(u"- **%s** (`%s`): %s %s" % d)
    if not DEFEITOS:
        linhas.append(u"Nenhum.")
    linhas += [u"", u"## Observações e diferenças em relação ao manual", u""]
    linhas += [u"- " + o for o in OBSERVACOES]
    linhas += [u"", u"## Ressalvas", u""]
    linhas += [u"- **%s:** %s" % (c, t) for c, t in sorted(RESSALVA.items())]
    linhas += [u"", u"## Verificações que não passaram", u""]
    linhas += ([u"- %s: %s (%s)" % (c, k["desc"], k.get("detail", u"")) for c, k in nao_ok] or [u"Nenhuma."])
    md = os.path.join(os.path.dirname(SAIDA), "SSS_HOMOLOGATION_EVIDENCE_%s%s.md" % (DATE_ISO, SUFFIX))
    io.open(md, "w", encoding="utf-8").write(u"\n".join(linhas) + u"\n")
    print("gerado:", md)


if __name__ == "__main__":
    main()
