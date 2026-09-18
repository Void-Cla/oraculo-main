"""
Calculador de Risco e Lucro Líquido Real (PT-BR)
Garante que NENHUMA ordem seja emitida a menos que a projeção de retorno
cubra todas as taxas da exchange + slippage + pelo menos 0,01 centavo de lucro líquido garantido.
"""
from dataclasses import dataclass
from typing import Dict, Any, Tuple
from ..config import CONFIG

@dataclass
class ResultadoValidacaoLucro:
    autorizado: bool
    lucro_bruto_usd: float
    taxa_entrada_usd: float
    taxa_saida_usd: float
    slippage_usd: float
    taxas_totais_usd: float
    lucro_liquido_usd: float
    lucro_minimo_exigido_usd: float
    retorno_liquido_percentual: float
    margem_seguranca_centavos: float
    motivo_rejeicao: str = ""

class CalculadorLucroLiquido:
    def __init__(self, lucro_minimo_centavos_usd: float = CONFIG.LUCRO_MINIMO_LIQUIDO_USD):
        self.lucro_minimo_centavos_usd = lucro_minimo_centavos_usd

    def calcular_e_validar(
        self,
        direcao: str,
        preco_entrada: float,
        alvo_saida_preco: float,
        tamanho_quantidade: float,
        taxa_entrada_pct: float = CONFIG.TAXA_ENTRADA_PADRAO,
        taxa_saida_pct: float = CONFIG.TAXA_SAIDA_PADRAO,
        slippage_pct: float = CONFIG.SLIPPAGE_ESTIMADO
    ) -> ResultadoValidacaoLucro:
        """
        Calcula os valores exatos em dólares (USD/USDT) de taxas e lucro.
        Apenas autoriza se: lucro_liquido_usd >= lucro_minimo_centavos_usd (ex: 0.01 USD)
        """
        if preco_entrada <= 0 or alvo_saida_preco <= 0 or tamanho_quantidade <= 0:
            return ResultadoValidacaoLucro(
                autorizado=False,
                lucro_bruto_usd=0.0,
                taxa_entrada_usd=0.0,
                taxa_saida_usd=0.0,
                slippage_usd=0.0,
                taxas_totais_usd=0.0,
                lucro_liquido_usd=0.0,
                lucro_minimo_exigido_usd=self.lucro_minimo_centavos_usd,
                retorno_liquido_percentual=0.0,
                margem_seguranca_centavos=0.0,
                motivo_rejeicao="Preço ou quantidade inválidos"
            )

        valor_nocional_entrada = preco_entrada * tamanho_quantidade
        valor_nocional_saida = alvo_saida_preco * tamanho_quantidade

        if direcao.upper() == 'COMPRA' or direcao.upper() == 'BUY':
            lucro_bruto_usd = valor_nocional_saida - valor_nocional_entrada
        elif direcao.upper() == 'VENDA' or direcao.upper() == 'SELL':
            lucro_bruto_usd = valor_nocional_entrada - valor_nocional_saida
        else:
            return ResultadoValidacaoLucro(
                autorizado=False,
                lucro_bruto_usd=0.0,
                taxa_entrada_usd=0.0,
                taxa_saida_usd=0.0,
                slippage_usd=0.0,
                taxas_totais_usd=0.0,
                lucro_liquido_usd=0.0,
                lucro_minimo_exigido_usd=self.lucro_minimo_centavos_usd,
                retorno_liquido_percentual=0.0,
                margem_seguranca_centavos=0.0,
                motivo_rejeicao=f"Direção desconhecida: {direcao}"
            )

        # Taxas em USD
        taxa_entrada_usd = valor_nocional_entrada * taxa_entrada_pct
        taxa_saida_usd = valor_nocional_saida * taxa_saida_pct
        slippage_usd = (valor_nocional_entrada + valor_nocional_saida) * 0.5 * slippage_pct
        taxas_totais_usd = taxa_entrada_usd + taxa_saida_usd + slippage_usd

        # Lucro líquido final após TODAS as taxas
        lucro_liquido_usd = lucro_bruto_usd - taxas_totais_usd
        
        # Margem de segurança acima do 0,01 centavo
        margem_seguranca = lucro_liquido_usd - self.lucro_minimo_centavos_usd
        retorno_liquido_pct = (lucro_liquido_usd / valor_nocional_entrada) * 100.0 if valor_nocional_entrada > 0 else 0.0

        # Regra de Ouro: Deve ser maior ou igual a todas as taxas + 0,01 centavo
        if lucro_liquido_usd >= self.lucro_minimo_centavos_usd:
            return ResultadoValidacaoLucro(
                autorizado=True,
                lucro_bruto_usd=round(lucro_bruto_usd, 4),
                taxa_entrada_usd=round(taxa_entrada_usd, 4),
                taxa_saida_usd=round(taxa_saida_usd, 4),
                slippage_usd=round(slippage_usd, 4),
                taxas_totais_usd=round(taxas_totais_usd, 4),
                lucro_liquido_usd=round(lucro_liquido_usd, 4),
                lucro_minimo_exigido_usd=self.lucro_minimo_centavos_usd,
                retorno_liquido_percentual=round(retorno_liquido_pct, 3),
                margem_seguranca_centavos=round(margem_seguranca, 4),
                motivo_rejeicao=""
            )
        else:
            return ResultadoValidacaoLucro(
                autorizado=False,
                lucro_bruto_usd=round(lucro_bruto_usd, 4),
                taxa_entrada_usd=round(taxa_entrada_usd, 4),
                taxa_saida_usd=round(taxa_saida_usd, 4),
                slippage_usd=round(slippage_usd, 4),
                taxas_totais_usd=round(taxas_totais_usd, 4),
                lucro_liquido_usd=round(lucro_liquido_usd, 4),
                lucro_minimo_exigido_usd=self.lucro_minimo_centavos_usd,
                retorno_liquido_percentual=round(retorno_liquido_pct, 3),
                margem_seguranca_centavos=round(margem_seguranca, 4),
                motivo_rejeicao=(
                    f"Lucro líquido projetado (${lucro_liquido_usd:.4f}) é inferior ao "
                    f"mínimo exigido (${self.lucro_minimo_centavos_usd:.2f}) após taxas (${taxas_totais_usd:.4f}). "
                    f"Trade bloqueado para proteção do capital."
                )
            )

CALCULADOR_RISCO = CalculadorLucroLiquido()
