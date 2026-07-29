"""
Models package — re-exports all models for convenient imports.
"""

from models.session import Session
from models.fingerprint import Fingerprint
from models.heartbeat import Heartbeat
from models.behavioral_event import (
    BehavioralEvent,  # legacy — kept for backward compat
    CopyEvent,
    PasteEvent,
    FormSubmitEvent,
    ButtonClickEvent,
    TYPED_EVENT_MODELS,
)
from models.rule import Rule, RuleMatch
from models.associations import SessionURL, BrowserSession
from models.dashboard import Dashboard
from models.user import User, ApiToken
from models.app_setting import AppSetting
from models.cors import AllowedOrigin
from models.taxii_feed import TaxiiFeed
from models.stix import (
    StixIPv4Addr,
    StixIPv6Addr,
    StixUserAgent,
    StixAutonomousSystem,
    StixCountry,
    StixIndicator,
    StixMalware,
    StixCampaign,
    StixIntrusionSet,
    StixRelationship,
)

__all__ = [
    "Session",
    "Fingerprint",
    "Heartbeat",
    "BehavioralEvent",
    "CopyEvent",
    "PasteEvent",
    "FormSubmitEvent",
    "ButtonClickEvent",
    "TYPED_EVENT_MODELS",
    "Rule",
    "RuleMatch",
    "SessionURL",
    "BrowserSession",
    "Dashboard",
    "User",
    "ApiToken",
    "AppSetting",
    "AllowedOrigin",
    "TaxiiFeed",
    "StixIPv4Addr",
    "StixIPv6Addr",
    "StixUserAgent",
    "StixAutonomousSystem",
    "StixCountry",
    "StixIndicator",
    "StixMalware",
    "StixCampaign",
    "StixIntrusionSet",
    "StixRelationship",
]
