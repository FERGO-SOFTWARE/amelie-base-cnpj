#!/usr/bin/env python3
"""
AMELIE · "Perto de você": a base de CNPJ em pedaços pequenos, com coordenada, para o app ler direto daqui.

Roda depois do gerar.py, em cima do que ele já deixou em saida/ (estab-UF-*.tsv.gz). Nada de banco e nada do
servidor da AMELIE: o app baixa só os pedaços da região onde o representante está e guarda no aparelho.

De onde vem a coordenada: do CNEFE 2022 do IBGE (Cadastro Nacional de Endereços para Fins Estatísticos), que tem
latitude e longitude de todos os endereços do Censo. Cada empresa é localizada pelo endereço dela, nesta ordem:
  n = no número          (CEP + rua + número iguais)
  p = perto do número    (CEP + rua iguais; o número mais próximo que o CNEFE tem)
  r = na rua             (CEP + rua iguais; o meio da rua)
  c = no CEP             (o meio do CEP, quando o CEP cobre até RAIO_CEP_M metros)
  m = só a cidade        (CEP de cidade inteira, ou CEP que o CNEFE não tem): fica fora dos pedaços "perto"
Quem pediu para não ser contatado (lista do site, em hash) não entra.

Saída (pasta perto/):
  <UF>-<quadrado>.tsv    um pedaço do mapa: uma empresa por linha, TAB, colunas em COLUNAS. Quadrado cheio é dividido
                         em 4 até caber em MAX_LINHAS (ou chegar a LADO_MIN graus).
  novos-<UF>.tsv         as empresas abertas nos últimos DIAS_NOVO dias (mesmas colunas), ordenadas por município
  indice-<UF>.json       os pedaços do estado: arquivo, caixa (sul, oeste, norte, leste), linhas e hash
  perto.json             o mês, as colunas e, por estado, a caixa e onde está o índice

Sem telefone e sem e-mail: contato sai do sistema, para o assinante, quando ele abre a empresa.

Uso: python3 perto.py [--ufs SP,MG] [--cnefe pasta_com_os_zip] [--hoje AAAA-MM-DD]
"""
import base_arq
import argparse, csv, glob, gzip, hashlib, io, json, math, os, re, subprocess, sys, time, unicodedata, urllib.request, zipfile

SAIDA = 'saida'; PERTO = 'perto'; TMP = 'tmp'
CNEFE_URL = os.environ.get('CNEFE_URL', 'https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/CSV/UF')
SITE_OPTOUT = os.environ.get('SITE_OPTOUT', 'https://amelieapp.com.br/cnpj-universo.php?optout=1')
FORMATO = 1
COLUNAS = ['cnpj', 'nome', 'cnae', 'inicio', 'lat', 'lng', 'prec', 'logradouro', 'numero', 'bairro', 'cep', 'ibge', 'porte']
MAX_LINHAS = 8000      # empresas por pedaço (~900 KB)
MAX_PEDACOS = 900      # por estado (o limite do GitHub é 1000 arquivos por release)
LADO_INI = 0.8         # graus (~88 km): o quadrado de partida
LADO_MIN = 0.05        # graus (~5,5 km): menor que isso não divide mais
RAIO_CEP_M = 1500      # CEP que cobre mais que isso é de cidade inteira: não serve para "perto"
DIAS_NOVO = 200        # o app mostra "novo" até 180 dias; a folga cobre o mês entre uma base e outra
AMOSTRAS_RUA = 60      # números guardados por rua, para achar o mais próximo
COD_UF = {'RO': 11, 'AC': 12, 'AM': 13, 'RR': 14, 'PA': 15, 'AP': 16, 'TO': 17, 'MA': 21, 'PI': 22, 'CE': 23, 'RN': 24, 'PB': 25, 'PE': 26, 'AL': 27,
          'SE': 28, 'BA': 29, 'MG': 31, 'ES': 32, 'RJ': 33, 'SP': 35, 'PR': 41, 'SC': 42, 'RS': 43, 'MS': 50, 'MT': 51, 'GO': 52, 'DF': 53}


def log(*a, aviso=False):
    print(time.strftime('%H:%M:%S'), *a, flush=True)
    if aviso and os.environ.get('GITHUB_ACTIONS'): print('::notice::' + ' '.join(map(str, a)), flush=True)


def erro(msg):
    if os.environ.get('GITHUB_ACTIONS'): print('::error::' + msg, flush=True)
    raise SystemExit(msg)


# ------------------------------------------------------------------ o nome da rua, do mesmo jeito nos dois lados

TIPOS = {'RUA', 'R', 'AVENIDA', 'AV', 'AVN', 'TRAVESSA', 'TRAV', 'TV', 'ALAMEDA', 'AL', 'PRACA', 'PCA', 'PC', 'RODOVIA', 'ROD', 'ESTRADA', 'EST', 'ESTR', 'LARGO', 'LGO',
         'VIA', 'VIELA', 'VLA', 'BECO', 'BC', 'QUADRA', 'Q', 'QD', 'CAMINHO', 'CAM', 'PASSAGEM', 'PSG', 'LADEIRA', 'LAD', 'VILA', 'VL', 'SERVIDAO', 'SERV',
         'ACESSO', 'AC', 'CONJUNTO', 'CJ', 'PARQUE', 'PQ', 'LOTEAMENTO', 'LOT', 'CALCADA', 'CALCADAO', 'BOULEVARD', 'BLV', 'RAMAL', 'CORREDOR', 'ESCADARIA', 'TRECHO',
         'LINHA', 'SITIO', 'FAZENDA', 'CHACARA', 'RUELA', 'JARDIM', 'SETOR', 'ST', 'AREA', 'MARGINAL', 'CONTORNO', 'ANEL', 'VIADUTO', 'PONTE', 'TUNEL', 'COMPLEXO', 'DISTRITO'}
ABREV = {'DR': 'DOUTOR', 'DRA': 'DOUTORA', 'PROF': 'PROFESSOR', 'PROFA': 'PROFESSORA', 'PROFESSORA': 'PROFESSORA', 'CEL': 'CORONEL', 'CAP': 'CAPITAO', 'GEN': 'GENERAL',
         'GAL': 'GENERAL', 'MAL': 'MARECHAL', 'MAJ': 'MAJOR', 'TEN': 'TENENTE', 'SGT': 'SARGENTO', 'ALM': 'ALMIRANTE', 'BRIG': 'BRIGADEIRO', 'PE': 'PADRE', 'PDE': 'PADRE',
         'FR': 'FREI', 'D': 'DOM', 'STO': 'SANTO', 'STA': 'SANTA', 'S': 'SAO', 'SR': 'SENHOR', 'SRA': 'SENHORA', 'N': 'NOSSA', 'NS': 'NOSSA SENHORA', 'NSA': 'NOSSA',
         'PRES': 'PRESIDENTE', 'GOV': 'GOVERNADOR', 'SEN': 'SENADOR', 'DEP': 'DEPUTADO', 'VER': 'VEREADOR', 'PREF': 'PREFEITO', 'MIN': 'MINISTRO', 'DES': 'DESEMBARGADOR',
         'ENG': 'ENGENHEIRO', 'COM': 'COMENDADOR', 'CDOR': 'COMENDADOR', 'CONS': 'CONSELHEIRO', 'VISC': 'VISCONDE', 'BR': 'BARAO', 'MONS': 'MONSENHOR', 'JD': 'JARDIM',
         'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5', 'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10', 'XI': '11', 'XII': '12', 'XIII': '13', 'XV': '15',
         'XXIII': '23', 'PRIMEIRO': '1', 'PRIMEIRA': '1'}
NUMEROS = {'UM': 1, 'DOIS': 2, 'TRES': 3, 'QUATRO': 4, 'CINCO': 5, 'SEIS': 6, 'SETE': 7, 'OITO': 8, 'NOVE': 9, 'DEZ': 10, 'ONZE': 11, 'DOZE': 12, 'TREZE': 13,
           'QUATORZE': 14, 'CATORZE': 14, 'QUINZE': 15, 'DEZESSEIS': 16, 'DEZESSETE': 17, 'DEZOITO': 18, 'DEZENOVE': 19, 'VINTE': 20, 'TRINTA': 30}
SOLTAS = {'DE', 'DA', 'DO', 'DAS', 'DOS', 'E'}


def sem_acento(s):
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')


def rua_norm(*partes):
    """'R. DR. João Pessôa' e 'RUA' + 'DOUTOR' + 'JOAO PESSOA' viram a mesma chave: 'DOUTOR JOAO PESSOA'."""
    t = sem_acento(' '.join(p for p in partes if p)).upper()
    t = re.sub(r'[^A-Z0-9 ]+', ' ', t)
    palavras = t.split()
    while palavras and palavras[0] in TIPOS and len(palavras) > 1: palavras = palavras[1:]
    out = []
    for p in palavras:
        p = ABREV.get(p, p)
        if p in SOLTAS: continue
        if p in NUMEROS:                                   # 'NOVE DE JULHO' = '9 DE JULHO'; 'VINTE E CINCO' = '25'
            v = NUMEROS[p]
            if v < 10 and out and out[-1] in ('20', '30'): out[-1] = str(int(out[-1]) + v)
            else: out.append(str(v))
            continue
        out.append(p.lstrip('0') or '0' if p.isdigit() else p)
    return ' '.join(out)


def num_norm(n):
    """'123', '0123', '123 A', 'Nº 123' → '123'; 'S/N', 'SN', '' → ''."""
    m = re.search(r'\d+', n or '')
    if not m: return ''
    v = m.group(0).lstrip('0')
    return v if v and len(v) <= 6 else ''


def metros(lat1, lng1, lat2, lng2):
    r = 6371000.0
    a = math.radians(lat2 - lat1); b = math.radians(lng2 - lng1)
    h = math.sin(a / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(b / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def coord(s):
    try: return float(s.replace(',', '.'))
    except (ValueError, AttributeError): return None


# ------------------------------------------------------------------ entrada: o que o gerar.py deixou

def ler_estabs(uf, optout, hoje):
    cams = sorted(glob.glob(os.path.join(SAIDA, 'estab-%s-*.tsv.gz' % uf)))
    if not cams: return []
    out = []
    for l in gzip.open(cams[-1], 'rt', encoding='utf-8'):
        p = l.rstrip('\n').split('\t')
        if len(p) < 20 or p[19] == '1': continue                      # MEI fica fora (o gerar.py já tira; aqui é a garantia)
        cnpj = p[0]
        if optout and hashlib.sha256(cnpj.encode()).hexdigest() in optout: continue
        nome = p[2] or p[15]
        if not nome: continue
        cep = re.sub(r'\D', '', p[9])
        out.append({'cnpj': cnpj, 'nome': nome[:80], 'cnae': p[3], 'inicio': p[4], 'log': p[5][:70], 'num': p[6][:10], 'bairro': p[8][:40],
                    'cep': cep if len(cep) == 8 else '', 'mun': p[11], 'porte': p[17],
                    'k2': '', 'k1': '', 'x': base_arq.extras(p)})
    for e in out:
        if not e['cep']: continue
        rn = rua_norm(e['log'])
        if not rn: continue
        e['k2'] = e['cep'] + '|' + rn
        n = num_norm(e['num'])
        if n: e['k1'] = e['k2'] + '|' + n
    return out


def optout_do_site():
    try:
        with urllib.request.urlopen(urllib.request.Request(SITE_OPTOUT, headers={'User-Agent': 'AMELIE-base'}), timeout=30) as r:
            s = {l.strip() for l in r.read().decode().split('\n') if re.fullmatch(r'[0-9a-f]{64}', l.strip())}
        log('não contatar: %d CNPJs fora' % len(s))
        return s
    except Exception as e:
        log('lista de não contatar não veio (%s): segue sem ela' % e, aviso=True)
        return set()


# ------------------------------------------------------------------ CNEFE

def cnefe_zip(uf, pasta):
    nome = '%d_%s.zip' % (COD_UF[uf], uf)
    if pasta:
        cam = os.path.join(pasta, nome)
        return cam if os.path.exists(cam) else None
    os.makedirs(TMP, exist_ok=True)
    cam = os.path.join(TMP, nome)
    for t in range(6):
        r = subprocess.run(['curl', '-sS', '--fail', '-L', '-m', '7200', '-C', '-', '--retry', '5', '-A', 'AMELIE/1.0 (amelieapp.com.br)', '-o', cam, CNEFE_URL + '/' + nome])
        if r.returncode == 0 and zipfile.is_zipfile(cam): return cam
        log('  CNEFE %s: tentativa %d falhou' % (uf, t + 1)); time.sleep(20 * (t + 1))
        if os.path.exists(cam) and not zipfile.is_zipfile(cam) and t >= 2: os.remove(cam)
    return None


OBRIG = ['CEP', 'NOM_SEGLOGR', 'NUM_ENDERECO', 'LATITUDE', 'LONGITUDE']


def cnefe_linhas(cam):
    """Gera (cep, tipo, titulo, nome, numero, lat, lng, nivel, municipio) de cada endereço do arquivo do estado."""
    with zipfile.ZipFile(cam) as z:
        nomes = [n for n in z.namelist() if n.lower().endswith('.csv')] or z.namelist()
        for nm in nomes:
            with z.open(nm) as f:
                txt = io.TextIOWrapper(f, encoding='utf-8', errors='replace', newline='')
                cab = txt.readline().lstrip('﻿').strip()
                sep = ';' if cab.count(';') >= cab.count(',') else ','
                cols = [c.strip().strip('"').upper() for c in cab.split(sep)]
                falta = [c for c in OBRIG if c not in cols]
                if falta: erro('CNEFE %s: faltam as colunas %s. Cabeçalho: %s' % (nm, falta, cols[:40]))
                ix = {c: cols.index(c) for c in OBRIG}
                i_tipo = cols.index('NOM_TIPO_SEGLOGR') if 'NOM_TIPO_SEGLOGR' in cols else -1
                i_tit = cols.index('NOM_TITULO_SEGLOGR') if 'NOM_TITULO_SEGLOGR' in cols else -1
                i_niv = cols.index('NV_GEO_COORD') if 'NV_GEO_COORD' in cols else -1
                i_mun = cols.index('COD_MUNICIPIO') if 'COD_MUNICIPIO' in cols else -1
                maxi = max(list(ix.values()) + [i_tipo, i_tit, i_niv, i_mun])
                for c in csv.reader(txt, delimiter=sep, quotechar='"'):
                    if len(c) <= maxi: continue
                    yield (c[ix['CEP']], c[i_tipo] if i_tipo >= 0 else '', c[i_tit] if i_tit >= 0 else '', c[ix['NOM_SEGLOGR']], c[ix['NUM_ENDERECO']],
                           c[ix['LATITUDE']], c[ix['LONGITUDE']], c[i_niv] if i_niv >= 0 else '', c[i_mun] if i_mun >= 0 else '')


def localizar(estabs, cam):
    """Põe lat, lng, prec e ibge em cada empresa. Lê o CNEFE uma vez, guardando só o que alguma empresa precisa."""
    ceps = {e['cep'] for e in estabs if e['cep']}
    need2 = {e['k2'] for e in estabs if e['k2']}
    need1 = {e['k1'] for e in estabs if e['k1']}
    a_cep = {}    # cep → [n, slat, slng, minlat, maxlat, minlng, maxlng, {mun: n}]
    a_rua = {}    # cep|rua → [n, slat, slng, [(num, lat, lng)]]
    a_num = {}    # cep|rua|num → [n, slat, slng]
    lidas = 0; usadas = 0; cache_rua = {}
    for cep, tipo, tit, nome, num, lat, lng, niv, mun in cnefe_linhas(cam):
        lidas += 1
        cep = cep.strip().zfill(8) if cep.strip().isdigit() else re.sub(r'\D', '', cep)
        if cep not in ceps: continue
        if niv.strip() in ('5', '6'): continue        # coordenada da localidade ou do setor: não é do endereço
        la = coord(lat); lo = coord(lng)
        if la is None or lo is None or not (-34.5 <= la <= 6.0 and -74.5 <= lo <= -28.0): continue
        usadas += 1
        c = a_cep.get(cep)
        if c is None: c = a_cep[cep] = [0, 0.0, 0.0, la, la, lo, lo, {}]
        c[0] += 1; c[1] += la; c[2] += lo
        if la < c[3]: c[3] = la
        if la > c[4]: c[4] = la
        if lo < c[5]: c[5] = lo
        if lo > c[6]: c[6] = lo
        if mun: c[7][mun] = c[7].get(mun, 0) + 1
        ch = (tipo, tit, nome)
        rn = cache_rua.get(ch)
        if rn is None:
            rn = rua_norm(tipo, tit, nome)
            if len(cache_rua) < 400000: cache_rua[ch] = rn
        k2 = cep + '|' + rn
        if k2 not in need2: continue
        r = a_rua.get(k2)
        if r is None: r = a_rua[k2] = [0, 0.0, 0.0, []]
        r[0] += 1; r[1] += la; r[2] += lo
        n = num_norm(num)
        if n:
            if len(r[3]) < AMOSTRAS_RUA: r[3].append((int(n), la, lo))
            k1 = k2 + '|' + n
            if k1 in need1:
                x = a_num.get(k1)
                if x is None: a_num[k1] = [1, la, lo]
                else: x[0] += 1; x[1] += la; x[2] += lo
    cont = {'n': 0, 'p': 0, 'r': 0, 'c': 0, 'm': 0}
    for e in estabs:
        e['lat'] = e['lng'] = None; e['prec'] = 'm'; e['ibge'] = ''
        c = a_cep.get(e['cep']) if e['cep'] else None
        if c:
            e['ibge'] = max(c[7].items(), key=lambda kv: kv[1])[0] if c[7] else ''
        x = a_num.get(e['k1']) if e['k1'] else None
        if x:
            e['lat'] = x[1] / x[0]; e['lng'] = x[2] / x[0]; e['prec'] = 'n'
        else:
            r = a_rua.get(e['k2']) if e['k2'] else None
            if r:
                n = num_norm(e['num'])
                if n and r[3]:
                    alvo = int(n); am = min(r[3], key=lambda s: abs(s[0] - alvo))
                    e['lat'] = am[1]; e['lng'] = am[2]; e['prec'] = 'p'
                else:
                    e['lat'] = r[1] / r[0]; e['lng'] = r[2] / r[0]; e['prec'] = 'r'
            elif c:
                la = c[1] / c[0]; lo = c[2] / c[0]
                e['lat'] = la; e['lng'] = lo
                e['prec'] = 'c' if metros(c[3], c[5], c[4], c[6]) / 2 <= RAIO_CEP_M else 'm'
        cont[e['prec']] += 1
    return lidas, usadas, cont


# ------------------------------------------------------------------ saída: os pedaços

def linha(e):
    return '\t'.join([e['cnpj'], e['nome'], e['cnae'], e['inicio'], '%.5f' % e['lat'] if e['lat'] is not None else '', '%.5f' % e['lng'] if e['lng'] is not None else '',
                      e['prec'], e['log'], e['num'], e['bairro'], e['cep'], e['ibge'], e['porte']]) + '\n'


def gravar(nome, es):
    cam = os.path.join(PERTO, nome)
    with open(cam, 'w', encoding='utf-8', newline='') as f:
        for e in es: f.write(linha(e))
    return {'a': nome, 'n': len(es), 'bytes': os.path.getsize(cam), 'h': hashlib.sha1(open(cam, 'rb').read()).hexdigest()[:12]}


def dividir(es, sul, oeste, lado, caminho, folhas, uf):
    """Quadrado [sul, sul+lado) × [oeste, oeste+lado): se couber, vira um arquivo; senão divide em 4."""
    if not es: return
    if len(es) <= MAX_LINHAS or lado / 2 < LADO_MIN - 1e-9:
        es.sort(key=lambda e: e['cnpj'])
        f = gravar('%s-%s.tsv' % (uf, caminho), es)
        f['b'] = [round(sul, 4), round(oeste, 4), round(sul + lado, 4), round(oeste + lado, 4)]
        folhas.append(f); return
    m = lado / 2
    q = [[], [], [], []]
    for e in es:
        q[(2 if e['lat'] >= sul + m else 0) + (1 if e['lng'] >= oeste + m else 0)].append(e)
    for i in range(4):
        dividir(q[i], sul + (m if i >= 2 else 0), oeste + (m if i % 2 else 0), m, caminho + str(i), folhas, uf)


def fazer_uf(uf, optout, hoje, pasta_cnefe, cn=None):
    es = ler_estabs(uf, optout, hoje)
    if not es: return None
    cam = cnefe_zip(uf, pasta_cnefe)
    if cam is None: erro('Não consegui o CNEFE de ' + uf)
    t0 = time.time()
    lidas, usadas, cont = localizar(es, cam)
    if not pasta_cnefe: os.remove(cam)
    perto = [e for e in es if e['prec'] != 'm' and e['lat'] is not None]
    raiz = {}
    for e in perto:
        k = (math.floor(e['lat'] / LADO_INI), math.floor(e['lng'] / LADO_INI))
        raiz.setdefault(k, []).append(e)
    global MAX_LINHAS
    max_ini = MAX_LINHAS
    while True:                                            # um "release" do GitHub guarda até 1000 arquivos: se passar, pedaços maiores
        folhas = []
        for (ky, kx), lst in sorted(raiz.items()):
            dividir(list(lst), ky * LADO_INI, kx * LADO_INI, LADO_INI, 'q%s%d_%s%d_' % ('s' if ky < 0 else 'n', abs(ky), 'o' if kx < 0 else 'l', abs(kx)), folhas, uf)
        if len(folhas) <= MAX_PEDACOS: break
        for f in folhas: os.remove(os.path.join(PERTO, f['a']))
        MAX_LINHAS *= 2
        log('  %s: %d pedaços é demais; tentando com até %d empresas por pedaço' % (uf, len(folhas), MAX_LINHAS))
    MAX_LINHAS = max_ini
    limite = time.strftime('%Y-%m-%d', time.gmtime(time.mktime(time.strptime(hoje, '%Y-%m-%d')) - DIAS_NOVO * 86400))
    novos = sorted([e for e in es if e['inicio'] and e['inicio'] >= limite], key=lambda e: (e['ibge'], e['inicio'], e['cnpj']))
    fn = gravar('novos-%s.tsv' % uf, novos)
    caixa = [min(f['b'][0] for f in folhas), min(f['b'][1] for f in folhas), max(f['b'][2] for f in folhas), max(f['b'][3] for f in folhas)] if folhas else None
    idx = {'formato': FORMATO, 'uf': uf, 'colunas': COLUNAS, 'total': len(es), 'perto': len(perto), 'precisao': cont, 'folhas': folhas, 'novos': fn}
    json.dump(idx, open(os.path.join(PERTO, 'indice-%s.json' % uf), 'w'), ensure_ascii=False, separators=(',', ':'))
    pct = lambda k: 100.0 * cont[k] / max(1, len(es))
    base = base_arq.fazer_uf(uf, es, COD_UF[uf], cn if cn is not None else {})
    log('%s: %s empresas · no número %.0f%% · perto do número %.0f%% · na rua %.0f%% · no CEP %.0f%% · só a cidade %.0f%% · %d pedaços · %s novas · CNEFE %s linhas (%s usadas) · %.0f s'
        % (uf, format(len(es), ','), pct('n'), pct('p'), pct('r'), pct('c'), pct('m'), len(folhas), format(len(novos), ','), format(lidas, ','), format(usadas, ','), time.time() - t0), aviso=True)
    return {'indice': 'indice-%s.json' % uf, 'h': hashlib.sha1(open(os.path.join(PERTO, 'indice-%s.json' % uf), 'rb').read()).hexdigest()[:12],
            'caixa': caixa, 'total': len(es), 'perto': len(perto), 'pedacos': len(folhas), 'novos': len(novos), 'precisao': cont, 'base': base}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--ufs', default=''); ap.add_argument('--cnefe', default=''); ap.add_argument('--hoje', default='')
    a = ap.parse_args()
    os.makedirs(PERTO, exist_ok=True)
    man = json.load(open(os.path.join(SAIDA, 'manifesto.json')))
    hoje = a.hoje or time.strftime('%Y-%m-%d', time.gmtime())
    ufs = [u for u in (a.ufs.split(',') if a.ufs else sorted(man['ufs'])) if u in COD_UF]
    optout = set() if a.cnefe else optout_do_site()
    out = {}; cn = {}; bases = {}
    for uf in ufs:
        r = fazer_uf(uf, optout, hoje, a.cnefe, cn)
        if r: bases[uf] = r.pop('base'); out[uf] = r
    if not out: erro('Nenhum estado gerado.')
    tot = sum(x['total'] for x in out.values()); per = sum(x['perto'] for x in out.values())
    json.dump({'formato': FORMATO, 'mes': man['mes'], 'id': man['id'], 'gerado': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'hoje': hoje, 'colunas': COLUNAS,
               'dias_novo': DIAS_NOVO, 'total': tot, 'perto': per, 'ufs': out},
              open(os.path.join(PERTO, 'perto.json'), 'w'), ensure_ascii=False, separators=(',', ':'))
    log('perto: %s empresas, %s com endereço no mapa (%.0f%%), %d pedaços em %d estados'
        % (format(tot, ','), format(per, ','), 100.0 * per / max(1, tot), sum(x['pedacos'] for x in out.values()), len(out)), aviso=True)
    b = base_arq.fechar(man, bases, cn, not a.ufs)
    if b: log('base em arquivos: %s empresas em %d arquivos de %d estados' % (format(b['total'], ','), sum(x['arquivos'] for x in bases.values()), len(bases)), aviso=True)
    if per < tot * 0.5: erro('Menos da metade das empresas ficou com endereço no mapa (%d de %d): o CNEFE mudou de formato? Nada é publicado.' % (per, tot))


if __name__ == '__main__':
    main()
