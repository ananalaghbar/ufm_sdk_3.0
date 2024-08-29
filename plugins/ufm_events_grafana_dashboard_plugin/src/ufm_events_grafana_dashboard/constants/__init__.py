#
# Copyright © 2013-2024 NVIDIA CORPORATION & AFFILIATES. ALL RIGHTS RESERVED.
#
# This software product is a proprietary product of Nvidia Corporation and its affiliates
# (the "Company") and all right, title, and interest in and to the software
# product, including all associated intellectual property rights, are and
# shall remain exclusively with the Company.
#
# This software product is governed by the End User License Agreement
# provided with the software product.
#
from enum import Enum


class DataType(Enum):
    """
    DataType Enums Class
    """
    TELEMETRY = 1


class ModelListeners(Enum):
    """
    ModelListeners Enums class
    """
    TELEMETRY_PROMETHEUS_EXPORTER = 1
    FLAPPING_LINKS_EVENTS_EXPORTER = 2


class Prometheus:
    """
    Prometheus Constants Class
    """
    LABELS = "labels"
    COUNTER_VALUE = "counter_value"
    TIMESTAMP = "timestamp"


class LinkFlapping:
    """Link Flapping Constants CLass"""
    LINK_ID = "link_hash_id"
    EXPECTED_TIME = "estimated_time"
    NODE_DESC = "node_description"
    PARTNER_NODE_DESC = "link_partner_description"

    LINK_FLAPPING_COUNTER = "link_flapping_counter"
    FIRST_TIME_OCCURRED = "first_time_occurred"
    LAST_TIME_OCCURRED = "last_time_occurred"
