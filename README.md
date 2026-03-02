# Sistema de Detecção de Impedimento Judicial

Aplicação web que analisa PDFs de processos judiciais e verifica se um juiz convocado atuou no primeiro grau, configurando impedimento legal para atuar no segundo grau.

## Como funciona

O sistema extrai o texto de cada PDF e procura por evidências de que o juiz informado praticou atos jurisdicionais de primeiro grau no processo. A detecção é baseada em:

- Títulos de primeiro grau próximos ao nome do juiz (ex.: "Juiz de Direito", "MM. Juíza")
- Blocos de assinatura em decisões ou sentenças
- Atos jurisdicionais no mesmo contexto do nome (ex.: "vistos", "decido", "sentencio")
- Menção à vara do juiz no documento (quando informada)

Páginas que contenham predominantemente marcadores de segundo grau (acórdão, câmara, desembargador etc.) são ignoradas para evitar falsos positivos.

### Níveis de confiança

| Nível | Cor | Critério |
|-------|-----|---------|
| ALTO | 🔴 | Nome + título de 1º grau **e** ato jurisdicional, ou bloco de assinatura |
| MÉDIO | 🟠 | Nome + título isolado, ou nome + vara confirmada (≥ 2 ocorrências) |
| BAIXO | 🟡 | Nome em ato jurisdicional isolado, ou apenas menção à vara |

## Requisitos

- Python 3.10 ou superior
- Dependências listadas em `requirements.txt`

## Instalação

```bash
# Clone ou copie o projeto para a pasta desejada

# Crie o ambiente virtual
python -m venv venv

# Ative o ambiente virtual
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Instale as dependências
pip install -r requirements.txt
```

## Execução

**Windows (duplo clique):**

Execute o arquivo `iniciar.bat`. Ele ativa o ambiente virtual e inicia a aplicação automaticamente.

**Linha de comando:**

```bash
streamlit run app.py
```

A aplicação abrirá no navegador em `http://localhost:8501`.

## Como usar

1. Na barra lateral, informe o **nome completo do juiz convocado**
2. Opcionalmente, informe a **vara do juiz** para aumentar a precisão
3. Faça o upload de um ou mais **arquivos PDF** dos processos
4. Clique em **Analisar Processos**
5. Visualize o resumo e o detalhamento das ocorrências encontradas
6. Exporte o relatório em **Excel (.xlsx)** ou **CSV**

## Estrutura do projeto

```
impedimento/
├── app.py              # Interface web (Streamlit)
├── detector.py         # Lógica de detecção de impedimento
├── requirements.txt    # Dependências Python
├── iniciar.bat         # Atalho de execução para Windows
└── venv/               # Ambiente virtual (criado localmente)
```

## Exportação de resultados

O relatório Excel gerado contém duas abas:

- **Resumo** — uma linha por processo com resultado, nível de confiança, vara identificada e número de ocorrências
- **Ocorrências Detalhadas** — cada ocorrência individualmente com página, tipo e trecho de contexto extraído do PDF

## Dependências

| Pacote | Uso |
|--------|-----|
| `streamlit` | Interface web |
| `pdfplumber` | Extração de texto de PDFs |
| `pandas` | Montagem de tabelas de resultado |
| `openpyxl` | Geração do relatório Excel |
