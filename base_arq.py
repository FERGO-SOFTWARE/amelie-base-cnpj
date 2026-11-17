#!/usr/bin/env python3
"""
A BASE EM ARQUIVOS — o que a tela Clientes novos da AMELIE lê no lugar das tabelas do banco.

As mesmas empresas do "Perto de você" (já com a coordenada), agora com tudo o que a busca usa
(razão social, telefone, e-mail, atividades secundárias, porte, capital), separadas por ATIVIDADE:
o representante procura pelo ramo que ele vende, então o sistema baixa só os arquivos do ramo dele.

  base/<UF>-d47.tsv.gz    as empresas do estado com atividade (principal ou secundária) na divisão 47
  base/<UF>-g478.tsv.gz   divisão grande demais é separada pelo grupo (3 dígitos)
  base/base-<UF>.json     de cada grupo de atividade para o arquivo, com tamanho e hash
  base/cn-<NN>.bin        todos os CNPJ que começam com NN, em ordem, 16 bytes cada:
                          CNPJ (8, inteiro) · UF (1, código do IBGE) · CNAE (3) · município da Receita (2) · porte (1) · 0
                          (o sistema acha um CNPJ por busca binária, sem abrir os arquivos grandes)
  base/base.json          o manifesto: mês, colunas, estados e os cn-NN

Quem pediu para não ser contatado e MEI ficam fora (quem lê é o perto.py, que já tira os dois).
"""
import gzip, hashlib, json, os, time

BASE = 'base'
FORMATO = 1
COLUNAS = ['cnpj', 'matriz', 'fantasia', 'razao', 'cnae', 'sec', 'inicio', 'logradouro', 'numero', 'complemento', 'bairro', 'cep', 'mun',
           'tel1', 'tel2', 'email', 'natureza', 'porte', 'capital', 'lat', 'lng', 'prec']
EXTRAS = ['matriz', 'fantasia', 'razao', 'logradouro', 'numero', 'complemento', 'bairro', 'tel1', 'tel2', 'email', 'natureza', 'capital', 'sec']
DIVISAO_MAX = 60000    # empresas numa divisão (2 dígitos) do estado; acima disso separa pelo grupo (3 dígitos)
REG = 16


def extras(p):
    """Do registro do gerar.py (lista de colunas) para o texto guardado em cada empresa."""
    sec = [c for c in (p[20].split(',') if len(p) > 20 and p[20] else []) if c and c != p[3]]
    return '\t'.join([p[1], p[2], p[15], p[5], p[6], p[7], p[8], p[12], p[13], p[14], p[16], p[18], ','.join(sec)])


def linha(e):
    x = dict(zip(EXTRAS, e['x'].split('\t')))
    tem = e.get('lat') is not None and e.get('prec') in ('n', 'p', 'r', 'c')
    return '\t'.join([e['cnpj'], x['matriz'], x['fantasia'], x['razao'], e['cnae'], x['sec'], e['inicio'], x['logradouro'], x['numero'], x['complemento'],
                      x['bairro'], e['cep'], e['mun'], x['tel1'], x['tel2'], x['email'], x['natureza'], e['porte'], x['capital'],
                      '%.5f' % e['lat'] if tem else '', '%.5f' % e['lng'] if tem else '', e.get('prec') or 'm']) + '\n'


def grupos_de(e):
    sec = e['x'].rsplit('\t', 1)[-1]
    return {c[:3] for c in [e['cnae']] + (sec.split(',') if sec else []) if len(c) >= 3}


def gravar_gz(nome, linhas):
    cam = os.path.join(BASE, nome); n = 0
    with open(cam, 'wb') as f:
        with gzip.GzipFile(filename='', mode='wb', fileobj=f, mtime=0, compresslevel=6) as g:   # mtime=0: mesmo conteúdo, mesmo arquivo
            for l in linhas: g.write(l.encode('utf-8')); n += 1
    return {'a': nome, 'n': n, 'bytes': os.path.getsize(cam), 'h': hashlib.sha1(open(cam, 'rb').read()).hexdigest()[:12]}


def fazer_uf(uf, es, cod_uf, cn):
    """Grava os arquivos do estado e junta os registros de CNPJ em cn (prefixo → lista de 16 bytes)."""
    os.makedirs(BASE, exist_ok=True)
    c3 = {}; gs = []
    for e in es:
        g = grupos_de(e); gs.append(g)
        for x in g: c3[x] = c3.get(x, 0) + 1
    c2 = {}
    for g, n in c3.items(): c2[g[:2]] = c2.get(g[:2], 0) + n
    chave = {g: ('g' + g if c2[g[:2]] > DIVISAO_MAX else 'd' + g[:2]) for g in c3}
    por = {}
    for i, g in enumerate(gs):
        for k in {chave[x] for x in g}: por.setdefault(k, []).append(i)
    arqs = {}
    for k in sorted(por):
        ids = sorted(por[k], key=lambda i: (es[i]['mun'].zfill(4), es[i]['cnpj']))
        arqs[k] = gravar_gz('%s-%s.tsv.gz' % (uf, k), (linha(es[i]) for i in ids))
    for e in es:
        try:
            r = int(e['cnpj']).to_bytes(8, 'big') + bytes([cod_uf]) + int(e['cnae'] or 0).to_bytes(3, 'big') + min(65535, int(e['mun'] or 0)).to_bytes(2, 'big') \
                + bytes([min(255, int(e['porte'] or 0)), 0])
        except ValueError: continue
        cn.setdefault(e['cnpj'][:2], []).append(r)
    idx = {'formato': FORMATO, 'uf': uf, 'colunas': COLUNAS, 'total': len(es), 'grupos': chave, 'arquivos': arqs}
    nome = 'base-%s.json' % uf
    json.dump(idx, open(os.path.join(BASE, nome), 'w'), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return {'indice': nome, 'h': hashlib.sha1(open(os.path.join(BASE, nome), 'rb').read()).hexdigest()[:12], 'total': len(es), 'arquivos': len(arqs)}


def fechar(man, ufs, cn, completo):
    """Os cn-NN e o manifesto. Geração de alguns estados (teste) não grava o geral."""
    if not completo: return None
    cns = {}
    for pfx in sorted(cn):
        regs = sorted(set(cn[pfx]))
        nome = 'cn-%s.bin' % pfx; cam = os.path.join(BASE, nome)
        with open(cam, 'wb') as f: f.write(b''.join(regs))
        cns[pfx] = {'a': nome, 'n': len(regs), 'bytes': os.path.getsize(cam), 'h': hashlib.sha1(open(cam, 'rb').read()).hexdigest()[:12]}
    m = {'formato': FORMATO, 'mes': man['mes'], 'id': man['id'], 'gerado': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'colunas': COLUNAS, 'reg': REG,
         'total': sum(x['total'] for x in ufs.values()), 'ufs': ufs, 'cn': cns}
    json.dump(m, open(os.path.join(BASE, 'base.json'), 'w'), ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return m
