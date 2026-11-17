#!/usr/bin/env python3
"""Testes do perto.py com dados inventados (nenhuma empresa ou endereço de verdade). Uso: python3 teste_perto.py"""
import gzip, json, os, sys, tempfile, unittest, zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import perto  # noqa: E402

CAB = ('COD_UNICO_ENDERECO;COD_UF;COD_MUNICIPIO;COD_DISTRITO;COD_SUBDISTRITO;COD_SETOR;NUM_QUADRA;NUM_FACE;CEP;DSC_LOCALIDADE;NOM_TIPO_SEGLOGR;'
       'NOM_TITULO_SEGLOGR;NOM_SEGLOGR;NUM_ENDERECO;DSC_MODIFICADOR;NOM_COMP_ELEM1;VAL_COMP_ELEM1;COD_ESPECIE;DSC_ESTABELECIMENTO;'
       'COD_INDICADOR_ESTAB_ENDERECO;COD_INDICADOR_FINALIDADE_CONST;COD_TIPO_ESPECI;LATITUDE;LONGITUDE;NV_GEO_COORD')


def estab(cnpj, fant, ini, log, num, cep, mei='0', razao='EMPRESA FICTICIA LTDA', cnae='4712100'):
    return '\t'.join([cnpj, '1', fant, cnae, ini, log, num, '', 'CENTRO', cep, 'SP', '7107', '11999990000', '', 'x@exemplo.test', razao, '2062', '1', '1000', mei, '']) + '\n'


def cnefe(cep, tipo, tit, nome, num, lat, lng, niv='1', mun='3550308'):
    return ';'.join(['1', '35', mun, '', '', '', '', '', cep, 'CENTRO', tipo, tit, nome, str(num), '', '', '', '1', '', '', '', '', str(lat), str(lng), niv])


class Nomes(unittest.TestCase):
    def test_rua_igual_dos_dois_lados(self):
        self.assertEqual(perto.rua_norm('R. DR. João Pessôa'), perto.rua_norm('RUA', 'DOUTOR', 'JOAO PESSOA'))
        self.assertEqual(perto.rua_norm('AV 9 DE JULHO'), perto.rua_norm('AVENIDA', '', 'NOVE DE JULHO'))
        self.assertEqual(perto.rua_norm('RUA VINTE E CINCO DE MARÇO'), perto.rua_norm('RUA', '', '25 DE MARCO'))
        self.assertEqual(perto.rua_norm('PCA. DA SÉ'), 'SE')
        self.assertEqual(perto.rua_norm('AV. PRES. VARGAS'), perto.rua_norm('AVENIDA', 'PRESIDENTE', 'VARGAS'))
        self.assertEqual(perto.rua_norm('RUA 07'), '7')
        self.assertEqual(perto.rua_norm('RUA'), 'RUA')            # rua que só tem o tipo não some

    def test_numero(self):
        self.assertEqual(perto.num_norm('0131 A'), '131')
        self.assertEqual(perto.num_norm('Nº 12'), '12')
        self.assertEqual(perto.num_norm('S/N'), '')
        self.assertEqual(perto.num_norm(''), '')
        self.assertEqual(perto.num_norm('12345678'), '')         # telefone no lugar do número

    def test_metros(self):
        self.assertAlmostEqual(perto.metros(-23.55, -46.63, -23.55, -46.63), 0, places=3)
        self.assertTrue(1050 < perto.metros(-23.55, -46.63, -23.56, -46.63) < 1170)


class Geracao(unittest.TestCase):
    def setUp(self):
        self.antes = os.getcwd()
        self.tmp = tempfile.TemporaryDirectory()
        os.chdir(self.tmp.name)
        os.makedirs('saida'); os.makedirs('cnefe')
        linhas = [
            estab('11111111000101', 'MERCADO AURORA', '2026-09-10', 'R. DR. JOÃO PESSÔA', '120', '01001000'),
            estab('11111111000202', 'PADARIA BOA VISTA', '2019-01-05', 'RUA DOUTOR JOAO PESSOA', '0131 A', '01001000'),
            estab('11111111000303', 'EMPORIO DO VALE', '2026-10-01', 'AV 9 DE JULHO', 'S/N', '01002000'),
            estab('11111111000404', 'LOJA SEM RUA', '2026-08-01', 'ESTRADA QUE NAO EXISTE', '5', '01002000'),
            estab('11111111000505', 'CEP DE CIDADE INTEIRA', '2026-08-01', 'RUA QUE O IBGE NAO TEM', '5', '13900000'),
            estab('11111111000606', 'CEP DESCONHECIDO', '2026-08-01', 'RUA A', '5', '99999999'),
            estab('11111111000707', 'MEI FORA', '2026-08-01', 'RUA A', '5', '01001000', mei='1'),
            estab('11111111000808', '', '2020-08-01', 'PCA. DA SÉ', '10', '01001000', razao='RAZAO SOCIAL USADA LTDA'),
            estab('11111111000909', 'PEDIU PARA SAIR', '2026-08-01', 'PCA. DA SÉ', '10', '01001000'),
        ]
        with gzip.open('saida/estab-SP-abc123.tsv.gz', 'wt', encoding='utf-8') as f: f.writelines(linhas)
        json.dump({'mes': '2026-11', 'id': 'abc123', 'ufs': {'SP': {'linhas': len(linhas)}}}, open('saida/manifesto.json', 'w'))
        c = [CAB,
             cnefe('01001000', 'RUA', 'DOUTOR', 'JOAO PESSOA', 120, -23.5501, -46.6331),
             cnefe('01001000', 'RUA', 'DOUTOR', 'JOAO PESSOA', 128, -23.5503, -46.6333),
             cnefe('01001000', 'RUA', 'DOUTOR', 'JOAO PESSOA', 300, -23.5520, -46.6350),
             cnefe('01001000', 'PRACA', '', 'DA SE', 10, -23.5505, -46.6340),
             cnefe('01001000', 'PRACA', '', 'DA SE', 10, -23.5507, -46.6342),
             cnefe('01001000', 'RUA', '', 'LONGE', 1, -10.0, -46.0, '6'),
             cnefe('01002000', 'AVENIDA', '', 'NOVE DE JULHO', 100, -23.5600, -46.6500),
             cnefe('01002000', 'AVENIDA', '', 'NOVE DE JULHO', 200, -23.5610, -46.6510),
             cnefe('13900000', 'RUA', '', 'A', 1, -22.70, -46.76, mun='3501608'),
             cnefe('13900000', 'RUA', '', 'B', 1, -22.75, -46.80, mun='3501608')]
        with zipfile.ZipFile('cnefe/35_SP.zip', 'w') as z: z.writestr('35_SP.csv', '\n'.join(c) + '\n')
        import hashlib
        self.optout = {hashlib.sha256(b'11111111000909').hexdigest()}

    def tearDown(self):
        os.chdir(self.antes); self.tmp.cleanup()

    def gerar(self):
        os.makedirs('perto', exist_ok=True)
        r = perto.fazer_uf('SP', self.optout, '2026-11-17', 'cnefe')
        idx = json.load(open('perto/indice-SP.json'))
        linhas = {}
        for f in idx['folhas']:
            for l in open('perto/' + f['a'], encoding='utf-8'):
                p = l.rstrip('\n').split('\t'); linhas[p[0]] = dict(zip(perto.COLUNAS, p))
        return r, idx, linhas

    def test_precisao_de_cada_endereco(self):
        r, idx, l = self.gerar()
        self.assertEqual(l['11111111000101']['prec'], 'n')
        self.assertEqual((l['11111111000101']['lat'], l['11111111000101']['lng']), ('-23.55010', '-46.63310'))
        self.assertEqual(l['11111111000202']['prec'], 'p')                       # 131 não existe: fica no 128
        self.assertEqual(l['11111111000202']['lat'], '-23.55030')
        self.assertEqual(l['11111111000303']['prec'], 'r')                       # sem número: o meio da rua
        self.assertEqual(l['11111111000303']['lat'], '-23.56050')
        self.assertEqual(l['11111111000404']['prec'], 'c')                       # rua que o IBGE não tem: o meio do CEP
        self.assertEqual(l['11111111000808']['prec'], 'n')
        self.assertEqual(l['11111111000808']['lat'], '-23.55060')                # média dos dois endereços iguais
        self.assertEqual(l['11111111000808']['nome'], 'RAZAO SOCIAL USADA LTDA')
        self.assertEqual(l['11111111000101']['ibge'], '3550308')

    def test_quem_fica_fora(self):
        r, idx, l = self.gerar()
        self.assertNotIn('11111111000707', l)                                     # MEI
        self.assertNotIn('11111111000909', l)                                     # pediu para não ser contatado
        self.assertNotIn('11111111000505', l)                                     # CEP de cidade inteira: sem "perto"
        self.assertNotIn('11111111000606', l)                                     # CEP que o IBGE não tem
        self.assertEqual(r['precisao'], {'n': 2, 'p': 1, 'r': 1, 'c': 1, 'm': 2})
        self.assertEqual((r['total'], r['perto']), (7, 5))

    def test_sem_telefone_nem_email(self):
        self.gerar()
        for a in os.listdir('perto'):
            t = open('perto/' + a, encoding='utf-8').read()
            self.assertNotIn('11999990000', t); self.assertNotIn('exemplo.test', t)

    def test_novos(self):
        r, idx, l = self.gerar()
        novos = [x.split('\t')[0] for x in open('perto/novos-SP.tsv', encoding='utf-8')]
        self.assertEqual(sorted(novos), ['11111111000101', '11111111000303', '11111111000404', '11111111000505', '11111111000606'])
        self.assertEqual(idx['novos']['n'], 5)

    def test_indice_bate_com_os_arquivos(self):
        import hashlib
        r, idx, l = self.gerar()
        self.assertEqual(sum(f['n'] for f in idx['folhas']), r['perto'])
        for f in idx['folhas']:
            b = open('perto/' + f['a'], 'rb').read()
            self.assertEqual(hashlib.sha1(b).hexdigest()[:12], f['h'])
            self.assertEqual(len(b), f['bytes'])
            for x in b.decode().strip().split('\n'):
                p = x.split('\t'); la = float(p[4]); lo = float(p[5])
                self.assertTrue(f['b'][0] <= la < f['b'][2] and f['b'][1] <= lo < f['b'][3], (f, la, lo))

    def test_quadrado_cheio_divide(self):
        antes = (perto.MAX_LINHAS, perto.MAX_PEDACOS)
        try:
            perto.MAX_LINHAS = 2
            r, idx, l = self.gerar()
            self.assertGreater(len(idx['folhas']), 1)
            self.assertTrue(all(f['n'] <= 2 or (f['b'][2] - f['b'][0]) <= perto.LADO_MIN + 1e-6 for f in idx['folhas']))
            self.assertEqual(sum(f['n'] for f in idx['folhas']), 5)
            perto.MAX_PEDACOS = 1                                                 # pedaços demais: junta em pedaços maiores
            for a in os.listdir('perto'): os.remove('perto/' + a)
            r, idx, l = self.gerar()
            self.assertEqual(len(idx['folhas']), 1)
            self.assertEqual(len(os.listdir('perto')), 3)                         # 1 pedaço + novos + índice
            self.assertEqual(perto.MAX_LINHAS, 2)
        finally:
            perto.MAX_LINHAS, perto.MAX_PEDACOS = antes

    def test_cabecalho_diferente_para_tudo(self):
        with zipfile.ZipFile('cnefe/35_SP.zip', 'w') as z: z.writestr('35_SP.csv', 'A;B;C\n1;2;3\n')
        os.makedirs('perto', exist_ok=True)
        with self.assertRaises(SystemExit): perto.fazer_uf('SP', set(), '2026-11-17', 'cnefe')

    def test_virgula_e_aspas(self):
        c = [CAB.replace(';', ','), cnefe('01001000', 'RUA', 'DOUTOR', '"JOAO PESSOA"', 120, -23.5, -46.6).replace(';', ',')]
        with zipfile.ZipFile('cnefe/35_SP.zip', 'w') as z: z.writestr('35_SP.csv', '\n'.join(c) + '\n')
        r, idx, l = self.gerar()
        self.assertEqual(l['11111111000101']['prec'], 'n')

    # ---- a base em arquivos (o que Clientes novos lê no lugar do banco)
    def base(self, extra=()):
        import base_arq
        if extra:
            with gzip.open('saida/estab-SP-abc123.tsv.gz', 'at', encoding='utf-8') as f: f.writelines(extra)
        cn = {}; os.makedirs('perto', exist_ok=True)
        r = perto.fazer_uf('SP', self.optout, '2026-11-17', 'cnefe', cn)
        idx = json.load(open('base/base-SP.json'))
        linhas = {}
        for k, a in idx['arquivos'].items():
            for l in gzip.open('base/' + a['a'], 'rt', encoding='utf-8'):
                p = l.rstrip('\n').split('\t'); linhas.setdefault(k, {})[p[0]] = dict(zip(base_arq.COLUNAS, p))
        return r, idx, linhas, cn

    def test_base_tem_tudo_que_a_busca_usa(self):
        r, idx, l, cn = self.base()
        e = l['d47']['11111111000101']
        self.assertEqual((e['fantasia'], e['razao'], e['tel1'], e['email'], e['mun'], e['matriz'], e['porte'], e['capital'], e['natureza']),
                         ('MERCADO AURORA', 'EMPRESA FICTICIA LTDA', '11999990000', 'x@exemplo.test', '7107', '1', '1', '1000', '2062'))
        self.assertEqual((e['lat'], e['lng'], e['prec'], e['logradouro'], e['numero']), ('-23.55010', '-46.63310', 'n', 'R. DR. JOÃO PESSÔA', '120'))
        # a empresa que o mapa não acha (só a cidade) entra na base, sem coordenada: a busca usa o centro da cidade
        self.assertEqual((l['d47']['11111111000606']['lat'], l['d47']['11111111000606']['prec']), ('', 'm'))
        self.assertEqual((l['d47']['11111111000505']['lat'], l['d47']['11111111000505']['prec']), ('', 'm'))
        self.assertNotIn('11111111000707', l['d47']); self.assertNotIn('11111111000909', l['d47'])      # MEI e quem pediu para sair
        self.assertEqual((r['base']['total'], idx['total'], idx['grupos']), (7, 7, {'471': 'd47'}))

    def test_base_secundaria_entra_no_arquivo_do_outro_ramo(self):
        ex = estab('11111111001010', 'TINTAS E MERCADO', '2021-01-01', 'RUA A', '5', '01001000')[:-1] + '4712100,4741500,4744099\n'
        r, idx, l, cn = self.base([ex])
        self.assertEqual(idx['grupos'], {'471': 'd47', '474': 'd47'})
        self.assertEqual(l['d47']['11111111001010']['sec'], '4741500,4744099')
        ex2 = estab('11111111001111', 'OFICINA', '2021-01-01', 'RUA A', '5', '01001000', cnae='4520001')[:-1] + '4520001,4530703\n'
        r, idx, l, cn = self.base([ex2])
        self.assertEqual(sorted(idx['arquivos']), ['d45', 'd47'])
        self.assertIn('11111111001111', l['d45']); self.assertNotIn('11111111001111', l['d47'])

    def test_base_divisao_grande_separa_por_grupo(self):
        import base_arq
        antes = base_arq.DIVISAO_MAX; base_arq.DIVISAO_MAX = 3
        try:
            ex = estab('11111111001010', 'TINTAS', '2021-01-01', 'RUA A', '5', '01001000', cnae='4741500')[:-1] + '4741500,4712100\n'
            r, idx, l, cn = self.base([ex])
        finally: base_arq.DIVISAO_MAX = antes
        self.assertEqual(idx['grupos'], {'471': 'g471', '474': 'g474'})
        self.assertIn('11111111001010', l['g471']); self.assertIn('11111111001010', l['g474'])           # principal num, secundária no outro
        self.assertEqual(len(l['g474']), 1)

    def test_base_arquivo_igual_tem_o_mesmo_hash(self):
        import hashlib
        r, idx, l, cn = self.base()
        a = idx['arquivos']['d47']; b = open('base/' + a['a'], 'rb').read()
        self.assertEqual((hashlib.sha1(b).hexdigest()[:12], len(b), a['n']), (a['h'], a['bytes'], 7))
        r2, idx2, l2, cn2 = self.base()
        self.assertEqual(idx2['arquivos']['d47']['h'], a['h'])                                           # gerar de novo não muda o arquivo: não sobe outra vez

    def test_cnpj_em_ordem_para_a_busca_binaria(self):
        import base_arq
        r, idx, l, cn = self.base()
        m = base_arq.fechar({'mes': '2026-11', 'id': 'abc123'}, {'SP': r['base']}, cn, True)
        self.assertEqual((m['total'], m['reg'], sorted(m['cn']), m['cn']['11']['n']), (7, 16, ['11'], 7))
        b = open('base/cn-11.bin', 'rb').read()
        regs = [b[i:i + 16] for i in range(0, len(b), 16)]
        self.assertEqual(regs, sorted(regs)); self.assertEqual(len(b), 7 * 16)
        self.assertEqual((int.from_bytes(regs[0][:8], 'big'), regs[0][8], int.from_bytes(regs[0][9:12], 'big'), int.from_bytes(regs[0][12:14], 'big'), regs[0][14]),
                         (11111111000101, 35, 4712100, 7107, 1))
        self.assertIsNone(base_arq.fechar({'mes': '2026-11', 'id': 'abc123'}, {'SP': r['base']}, cn, False))   # teste de alguns estados não troca o geral


if __name__ == '__main__':
    unittest.main(verbosity=1)
