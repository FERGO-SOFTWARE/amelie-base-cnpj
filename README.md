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
