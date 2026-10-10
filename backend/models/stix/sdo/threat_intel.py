"""STIX SDO tables currently supported by the intelligence store."""

from services.database import db

from models.stix.base import StixObjectBase


class StixCountry(StixObjectBase, db.Model):
    """Country-scoped STIX Location SDO."""
    __tablename__ = "stix_country"


class StixIndicator(StixObjectBase, db.Model):
    __tablename__ = "stix_indicator"

    name = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)

    def to_dict(self):
        data = super().to_dict()
        data.update(name=self.name, description=self.description)
        return data


class StixMalware(StixObjectBase, db.Model):
    __tablename__ = "stix_malware"


class StixCampaign(StixObjectBase, db.Model):
    __tablename__ = "stix_campaign"


class StixIntrusionSet(StixObjectBase, db.Model):
    __tablename__ = "stix_intrusion_set"