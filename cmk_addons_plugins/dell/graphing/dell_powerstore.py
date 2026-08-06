#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from cmk.graphing.v1 import Title
from cmk.graphing.v1.graphs import Graph, MinimalRange
from cmk.graphing.v1.metrics import (
    Color,
    CriticalOf,
    DecimalNotation,
    Difference,
    IECNotation,
    Metric,
    StrictPrecision,
    Sum,
    TimeNotation,
    Unit,
    WarningOf,
)
from cmk.graphing.v1.perfometers import Closed, FocusRange, Perfometer

UNIT_PERCENTAGE = Unit(DecimalNotation("%"))
UNIT_BYTES = Unit(IECNotation("B"), StrictPrecision(2))
UNIT_PER_SECOND = Unit(DecimalNotation("/s"))
UNIT_BYTES_PER_SECOND = Unit(IECNotation("B/s"))
UNIT_NUMBER = Unit(DecimalNotation(""), StrictPrecision(2))


metric_total_iops = Metric(
    name="total_iops",
    title=Title("Total IO/s"),
    unit=UNIT_PER_SECOND,
    color=Color.LIGHT_BLUE,
)

graph_total_iops = Graph(
    name="total_iops",
    title=Title("Total IO/s"),
    simple_lines=(
        "total_iops",
    ),
)

metric_total_bandwidth = Metric(
    name="total_bandwidth",
    title=Title("Total Bandwidth"),
    unit=UNIT_BYTES_PER_SECOND,
    color=Color.PURPLE,
)

graph_total_bandwidth = Graph(
    name="total_bandwidth",
    title=Title("Total Bandwidth"),
    simple_lines=(
        "total_bandwidth",
    ),
)

metric_physical_free = Metric(
    name="physical_free",
    title=Title("Total Free Space"),
    unit=UNIT_BYTES,
    color=Color.LIGHT_GREEN,
)

metric_physical_used = Metric(
    name="physical_used",
    title=Title("Total Used Space"),
    unit=UNIT_BYTES,
    color=Color.LIGHT_PURPLE,
)

graph_physical_absolute = Graph(
    name="physical_absolute",
    title=Title("Physical Capacity"),
    simple_lines=(
        Sum(Title("Total Space"), Color.DARK_BLUE, ("physical_used", "physical_free")),
        WarningOf("physical_used"),
        CriticalOf("physical_used"),
    ),
    compound_lines=(
        "physical_used",
        "physical_free",
    ),
)

metric_physical_used_percent = Metric(
    name="physical_used_percent",
    title=Title("Physical Space Used [%]"),
    unit=UNIT_PERCENTAGE,
    color=Color.CYAN,
)

graph_physical_percent = Graph(
    name="physical_percent",
    title=Title("Physical Capacity [%]"),
    minimal_range=MinimalRange(0, 100),
    compound_lines=(
        "physical_used_percent",
    ),
    simple_lines=(
        WarningOf("physical_used_percent"),
        CriticalOf("physical_used_percent"),
    ),
)

perfometer_physical_percent = Perfometer(
    name="physical_used_percent",
    focus_range=FocusRange(Closed(0), Closed(100)),
    segments=("physical_used_percent",),
)
