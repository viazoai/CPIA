from __future__ import annotations

import hashlib

from pipeline.agents.parser import _norm_header


def fingerprint(wb, header_scan_rows: int = 5) -> str:
    """시트명(정렬) + 각 시트 헤더 영역(앞 N행) 정규화 텍스트의 sha256.

    같은 양식 = 같은 fingerprint (캐시 키). 컬럼 시프트·시트명/헤더 변이 시 달라짐.
    """
    parts: list[str] = []
    for name in sorted(wb.sheetnames):
        parts.append(f"##{name}")
        ws = wb[name]
        max_col = ws.max_column or 0
        for r in range(1, header_scan_rows + 1):
            cells = [_norm_header(ws.cell(r, c).value) for c in range(1, max_col + 1)]
            parts.append("|".join(cells))
    blob = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
