# ==============================================================================
# SCRIPT DE GERENCIAMENTO DO TÚNEL SSH (CLONE 7 -> SSS)
# ==============================================================================
#
# INFORMAÇÕES SOBRE EXECUÇÃO E POLÍTICA DE SEGURANÇA (SOLUÇÃO 1):
# ------------------------------------------------------------------------------
# Se surgir o erro de "arquivo não assinado digitalmente" (ExecutionPolicy) ou
# restrição de execução via rede UNC (\\wsl.localhost\...), execute o script
# invocando o PowerShell com o parâmetro "-ExecutionPolicy Bypass":
#
# Exemplos de uso prático (Solução 1):
#   powershell -ExecutionPolicy Bypass -File .\sss-tunel-local-109_v2.ps1 start
#   powershell -ExecutionPolicy Bypass -File .\sss-tunel-local-109_v2.ps1 status
#   powershell -ExecutionPolicy Bypass -File .\sss-tunel-local-109_v2.ps1 stop
#
# Vantagens da Solução 1:
#   - Não necessita de privilégios de Administrador no Windows.
#   - Não modifica permanentemente as políticas globais do sistema operativo.
#   - Aplica a permissão temporária unicamente para a chamada atual.
#
# Formas de uso normais (caso a política da sessão já esteja desbloqueada):
#   .\sss-tunel-local-109_v2.ps1 start
#   .\sss-tunel-local-109_v2.ps1 status
#   .\sss-tunel-local-109_v2.ps1 stop
# ==============================================================================

param (
    # Valida a ação informada; assume 'status' por omissão caso nada seja especificado
    [ValidateSet("start", "stop", "status")]
    [string]$Acao = "status"
)

# ------------------------------------------------------------------------------
# Parâmetros de Ligação e Portas
# ------------------------------------------------------------------------------
$Server = "mastersafgf@10.238.10.109"           # Endereço da clone 7
$PidFile = "$HOME\.sss-tunel-local-109_v2.pid"  # Ficheiro temporário que armazena o PID do processo
$Portas = @(18000, 18001)                      # 18000 = DEV, 18001 = PROD

# ------------------------------------------------------------------------------
# Função Auxiliar: Verificar se o processo SSH do túnel permanece ativo
# ------------------------------------------------------------------------------
function Obter-Processo {
    if (Test-Path $PidFile) {
        $pId = Get-Content $PidFile -ErrorAction SilentlyContinue
        if ($pId) {
            # Tenta obter o processo ativo através do PID registado no ficheiro
            return Get-Process -Id $pId -ErrorAction SilentlyContinue
        }
    }
    return $null
}

# ------------------------------------------------------------------------------
# Gestão das Ações
# ------------------------------------------------------------------------------
switch ($Acao) {
    "start" {
        $proc = Obter-Processo
        if ($proc) {
            Write-Host "O túnel já se encontra ativo (PID: $($proc.Id))." -ForegroundColor Yellow
            return
        }

        # Parâmetros de compatibilidade do SSH para suporte ao OpenSSH 5.3 legado da clone 7
        $sshArgs = @(
            "-o", "HostKeyAlgorithms=+ssh-rsa",
            "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
            "-o", "ServerAliveInterval=30",
            "-o", "ExitOnForwardFailure=yes",
            "-L", "18000:127.0.0.1:18000",
            "-L", "18001:127.0.0.1:18001",
            $Server
        )

        # Inicia o SSH numa janela própria de modo a viabilizar a inserção de credenciais
        $novoProc = Start-Process -FilePath "ssh" -ArgumentList $sshArgs -PassThru
        $novoProc.Id | Out-File -FilePath $PidFile -Encoding ascii -Force

        Write-Host "A iniciar o túnel (PID: $($novoProc.Id))..." -ForegroundColor Cyan
        Start-Sleep -Seconds 3

        # Valida o estado imediatamente após a inicialização
        & $MyInvocation.MyCommand.Path status
    }

    "stop" {
        $proc = Obter-Processo
        if ($proc) {
            Stop-Process -Id $proc.Id -Force
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
            Write-Host "Túnel terminado com sucesso." -ForegroundColor Green
        } else {
            # Caso o processo tenha ficado órfão ou o ficheiro de PID tenha sido eliminado
            Get-Process ssh -ErrorAction SilentlyContinue | Stop-Process -Force
            Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
            Write-Host "Nenhum túnel ativo encontrado (processos ssh residuais limpos)." -ForegroundColor Yellow
        }
    }

    "status" {
        $proc = Obter-Processo
        if ($proc) {
            Write-Host "Estado do Processo: ATIVO (PID: $($proc.Id))" -ForegroundColor Green
        } else {
            Write-Host "Estado do Processo: FORA DO AR" -ForegroundColor Red
        }

        # Verificação do estado das portas locais mapeadas
        foreach ($p in $Portas) {
            try {
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$p/script_scheduling_service/default/login" -TimeoutSec 2 -UseBasicParsing
                Write-Host "Porta $p : Conectada (HTTP $($resp.StatusCode))" -ForegroundColor Cyan
            } catch {
                Write-Host "Porta $p : Sem resposta" -ForegroundColor DarkGray
            }
        }
    }
}