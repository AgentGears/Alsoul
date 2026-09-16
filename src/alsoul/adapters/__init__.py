from .contracts import (
    AdapterError,
    AdapterOutcomeUnknown,
    AdapterRejected,
    FirstPartyPresentationAcceptance,
    FirstPartyPresentationAdapter,
    ModelProviderAdapter,
    WorldAcquisitionAdapter,
    WorldResultExtractor,
)
from .fakes import FakeModelAdapter, FakePresentationAdapter, FakeWorldAdapter
from .http_world import HttpResponse, HttpTransport, HttpWorldAdapter, UrllibHttpTransport
from .json_model import (
    JsonHttpResponse,
    JsonHttpTransport,
    JsonModelProviderAdapter,
    UrllibJsonTransport,
)
from .json_personal_calendar_mutation import (
    CALENDAR_MUTATION_WIRE_SCHEMA_VERSION,
    CalendarMutationHttpResponse,
    CalendarMutationWireTransport,
    CredentialSecretResolver,
    JsonPersonalCalendarMutationAdapter,
    UrllibCalendarMutationTransport,
)
from . import json_personal_calendar_presentation as _json_personal_calendar_presentation
from .json_personal_calendar_presentation_v2 import JsonPersonalCalendarPresentationAdapter
from .json_presentation import JsonFirstPartyPresentationAdapter
from .world_extract import F4JsonMemoryRequirementExtractor, https_origin

# Keep established submodule imports on the current qualified sink class.
_json_personal_calendar_presentation.JsonPersonalCalendarPresentationAdapter = (
    JsonPersonalCalendarPresentationAdapter
)

__all__ = [
    "AdapterError",
    "AdapterOutcomeUnknown",
    "AdapterRejected",
    "CALENDAR_MUTATION_WIRE_SCHEMA_VERSION",
    "CalendarMutationHttpResponse",
    "CalendarMutationWireTransport",
    "CredentialSecretResolver",
    "F4JsonMemoryRequirementExtractor",
    "FakeModelAdapter",
    "FakePresentationAdapter",
    "FakeWorldAdapter",
    "FirstPartyPresentationAcceptance",
    "FirstPartyPresentationAdapter",
    "HttpResponse",
    "HttpTransport",
    "HttpWorldAdapter",
    "JsonFirstPartyPresentationAdapter",
    "JsonHttpResponse",
    "JsonHttpTransport",
    "JsonModelProviderAdapter",
    "JsonPersonalCalendarMutationAdapter",
    "JsonPersonalCalendarPresentationAdapter",
    "ModelProviderAdapter",
    "UrllibCalendarMutationTransport",
    "UrllibHttpTransport",
    "UrllibJsonTransport",
    "WorldAcquisitionAdapter",
    "WorldResultExtractor",
    "https_origin",
]
