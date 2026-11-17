#!/usr/bin/env bash
# Publica a pasta base/ (a base em arquivos, que Clientes novos lê no lugar do banco):
#   releases arq-UF (os arquivos por atividade + base-UF.json) e, no fim, o release arq (cn-NN.bin + base.json).
# Mesmo cuidado do publicar_perto.sh: só sobe o que mudou e espera quando o limite de chamadas do GitHub está no fim.
# Rodar de novo depois de uma falha continua de onde parou.
set -euo pipefail
REPO="${REPO:?}"; MES="${1:-}"; SO_UFS="${2:-}"

respirar() {
  local resta reset agora
  resta=$(gh api rate_limit --jq '.resources.core.remaining' 2>/dev/null || echo 500)
  if [ "$resta" -lt "${1:-80}" ]; then
    reset=$(gh api rate_limit --jq '.resources.core.reset' 2>/dev/null || echo 0); agora=$(date +%s)
    local espera=$(( reset > agora ? reset - agora + 10 : 60 ))
    echo "::notice::limite de chamadas do GitHub quase no fim (restam $resta): esperando $(( espera / 60 )) min"
    sleep "$espera"
  fi
}

# publicar TAG TITULO NOTAS INDICE(local) CHAVE_DOS_ARQUIVOS(no json)
publicar() {
  local TAG="$1" TIT="$2" NOTAS="$3" IDX="$4" CHAVE="$5"
  respirar 60
  gh release view "$TAG" -R "$REPO" >/dev/null 2>&1 || gh release create "$TAG" -R "$REPO" --latest=false --title "$TIT" --notes "$NOTAS"
  gh release view "$TAG" -R "$REPO" --json assets --jq '.assets[] | [.name, .size] | @tsv' > la.tsv || : > la.tsv
  curl -sSL --fail -o velho.json "https://github.com/$REPO/releases/download/$TAG/$(basename "$IDX")" 2>/dev/null || echo '{}' > velho.json
  python3 - "$IDX" "$CHAVE" <<'PY'
import json, os, sys
idx = json.load(open(sys.argv[1])); chave = sys.argv[2]
try: velho = json.load(open('velho.json'))
except Exception: velho = {}
hv = {f['a']: f.get('h') for f in (velho.get(chave) or {}).values()}
la = {}
for l in open('la.tsv'):
    p = l.rstrip('\n').split('\t')
    if len(p) == 2 and p[1].isdigit(): la[p[0]] = int(p[1])
todos = list(idx[chave].values())
subir = ['base/' + f['a'] for f in todos if not (f['a'] in la and la[f['a']] == f['bytes'] and hv.get(f['a']) == f['h'])]
open('subir.txt', 'w').write('\n'.join(subir) + ('\n' if subir else ''))
fica = {f['a'] for f in todos} | {os.path.basename(sys.argv[1])}
open('sobra.txt', 'w').write('\n'.join(sorted(a for a in la if a not in fica)) + '\n')
print('%s: %d arquivos, %d para subir, %d já estavam iguais' % (os.path.basename(sys.argv[1]), len(todos), len(subir), len(todos) - len(subir)))
PY
  # Primeiro os arquivos, por último o índice: o sistema nunca vê um índice apontando para arquivo que ainda não subiu.
  while mapfile -t -n 25 LOTE && [ "${#LOTE[@]}" -gt 0 ]; do
    respirar 60
    gh release upload "$TAG" -R "$REPO" --clobber "${LOTE[@]}"
  done < subir.txt
  respirar 20
  gh release upload "$TAG" -R "$REPO" --clobber "$IDX"
  while read -r a; do [ -n "$a" ] || continue; respirar 20; gh release delete-asset "$TAG" "$a" -R "$REPO" -y || true; done < sobra.txt
  echo "::notice::publicado $TAG ($(wc -l < subir.txt) enviados)"
}

for IDX in base/base-??.json; do
  UF=$(basename "$IDX" .json); UF=${UF#base-}
  publicar "arq-$UF" "Base em arquivos · $UF" "Empresas de $UF por atividade, para a tela Clientes novos da AMELIE. Gerado automaticamente (dados abertos da Receita Federal + CNEFE/IBGE). Sem MEI e sem quem pediu para não ser contatado." "$IDX" arquivos
done

# O geral (CNPJ em ordem + manifesto) só sobe quando todos os estados subiram.
if [ -z "$SO_UFS" ] && [ -f base/base.json ]; then
  publicar arq "Base em arquivos" "Manifesto e índice de CNPJ da base em arquivos (arq-UF)." base/base.json cn
  echo "::notice::base.json publicado ($MES)"
fi
