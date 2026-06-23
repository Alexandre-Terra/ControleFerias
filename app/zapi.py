"""Cliente HTTP da Z-API (envio de WhatsApp).

A Z-API expõe o envio de texto em
``POST {base_url}/instances/{id}/token/{token}/send-text`` com o header
``Client-Token`` e corpo JSON ``{"phone", "message"}``.

Segurança: o ``instance_token`` vai no PATH da URL e o ``client_token`` no
header. Nenhuma string devolvida por este módulo (nem mensagem de exceção) pode
conter esses segredos — ``_redigir`` os remove de qualquer ``detalhe`` antes de
retornar, no mesmo espírito de ``cli._banco_alvo`` (mascarar credenciais em log).
"""
import re

import requests

# (connect, read) em segundos. Falha de rede não pode travar o comando agendado.
TIMEOUT = (5, 15)


def normalizar_telefone(valor):
    """Mantém só dígitos; retorna ``None`` se não parecer um telefone.

    Aceita ``+55 (11) 99999-9999`` → ``5511999999999``. Valida 10–13 dígitos
    (fixo/celular nacional com DDI/DDD). Linhas inválidas são descartadas pelo
    chamador, evitando que a Z-API rejeite o lote inteiro.
    """
    if not valor:
        return None
    digitos = re.sub(r"\D", "", valor)
    if not 10 <= len(digitos) <= 13:
        return None
    return digitos


def _redigir(texto, *segredos):
    """Remove segredos (tokens) de uma string, para log/exibição seguros."""
    if texto is None:
        return texto
    saida = str(texto)
    for s in segredos:
        if s:
            saida = saida.replace(str(s), "***")
    return saida


def _endpoint(config, recurso):
    base = (config.base_url or "https://api.z-api.io").rstrip("/")
    return (
        f"{base}/instances/{config.instance_id}"
        f"/token/{config.instance_token}/{recurso}"
    )


def enviar_texto(config, phone, mensagem):
    """Envia uma mensagem de texto. Retorna ``(ok: bool, detalhe: str)``.

    Nunca levanta exceção: erros de rede/HTTP viram ``(False, motivo)``.
    O ``detalhe`` nunca contém os tokens. Sucesso exige 2xx **e** um id de
    mensagem no corpo (a Z-API pode responder 200 com corpo de erro).
    """
    segredos = (config.instance_token, config.client_token)
    telefone = normalizar_telefone(phone)
    if telefone is None:
        return False, f"Telefone inválido: {phone!r}"

    url = _endpoint(config, "send-text")
    headers = {"Client-Token": config.client_token or ""}
    payload = {"phone": telefone, "message": mensagem}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    except requests.exceptions.RequestException as exc:
        return False, _redigir(
            f"Falha de conexão: {type(exc).__name__}: {exc}", *segredos
        )

    try:
        dados = resp.json()
    except ValueError:
        dados = {}

    ref = isinstance(dados, dict) and (dados.get("messageId") or dados.get("zaapId"))
    if resp.ok and ref:
        return True, f"messageId={ref}"
    return False, _redigir(f"HTTP {resp.status_code}: {resp.text[:400]}", *segredos)
