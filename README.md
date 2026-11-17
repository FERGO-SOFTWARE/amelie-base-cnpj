# amelie-base-cnpj

Gera, todo mês, a base de empresas ativas que a AMELIE usa em **Clientes novos**.

A Receita Federal publica os dados abertos de CNPJ (vários GB). Em vez de a hospedagem do site
ler tudo isso, uma máquina do GitHub faz o trabalho pesado (`gerar.py`):

1. baixa os arquivos do mês (Estabelecimentos, Empresas, Simples, Cnaes);
2. fica só com as empresas **ATIVAS** das atividades que os representantes visitam
   (`universo.txt` + as que os representantes acrescentaram, lidas do site);
3. junta razão social, porte e MEI; tira o CPF que a Receita gruda na razão de empresário individual;
4. separa por estado e publica em **Releases** (`estab-UF-<id>.tsv.gz`, `cnaes-<id>.tsv.gz`, `manifesto.json`).

O site lê `releases/latest/download/manifesto.json`, baixa só os estados de que precisa e grava.

Roda sozinho todo dia às 06:17 (Brasília) e só gera quando há mês novo ou mudança nas atividades.
Para forçar: Actions › Base de CNPJ › Run workflow.

Só dado público de CNPJ (Lei de Acesso à Informação).

## Perto de você (`perto.py`)

Depois que a base do mês sai, o workflow **Perto de você** põe coordenada em cada empresa (endereços do CNEFE 2022, do IBGE) e publica em pedaços pequenos do mapa:

- um release por estado, `perto-UF`: `UF-<quadrado>.tsv` (até ~8 mil empresas cada), `novos-UF.tsv` (abertas nos últimos 200 dias) e `indice-UF.json`;
- o release `perto`, com o `perto.json` (mês, colunas e onde está o índice de cada estado).

Colunas: `cnpj, nome, cnae, inicio, lat, lng, prec, logradouro, numero, bairro, cep, ibge, porte`. `prec` diz o quanto a coordenada é exata: `n` no número, `p` perto do número, `r` na rua, `c` no CEP, `m` só a cidade (fica fora dos pedaços).

Sem telefone e sem e-mail. MEI fica fora. Quem pediu para não ser contatado fica fora.

Testes (dados inventados): `python3 teste_perto.py`.
