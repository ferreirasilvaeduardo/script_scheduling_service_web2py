# Tunel do navegador ate o web do SSS no 3067 (DEPLOYMENT-SERVER, passo 13), em segundo plano, no Windows.
# Versao PowerShell do sss-tunel-3067.sh: usa o cliente OpenSSH do Windows 10/11 (ssh.exe).
# Duas pernas: este computador -> bastion (porta + 10000) -> 3067 (127.0.0.1:porta). So com chave (BatchMode):
# em segundo plano nao ha onde digitar senha. Se a conexao cair, reabre em 10 s.
#
# Uso (PowerShell):  .\sss-tunel-3067.ps1 start | stop | status
# Se a politica de execucao bloquear:  powershell -ExecutionPolicy Bypass -File .\sss-tunel-3067.ps1 start
# Navegador: http://127.0.0.1:18000/ (DEV) e http://127.0.0.1:18001/ (PROD).
param([Parameter(Position = 0)][string]$Acao = "")

$Bastion = "mastersafgf@10.238.10.109"
$Destino = "mastersafgf@10.129.164.55"
$Portas = @(18000, 18001)          # portas do web no 3067 (DEV e PROD); as mesmas neste computador
$Deslocamento = 10000              # porta intermediaria no bastion: porta + 10000 (28000, 28001)
$Dir = Join-Path $env:USERPROFILE ".sss_tunel"
$PidFile = Join-Path $Dir "tunel.pid"
$Log = Join-Path $Dir "tunel.log"

# PubkeyAcceptedKeyTypes (nome antigo de PubkeyAcceptedAlgorithms): aceito pelos OpenSSH 8.x e 9.x do Windows.
$SshOpts = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=30",
             "-o", "ServerAliveCountMax=3", "-o", "ExitOnForwardFailure=yes",
             "-o", "HostKeyAlgorithms=+ssh-rsa", "-o", "PubkeyAcceptedKeyTypes=+ssh-rsa")

function Test-Rodando {
    if (-not (Test-Path $PidFile)) { return $false }
    $id = Get-Content $PidFile -ErrorAction SilentlyContinue
    return [bool]($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue))
}

function Write-Log([string]$Texto) {
    Add-Content -Path $Log -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Texto)
}

function Start-Laco {
    $local = @(); $remoto = ""
    foreach ($p in $Portas) {
        $local += @("-L", ("127.0.0.1:{0}:127.0.0.1:{1}" -f $p, ($p + $Deslocamento)))
        $remoto += (" -L 127.0.0.1:{0}:127.0.0.1:{1}" -f ($p + $Deslocamento), $p)
    }
    $interno = "ssh -o BatchMode=yes -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -N$remoto $Destino"
    while ($true) {
        Write-Log ("abrindo o tunel ({0})" -f ($Portas -join " "))
        # -tt: o ssh do bastion recebe SIGHUP quando esta conexao cai e libera as portas intermediarias.
        & ssh.exe -tt @SshOpts @local $Bastion $interno *>> $Log
        Write-Log ("tunel caiu (codigo {0}); nova tentativa em 10 s" -f $LASTEXITCODE)
        Start-Sleep -Seconds 10
    }
}

function Show-Status {
    if (Test-Rodando) { "laco no ar (pid {0}); log: {1}" -f (Get-Content $PidFile), $Log } else { "fora do ar" }
    foreach ($p in $Portas) {
        $url = "http://127.0.0.1:$p/script_scheduling_service/default/login"
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10 -MaximumRedirection 0
            "porta {0}: HTTP {1}" -f $p, $r.StatusCode
        } catch {
            $code = $_.Exception.Response.StatusCode.value__
            if ($code) { "porta {0}: HTTP {1}" -f $p, $code } else { "porta {0}: sem resposta" -f $p }
        }
    }
}

switch ($Acao) {
    "start" {
        if (Test-Rodando) { "ja no ar (pid {0})" -f (Get-Content $PidFile); exit 0 }
        if (-not (Get-Command ssh.exe -ErrorAction SilentlyContinue)) {
            "ssh.exe nao encontrado: instale o Cliente OpenSSH (Configuracoes > Aplicativos > Recursos opcionais)"
            exit 2
        }
        New-Item -ItemType Directory -Force -Path $Dir | Out-Null
        # Processo proprio, sem janela, que sobrevive ao fechamento deste PowerShell.
        $proc = Start-Process -FilePath "powershell.exe" -WindowStyle Hidden -PassThru -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "_laco")
        Set-Content -Path $PidFile -Value $proc.Id
        Start-Sleep -Seconds 6
        Show-Status
    }
    "stop" {
        if (-not (Test-Rodando)) { "fora do ar"; Remove-Item $PidFile -ErrorAction SilentlyContinue; exit 0 }
        $id = [int](Get-Content $PidFile)
        # O laco e os ssh.exe filhos dele.
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" | ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        "tunel parado"
    }
    "status" { Show-Status }
    "_laco" { Start-Laco }
    default { "uso: .\sss-tunel-3067.ps1 start | stop | status"; exit 2 }
}
