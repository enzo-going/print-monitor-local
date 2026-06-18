"""Backend de coleta via SNMP.

Implementacao real planejada para a Fase 3. Este modulo ja reune os OIDs mais
comuns de contador total e expoe a interface ``CounterBackend``. Enquanto a
leitura real nao e implementada, o backend levanta um erro informativo, e o
fallback mockado (``collector.MockBackend``) deve ser usado.

OIDs de referencia:
- Printer-MIB ``prtMarkerLifeCount`` (RFC 3805): 1.3.6.1.2.1.43.10.2.1.4.1.1
  (contador total de impressoes para o marcador 1; o mais portavel entre
  fabricantes).
- Alguns fabricantes expoem contadores proprios; ver
  ``docs/limitacoes-fabricantes.md``.
"""

from __future__ import annotations

from .config import Config
from .models import Printer

# OID padrao Printer-MIB para contador total (prtMarkerLifeCount, marcador 1).
OID_PRT_MARKER_LIFE_COUNT = "1.3.6.1.2.1.43.10.2.1.4.1.1"

# OIDs alternativos observados em alguns fabricantes (uso futuro).
COMMON_TOTAL_COUNTER_OIDS = (
    OID_PRT_MARKER_LIFE_COUNT,
)


class SNMPBackend:
    """Le o contador total via SNMP (a ser implementado na Fase 3).

    Segue a mesma interface de ``CounterBackend`` para substituir o mock sem
    alterar o restante do codigo.
    """

    def __init__(self, config: Config, oid: str = OID_PRT_MARKER_LIFE_COUNT):
        self.config = config
        self.oid = oid

    def read_total_counter(self, printer: Printer) -> int:  # pragma: no cover
        raise NotImplementedError(
            "Coleta SNMP real sera implementada na Fase 3. "
            "Use o backend mockado (PRINT_MONITOR_BACKEND=mock) por enquanto."
        )
