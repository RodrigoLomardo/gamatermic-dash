#!/usr/bin/env python3
"""Gera docs/exemplos/vendas_exemplo_2022_2026.csv: vendas FICTICIAS (empresas e nomes inventados) para testar dashboards.

Determinístico (seed fixa). Formato igual ao do relatorio Ploomes: ';' como separador, datas dd/mm/aaaa, decimais com virgula.
Uso: python3 scripts/gerar-vendas-exemplo.py [saida.csv]
"""
import csv
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

random.seed(2026)
INI, FIM = date(2022, 1, 1), date(2026, 11, 1)

# zona -> (peso de vendas, {UF: peso}, fator de preco)
ZONAS = {
    "Sudeste": (0.44, {"SP": 6, "RJ": 2.2, "MG": 2, "ES": 0.6}, 1.00),
    "Sul": (0.19, {"PR": 1.6, "RS": 1.5, "SC": 1.3}, 1.03),
    "Nordeste": (0.17, {"BA": 1.6, "PE": 1.2, "CE": 1.1, "MA": 0.5, "RN": 0.4, "PB": 0.4, "AL": 0.3, "SE": 0.3, "PI": 0.3}, 0.95),
    "Centro-Oeste": (0.12, {"GO": 1.2, "MT": 1.1, "MS": 0.8, "DF": 1.0}, 1.02),
    "Norte": (0.08, {"PA": 1.0, "AM": 1.0, "TO": 0.4, "RO": 0.4, "AC": 0.2, "RR": 0.15, "AP": 0.15}, 0.97),
}
# categoria -> (produtos com preco medio, peso, sazonalidade: mes de pico)
CATEGORIAS = {
    "Válvulas": ([("Válvula esfera 1/2\"", 180), ("Válvula gaveta 2\"", 640), ("Válvula borboleta 4\"", 1450), ("Válvula de segurança", 2300)], 0.26, 3),
    "Bombas": ([("Bomba centrífuga 1cv", 1900), ("Bomba submersa 3cv", 4200), ("Bomba dosadora", 3100), ("Bomba de vácuo", 5600)], 0.20, 9),
    "Instrumentação": ([("Transmissor de pressão", 1250), ("Medidor de vazão", 3900), ("Sensor de temperatura", 420), ("Manômetro inox", 160)], 0.18, 6),
    "Tubulação": ([("Tubo aço carbono 6m", 520), ("Conexão flangeada", 95), ("Curva 90° inox", 140), ("Junta espiralada", 55)], 0.15, 11),
    "Automação": ([("CLP compacto", 3800), ("Inversor de frequência", 2700), ("Painel de comando", 8200), ("IHM 7\"", 1900)], 0.11, 8),
    "Serviços": ([("Manutenção preventiva", 2400), ("Instalação e comissionamento", 7800), ("Calibração", 650), ("Treinamento técnico", 3200)], 0.10, 12),
}
SEGMENTOS = {"Óleo e Gás": 0.2, "Alimentos e Bebidas": 0.17, "Químico": 0.14, "Mineração": 0.1, "Saneamento": 0.13, "Energia": 0.1, "Farmacêutico": 0.06, "Papel e Celulose": 0.05, "Automotivo": 0.05}
CANAIS = {"Venda direta": 0.45, "Representante": 0.25, "Distribuidor": 0.2, "E-commerce B2B": 0.1}
PAGAMENTOS = {"Boleto 28 dias": 0.35, "Boleto 30/60": 0.2, "PIX": 0.15, "Cartão corporativo": 0.1, "Transferência": 0.12, "À vista": 0.08}
VENDEDORES = ["Ana Paula Ribeiro", "Bruno Carvalho", "Camila Torres", "Diego Martins", "Eduarda Lopes", "Felipe Andrade", "Gabriela Nunes", "Henrique Souza",
              "Isabela Moura", "João Vitor Pires", "Karina Duarte", "Leonardo Faria"]
VEND_ZONA = {v: random.choice(list(ZONAS)) for v in VENDEDORES}  # cada um tem zona preferida (60% das vendas)

A = ["Aço", "Alfa", "Atlântica", "Brasil", "Central", "Delta", "Eletro", "Fluxo", "Global", "Hidro", "Indu", "Jupiter", "Kappa", "Litoral", "Metal", "Nova",
     "Ômega", "Petro", "Quimi", "Rio", "Sider", "Terra", "Ultra", "Vale", "Zênite", "Norte", "Sul", "Planalto", "Pampa", "Amazônia"]
B = ["Química", "Industrial", "Engenharia", "Alimentos", "Energia", "Mineração", "Saneamento", "Papel", "Plásticos", "Bebidas", "Fertilizantes", "Logística", "Petróleo", "Têxtil"]
SUF = ["Ltda", "S.A.", "Indústria", "do Brasil", "Group"]


def pick(d):
    return random.choices(list(d), weights=list(d.values()))[0]


# ---- clientes (fixos: mesma UF/segmento sempre) ----
clientes, nomes = [], set()
while len(clientes) < 320:
    nome = f"{random.choice(A)} {random.choice(B)} {random.choice(SUF)}"
    if nome in nomes:
        continue
    nomes.add(nome)
    zona = random.choices(list(ZONAS), weights=[z[0] for z in ZONAS.values()])[0]
    uf = pick(ZONAS[zona][1])
    porte = random.choices(["Pequeno", "Médio", "Grande"], weights=[0.5, 0.35, 0.15])[0]
    # curva ABC: poucos clientes concentram o volume (Pareto)
    peso = {"Pequeno": 1, "Médio": 4, "Grande": 14}[porte] * random.lognormvariate(0, 0.6)
    entrada = INI + timedelta(days=int(random.betavariate(1.2, 2.2) * (FIM - INI).days))  # clientes entram ao longo do tempo
    clientes.append({"nome": nome, "zona": zona, "uf": uf, "segmento": pick(SEGMENTOS), "porte": porte, "peso": peso, "entrada": entrada})

dias = (FIM - INI).days
pedido = 100000
linhas = []
for i in range(dias + 1):
    d = INI + timedelta(days=i)
    if d.weekday() == 6:
        continue
    # volume diario: tendencia de crescimento (~18%/ano) + sazonalidade + sabado fraco + fim de mes forte + choque (2022-S2 retracao)
    anos = i / 365
    base = 24 * (1.18 ** anos)
    sazon = 1 + 0.18 * math.sin((d.month - 3) / 12 * 2 * math.pi) + (0.25 if d.month in (11, 12) else 0)
    base *= sazon * (0.4 if d.weekday() == 5 else 1) * (1.35 if d.day >= 26 else 1) * (0.8 if (d.year == 2022 and d.month >= 7 and d.month <= 9) else 1)
    if d.month == 1 and d.day <= 6 or (d.month == 12 and d.day >= 24):
        base *= 0.3
    n = max(0, int(random.gauss(base, base * 0.25)))
    ativos = [c for c in clientes if c["entrada"] <= d]
    if not ativos:
        continue
    pesos = [c["peso"] for c in ativos]
    for _ in range(n):
        c = random.choices(ativos, weights=pesos)[0]
        cat = random.choices(list(CATEGORIAS), weights=[v[1] * (1 + 0.35 * math.cos((d.month - v[2]) / 12 * 2 * math.pi)) for v in CATEGORIAS.values()])[0]
        prod, preco = random.choice(CATEGORIAS[cat][0])
        # vendedor: 60% da zona dele
        pool = [v for v in VENDEDORES if VEND_ZONA[v] == c["zona"]] or VENDEDORES
        vend = random.choice(pool) if random.random() < 0.6 else random.choice(VENDEDORES)
        canal = pick(CANAIS) if c["porte"] != "Grande" else random.choices(list(CANAIS), weights=[0.7, 0.1, 0.15, 0.05])[0]
        qtd = max(1, int(random.lognormvariate({"Pequeno": 0.4, "Médio": 1.0, "Grande": 1.7}[c["porte"]], 0.7))) if cat != "Serviços" else random.choice([1, 1, 1, 2, 3])
        unit = preco * ZONAS[c["zona"]][2] * (1.06 ** anos) * random.uniform(0.9, 1.12)  # inflacao + variacao
        desc = random.choice([0, 0, 0, 2, 3, 5, 5, 8, 10, 12, 15]) + (3 if c["porte"] == "Grande" else 0) + (2 if canal == "Distribuidor" else 0)
        valor = unit * qtd * (1 - desc / 100)
        margem_pct = {"Válvulas": 0.34, "Bombas": 0.29, "Instrumentação": 0.38, "Tubulação": 0.22, "Automação": 0.31, "Serviços": 0.52}[cat] - desc / 200 + random.uniform(-0.05, 0.05)
        custo = valor * (1 - margem_pct)
        r = random.random()
        status = "Cancelado" if r < 0.035 else "Devolvido" if r < 0.05 else "Em entrega" if (FIM - d).days < 10 and r < 0.6 else "Entregue"
        entrega = max(1, int(random.gauss({"Sudeste": 4, "Sul": 6, "Centro-Oeste": 8, "Nordeste": 10, "Norte": 15}[c["zona"]], 2.5)))
        nota = None if status in ("Cancelado", "Em entrega") else min(5, max(1, round(random.gauss(4.3 - entrega / 25 - (1.5 if status == "Devolvido" else 0), 0.8))))
        pedido += 1
        linhas.append([pedido, d, c["nome"], c["segmento"], c["porte"], c["zona"], c["uf"], cat, prod, vend, canal, pick(PAGAMENTOS), qtd,
                       unit, desc, valor, custo, status, entrega, nota, "Sim" if (d - c["entrada"]).days < 30 else "Não"])

brl = lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
saida = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "docs/exemplos/vendas_exemplo_2022_2026.csv")
saida.parent.mkdir(parents=True, exist_ok=True)
with saida.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, delimiter=";", lineterminator="\n")
    w.writerow(["Pedido", "Data do Pedido", "Cliente", "Segmento do Cliente", "Porte do Cliente", "Zona do Brasil", "Estado", "Categoria", "Produto", "Vendedor",
                "Canal de Venda", "Forma de Pagamento", "Quantidade", "Preço Unitário", "Desconto (%)", "Valor", "Custo", "Status", "Prazo de Entrega (dias)",
                "Avaliação (1-5)", "Cliente Novo"])
    for r in linhas:
        r[1] = r[1].strftime("%d/%m/%Y")
        r[13], r[15], r[16] = brl(r[13]), brl(r[15]), brl(r[16])
        r[14] = str(r[14]).replace(".", ",")
        r[19] = "" if r[19] is None else r[19]
        w.writerow(r)
print(f"{len(linhas)} vendas -> {saida} ({saida.stat().st_size / 1e6:.1f} MB)")
