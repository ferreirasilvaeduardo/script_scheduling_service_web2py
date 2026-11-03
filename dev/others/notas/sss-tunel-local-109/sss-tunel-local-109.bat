@echo off
setlocal enabledelayedexpansion

:: ==============================================================================
:: GERENCIADOR DE TÚNEL SSH (CLONE 7 -> SSS) PARA CMD DO WINDOWS
:: ==============================================================================
:: Uso:
::   sss-tunel-local-109.bat start   (Inicia a conexão SSH com portas 18000 e 18001)
::   sss-tunel-local-109.bat status  (Verifica se o ssh.exe está rodando e testa as portas)
::   sss-tunel-local-109.bat stop    (Encerra os processos do túnel SSH)
:: ==============================================================================

set SERVER=mastersafgf@10.238.10.109
set CMD_ACTION=%1
if "%CMD_ACTION%"=="" set CMD_ACTION=status

if /I "%CMD_ACTION%"=="start" goto :do_start
if /I "%CMD_ACTION%"=="stop" goto :do_stop
if /I "%CMD_ACTION%"=="status" goto :do_status

echo Uso: %0 [start ^| stop ^| status]
goto :eof

:: ------------------------------------------------------------------------------
:do_start
:: ------------------------------------------------------------------------------
tasklist /FI "IMAGENAME eq ssh.exe" 2>NUL | find /I "ssh.exe" >NUL
if "%ERRORLEVEL%"=="0" (
    echo [AVISO] O processo ssh.exe ja esta ativo.
    goto :do_status
)

echo [INFO] Iniciando tunel SSH para %SERVER%...
:: Inicia o ssh.exe mantendo a compatibilidade com o OpenSSH 5.3 da clone 7
start "Tunel-SSH-Clone7" ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedAlgorithms=+ssh-rsa -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -L 18000:127.0.0.1:18000 -L 18001:127.0.0.1:18001 %SERVER%

echo [INFO] Aguardando 3 segundos para estabilizar a conexao...
timeout /t 3 /nobreak >NUL
goto :do_status

:: ------------------------------------------------------------------------------
:do_stop
:: ------------------------------------------------------------------------------
echo [INFO] Encerrando processos ssh.exe...
taskkill /F /IM ssh.exe >NUL 2>&1
if "%ERRORLEVEL%"=="0" (
    echo [SUCESSO] Tunel finalizado.
) else (
    echo [AVISO] Nenhum processo ssh.exe ativo encontrado.
)
goto :eof

:: ------------------------------------------------------------------------------
:do_status
:: ------------------------------------------------------------------------------
echo ===================================================
tasklist /FI "IMAGENAME eq ssh.exe" 2>NUL | find /I "ssh.exe" >NUL
if "%ERRORLEVEL%"=="0" (
    echo Processo: ATIVO (ssh.exe rodando)
) else (
    echo Processo: FORA DO AR
)

:: Checagem de portas via curl nativo do Windows (disponivel no Win 10/11)
echo ---------------------------------------------------
for %%P in (18000 18001) do (
    set "CODE="
    for /f "delims=" %%C in ('curl -s -o NUL -m 2 -w "%%{http_code}" "http://127.0.0.1:%%P/script_scheduling_service/default/login" 2^>NUL') do set CODE=%%C
    if "!CODE!"=="" (
        echo Porta %%P : Sem resposta
    ) else (
        echo Porta %%P : Conectada (HTTP !CODE!)
    )
)
echo ===================================================
goto :eof