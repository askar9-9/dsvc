from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_init"
down_revision = None
branch_labels = None
depends_on = None


def uuid_pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def ts(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=sa.text("now()"))


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        uuid_pk(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        ts("created_at"),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "homes",
        uuid_pk(),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("elevation", sa.Integer()),
        sa.Column("time_zone", sa.String(100), nullable=False, server_default="Asia/Almaty"),
        sa.Column("currency", sa.String(10), nullable=False, server_default="KZT"),
        sa.Column("unit_system", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        ts("created_at"),
    )

    op.create_table(
        "floors",
        uuid_pk(),
        sa.Column("home_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("homes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("icon", sa.String(100)),
        ts("created_at"),
    )

    op.create_table(
        "areas",
        uuid_pk(),
        sa.Column("home_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("homes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("floor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("floors.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("icon", sa.String(100)),
        sa.Column("picture", sa.Text()),
        sa.Column("temperature_entity_id", sa.String(255)),
        sa.Column("humidity_entity_id", sa.String(255)),
        ts("created_at"),
        ts("updated_at"),
    )
    op.create_index("ix_areas_home_id", "areas", ["home_id"])

    op.create_table(
        "integrations",
        uuid_pk(),
        sa.Column("home_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("homes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(100), nullable=False),
        sa.Column("config_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        ts("created_at"),
    )

    op.create_table(
        "devices",
        uuid_pk(),
        sa.Column("home_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("homes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("area_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("areas.id", ondelete="SET NULL")),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("integrations.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_by_user", sa.String(255)),
        sa.Column("manufacturer", sa.String(255)),
        sa.Column("model", sa.String(255)),
        sa.Column("serial_number", sa.String(255)),
        sa.Column("sw_version", sa.String(100)),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="online"),
        ts("created_at"),
        ts("updated_at"),
    )
    op.create_index("ix_devices_area_id", "devices", ["area_id"])
    op.create_index("ix_devices_home_id", "devices", ["home_id"])
    op.create_index("ix_devices_type", "devices", ["type"])
    op.create_index("ix_devices_status", "devices", ["status"])

    op.create_table(
        "entities",
        uuid_pk(),
        sa.Column("entity_id", sa.String(255), nullable=False, unique=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE")),
        sa.Column("area_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("areas.id", ondelete="SET NULL")),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("platform", sa.String(100), nullable=False, server_default="demo"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("original_name", sa.String(255)),
        sa.Column("state", sa.String(255), nullable=False, server_default="unknown"),
        sa.Column("attributes_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("unit_of_measurement", sa.String(50)),
        sa.Column("device_class", sa.String(100)),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("hidden_by", sa.String(100)),
        sa.Column("disabled_by", sa.String(100)),
        ts("created_at"),
        ts("updated_at"),
    )
    op.create_index("ix_entities_entity_id", "entities", ["entity_id"], unique=True)
    op.create_index("ix_entities_domain", "entities", ["domain"])
    op.create_index("ix_entities_area_id", "entities", ["area_id"])
    op.create_index("ix_entities_device_id", "entities", ["device_id"])

    op.create_table(
        "automations",
        uuid_pk(),
        sa.Column("home_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("homes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("mode", sa.String(50), nullable=False, server_default="single"),
        sa.Column("trigger_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("condition_json", postgresql.JSONB()),
        sa.Column("action_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_triggered", sa.DateTime(timezone=True)),
        ts("created_at"),
        ts("updated_at"),
    )

    op.create_table(
        "entity_states",
        uuid_pk(),
        sa.Column("entity_id", sa.String(255), sa.ForeignKey("entities.entity_id", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.String(255), nullable=False),
        sa.Column("attributes_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_changed", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("context_id", sa.String(255)),
        ts("created_at"),
    )
    op.create_index("ix_entity_states_entity_id", "entity_states", ["entity_id"])
    op.create_index("ix_entity_states_last_changed", "entity_states", ["last_changed"])

    op.create_table(
        "events",
        uuid_pk(),
        sa.Column("entity_id", sa.String(255), sa.ForeignKey("entities.entity_id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("old_state", sa.String(255)),
        sa.Column("new_state", sa.String(255)),
        sa.Column("source", sa.String(50), nullable=False, server_default="system"),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("automation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("automations.id", ondelete="SET NULL")),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        ts("created_at"),
    )
    op.create_index("ix_events_entity_id", "events", ["entity_id"])
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_source", "events", ["source"])
    op.create_index("ix_events_created_at", "events", ["created_at"])

    op.create_table(
        "automation_runs",
        uuid_pk(),
        sa.Column("automation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("automations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_by", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="running"),
        ts("started_at"),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "energy_readings",
        uuid_pk(),
        sa.Column("entity_id", sa.String(255), sa.ForeignKey("entities.entity_id", ondelete="CASCADE"), nullable=False),
        sa.Column("power_w", sa.Float(), nullable=False, server_default="0"),
        sa.Column("energy_kwh", sa.Float(), nullable=False, server_default="0"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_energy_readings_entity_id", "energy_readings", ["entity_id"])
    op.create_index("ix_energy_readings_recorded_at", "energy_readings", ["recorded_at"])


def downgrade() -> None:
    for table in [
        "energy_readings",
        "automation_runs",
        "events",
        "entity_states",
        "automations",
        "entities",
        "devices",
        "integrations",
        "areas",
        "floors",
        "homes",
        "users",
    ]:
        op.drop_table(table)
