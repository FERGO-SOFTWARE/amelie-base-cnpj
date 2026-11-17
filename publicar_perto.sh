#!/usr/bin/env bash
# Publica a pasta perto/ nos releases perto-UF e, no fim, o manifesto no release perto.
# O GitHub aceita 1.000 chamadas por hora neste tipo de acesso e o Brasil inteiro tem ~2.600 pedaços:
#  - só sobe o pedaço que mudou (compara com o índice já publicado e com o tamanho do arquivo que já está lá);
#  - antes de cada lote confere quantas chamadas restam; se estiver no fim, espera a hora virar.
# Rodar de novo depois de uma falha continua de onde parou.
set -euo pipefail
REPO="${REPO:?}"; MES="${1:-}"; SO_UFS="${2:-}"

respirar() {   # espera quando restam poucas chamadas nesta hora
  local resta reset agora
  resta=$(gh api rate_limit --jq '.resources.core.remaining' 2>/dev/null || echo 500)
  if [ "$resta" -lt "${1:-80}" ]; then
    reset=$(gh api rate_limit --jq '.resources.core.reset' 2>/dev/null || echo 0); agora=$(date +%s)
    local espera=$(( reset > agora ? reset - agora + 10 : 60 ))
    echo "::notice::limite de chamadas do GitHub quase no fim (restam $resta): esperando $(( espera / 60 )) min"
    sleep "$espera"
  fi
}

for IDX in perto/indice-*.json; do
  UF=$(basename "$IDX" .json); UF=${UF#indice-}; TAG="perto-$UF"
  respirar 60
  gh release view "$TAG" -R "$REPO" >/dev/null 2>&1 || gh release create "$TAG" -R "$REPO" --latest=false --title "Perto de você · $UF" --notes "Empresas de $UF com coordenada, em pedaços do mapa. Gerado automaticamente (Receita Federal + CNEFE/IBGE). Sem telefone e sem e-mail."
  gh release view "$TAG" -R "$REPO" --json assets --jq '.assets[] | [.name, .size] | @tsv' > la.tsv || : > la.tsv
  curl -sSL --fail -o velho.json "https://github.com/$REPO/releases/download/$TAG/indice-$UF.json" 2>/dev/null || echo '{}' > velho.json
  python3 - "$IDX" "$UF" <<'PY'
import json, os, sys
idx = json.load(open(sys.argv[1])); uf = sys.argv[2]
try: velho = json.load(open('velho.json'))
except Exception: velho = {}
hv = {f['a']: f.get('h') for f in velho.get('folhas', [])}
if velho.get('novos'): hv[velho['novos']['a']] = velho['novos'].get('h')
la = {}
for l in open('la.tsv'):
    p = l.rstrip('\n').split('\t')
    if len(p) == 2 and p[1].isdigit(): la[p[0]] = int(p[1])
todos = idx['folhas'] + [idx['novos']]
subir = []
for f in todos:
    igual = f['a'] in la and la[f['a']] == f['bytes'] and (hv.get(f['a']) in (None, f['h']))
    if not igual: subir.append('perto/' + f['a'])
open('subir.txt', 'w').write('\n'.join(subir) + ('\n' if subir else ''))
fica = {f['a'] for f in todos} | {'indice-%s.json' % uf}
open('sobra.txt', 'w').write('\n'.join(sorted(a for a in la if a not in fica)) + '\n')
print('%s: %d arquivos, %d para subir, %d já estavam iguais' % (uf, len(todos), len(subir), len(todos) - len(subir)))
PY
  # Primeiro os pedaços, por último o índice: o sistema nunca vê um índice apontando para pedaço que ainda não subiu.
  while mapfile -t -n 25 LOTE && [ "${#LOTE[@]}" -gt 0 ]; do
    respirar 60
    gh release upload "$TAG" -R "$REPO" --clobber "${LOTE[@]}"
  done < subir.txt
  respirar 20
  gh release upload "$TAG" -R "$REPO" --clobber "$IDX"
  while read -r a; do [ -n "$a" ] || continue; respirar 20; gh release delete-asset "$TAG" "$a" -R "$REPO" -y || true; done < sobra.txt
  echo "::notice::publicado $TAG ($(wc -l < subir.txt) enviados)"
done

# O manifesto geral só sobe quando todos os estados subiram. Geração de alguns estados não troca o geral.
if [ -z "$SO_UFS" ]; then
  respirar 20
  gh release view perto -R "$REPO" >/dev/null 2>&1 || gh release create perto -R "$REPO" --latest=false --title "Perto de você" --notes "Manifesto dos pedaços por estado (perto-UF)."
  gh release upload perto -R "$REPO" --clobber perto/perto.json
  echo "::notice::perto.json publicado ($MES)"
fi
