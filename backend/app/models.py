"""Importa todos os models para o metadata do Alembic."""
from app.modules.analysis.models import AnalysisView  # noqa: F401
from app.modules.audit.models import AuditLog  # noqa: F401
from app.modules.dashboards.models import Dashboard, Widget  # noqa: F401
from app.modules.datasets.models import (  # noqa: F401
    Dataset,
    DatasetField,
    DatasetRow,
    DataSource,
    IngestionRowError,
    IngestionRun,
    Job,
    SourceBinding,
    UploadedFile,
)
from app.modules.devices.models import (  # noqa: F401
    Device,
    DeviceCredential,
    DevicePairingRequest,
    Playlist,
    PlaylistItem,
)
from app.modules.iam.models import (  # noqa: F401
    Group,
    GroupRole,
    Permission,
    RefreshToken,
    ResourceGrant,
    Role,
    RolePermission,
    Sector,
    User,
    UserGroup,
    UserRole,
)
from app.modules.settings.models import SystemSetting  # noqa: F401
