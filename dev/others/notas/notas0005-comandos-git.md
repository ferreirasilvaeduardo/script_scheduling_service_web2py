O comando padrão para enviar as suas alterações locais para o repositório remoto é:

```bash
git push

```

Para garantir que o envio ocorra sem erros, o fluxo completo e os cenários mais comuns funcionam da seguinte forma:

---

### 1. Fluxo padrão (Commit e Push)

Antes de enviar, certifique-se de que os arquivos foram adicionados e commitados:

```bash
# 1. Verifica os arquivos alterados
git status

# 2. Adiciona as alterações para a área de stage (incluindo o .gitignore)
git add .

# 3. Cria o commit local
git commit -m "chore: atualiza regras do gitignore"

# 4. Envia para o repositório remoto
git push

```

---

### 2. Primeiro push da branch (upstream)

Se a branch local for nova e ainda não existir no repositório remoto, o Git solicitará a vinculação com o parâmetro `-u` (ou `--set-upstream`):

```bash
# Exemplo para a branch main
git push -u origin main

# Ou para a branch master
git push -u origin master

# Se estiver em uma branch de feature/desenvolvimento
git push -u origin nome-da-sua-branch

```

*Nas próximas vezes que estiver nessa mesma branch, basta executar apenas `git push`.*

---

### 3. Principais erros e como resolver

* **Erro de autenticação (`Authentication failed`)**:
* **HTTPS (GitHub/GitLab)**: Não aceita a senha comum da conta. É necessário utilizar um **Personal Access Token (PAT)** ou autenticar via GitHub CLI (`gh auth login`).
* **SSH**: Verifique se a sua chave pública está vinculada ao repositório executando `ssh -T git@github.com`.


* **Erro de conflito (`[rejected - non-fast-forward]`)**:
* Significa que há commits no servidor remoto que você ainda não tem localmente. Puxe as atualizações antes de enviar:
```bash
git pull --rebase
git push

```




* **Descobrir o nome da branch e do remoto atual**:
```bash
# Mostra a branch atual
git branch --show-current

# Mostra a URL remota configurada
git remote -v

```