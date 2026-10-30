from typing import ClassVar

from pydantic import BaseModel

from app.core.errors import Unprocessable
from app.modules.connectors.base import FetchContext, register
from app.modules.ingestion.pipeline.extract import Extracted, extract, sniff_kind


class FileUploadConfig(BaseModel):
    pass


@register
class FileUploadConnector:
    """Upload manual de CSV/XLSX. Conectores reais (Ploomes/Omie, http_pull) entram na Fase 2 com este contrato."""

    kind: ClassVar[str] = "file_upload"
    config_schema: ClassVar[type[BaseModel]] = FileUploadConfig
    supports_push: ClassVar[bool] = False

    async def test_connection(self, ctx: FetchContext) -> None:
        return None

    def fetch(self, ctx: FetchContext) -> Extracted:
        if ctx.file_path is None:
            raise Unprocessable("Fonte de upload requer um arquivo.")
        return extract(ctx.file_path, sniff_kind(ctx.file_path), ctx.parser_options)
