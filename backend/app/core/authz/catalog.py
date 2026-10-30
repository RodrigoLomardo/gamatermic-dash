"""Catalogo de permissoes (fonte da verdade em codigo; semeado no banco) e roles de sistema."""

PERMISSIONS: dict[str, str] = {
    "dashboard:view": "Visualizar dashboards",
    "dashboard:create": "Criar dashboards",
    "dashboard:edit": "Editar dashboards",
    "dashboard:delete": "Excluir dashboards",
    "dataset:view": "Ver datasets e campos",
    "dataset:manage": "Criar e configurar datasets",
    "dataset:query": "Consultar datasets (editor)",
    "datasource:manage": "Gerenciar fontes de dados",
    "ingestion:upload": "Enviar arquivos de carga",
    "ingestion:view": "Ver histórico de cargas",
    "playlist:manage": "Gerenciar playlists",
    "device:manage": "Gerenciar e parear TVs",
    "user:manage": "Gerenciar usuários",
    "role:manage": "Gerenciar perfis (roles)",
    "group:manage": "Gerenciar grupos",
    "grant:manage": "Gerenciar concessões por recurso",
    "audit:view": "Consultar auditoria",
}

ALL = {p: "all" for p in PERMISSIONS}

SYSTEM_ROLES: dict[str, dict] = {
    "Administrador": {"description": "Acesso total.", "permissions": ALL},
    "Editor de Dashboards": {
        "description": "Cria e edita dashboards e playlists.",
        "permissions": {
            "dashboard:view": "all", "dashboard:create": "all", "dashboard:edit": "all", "dashboard:delete": "all",
            "dataset:view": "all", "dataset:query": "all", "playlist:manage": "all",
        },
    },
    "Operador de Dados": {
        "description": "Envia arquivos e acompanha cargas.",
        "permissions": {
            "dataset:view": "all", "ingestion:upload": "all", "ingestion:view": "all", "dashboard:view": "all",
        },
    },
    "Gestor": {
        "description": "Visualiza as dashboards com concessão.",
        "permissions": {"dashboard:view": "granted", "dataset:view": "granted"},
    },
    "Visualizador": {
        "description": "Visualiza apenas dashboards concedidas.",
        "permissions": {"dashboard:view": "granted"},
    },
}

LEVELS = {"view": 1, "edit": 2, "manage": 3}
