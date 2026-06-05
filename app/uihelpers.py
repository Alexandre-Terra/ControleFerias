"""Pequenos helpers de apresentação para os templates (avatar)."""

# Paleta de cores do avatar (mesma do protótipo de design).
_HUES = ["var(--info)", "var(--ok)", "var(--warn)", "var(--risk)", "#7C5CD6", "#0E9A8A"]


def iniciais(nome):
    """Iniciais do nome: 1ª letra do primeiro + 1ª do último sobrenome."""
    partes = (nome or "").strip().split()
    if not partes:
        return "?"
    primeiro = partes[0][0]
    ultimo = partes[-1][0] if len(partes) > 1 else ""
    return (primeiro + ultimo).upper()


def avatar_cor(nome):
    """Cor estável derivada do nome (determinística, sem estado)."""
    soma = sum(ord(c) for c in (nome or "")) % len(_HUES)
    return _HUES[soma]
