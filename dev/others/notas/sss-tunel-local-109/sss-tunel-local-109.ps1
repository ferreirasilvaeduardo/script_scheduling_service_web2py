# ==============================================================================
# SCRIPT DE TUNELAMENTO SSH LOCAL -> CLONE 7 (10.238.10.109)
# ==============================================================================
# Pré-requisito de execução no PowerShell (caso bloqueado por assinatura digital):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
#
# Finalidade:
#   Cria e gerencia um túnel SSH em segundo plano da máquina local (Windows) para
#   o servidor intermediário (clone 7), permitindo acessar a interface web do SSS:
#     - DEV:  http://127.0.0.1:18000/script_scheduling_service/default/login[cite: 1, 2]
#     - PROD: http://127.0.0.1:18001/script_scheduling_service/default/login[cite: 1, 2]
#
# Formas de uso:
#   .\sss-tunel-local-109.ps1 -Action start   # Inicia o túnel oculto[cite: 1, 2]
#   .\sss-tunel-local-109.ps1 -Action status  # Verifica se o processo e as portas respondem[cite: 1, 2]
#   .\sss-tunel-local-109.ps1 -Action stop    # Finaliza os processos SSH ativos deste túnel[cite: 1, 2]
# ==============================================================================

param (
    # Valida o parâmetro passado na linha de comando; valor padrão é 'status'[cite: 1, 2]
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "status"
)

# ------------------------------------------------------------------------------
# Configurações de Conexão e Portas
# ------------------------------------------------------------------------------
# Host remoto de destino do túnel SSH[cite: 1, 2]
$Server = "mastersafgf@10.238.10.109"

# Portas locais mapeadas 1:1 para as portas da clone 7[cite: 1, 2]
# 18000 = Ambiente DEV / 18001 = Ambiente PROD
$Ports = @(18000, 18001)

# ------------------------------------------------------------------------------
# Função Auxiliar: Verificar se o túnel já está rodando
# ------------------------------------------------------------------------------
function Check-Tunnel {
    # Consulta a classe Win32_Process via WMI/CIM para inspecionar os processos ssh.exe
    # Permite ler o campo 'CommandLine' mesmo sem executar o terminal como Administrador
    Get-CimInstance Win32_Process -Filter "Name = 'ssh.exe'" -ErrorAction SilentlyContinue | 
        Where-Object { $_.CommandLine -like "*$Server*" }
}

# ------------------------------------------------------------------------------
# Fluxo Principal por Ação
# ------------------------------------------------------------------------------
switch ($Action) {
    "start" {
        # 1. Checa se o processo do túnel já existe para evitar instâncias duplicadas
        $running = Check-Tunnel
        if ($running) {
            Write-Host "Tunel ja esta em execucao (PID: $($running.ProcessId))" -ForegroundColor Yellow
            return
        }

        # 2. Configura as diretivas de segurança e conectividade do cliente SSH:
        $fwdArgs = @(
                    "-N", 
                    "-o", "BatchMode=yes", 
                    "-o", "ExitOnForwardFailure=yes", 
                    "-o", "ServerAliveInterval=30",
                    "-o", "HostKeyAlgorithms=+ssh-rsa",
                    "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa"
        )
        # 3. Adiciona os redirecionamentos locais (-L 127.0.0.1:porta:127.0.0.1:porta)
        #    Uso de delimitador ${p} para evitar colisão sintática com o interpretador PowerShell
        foreach ($p in $Ports) {
            $fwdArgs += @("-L", "127.0.0.1:${p}:127.0.0.1:${p}")
        }
        $fwdArgs += $Server

        # 4. Dispara o ssh.exe de forma oculta (-WindowStyle Hidden) em segundo plano
        Start-Process -FilePath "ssh" -ArgumentList $fwdArgs -WindowStyle Hidden
        
        # Aguarda 2 segundos para o processo se estabilizar antes de verificar o status
        Start-Sleep -Seconds 2
        
        # Chama a ação de status automaticamente após subir o processo
        & $MyInvocation.MyCommand.Path status
    }

    "stop" {
        # Localiza o processo SSH associado a este host e encerra forçadamente
        $running = Check-Tunnel
        if ($running) {
            $running | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
            Write-Host "Tunel finalizado." -ForegroundColor Green
        } else {
            Write-Host "Nenhum tunel ativo encontrado." -ForegroundColor Yellow
        }
    }

    "status" {
        # 1. Validação de processo no sistema operacional
        $running = Check-Tunnel
        if ($running) {
            Write-Host "Tunel ATIVO (PID: $($running.ProcessId))" -ForegroundColor Green
        } else {
            Write-Host "Tunel FORA DO AR" -ForegroundColor Red
        }

        # 2. Teste real de conectividade HTTP em cada porta mapeada
        foreach ($p in $Ports) {
            try {
                # Tenta efetuar uma requisição HTTP básica com timeout curto (3s)
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:${p}/script_scheduling_service/default/login" -TimeoutSec 3 -UseBasicParsing
                Write-Host "Porta ${p}: HTTP $($resp.StatusCode)" -ForegroundColor Cyan
            } catch {
                # Se a porta estiver fechada ou o serviço remoto não responder
                Write-Host "Porta ${p}: sem resposta" -ForegroundColor DarkGray
            }
        }
    }
}