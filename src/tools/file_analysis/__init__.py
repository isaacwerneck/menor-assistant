"""Leitura local de arquivos com armazenamento privado e execução limitada.

API para integrar: ingest(data, filename) -> recibo; inspect(file_id) -> recibo.
O arquivo é sempre identificado por token aleatório, nunca por caminho do usuário.
"""
from src.tools.file_analysis.service import capabilities, ingest, inspect

__all__ = ("capabilities", "ingest", "inspect")
