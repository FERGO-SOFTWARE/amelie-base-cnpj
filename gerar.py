#!/usr/bin/env python3
"""
AMELIE · Base de CNPJ pronta, gerada fora da hospedagem.

A Receita publica todo mês ~60 milhões de estabelecimentos (vários GB). Ler e filtrar isso
na hospedagem compartilhada travava o site por dias. Aqui o trabalho pesado roda numa
máquina do GitHub: baixa os arquivos, fica só com as empresas ATIVAS das atividades que os
representantes visitam, junta razão social/porte/MEI e separa por estado. O site baixa só
os estados de que precisa, já prontos, e grava.

Saída (pasta saida/):
  estab-<UF>-<id>.tsv.gz  uma empresa por linha, UTF-8, separado por TAB (colunas em COLUNAS)
  cnaes-<id>.tsv.gz       código e descrição oficial das atividades
  manifesto.json          mês, id, universo de atividades e a lista de arquivos (com sha256)

Uso: python3 gerar.py [--mes AAAA-MM] [--limite N] (limite = linhas por arquivo, só para teste)
"""
import argparse, csv, gzip, hashlib, io, json, os, re, subprocess, sys, threading, queue, time, urllib.request, zipfile, xml.etree.ElementTree as ET

TOKEN = os.environ.get('RECEITA_TOKEN', 'YggdBLfdninEJX9')
BASE = os.environ.get('RECEITA_URL', 'https://arquivos.receitafederal.gov.br/public.php')
SITE_UNIVERSO = os.environ.get('SITE_UNIVERSO', 'https://amelieapp.com.br/cnpj-universo.php')
FORMATO = 1
REGRA = 3      # 1 = principal ou secundária no universo · 2 = principal no universo · 3 = e sem MEI
COLUNAS = ['cnpj', 'matriz', 'fantasia', 'cnae', 'inicio', 'logradouro', 'numero', 'complemento', 'bairro', 'cep', 'uf', 'mun',
           'tel1', 'tel2', 'email', 'razao', 'natureza', 'porte', 'capital', 'mei', 'cnaes']
TMP = 'tmp'; SAIDA = 'saida'


def log(*a, aviso=False):
    print(time.strftime('%H:%M:%S'), *a, flush=True)
    if aviso and os.environ.get('GITHUB_ACTIONS'):
        print('::notice::' + ' '.join(map(str, a)), flush=True)   # aparece no resumo da execução


def erro(msg):
    if os.environ.get('GITHUB_ACTIONS'): print('::error::' + msg, flush=True)
    raise SystemExit(msg)


def curl(args, tentativas=8):
    for t in range(tentativas):
        r = subprocess.run(['curl', '-sS', '--fail', '-u', TOKEN + ':', '-A', 'AMELIE/1.0 (amelieapp.com.br)'] + args)
        if r.returncode == 0:
            return True
        log('  curl falhou (%d), tentativa %d' % (r.returncode, t + 1)); time.sleep(min(60, 5 * (t + 1)))
    return False


LOCAL = os.environ.get('RECEITA_LOCAL', '')   # pasta com <mes>/<arquivo>.zip, só para teste


def listar(mes=None):
    if LOCAL:
        if mes is None: return sorted(d for d in os.listdir(LOCAL) if re.fullmatch(r'\d{4}-\d{2}', d))
        return {f: os.path.getsize(os.path.join(LOCAL, mes, f)) for f in os.listdir(os.path.join(LOCAL, mes)) if f.lower().endswith('.zip')}
    url = BASE + '/webdav/' + (mes + '/' if mes else '')
    for t in range(6):   # a Receita às vezes não responde de primeira
        out = subprocess.run(['curl', '-sS', '--fail', '-m', '120', '-u', TOKEN + ':', '-X', 'PROPFIND', '-H', 'Depth: 1', url], capture_output=True)
        if out.returncode == 0: break
        log('  listagem falhou (%s), tentativa %d' % (out.stderr.decode()[:120].strip(), t + 1)); time.sleep(30 * (t + 1))
    else:
        erro('Receita não respondeu à listagem: ' + out.stderr.decode()[:200])
    doc = ET.fromstring(out.stdout)
    itens = []
    for r in doc.iter('{DAV:}response'):
        href = urllib.request.unquote(r.findtext('{DAV:}href') or '')
        tam = int(r.findtext('.//{DAV:}getcontentlength') or 0)
        itens.append((href, tam))
    if mes is None:
        return sorted({m.group(1) for h, _ in itens for m in [re.search(r'(\d{4}-\d{2})/?$', h)] if m})
    return {m.group(1): t for h, t in itens for m in [re.search(r'/([^/]+\.zip)$', h, re.I)] if m}


def universo():
    """Atividades do sistema (universo.txt) + as que os representantes acrescentaram (site)."""
    u = {l.strip() for l in open('universo.txt') if re.fullmatch(r'\d{2,7}', l.strip())}
    try:
        with urllib.request.urlopen(urllib.request.Request(SITE_UNIVERSO, headers={'User-Agent': 'AMELIE-base'}), timeout=30) as r:
            extra = {l.strip() for l in r.read().decode().split('\n') if re.fullmatch(r'\d{2,7}', l.strip())}
        log('universo do site: %d atividades (%d novas)' % (len(extra), len(extra - u)))
        u |= extra
    except Exception as e:
        log('site não respondeu (%s): só o universo.txt' % e)
    return sorted(u)


class Universo:
    def __init__(self, codigos):
        self.exato = {c for c in codigos if len(c) == 7}
        self.pref = {}
        for c in codigos:
            if len(c) < 7: self.pref.setdefault(len(c), set()).add(c)

    def tem(self, c):
        if c in self.exato: return True
        return any(c[:n] in s for n, s in self.pref.items())


def baixar_um(mes, nome, tamanho):
    """A Receita entrega ~0,7 MB/s por conexão: baixamos 4 arquivos ao mesmo tempo."""
    dest = os.path.join(TMP, nome)
    if LOCAL:
        import shutil; shutil.copy(os.path.join(LOCAL, mes, nome), dest); return dest
    for _ in range(3):
        if curl(['-m', '14400', '-C', '-', '--retry', '5', '-o', dest, '%s/dav/files/%s/%s/%s' % (BASE, TOKEN, mes, nome)]) \
                and (not tamanho or os.path.getsize(dest) == tamanho):
            return dest
    return None


def linhas(zip_caminho, limite=0):
    with zipfile.ZipFile(zip_caminho) as z:
        with z.open(z.namelist()[0]) as f:
            for i, l in enumerate(f):
                if limite and i >= limite: break
                yield l


def campos(l):
    return next(csv.reader([l.decode('latin-1').rstrip('\r\n')], delimiter=';', quotechar='"'))


def limpo(s):
    return re.sub(r'[\t\r\n]+', ' ', s).strip()


def tel(ddd, num):
    d = re.sub(r'\D', '', ddd); t = re.sub(r'\D', '', num)
    if len(t) < 8 or re.fullmatch(r'0+', t): return ''
    return (d.lstrip('0') + t)[:12]


def data(s):
    m = re.fullmatch(r'(\d{4})(\d{2})(\d{2})', s)
    if not m or m.group(1) <= '1900': return ''
    try:
        time.strptime(s, '%Y%m%d'); return '%s-%s-%s' % m.groups()
    except ValueError:
        return ''


def razao_limpa(r):
    r = re.sub(r'\s+', ' ', r).strip()
    r = re.sub(r'[\s\-]*\d{3}\.?\d{3}\.?\d{3}-?\d{2}\s*$', '', r)
    r = re.sub(r'\b\d{11}\b', '', r)
    return re.sub(r'\s+', ' ', r).strip()


EMAIL = re.compile(r'^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--mes'); ap.add_argument('--limite', type=int, default=0)
    ap.add_argument('--so-conferir', action='store_true', help='só diz se precisa gerar (saída: precisa=sim/nao)')
    ap.add_argument('--manifesto-atual', default='', help='manifesto.json publicado (para comparar)')
    a = ap.parse_args()
    os.makedirs(TMP, exist_ok=True); os.makedirs(SAIDA, exist_ok=True)
    mes = a.mes or listar()[-1]
    cod = universo(); umd5 = hashlib.md5(('\n'.join(cod) + '\nregra=%d' % REGRA).encode()).hexdigest()
    if a.so_conferir:
        atual = {}
        try: atual = json.load(open(a.manifesto_atual))
        except Exception: pass
        precisa = not (atual.get('mes') == mes and atual.get('universo_md5') == umd5 and atual.get('formato') == FORMATO)
        log('mês publicado na Receita: %s · base atual: %s · precisa gerar: %s' % (mes, atual.get('mes'), precisa), aviso=True)
        with open(os.environ.get('GITHUB_OUTPUT', '/dev/null'), 'a') as o:
            o.write('precisa=%s\nmes=%s\n' % ('sim' if precisa else 'nao', mes))
        return
    U = Universo(cod)
    tam = listar(mes)
    est = sorted([n for n in tam if n.lower().startswith('estabele')])
    emp = sorted([n for n in tam if n.lower().startswith('empresa')])
    simp = [n for n in tam if n.lower().startswith('simples')]
    cn = [n for n in tam if n.lower().startswith('cnae')]
    if len(est) < 10 or len(emp) < 10 or not simp or not cn:
        erro('A pasta %s está incompleta: %s' % (mes, sorted(tam)))
    log('mês %s · %d atividades no universo · %.1f GB para baixar' % (mes, len(cod), sum(tam[n] for n in est + emp + simp + cn) / 1e9), aviso=True)

    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(max_workers=int(os.environ.get('CONEXOES', '4')))
    fila = [(n, pool.submit(baixar_um, mes, n, tam[n])) for n in cn + est + emp + simp]
    por_uf = {}; antes = {}; basicos = set(); empresas = {}; mei = set(); cnaes = []
    lidas = 0; t0 = time.time()
    for nome, fut in fila:
        cam = fut.result()
        if cam is None: erro('Não consegui baixar ' + nome)
        b = nome.lower(); n0 = 0
        if b.startswith('cnae'):
            for l in linhas(cam):
                c = campos(l)
                if len(c) >= 2 and re.fullmatch(r'\d{7}', c[0]): cnaes.append((c[0], limpo(c[1])))
        elif b.startswith('estabele'):
            for l in linhas(cam, a.limite):
                n0 += 1
                p = l.split(b'";"', 6)
                if len(p) < 7 or p[5] != b'02': continue          # só ATIVA (6º campo)
                c = campos(l)
                if len(c) < 28 or c[5] != '02': continue
                uf = c[19].upper()
                if not re.fullmatch(r'[A-Z]{2}', uf) or uf == 'EX': continue
                pr = re.sub(r'\D', '', c[11])
                inter = []
                if U.tem(pr): inter.append(pr)
                for s in c[12].split(','):
                    s = re.sub(r'\D', '', s)
                    if len(s) == 7 and s not in inter and U.tem(s): inter.append(s)
                if not inter: continue
                antes[uf] = antes.get(uf, 0) + 1
                # Regra 2: a atividade PRINCIPAL precisa ser do universo. Só a secundária
                # (o mercadinho que declarou "comércio de tintas") não basta — trazia 75%
                # das empresas do Brasil e enchia a lista de quem não compra.
                if REGRA >= 2 and not (inter and inter[0] == pr): continue
                cnpj = c[0] + c[1] + c[2]
                if not re.fullmatch(r'\d{14}', cnpj): continue
                email = c[27].strip().lower()
                lin = [cnpj, '1' if c[3] == '1' else '0', limpo(c[4]), pr, data(c[10]), limpo(c[13] + ' ' + c[14]), limpo(c[15]),
                       limpo(c[16]), limpo(c[17]), re.sub(r'\D', '', c[18]), uf, str(int(c[20] or 0)), tel(c[21], c[22]), tel(c[23], c[24]),
                       email if EMAIL.match(email) and len(email) <= 120 else '']
                f = por_uf.get(uf)
                if f is None: f = por_uf[uf] = open(os.path.join(TMP, 'parcial-%s.tsv' % uf), 'w', encoding='utf-8')
                f.write('\t'.join(lin) + '\t' + ','.join(inter) + '\n')
                basicos.add(c[0])
        elif b.startswith('empresa'):
            for l in linhas(cam, a.limite):
                n0 += 1
                if l[1:9].decode('ascii', 'replace') not in basicos: continue
                c = campos(l)
                if len(c) < 6: continue
                cap = c[4].replace('.', '').replace(',', '.')
                try: cap = '%.2f' % float(cap) if float(cap) else ''
                except ValueError: cap = ''
                empresas[c[0]] = (limpo(razao_limpa(c[1])), str(int(c[2])) if c[2].isdigit() and int(c[2]) else '',
                                  str(int(c[5])) if c[5].isdigit() and int(c[5]) else '', cap)
        elif b.startswith('simples'):
            for l in linhas(cam, a.limite):
                n0 += 1
                if l[1:9].decode('ascii', 'replace') not in basicos: continue
                c = campos(l)
                if len(c) >= 7 and c[4].upper() == 'S' and re.sub(r'\D', '', c[6]) in ('', '00000000'): mei.add(c[0])
        lidas += n0
        os.remove(cam)
        log('%s lido: %s linhas · %s empresas guardadas · %.0f s' % (nome, format(n0, ','), format(len(basicos), ','), time.time() - t0))
    for f in por_uf.values(): f.close()

    gid = time.strftime('%Y%m%d%H%M', time.gmtime()) + '-' + umd5[:6]
    arquivos = {}
    def gravar(nome, gerador):
        cam = os.path.join(SAIDA, nome); n = 0
        with gzip.open(cam, 'wt', encoding='utf-8', compresslevel=9) as g:
            for linha in gerador: g.write(linha); n += 1
        h = hashlib.sha256(open(cam, 'rb').read()).hexdigest()
        return {'arquivo': nome, 'linhas': n, 'bytes': os.path.getsize(cam), 'sha256': h}
    sem_mei = {}
    for uf in sorted(por_uf):
        def juntar(uf=uf):
            for l in open(os.path.join(TMP, 'parcial-%s.tsv' % uf), encoding='utf-8'):
                p = l.rstrip('\n').split('\t')
                bas = p[0][:8]; e = empresas.get(bas, ('', '', '', ''))
                if REGRA >= 3 and bas in mei:   # regra 3: MEI quase nunca compra de representante — fica fora
                    sem_mei[uf] = sem_mei.get(uf, 0) + 1
                    continue
                yield '\t'.join(p[:15] + list(e) + ['1' if bas in mei else '0', p[15]]) + '\n'
        arquivos[uf] = gravar('estab-%s-%s.tsv.gz' % (uf, gid), juntar())
        os.remove(os.path.join(TMP, 'parcial-%s.tsv' % uf))
        log('estado %s: %s empresas (MEI fora: %s; secundária fora: %s) · %.1f MB' % (uf, format(arquivos[uf]['linhas'], ','), format(sem_mei.get(uf, 0), ','),
            format(antes.get(uf, 0) - arquivos[uf]['linhas'] - sem_mei.get(uf, 0), ','), arquivos[uf]['bytes'] / 1e6))
    c = gravar('cnaes-%s.tsv.gz' % gid, ('%s\t%s\n' % x for x in cnaes))
    man = {'formato': FORMATO, 'mes': mes, 'id': gid, 'gerado': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'universo_md5': umd5, 'universo': cod, 'regra': REGRA, 'antes_regra': sum(antes.values()), 'mei_fora': sum(sem_mei.values()), 'colunas': COLUNAS, 'linhas_lidas': lidas,
           'total': sum(x['linhas'] for x in arquivos.values()), 'cnaes': c, 'ufs': arquivos, 'teste': bool(a.limite)}
    json.dump(man, open(os.path.join(SAIDA, 'manifesto.json'), 'w'), ensure_ascii=False, indent=1)
    log('por estado: ' + ' · '.join('%s %s' % (u, format(arquivos[u]['linhas'], ',')) for u in sorted(arquivos)), aviso=True)
    log('MEI fora: %s · só secundária fora: %s' % (format(sum(sem_mei.values()), ','), format(sum(antes.values()) - man['total'] - sum(sem_mei.values()), ',')), aviso=True)
    log('pronto: %s empresas em %d estados, de %s linhas lidas, em %.0f min' % (format(man['total'], ','), len(arquivos), format(lidas, ','), (time.time() - t0) / 60), aviso=True)


if __name__ == '__main__':
    main()
