from enum import Enum


class AssetType(str, Enum):
    DOMAIN = "domain"
    SUBDOMAIN = "subdomain"
    IP_ADDRESS = "ip_address"
    SERVICE = "service"
    CERTIFICATE = "certificate"
    TECHNOLOGY = "technology"


class AssetStatus(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    ARCHIVED = "archived"


class RelationshipType(str, Enum):
    SUBDOMAIN_OF = "subdomain_of"
    SERVICE_ON = "service_on"
    RESOLVES_TO = "resolves_to"
    CERTIFICATE_FOR = "certificate_for"
    TECHNOLOGY_USED_BY = "technology_used_by"
