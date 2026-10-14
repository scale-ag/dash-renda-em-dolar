# -*- coding: utf-8 -*-
"""
Configuração do cliente — TEMPLATE.

Este é o ÚNICO arquivo que precisa ser editado para colocar o funil de um
cliente novo no ar. Já preenchido para Bruno Corano — Renda em Dólar (o build
se recusa a rodar enquanto algum marcador de texto continuar aqui).
Ordem completa: "CHECKLIST DE NOVO CLIENTE" no topo do CLAUDE.md.

Depois de editar, teste localmente:

    python build/build.py --meta-file meta.csv --sales-file sales.csv --out dist/index.html

`build/config.example.py` é a cópia intacta deste modelo — mantenha-o
sem preencher, para restaurar o config.py se precisar começar do zero.
"""
from __future__ import annotations

# ==========================================================================
# 1) PLANILHA(S) DO CLIENTE (Google Sheets)
# ==========================================================================
# SPREADSHEET_ID: o trecho entre /d/ e /edit na URL da planilha
#   (https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit#gid=...)
# GID_META / GID_SALES: o número depois de "gid=" na URL de cada aba.
# A planilha precisa estar com o link público em modo "Qualquer pessoa com
# o link pode visualizar" (o build lê via export CSV, SOMENTE LEITURA).
SPREADSHEET_ID = "1iIMkIbI7Ks-fxxaB0Lq0UHXRLcPYHsdMnSUqNfWwlGA"  # RD | Extração Queries
# Opcional: se a lista de Compradores estiver em OUTRA planilha, coloque o ID
# dela aqui. Vazio = Compradores na mesma planilha do Meta Ads (padrão).
# Compradores = aba DADOS_HOTMART da planilha "RD-P01 | ACOMPANHAMENTO GERAL | LOOKER"
SPREADSHEET_ID_SALES = "1IhhBlPT6TBcI9FBMcO_zcP8SDK0ctYuwEv8vvSEF1Ow"
GID_META = "0"            # aba "Meta Ads"
GID_SALES = "953734831"   # aba "DADOS_HOTMART"

# ==========================================================================
# 2) REGRAS DE NEGÓCIO
# ==========================================================================
# Fator de imposto aplicado sobre o gasto do Meta Ads quando o toggle
# "Imposto Meta" estiver ligado. Use 1.0 se o cliente não tiver imposto.
TAX_FACTOR = 1.1383

# Produto principal do funil (base de Vendas/CAC/ConvCHK/Ticket). Casamento
# por PREFIXO sobre o nome NORMALIZADO (sem acento, minúsculas) da coluna
# Produto da planilha de Compradores — escreva sem acento e em minúsculas.
MAIN_PRODUCT_PREFIX = "renda em dolar"

# Qual coluna UTM da planilha de Compradores carrega o Ad Name do Meta:
# "utm_content", "utm_term" ou "utm_medium". Depende do parametrizador de URL
# dos anúncios do cliente — CONFIRA nos dados antes de assumir: a coluna que
# não carrega o anúncio costuma trazer o posicionamento (Instagram_Feed/Stories),
# e casar pela coluna errada zera as atribuições.
AD_UTM_COLUMN = "utm_content"   # utm_term traz o posicionamento (Instagram_Feed/Reels...)

# A planilha de Compradores tem uma coluna de status de pagamento confiável?
# SIM -> False (o build filtra por is_paid()). NÃO (toda linha já é uma compra
# concretizada) -> True (conta todas as linhas como venda paga).
# DADOS_HOTMART não tem coluna de status: toda linha é compra aprovada.
COUNT_ALL_AS_PAID = True

# Valores de utm_source que identificam venda vinda do Meta Ads. Venda do
# produto principal com essa origem conta na aba Meta Ads mesmo se a UTM não
# casar com uma linha do Meta. Vazio = só o match campanha+anúncio vale.
META_UTM_SOURCES = ["fb"]

# ==========================================================================
# 3) RÓTULOS EXIBIDOS NA INTERFACE
# ==========================================================================
CLIENT_NAME = "Bruno Corano"
CLIENT_SUB = "Renda em Dólar — Funil VSL"
TAX_LABEL = "Imposto Meta ×1,1383"
MAIN_PRODUCT = "Renda em Dólar"

# ==========================================================================
# 4) METAS (aba Relatórios) — código de cor de CAC/ROAS
# ==========================================================================
#   • ROAS: quanto MAIOR, melhor  -> desempenho = roas / ROAS_TARGET
#   • CAC : quanto MENOR, melhor  -> desempenho = CAC_TARGET / cac
# Faixas (sobre o desempenho): <REPORT_BAND_LOW vermelho · até 0,99 amarelo ·
#   até REPORT_BAND_HIGH verde · acima disso azul-ciano.
# CAC alvo = ticket médio (~R$ 324, ago–out/2026) ÷ ROAS alvo 2,0
CAC_TARGET = 162.0
# ROAS alvo definido pelo gestor (Faturamento / Gasto)
ROAS_TARGET = 2.0
REPORT_BAND_LOW = 0.70
REPORT_BAND_HIGH = 1.30

# ==========================================================================
# 5) IA INSIGHTS (Cloudflare Worker) — ver SETUP-IA.md
# ==========================================================================
# URL pública do Worker (não é secreta). Vazio = aba IA Insights indisponível.
# Preencher depois de publicar o Worker (checklist do CLAUDE.md).
# Preencher com https://renda-em-dolar-ia-insights.<subdominio>.workers.dev
# depois de publicar o Worker (SETUP-IA.md).
IA_WORKER_URL = ""
