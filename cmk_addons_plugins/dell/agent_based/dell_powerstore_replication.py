#!/usr/bin/env python3
# -*- encoding: utf-8; py-indent-offset: 4 -*-

from cmk.agent_based.v2 import (
    AgentSection,
    CheckPlugin,
    CheckResult,
    DiscoveryResult,
    Result,
    Service,
    State,
)
from cmk_addons.plugins.dell.powerstore_lib import (
    DellPowerStoreAPIData,
    parse_dell_powerstore,
)

agent_section_replication_session = AgentSection(
    name="replication_session",
    parse_function=parse_dell_powerstore,
    parsed_section_name="replication_session",
)

def _is_metro(d: dict) -> bool:
    # Your data: type="Metro_Active_Active"
    return str(d.get("type", "")).startswith("Metro_") or str(d.get("role", "")).startswith("Metro_")

def _short_id(full_id: str) -> str:
    return (full_id or "")[:8]

def _item_name(d: dict) -> str:
    # "Resource" in GUI -> now provided by agent as resource_name
    res = str(d.get("resource_name") or d.get("local_resource_id") or "<unknown>")
    return res

def discovery_dell_powerstore_replication(section: DellPowerStoreAPIData) -> DiscoveryResult:
    for d in section:
        if isinstance(d, dict) and _is_metro(d) and d.get("id"):
            yield Service(item=_item_name(d))

def _find_session_by_item(item: str, section: DellPowerStoreAPIData) -> dict | None:
    for d in section:
        if not isinstance(d, dict) or not _is_metro(d):
            continue
        res = str(d.get("resource_name") or d.get("local_resource_id") or "")
        if res == item:
            return d
    return None

def check_dell_powerstore_replication(item: str, section: DellPowerStoreAPIData) -> CheckResult:
    sess = _find_session_by_item(item, section)
    if sess is None:
        yield Result(State.UNKNOWN, "Metro session not found in replication_session section")
        return

    state = str(sess.get("state", "UNKNOWN"))
    data_conn = str(sess.get("data_connection_state", "UNKNOWN"))
    data_transfer = str(sess.get("data_transfer_state", ""))
    role = str(sess.get("role", ""))
    typ = str(sess.get("type", ""))
    err = sess.get("error_code", None)

    wd = sess.get("witness_details") if isinstance(sess.get("witness_details"), dict) else {}
    witness_name = str(wd.get("witness_name", "") or "")
    witness_state = str(wd.get("state", "") or "")

    # Your policy:
    # - WARN if state != OK
    # - WARN if data_connection_state != OK
    # - WARN if witness_state != Engaged
    # - CRIT if error_code exists
    if err is not None:
        cmk_state = State.CRIT
        warn_reasons = []
    else:
        warn_reasons = []
        if state != "OK":
            warn_reasons.append(f"state={state}")
        if data_conn != "OK":
            warn_reasons.append(f"data_connection_state={data_conn}")
        if witness_state and witness_state != "Engaged":
            warn_reasons.append(f"witness_state={witness_state}")

        cmk_state = State.WARN if warn_reasons else State.OK

    msg = f"type={typ}, role={role}, state={state}, data_connection={data_conn}"
    if data_transfer:
        msg += f", data_transfer={data_transfer}"
    if witness_name or witness_state:
        msg += f", witness={witness_name}:{witness_state}".rstrip(":")
    if warn_reasons:
        msg += ", warn=" + ";".join(warn_reasons)
    if err is not None:
        msg += f", error_code={err}"

    yield Result(state=cmk_state, summary="State: " + msg)

check_plugin_dell_powerstore_replication = CheckPlugin(
    name="dell_powerstore_replication",
    service_name="Metro %s",
    sections=["replication_session"],
    discovery_function=discovery_dell_powerstore_replication,
    check_function=check_dell_powerstore_replication,
)
