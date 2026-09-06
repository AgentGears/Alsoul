from __future__ import annotations

from alsoul.host.config import FoundationHostConfig
from alsoul.host.readiness import HostReadiness, require_host_readiness
from alsoul.services import ConfiguredFoundationRuntime, FoundationServices, RuntimeSecrets
from alsoul.storage import create_sqlite_engine


class FoundationHostApplication:
    """Own the process lifetime of the configured F4 runtime host.

    The host opens only pre-existing compatible state. It never creates schema,
    CompanionPerson identity, CounterpartPerson identity, or RelationshipState.
    Those remain explicit administration boundaries outside the runtime process.
    """

    def __init__(
        self,
        *,
        config: FoundationHostConfig,
        secrets: RuntimeSecrets | None = None,
    ) -> None:
        self.config = config
        self.readiness: HostReadiness = require_host_readiness(config)
        self.engine = create_sqlite_engine(config.database_path)
        self.services = FoundationServices(self.engine)
        self.runtime = ConfiguredFoundationRuntime(
            self.services,
            config=config.runtime,
            secrets=secrets or RuntimeSecrets(),
        )

    def close(self) -> None:
        self.engine.dispose()

    def __enter__(self) -> "FoundationHostApplication":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.close()


__all__ = ["FoundationHostApplication"]
