# Triotour

Sistema web Flask + SQLite para cadastro de clientes, cotações de passagens, pacotes de viagem, roteiros por dia e propostas profissionais.

## Como executar

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Acesse `http://127.0.0.1:5000`.

## Recursos

- Clientes com telefone/WhatsApp, e-mail, documento e observações.
- Cotações aéreas ou rodoviárias com ida, volta, bagagem, valores e termos.
- Pacotes com transporte, hospedagem, alimentação, roteiro diário reordenável e itens inclusos personalizados.
- Lista de propostas com filtros, duplicação, alteração de status e exclusão.
- Configurações da Triotour usadas automaticamente nos documentos.
- Visualização, impressão e exportação em PDF pelo diálogo de impressão do navegador.
