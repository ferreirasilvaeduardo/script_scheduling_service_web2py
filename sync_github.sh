#!/usr/bin/env bash
# ==============================================================================
# Script: sync_github.sh
# Objetivo: Alinhar o Git ao .gitignore e espelhar exatamente no GitHub
# ==============================================================================

set -e  # Interrompe a execução imediatamente em caso de erro

# 1. Valida se o diretório atual é um repositório Git
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "[-] Erro: Este diretório não é um repositório Git válido."
    exit 1
fi

# 2. Identifica a branch ativa
CURRENT_BRANCH=$(git branch --show-current)

if [ -z "$CURRENT_BRANCH" ]; then
    echo "[-] Erro: Não foi possível identificar a branch atual (HEAD desanexado?)."
    exit 1
fi

echo "[+] Branch detectada: $CURRENT_BRANCH"

# 3. Limpa o cache do Git (mantém arquivos físicos intactos)
echo "[+] Removendo arquivos rastreados do índice local..."
git rm -r --cached . >/dev/null 2>&1 || true

# 4. Re-adiciona tudo respeitando o .gitignore atualizado
echo "[+] Reindexando arquivos com base no .gitignore..."
git add .

# 5. Verifica se há alterações para commitar
if git diff-index --quiet HEAD --; then
    echo "[!] Nenhuma alteração detectada no índice em relação ao último commit."
else
    echo "[+] Criando commit de alinhamento..."
    git commit -m "chore: alinha gitignore e limpa arquivos rastreados"
fi

# 6. Push com lease de segurança para o GitHub
echo "[+] Espelhando branch '$CURRENT_BRANCH' no GitHub (origin)..."
git push origin "$CURRENT_BRANCH" --force-with-lease

echo ""
echo "[✓] Sincronização concluída com sucesso! Estado final do repositório:"
git status -s