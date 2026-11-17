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


if __name__ == '__main__':
    unittest.main(verbosity=1)
